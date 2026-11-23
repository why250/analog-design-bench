"""Independent conforming P1 triangle FEM for the frozen DC contact experiment.

The actual uniform M6 polygon is extruded with its exported conductivity and
thickness. Both original 10 um terminal end faces are equipotential (1 V/0 V);
all other boundaries are insulating. Geometry, material and contact readers
are shared with dc_resistance.py, but no finite-volume operator is used.

Unconstrained SciPy Delaunay is NOT assumed to preserve polygon boundaries.
Every required densified original boundary segment must be recovered before
filtering; retained triangle boundary edges must then equal that exact set.
Area, non-crossing, connectivity and disk topology are independently checked.
Failure rejects the experiment; no geometry jitter or contact fitting is used.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import warnings
from typing import Any, Sequence

import numpy as np
import scipy
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import MatrixRankWarning, spsolve
from scipy.spatial import Delaunay, QhullError

from dc_resistance import Contact, DCError, locate_contact, material_from_ltd
from plot_geometry import read_export


class FEMError(ValueError):
    """The fixed geometric/contact experiment cannot be certified numerically."""


@dataclass
class FEMMesh:
    vertices_um: np.ndarray
    triangles: np.ndarray
    required_boundary_edges: np.ndarray
    original_edge_nodes: tuple[np.ndarray, ...]
    validation: dict[str, Any]


@dataclass
class FEMSolution:
    metrics: dict[str, Any]
    mesh: FEMMesh
    voltage_V: np.ndarray
    sheet_current_A_per_m: np.ndarray


def _cross(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def _area(points: np.ndarray) -> float:
    translated = points - points[0]
    return float(_cross(translated, np.roll(translated, -1, axis=0)).sum() / 2)


def _distance(points: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    nearest = np.full(len(points), np.inf)
    for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
        edge = b - a
        fraction = np.clip((points - a) @ edge / float(edge @ edge), 0, 1)
        delta = points - (a + fraction[:, None] * edge)
        nearest = np.minimum(nearest, np.sqrt(np.einsum("ij,ij->i", delta, delta)))
    return nearest


def _inside(points: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    """Independent ray classification; boundary treatment is supplied separately."""
    result = np.zeros(len(points), dtype=bool)
    x, y = points.T
    for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
        if a[1] == b[1]:
            continue
        crosses = (a[1] > y) != (b[1] > y)
        intersection = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
        result ^= crosses & (x < intersection)
    return result


def _polygon(points: Sequence[tuple[float, float]]) -> tuple[np.ndarray, float]:
    polygon = np.asarray(points, dtype=float)
    if polygon.ndim != 2 or polygon.shape[1] != 2 or len(polygon) < 3 or not np.all(np.isfinite(polygon)):
        raise FEMError("A finite simple two-dimensional polygon is required")
    if np.array_equal(polygon[0], polygon[-1]):
        polygon = polygon[:-1]
    span = np.ptp(polygon, axis=0)
    if not np.all(np.isfinite(span)):
        raise FEMError("Polygon coordinate extent is not numerically representable")
    scale = max(1.0, float(span.max()))
    tolerance = 1e-10 * scale
    edges = np.roll(polygon, -1, axis=0) - polygon
    lengths = np.linalg.norm(edges, axis=1)
    if len(polygon) < 3 or not np.all(np.isfinite(lengths)) or np.any(lengths <= tolerance) or len(np.unique(polygon, axis=0)) != len(polygon):
        raise FEMError("Zero-length edges or repeated non-closing vertices are unsupported")
    if not math.isfinite(_area(polygon)) or abs(_area(polygon)) <= tolerance * scale:
        raise FEMError("The polygon has zero or numerically degenerate area")
    # Nonadjacent edges must neither intersect nor touch: no holes, zero-width
    # bridges, self-intersections or self-touching conductor islands are allowed.
    for i, (a, b) in enumerate(zip(polygon, np.roll(polygon, -1, axis=0))):
        for j in range(i + 1, len(polygon)):
            if j == i + 1 or (i == 0 and j == len(polygon) - 1):
                continue
            c, d = polygon[j], polygon[(j + 1) % len(polygon)]
            ab, cd = b - a, d - c
            p, q = float(_cross(ab, c - a)), float(_cross(ab, d - a))
            r, s = float(_cross(cd, a - c)), float(_cross(cd, b - c))
            eps_ab, eps_cd = tolerance * lengths[i], tolerance * lengths[j]
            proper = ((p > eps_ab and q < -eps_ab) or (p < -eps_ab and q > eps_ab)) and ((r > eps_cd and s < -eps_cd) or (r < -eps_cd and s > eps_cd))
            touches = any(abs(value) <= eps and np.all(point >= np.minimum(start, end) - tolerance) and np.all(point <= np.maximum(start, end) + tolerance)
                          for value, eps, point, start, end in ((p, eps_ab, c, a, b), (q, eps_ab, d, a, b), (r, eps_cd, a, c, d), (s, eps_cd, b, c, d)))
            if proper or touches:
                raise FEMError("The conductor polygon self-intersects or has a nonadjacent boundary touch")
    return polygon, tolerance


def _edges(triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    directed = np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]))
    return np.unique(np.sort(directed, axis=1), axis=0, return_counts=True)


def _edge_set(edges: np.ndarray) -> set[tuple[int, int]]:
    return {tuple(map(int, edge)) for edge in edges}


def validate_mesh(vertices: np.ndarray, triangles: np.ndarray, polygon: np.ndarray,
                  required_boundary: np.ndarray, tolerance: float) -> dict[str, Any]:
    """Certify the retained Delaunay submesh on the unchanged polygon boundary."""
    if not len(triangles) or triangles.ndim != 2 or triangles.shape[1] != 3:
        raise FEMError("No complete triangular conductor mesh remains")
    if len(np.unique(np.sort(triangles, axis=1), axis=0)) != len(triangles):
        raise FEMError("Duplicate triangles are not allowed")
    used = np.unique(triangles)
    if not np.array_equal(used, np.arange(len(vertices))):
        raise FEMError("A generated boundary/interior node was omitted from the retained mesh")
    coordinates = vertices[triangles]
    signed_area = _cross(coordinates[:, 1] - coordinates[:, 0], coordinates[:, 2] - coordinates[:, 0]) / 2
    if not np.all(np.isfinite(signed_area)) or np.any(signed_area <= tolerance * tolerance):
        raise FEMError("Zero-area, inverted or nonfinite triangles are not allowed")
    directed = np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]))
    edges, inverse, counts = np.unique(np.sort(directed, axis=1), axis=0, return_inverse=True, return_counts=True)
    if np.any((counts != 1) & (counts != 2)):
        raise FEMError("Triangle edges are nonmanifold")
    actual_boundary = edges[counts == 1]
    missing = _edge_set(required_boundary) - _edge_set(actual_boundary)
    extra = _edge_set(actual_boundary) - _edge_set(required_boundary)
    if missing or extra:
        raise FEMError(f"Conforming boundary recovery failed: {len(missing)} missing and {len(extra)} extra edges")
    # Delaunay is planar and every original boundary subsegment was recovered
    # before filtering. Explicit crossing and midpoint tests additionally guard
    # the polygon classification and make a concave-gap bridge unacceptable.
    starts, ends = vertices[edges[:, 0]], vertices[edges[:, 1]]
    lengths = np.linalg.norm(ends - starts, axis=1)
    for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
        segment = b - a
        p, q = _cross(segment, starts - a), _cross(segment, ends - a)
        r, s = _cross(ends - starts, a - starts), _cross(ends - starts, b - starts)
        eps_first = tolerance * float(np.linalg.norm(segment))
        eps_second = tolerance * lengths
        crosses_first = ((p > eps_first) & (q < -eps_first)) | ((p < -eps_first) & (q > eps_first))
        crosses_second = ((r > eps_second) & (s < -eps_second)) | ((r < -eps_second) & (s > eps_second))
        if np.any(crosses_first & crosses_second):
            raise FEMError("A triangle edge crosses the original conductor boundary")
    midpoints = (starts + ends) / 2
    if not np.all(_inside(midpoints, polygon) | (_distance(midpoints, polygon) <= tolerance)):
        raise FEMError("A triangle edge midpoint is outside the original polygon")
    if not np.all(_inside(coordinates.mean(axis=1), polygon)):
        raise FEMError("A retained triangle centroid lies outside the original polygon")
    area = float(signed_area.sum())
    expected_area = abs(_area(polygon))
    area_tolerance = max(1e-10 * expected_area, tolerance * tolerance * len(required_boundary))
    if abs(area - expected_area) > area_tolerance:
        raise FEMError("Triangle total area differs from the unchanged polygon area")
    graph = coo_matrix((np.ones(2 * len(edges)), (np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]])), shape=(len(vertices), len(vertices))).tocsr()
    components = int(connected_components(graph, directed=False, return_labels=False))
    # Sharing just a vertex is not sufficient for a conducting FEM domain.
    # Require all elements to connect through complete interior triangle edges.
    order = np.argsort(inverse, kind="stable")
    offsets = np.r_[0, np.cumsum(counts)[:-1]][counts == 2]
    owners = np.tile(np.arange(len(triangles)), 3)
    first, second = owners[order[offsets]], owners[order[offsets + 1]]
    dual = coo_matrix((np.ones(2 * len(first)), (np.r_[first, second], np.r_[second, first])), shape=(len(triangles), len(triangles))).tocsr()
    triangle_components = int(connected_components(dual, directed=False, return_labels=False))
    euler = len(vertices) - len(edges) + len(triangles)
    if components != 1 or triangle_components != 1 or euler != 1:
        raise FEMError("The retained mesh is not one connected simply connected conductor disk")
    return {"status": "VALIDATED_CONFORMING_SIMPLE_POLYGON_MESH", "node_count": len(vertices),
            "triangle_count": len(triangles), "unique_edge_count": len(edges),
            "required_boundary_segment_count": len(required_boundary), "actual_boundary_segment_count": len(actual_boundary),
            "missing_boundary_segments": 0, "extra_boundary_segments": 0, "boundary_crossings": 0,
            "connected_components": components, "triangle_edge_connected_components": triangle_components, "Euler_V_minus_E_plus_T": euler,
            "polygon_area_um2": expected_area, "triangle_area_um2": area,
            "absolute_area_difference_um2": abs(area - expected_area), "area_tolerance_um2": area_tolerance,
            "coordinate_tolerance_um": tolerance, "minimum_triangle_area_um2": float(signed_area.min()),
            "geometry_jitter": False}


def make_mesh(points: Sequence[tuple[float, float]], h_um: float) -> FEMMesh:
    """Generate and certify a boundary-preserving subset of an unjittered Delaunay."""
    if not math.isfinite(h_um) or h_um <= 0:
        raise FEMError("Mesh spacing must be finite and positive")
    polygon, tolerance = _polygon(points)
    counts = []
    for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
        ratio = float(np.linalg.norm(b - a)) / h_um
        if not math.isfinite(ratio) or ratio > 200_000:
            raise FEMError("Requested mesh exceeds the explicit boundary-point safety limit")
        counts.append(max(1, math.ceil(ratio)))
    low, high = polygon.min(axis=0), polygon.max(axis=0)
    dimensions = (high - low) / h_um
    if not np.all(np.isfinite(dimensions)) or math.ceil(float(dimensions[0])) * math.ceil(float(dimensions[1])) > 2_000_000 or sum(counts) > 200_000:
        raise FEMError("Requested mesh exceeds the explicit two-million candidate-point safety limit")
    boundary = []
    for a, b, count in zip(polygon, np.roll(polygon, -1, axis=0), counts):
        boundary.extend(a + np.arange(count)[:, None] / count * (b - a))
    boundary = np.asarray(boundary)
    number_boundary = len(boundary)
    indices = np.arange(number_boundary)
    required = np.sort(np.column_stack((indices, np.roll(indices, -1))), axis=1)
    original_nodes = []
    offset = 0
    for count in counts:
        original_nodes.append(np.arange(offset, offset + count + 1) % number_boundary)
        offset += count
    x, y = np.arange(low[0] + h_um / 2, high[0], h_um), np.arange(low[1] + h_um / 2, high[1], h_um)
    if len(x) * len(y) > 2_000_000 or number_boundary > 200_000:
        raise FEMError("Requested mesh exceeds the explicit two-million candidate-point safety limit")
    xx, yy = np.meshgrid(x, y)
    interior = np.column_stack((xx.ravel(), yy.ravel()))
    interior = interior[_inside(interior, polygon)]
    interior = interior[_distance(interior, polygon) >= h_um / 2 - tolerance]
    vertices = np.vstack((boundary, interior))
    if len(np.unique(vertices, axis=0)) != len(vertices):
        raise FEMError("Duplicate generated nodes are unsupported; no automatic coordinate merging is performed")
    options = "Qbb Qc Qz Q12"
    try:
        delaunay = Delaunay(vertices, qhull_options=options)
    except QhullError as exc:
        raise FEMError("Unjittered Delaunay failed; input geometry has not been perturbed") from exc
    all_triangles = delaunay.simplices.copy()
    coordinates = vertices[all_triangles]
    signed_area2 = _cross(coordinates[:, 1] - coordinates[:, 0], coordinates[:, 2] - coordinates[:, 0])
    maximum_edge_length = np.maximum.reduce([np.linalg.norm(coordinates[:, b] - coordinates[:, a], axis=1) for a, b in ((0,1),(1,2),(2,0))])
    degenerate = np.abs(signed_area2) <= tolerance * maximum_edge_length
    # Qhull can represent theoretically collinear densified boundary points as
    # tiny floating-point triangles. Only triangles whose three nodes belong
    # to ONE unchanged original straight edge may be discarded as zero height.
    # Interior slivers and unrecovered boundary segments remain hard failures.
    boundary_sets = [set(map(int, nodes)) for nodes in original_nodes]
    for triangle in all_triangles[degenerate]:
        if not any(set(map(int, triangle)).issubset(nodes) for nodes in boundary_sets):
            raise FEMError("A near-zero-area triangle is not an analytically collinear original boundary artifact")
    removed_sliver_area = float(np.abs(signed_area2[degenerate]).sum() / 2)
    all_triangles = all_triangles[~degenerate]
    all_edges, _ = _edges(all_triangles)
    if _edge_set(required) - _edge_set(all_edges):
        raise FEMError("Unconstrained Delaunay did not recover every required original boundary subsegment; refusing this mesh")
    if len(delaunay.coplanar) or len(np.unique(all_triangles)) != len(vertices):
        raise FEMError("Qhull omitted a generated node; refusing hidden boundary or interior node loss")
    triangles = all_triangles[_inside(vertices[all_triangles].mean(axis=1), polygon)]
    area2 = _cross(vertices[triangles[:, 1]] - vertices[triangles[:, 0]], vertices[triangles[:, 2]] - vertices[triangles[:, 0]])
    triangles[area2 < 0] = triangles[area2 < 0][:, [0, 2, 1]]
    validation = validate_mesh(vertices, triangles, polygon, required, tolerance)
    validation.update(boundary_recovered_before_filter=True, boundary_node_count=number_boundary,
                      interior_node_count=len(interior), interior_minimum_boundary_distance_rule="h/2 in unchanged polygon coordinates",
                      qhull_options=options, qhull_coplanar_omitted_nodes=0,
                      analytically_collinear_boundary_artifacts_removed=int(degenerate.sum()),
                      removed_boundary_artifact_absolute_area_um2=removed_sliver_area)
    return FEMMesh(vertices, triangles, required, tuple(original_nodes), validation)


def solve_fem(points: Sequence[tuple[float, float]], contacts: Sequence[Contact],
              conductivity_s_per_m: float, thickness_m: float, h_um: float) -> FEMSolution:
    """Solve the fixed 1 V/0 V electrode problem with exact P1 element integrals."""
    if len(contacts) != 2 or any(not math.isfinite(v) or v <= 0 for v in (conductivity_s_per_m, thickness_m)):
        raise FEMError("Two full-edge contacts and positive finite bulk conductivity/thickness are required")
    if not math.isfinite(h_um) or h_um <= 0 or h_um > min(c.width_um for c in contacts) / 4:
        raise FEMError("Resolve each unchanged contact with at least four boundary segments")
    polygon, tolerance = _polygon(points)
    mesh = make_mesh(polygon, h_um)
    contact_nodes = []
    for contact in contacts:
        a, b = np.asarray(contact.start), np.asarray(contact.end)
        matches = [i for i, (start, end) in enumerate(zip(polygon, np.roll(polygon, -1, axis=0)))
                   if (np.linalg.norm(start - a) <= tolerance and np.linalg.norm(end - b) <= tolerance)
                   or (np.linalg.norm(start - b) <= tolerance and np.linalg.norm(end - a) <= tolerance)]
        if len(matches) != 1:
            raise FEMError("Each Dirichlet contact must be exactly one original complete polygon edge")
        contact_nodes.append(mesh.original_edge_nodes[matches[0]])
    if np.intersect1d(*contact_nodes).size:
        raise FEMError("The two fixed-voltage contacts overlap or touch")
    vertices, triangles = mesh.vertices_um, mesh.triangles
    coordinates = vertices[triangles]
    area2 = _cross(coordinates[:, 1] - coordinates[:, 0], coordinates[:, 2] - coordinates[:, 0])
    area = area2 / 2
    gradients = np.stack((coordinates[:, [1, 2, 0], 1] - coordinates[:, [2, 0, 1], 1],
                          coordinates[:, [2, 0, 1], 0] - coordinates[:, [1, 2, 0], 0]), axis=2) / area2[:, None, None]
    sheet_g = conductivity_s_per_m * thickness_m
    element = sheet_g * area[:, None, None] * np.einsum("tik,tjk->tij", gradients, gradients)
    rows, columns = np.repeat(triangles, 3, axis=1).ravel(), np.tile(triangles, (1, 3)).ravel()
    stiffness = coo_matrix((element.ravel(), (rows, columns)), shape=(len(vertices), len(vertices))).tocsr()
    stiffness.sum_duplicates()
    voltage = np.zeros(len(vertices))
    voltage[contact_nodes[0]] = 1
    fixed = np.concatenate(contact_nodes)
    free = np.setdiff1d(np.arange(len(vertices)), fixed)
    if not len(free):
        raise FEMError("The mesh has no free conductor nodes")
    rhs = -(stiffness[free][:, fixed] @ voltage[fixed])
    with warnings.catch_warnings():
        warnings.simplefilter("error", MatrixRankWarning)
        try:
            voltage[free] = spsolve(stiffness[free][:, free], rhs)
        except (MatrixRankWarning, RuntimeError) as exc:
            raise FEMError("The free-node FEM stiffness solve is singular or failed") from exc
    if not np.all(np.isfinite(voltage)):
        raise FEMError("The FEM voltage solution is nonfinite")
    reaction = stiffness @ voltage
    current = [float(reaction[nodes].sum()) for nodes in contact_nodes]
    gradient_v = np.einsum("ti,tij->tj", voltage[triangles], gradients)
    element_power = float(sheet_g * np.sum(area * np.einsum("ij,ij->i", gradient_v, gradient_v)))
    matrix_power = float(voltage @ reaction)
    scale = max(abs(current[0]), abs(current[1]), 1e-30)
    imbalance = abs(sum(current)) / scale
    free_residual = float(np.max(np.abs(reaction[free]))) / scale
    power_error = max(abs(element_power - current[0]), abs(matrix_power - current[0])) / scale
    if current[0] <= 0 or current[1] >= 0 or element_power <= 0 or not all(math.isfinite(v) for v in (*current, element_power, matrix_power, imbalance, free_residual, power_error)):
        raise FEMError("Invalid terminal current or dissipated power")
    if max(imbalance, free_residual, power_error) > 1e-7:
        raise FEMError("FEM current conservation, free residual or independent element-power check failed")
    metrics = {"h_um": h_um, "R_ohm": 1 / current[0], "conductance_S": current[0],
               "mesh_validation": mesh.validation, "terminal_current_A_at_1V": {contact.name: value for contact, value in zip(contacts, current)},
               "element_dissipation_W": element_power, "matrix_dissipation_W": matrix_power,
               "relative_terminal_current_imbalance": imbalance, "relative_free_node_residual": free_residual,
               "relative_independent_power_error": power_error, "voltage_min_V": float(voltage.min()), "voltage_max_V": float(voltage.max()),
               "contact_node_counts": [len(nodes) for nodes in contact_nodes], "contact_widths_um": [c.width_um for c in contacts],
               "operator": "Kij = sigma*t*sum_T(area_T*grad(Ni).grad(Nj)); exact P1 element integration; no finite-volume stencil",
               "coordinate_units": "um; area and squared-gradient scale cancel in the stiffness; currents are A"}
    json.dumps(metrics, allow_nan=False)
    return FEMSolution(metrics, mesh, voltage, -sheet_g * 1e6 * gradient_v)


def _source(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"name": path.name, "path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def analyze_export(input_dir: str | Path, output_dir: str | Path,
                   grids_um: Sequence[float] = (0.5, 0.25), plots: bool = True) -> dict[str, Any]:
    source, output = Path(input_dir).resolve(strict=True), Path(output_dir).resolve()
    if output == source or source.is_relative_to(output) or output.is_relative_to(source):
        raise FEMError("FEM output must be separate from its unchanged source deck")
    if output.exists():
        raise FileExistsError("Use a fresh FEM output directory")
    if len(grids_um) < 2 or any(not math.isfinite(h) or h <= 0 for h in grids_um) or any(a <= b for a, b in zip(grids_um, grids_um[1:])):
        raise FEMError("Retain at least two strictly decreasing finite positive mesh spacings")
    sources = [_source(source / name) for name in ("proj_a", "proj.pin", "proj.prt", "proj.ltd")]
    polygons, pins, ports = read_export(source)
    if len(ports) != 2 or any(port.plus_pins != (f"P{port.number}",) or port.minus_pins != ("P4",) or port.reference_real_ohm != 50 or port.reference_imag_ohm != 0 for port in ports):
        raise FEMError("This experiment requires the complete P1/P4 and P2/P4 two-port with 50 ohm references")
    signal = [p for p in polygons if p.layer == 35]
    if len(signal) != 1 or any(p.layer not in (7, 35) for p in polygons):
        raise FEMError("Only one uniform M6 polygon and separate finite M1 return polygons are supported; no vias")
    signal_pins = {pin.name: pin for pin in pins if pin.layer == 35}
    if set(signal_pins) != {"P1", "P2"} or len([pin for pin in pins if pin.name == "P4" and pin.layer == 7]) != 1:
        raise FEMError("Unexpected signal pins or missing common finite-reference pin")
    contacts = [locate_contact(signal[0].points_um, signal_pins[name], 10.0) for name in ("P1", "P2")]
    material = material_from_ltd((source / "proj.ltd").read_text(encoding="utf-8-sig"))
    solutions = [solve_fem(signal[0].points_um, contacts, material["conductivity_s_per_m"], material["thickness_m"], float(h)) for h in grids_um]
    if [_source(source / name) for name in ("proj_a", "proj.pin", "proj.prt", "proj.ltd")] != sources:
        raise FEMError("An actual source deck changed during the independent solve")
    report = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(), "status": "NUMERICAL_DC_CONFORMING_FEM_ESTIMATE",
              "device_target_result": "NOT_EVALUATED", "method": "Conforming P1 triangular Galerkin FEM on the unchanged simple M6 polygon",
              "excitation": "V(P1)-V(P2)=1 V; original full 10 um end faces equipotential through the uniform thickness; other boundaries Neumann zero flux",
              "contact_model_changed_or_fitted": False, "material": material,
              "contacts": [{"name": c.name, "edge_start_um": c.start, "edge_end_um": c.end, "actual_width_um": c.width_um,
                            "RF_pin_to_actual_edge_distance_um": c.pin_to_edge_distance_um} for c in contacts],
              "meshes": [s.metrics for s in solutions], "finest_R_ohm": solutions[-1].metrics["R_ohm"],
              "refinement": [{"coarser_h_um": a.metrics["h_um"], "finer_h_um": b.metrics["h_um"],
                              "signed_finer_minus_coarser_R_ohm": b.metrics["R_ohm"] - a.metrics["R_ohm"],
                              "absolute_change_ohm": abs(b.metrics["R_ohm"] - a.metrics["R_ohm"]),
                              "relative_change": abs(b.metrics["R_ohm"] - a.metrics["R_ohm"]) / b.metrics["R_ohm"]} for a, b in zip(solutions, solutions[1:])],
              "return_condition": "Separate M1 has zero DC injection with the same P4 and I1+I2=0; no via or conductive dielectric path",
              "sources": sources, "runtime": {"numpy_version": np.__version__, "scipy_version": scipy.__version__},
              "limitations": ["The full-end-face Dirichlet contact is fixed; RF excitation equivalence still requires separate evidence",
                              "Unconstrained Delaunay is accepted only after full boundary, area, crossing and topology checks; unsupported meshes are rejected",
                              "Conforming fixed-voltage P1 energy gives a discrete conductance above the continuum value in exact arithmetic, but independent Delaunay refinements are not nested",
                              "Observed refinement differences are not rigorous continuum error bounds; no contact or conductivity is selected to match RF",
                              "The finite-volume operator is not reused; only actual geometry/material/contact readers are shared",
                              "This numerical research-stack DC comparison establishes no device, foundry or parent-filter acceptance"]}
    serialized = json.dumps(report, indent=2, allow_nan=False) + "\n"
    output.mkdir(parents=True, exist_ok=False)
    (output / "dc-fem-analysis.json").write_text(serialized, encoding="utf-8")
    finest = solutions[-1]
    np.savez_compressed(output / "dc-fem-finest-mesh.npz", vertices_um=finest.mesh.vertices_um, triangles=finest.mesh.triangles,
                        required_boundary_edges=finest.mesh.required_boundary_edges, voltage_V=finest.voltage_V,
                        sheet_current_A_per_m=finest.sheet_current_A_per_m)
    if plots:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 6), constrained_layout=True)
        vertices = finest.mesh.vertices_um
        field = ax.tripcolor(vertices[:, 0], vertices[:, 1], finest.mesh.triangles, finest.voltage_V, shading="gouraud", cmap="viridis", vmin=0, vmax=1)
        polygon = np.asarray(signal[0].points_um)
        closed = np.vstack((polygon, polygon[0]))
        ax.plot(closed[:, 0], closed[:, 1], color="black", linewidth=0.5)
        for contact, color in zip(contacts, ("red", "blue")):
            ax.plot([contact.start[0], contact.end[0]], [contact.start[1], contact.end[1]], color=color, linewidth=3, label=contact.name)
        ax.set(xlabel="x (um)", ylabel="y (um)", title="Conforming P1 DC estimate; fixed full end-face contacts", aspect="equal")
        ax.legend()
        fig.colorbar(field, ax=ax, label="Voltage (V)")
        fig.savefig(output / "dc-fem-voltage.png", dpi=180)
        plt.close(fig)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--grids-um", nargs="+", type=float, default=[0.5, 0.25])
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    try:
        report = analyze_export(args.input_dir, args.output_dir, args.grids_um, not args.no_plots)
    except (FEMError, DCError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Conforming DC FEM estimate: {report['finest_R_ohm']:.10g} ohm; {len(report['meshes'])} validated meshes; device not evaluated")


if __name__ == "__main__":
    main()
