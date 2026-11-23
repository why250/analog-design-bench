"""Independent finite-volume DC sheet solve on the actual exported M6 polygon.

The electrical contacts are full 10 um terminal end faces associated with the
physical P1/P2 pins. This is an explicit DC contact model; a Momentum point pin
alone does not establish its width. Compare the result with low-frequency RF R
before adopting a broadband extension. No RF sample is called a DC solve.

Square cells have neighbor conductance sigma*thickness. Boundary contacts use
their face width divided by their distance to the cell center, retaining the
half-cell boundary resistance. All other boundaries are insulating. Staircase
domain error is assessed by refinement; observed differences are not rigorous
continuum error bounds. The separate finite M1 frame has zero DC injection when
both signal currents reference the SAME P4 and I1+I2=0. No interlayer DC path is
included or permitted by this helper.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import warnings
from typing import Any, Sequence

import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import MatrixRankWarning, spsolve

from plot_geometry import Pin, Polygon, read_export


class DCError(ValueError):
    """Geometry or numerical evidence does not support this sheet experiment."""


@dataclass(frozen=True)
class Contact:
    name: str
    start: tuple[float, float]
    end: tuple[float, float]
    inward_normal: tuple[float, float]
    pin_to_edge_distance_um: float

    @property
    def width_um(self) -> float:
        return math.dist(self.start, self.end)


@dataclass
class SheetSolution:
    metrics: dict[str, Any]
    x_um: np.ndarray
    y_um: np.ndarray
    mask: np.ndarray
    voltage: np.ndarray


def inside_polygon(x: np.ndarray, y: np.ndarray, points: Sequence[tuple[float, float]]) -> np.ndarray:
    """Even/odd interior test; grid centers should avoid exact polygon edges."""
    inside = np.zeros(np.broadcast_shapes(x.shape, y.shape), dtype=bool)
    for (x1, y1), (x2, y2) in zip(points, list(points[1:]) + [points[0]]):
        if y1 == y2:
            continue
        crossing = ((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1)
        inside ^= crossing
    return inside


def locate_contact(points: Sequence[tuple[float, float]], pin: Pin,
                   width_um: float, tolerance_um: float = 0.002) -> Contact:
    """Associate a point pin with one actual axis-aligned terminal end face."""
    area2 = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2)
                in zip(points, list(points[1:]) + [points[0]]))
    if area2 == 0:
        raise DCError("A conducting polygon has zero area")
    orientation = 1 if area2 > 0 else -1
    matches = []
    position = np.array([pin.x_um, pin.y_um])
    for start, end in zip(points, list(points[1:]) + [points[0]]):
        a, b = np.asarray(start), np.asarray(end)
        delta = b - a
        length = float(np.linalg.norm(delta))
        if length == 0 or not (abs(delta[0]) <= 1e-10 or abs(delta[1]) <= 1e-10):
            continue
        tangent = delta / length
        projection = float((position - a) @ tangent)
        nearest = a + np.clip(projection, 0, length) * tangent
        distance = float(np.linalg.norm(position - nearest))
        if distance <= tolerance_um and abs(length - width_um) <= 2 * tolerance_um:
            normal = orientation * np.array([-tangent[1], tangent[0]])
            matches.append(Contact(pin.name, tuple(map(float, a)), tuple(map(float, b)),
                                   tuple(map(float, normal)), distance))
    if len(matches) != 1:
        raise DCError(f"Pin {pin.name} must identify exactly one actual {width_um:g} um terminal edge")
    return matches[0]


def material_from_ltd(text: str, layer: int = 35) -> dict[str, Any]:
    """Read actual uniform bulk conductivity/thickness from the solver deck."""
    for name, expected in (("DISTANCE", "METRE"), ("CONDUCTIVITY", "SIEMENS/M")):
        if re.search(rf"(?im)^\s*{name}\s*=\s*{re.escape(expected)}\s*$", text) is None:
            raise DCError(f"Explicit {name}={expected} units are required")
    masks = re.findall(rf"(?im)^\s*MASK\s+{layer}\s+([^\r\n]+)$", text)
    if len(masks) != 1:
        raise DCError("Exactly one actual signal-layer mask definition is required")
    material = re.search(r"\bMATERIAL=([^\s]+)", masks[0])
    operation = re.search(r"\bOPERATION=([^\s]+)", masks[0])
    if material is None or operation is None:
        raise DCError("The signal mask lacks material or finite-thickness mapping")
    materials = re.findall(rf"(?im)^\s*MATERIAL\s+{re.escape(material.group(1))}\s+([^\r\n]+)$", text)
    operations = re.findall(rf"(?im)^\s*OPERATION\s+{re.escape(operation.group(1))}\s+([^\r\n]+)$", text)
    if len(materials) != 1 or len(operations) != 1:
        raise DCError("Signal conductor material/operation is missing or ambiguous")
    conductivity = re.search(r"(?<!\w)CONDUCTIVITY=([^\s]+)", materials[0])
    imaginary = re.search(r"(?<!\w)IMAG_CONDUCTIVITY=([^\s]+)", materials[0])
    thickness = re.fullmatch(r"EXPAND=([^\s]+)\s+(?:UP|DOWN)", operations[0].strip(), re.I)
    if conductivity is None or imaginary is None or thickness is None:
        raise DCError("A real bulk conductor and uniform expanded thickness are required")
    sigma, imag, thick = float(conductivity.group(1)), float(imaginary.group(1)), float(thickness.group(1))
    if not all(math.isfinite(v) for v in (sigma, imag, thick)) or sigma <= 0 or thick <= 0 or imag != 0:
        raise DCError("Unsupported complex, zero, or nonfinite DC conductor parameters")
    return {"layer": layer, "material": material.group(1), "conductivity_s_per_m": sigma,
            "thickness_m": thick, "sheet_resistance_ohm": 1 / (sigma * thick),
            "source": "actual exported proj.ltd; process values remain research assumptions"}


def solve_sheet(points: Sequence[tuple[float, float]], contacts: Sequence[Contact],
                conductivity_s_per_m: float, thickness_m: float, grid_um: float) -> SheetSolution:
    """Solve unit terminal voltage on one connected pixelated conductor sheet."""
    if len(contacts) != 2:
        raise DCError("Exactly two independent terminal contacts are required")
    if any(not math.isfinite(v) or v <= 0 for v in (conductivity_s_per_m, thickness_m, grid_um)):
        raise DCError("Conductivity, thickness and grid spacing must be finite and positive")
    if grid_um > min(c.width_um for c in contacts) / 4:
        raise DCError("At least four cells across each contact are required")
    # Collinear terminal faces of an open loop must retain their insulating gap.
    # Otherwise a coarse cell graph could bridge the gap without a drawn short.
    first, second = contacts
    n1, n2 = np.array(first.inward_normal), np.array(second.inward_normal)
    t1 = (np.array(first.end) - np.array(first.start)) / first.width_um
    line_separation = abs(float((np.array(second.start) - np.array(first.start)) @ n1))
    if float(n1 @ n2) > 1 - 1e-10 and line_separation <= 0.002:
        ranges = [sorted(float(np.array(p) @ t1) for p in (c.start, c.end)) for c in contacts]
        gap = max(ranges[1][0] - ranges[0][1], ranges[0][0] - ranges[1][1])
        if gap <= 0 or grid_um > gap / 2:
            raise DCError("The insulating gap between terminal end faces is not resolved by two cells")
    coordinates = np.asarray(points, dtype=float)
    if coordinates.ndim != 2 or coordinates.shape[1] != 2 or not np.all(np.isfinite(coordinates)):
        raise DCError("A finite two-dimensional conducting polygon is required")
    minimum, maximum = coordinates.min(axis=0), coordinates.max(axis=0)
    x = minimum[0] + grid_um * (np.arange(math.ceil((maximum[0] - minimum[0]) / grid_um)) + 0.5)
    y = minimum[1] + grid_um * (np.arange(math.ceil((maximum[1] - minimum[1]) / grid_um)) + 0.5)
    xx, yy = np.meshgrid(x, y)
    mask = inside_polygon(xx, yy, points)
    count = int(mask.sum())
    if not count:
        raise DCError("No conductor cells remain at this grid spacing")
    index = np.full(mask.shape, -1, dtype=int)
    index[mask] = np.arange(count)
    pairs = []
    for first, second in ((index[:, :-1], index[:, 1:]), (index[:-1, :], index[1:, :])):
        present = (first >= 0) & (second >= 0)
        pairs.append((first[present], second[present]))
    edge_i = np.concatenate([a for a, _ in pairs])
    edge_j = np.concatenate([b for _, b in pairs])
    graph = coo_matrix((np.ones(2 * len(edge_i)), (np.r_[edge_i, edge_j], np.r_[edge_j, edge_i])), shape=(count, count)).tocsr()
    components = int(connected_components(graph, directed=False, return_labels=False))
    if components != 1:
        raise DCError(f"Rasterized signal conductor has {components} disconnected components")
    sheet_g = conductivity_s_per_m * thickness_m
    cell_x, cell_y = xx[mask], yy[mask]
    contact_g = []
    contact_widths = []
    contact_counts = []
    for contact in contacts:
        a, b = np.array(contact.start), np.array(contact.end)
        normal = np.array(contact.inward_normal)
        tangent = (b - a) / contact.width_um
        displacement = np.column_stack((cell_x - a[0], cell_y - a[1]))
        distance = displacement @ normal
        along = displacement @ tangent
        face_width = np.maximum(0, np.minimum(along + grid_um / 2, contact.width_um) - np.maximum(along - grid_um / 2, 0))
        # A boundary-adjacent cell must have no conductor neighbor outward.
        outward_y, outward_x = -int(round(normal[1])), -int(round(normal[0]))
        if abs(outward_x) + abs(outward_y) != 1:
            raise DCError("Only axis-aligned full-face terminal contacts are supported")
        rows, columns = np.nonzero(mask)
        nr, nc = rows + outward_y, columns + outward_x
        inside_grid = (nr >= 0) & (nr < len(y)) & (nc >= 0) & (nc < len(x))
        outward_present = np.zeros(count, dtype=bool)
        outward_present[inside_grid] = mask[nr[inside_grid], nc[inside_grid]]
        selected = (distance > 1e-9) & (distance <= grid_um * (1 + 1e-9)) & (face_width > 0) & ~outward_present
        if not np.any(selected):
            raise DCError(f"No resolvable boundary cells connect to {contact.name}")
        conductance = np.zeros(count)
        conductance[selected] = sheet_g * face_width[selected] / distance[selected]
        contact_g.append(conductance)
        contact_widths.append(float(face_width[selected].sum()))
        contact_counts.append(int(selected.sum()))
    if np.any((contact_g[0] > 0) & (contact_g[1] > 0)):
        raise DCError("Contacts overlap on a grid cell; the terminal gap is unresolved")
    diagonal = sheet_g * np.asarray(graph.sum(axis=1)).ravel() + contact_g[0] + contact_g[1]
    laplacian = diags(diagonal) - sheet_g * graph
    rhs = contact_g[0]  # Contact voltages are 1 V and 0 V.
    with warnings.catch_warnings():
        warnings.simplefilter("error", MatrixRankWarning)
        voltage = spsolve(laplacian.tocsc(), rhs)
    if not np.all(np.isfinite(voltage)):
        raise DCError("The DC solution is nonfinite")
    residual = float(np.linalg.norm(laplacian @ voltage - rhs) / np.linalg.norm(rhs))
    ip = float(contact_g[0] @ (1 - voltage))
    inn = float(contact_g[1] @ (-voltage))
    balance = abs(ip + inn) / max(abs(ip), abs(inn))
    power = float(sheet_g * np.sum((voltage[edge_i] - voltage[edge_j])**2)
                  + contact_g[0] @ (1 - voltage)**2 + contact_g[1] @ voltage**2)
    power_error = abs(power - ip) / abs(ip)
    if ip <= 0 or inn >= 0 or residual > 1e-10 or balance > 1e-8 or power_error > 1e-8:
        raise DCError("The DC solve failed current, residual, or dissipation consistency")
    if voltage.min() < -1e-10 or voltage.max() > 1 + 1e-10:
        raise DCError("The resistor-network maximum principle is violated")
    field = np.zeros(mask.shape)
    field[mask] = voltage
    return SheetSolution({"grid_um": grid_um, "conductor_cells": count, "neighbor_edges": len(edge_i),
                          "connected_components": components, "R_ohm": 1 / ip,
                          "terminal_current_A_at_1V": {contacts[0].name: ip, contacts[1].name: inn},
                          "contact_resolved_width_um": contact_widths, "contact_boundary_cells": contact_counts,
                          "relative_equation_residual": residual, "relative_terminal_current_imbalance": balance,
                          "relative_dissipation_error": power_error,
                          "voltage_minimum_V": float(voltage.min()), "voltage_maximum_V": float(voltage.max())},
                         x, y, mask, field)


def analyze_export(input_dir: str | Path, output_dir: str | Path,
                   grids_um: Sequence[float] = (0.5, 0.25, 0.125), contact_width_um: float = 10,
                   construction_receipt: str | Path | None = None, plots: bool = True) -> dict[str, Any]:
    source, output = Path(input_dir).resolve(strict=True), Path(output_dir).resolve()
    if output == source or source.is_relative_to(output) or output.is_relative_to(source):
        raise DCError("DC output must be separate from its unchanged source deck")
    if output.exists():
        raise FileExistsError("Use a fresh DC output directory")
    if len(grids_um) < 2 or any(a <= b for a, b in zip(grids_um, grids_um[1:])):
        raise DCError("Use at least two strictly decreasing positive mesh spacings")
    polygons, pins, ports = read_export(source)
    if len(ports) != 2 or any(port.plus_pins != (f"P{port.number}",) or port.minus_pins != ("P4",) for port in ports):
        raise DCError("This DC experiment requires two signal ports with the same physical P4 reference")
    signal = [p for p in polygons if p.layer == 35]
    if len(signal) != 1 or any(p.layer not in (7, 35) for p in polygons):
        raise DCError("Exactly one M6 polygon and separate M1 return polygons are supported; vias/other layers need a different DC model")
    signal_pins = {pin.name: pin for pin in pins if pin.layer == 35}
    if set(signal_pins) != {"P1", "P2"} or len([pin for pin in pins if pin.name == "P4" and pin.layer == 7]) != 1:
        raise DCError("Unexpected auxiliary signal, missing contact, or invalid finite-reference pin")
    points = signal[0].points_um
    contacts = [locate_contact(points, signal_pins[name], contact_width_um) for name in ("P1", "P2")]
    material = material_from_ltd((source / "proj.ltd").read_text(encoding="utf-8-sig"))
    solutions = [solve_sheet(points, contacts, material["conductivity_s_per_m"], material["thickness_m"], float(grid)) for grid in grids_um]
    refinements = [{"coarser_grid_um": a.metrics["grid_um"], "finer_grid_um": b.metrics["grid_um"],
                    "absolute_change_ohm": abs(a.metrics["R_ohm"] - b.metrics["R_ohm"]),
                    "relative_change": abs(a.metrics["R_ohm"] - b.metrics["R_ohm"]) / b.metrics["R_ohm"]}
                   for a, b in zip(solutions, solutions[1:])]
    estimate = None
    if construction_receipt:
        construction = json.loads(Path(construction_receipt).read_text(encoding="utf-8-sig"))
        geometry = construction["geometry"]
        diameter, width, gap = (float(geometry[key]) for key in ("D_um", "w_um", "s_um"))
        perimeter = 8 * (diameter - width) / (1 + math.sqrt(2))
        squares = (perimeter - (gap + contact_width_um)) / width + 2 * (5 + width / 2) / contact_width_um
        estimate = {"R_ohm": material["sheet_resistance_ohm"] * squares,
                    "approximate_squares": squares, "regular_octagon_centerline_perimeter_um": perimeter,
                    "source": "independent centerline estimate using frozen construction dimensions",
                    "limitations": "Ignores corner current crowding and detailed feed junction spreading; not a second exact DC solve"}
    report = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
              "status": "NUMERICAL_DC_SHEET_ESTIMATE", "excitation": "V(P1)-V(P2)=1 V; shared P4 reference; Icm=0",
              "contact_model": "Full-width actual terminal end edges; uniform potential across conductor thickness",
              "contact_width_requested_um": contact_width_um,
              "contacts": [{"name": c.name, "edge_start_um": c.start, "edge_end_um": c.end,
                            "actual_width_um": c.width_um, "inward_normal": c.inward_normal,
                            "RF_pin_to_actual_edge_distance_um": c.pin_to_edge_distance_um} for c in contacts],
              "material": material, "meshes": [s.metrics for s in solutions], "refinement": refinements,
              "finest_R_ohm": solutions[-1].metrics["R_ohm"], "independent_centerline_estimate": estimate,
              "return_condition": "Separate finite M1 frame has no DC injection under the same-P4 Icm=0 constraint; no vias or conducting dielectric leakage",
              "limitations": ["Full-width DC end-face contacts are an explicit realization of the RF terminal planes, not established solely by point pin metadata",
                              "Compare with retained low-frequency RF Re(Zd); contact/source and discretization differences require explanation",
                              "Staircase boundary mesh; observed refinement differences are not rigorous error bounds",
                              "Uniform real conductivity and thickness from the assumed research stack; no foundry or measurement qualification"],
              "sources": [{"name": name, "bytes": (source / name).stat().st_size,
                           "sha256": hashlib.sha256((source / name).read_bytes()).hexdigest()}
                          for name in ("proj_a", "proj.pin", "proj.prt", "proj.ltd")]}
    json.dumps(report, allow_nan=False)
    output.mkdir(parents=True, exist_ok=False)
    (output / "dc-analysis.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    finest = solutions[-1]
    np.savez_compressed(output / "dc-finest-grid.npz", x_um=finest.x_um, y_um=finest.y_um,
                        conductor_mask=finest.mask, voltage_V=finest.voltage)
    if plots:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 6), constrained_layout=True)
        h = finest.metrics["grid_um"]
        field = ax.imshow(np.ma.array(finest.voltage, mask=~finest.mask), origin="lower",
                          extent=(finest.x_um[0] - h / 2, finest.x_um[-1] + h / 2,
                                  finest.y_um[0] - h / 2, finest.y_um[-1] + h / 2), cmap="viridis", vmin=0, vmax=1)
        for contact, color in zip(contacts, ("red", "blue")):
            ax.plot([contact.start[0], contact.end[0]], [contact.start[1], contact.end[1]], color=color, linewidth=3, label=contact.name)
        ax.set(xlabel="x (um)", ylabel="y (um)", title="Independent DC sheet voltage; full terminal-edge contacts", aspect="equal")
        ax.legend()
        fig.colorbar(field, ax=ax, label="Voltage (V)")
        fig.savefig(output / "dc-voltage.png", dpi=180)
        plt.close(fig)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--grids-um", nargs="+", type=float, default=[0.5, 0.25, 0.125])
    parser.add_argument("--contact-width-um", type=float, default=10)
    parser.add_argument("--construction-receipt", type=Path)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    report = analyze_export(args.input_dir, args.output_dir, args.grids_um, args.contact_width_um,
                            args.construction_receipt, not args.no_plots)
    print(f"Independent DC sheet estimate: {report['finest_R_ohm']:.8g} ohm; retained {len(report['meshes'])} meshes")


if __name__ == "__main__":
    main()
