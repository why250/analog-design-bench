"""Check actual Momentum physical inputs against the frozen research contract.

This standard-library check reads proj.ltd and the exported geometry/pin/port
files. ADS 2027 User Guide / Material Definitions / Dielectrics specifies direct
imaginary permittivity as negative for passive loss: er_imag = -er_real * TanD.
The frozen positive loss tangent is retained; positive direct imaginary values
are rejected as an incorrect realization, not accepted as passive loss.
It validates physical input consistency only; mesh convergence, executed
solver mode, EM results and parent-filter acceptance remain separate checks.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shlex
import sys
import tomllib
from typing import Any

import plot_geometry as geometry


TASK_ID = "rf-inductor-120ph-65g-em"
TASK_VERSION = TASK_ID + "-r1"
GEOMETRY_TOLERANCE_UM = 0.005
NOMINAL_FRAME_FACTOR = 1.8
SENSITIVITY_FRAME_FACTORS = (1.5, 1.8, 2.2)


class InputError(ValueError):
    """The actual input format or frozen contract is unsupported/incomplete."""


def _fields(tokens: list[str]) -> tuple[dict[str, str], list[str]]:
    fields: dict[str, str] = {}
    flags: list[str] = []
    for token in tokens:
        if "=" not in token:
            flags.append(token.upper())
            continue
        key, value = token.split("=", 1)
        key = key.upper()
        if not key or not value or key in fields:
            raise InputError("Empty or repeated LTD field")
        fields[key] = value
    return fields, flags


def parse_ltd(text: str) -> dict[str, Any]:
    """Read the exported V2 material, operation, mask and stratified-stack tables."""
    data: dict[str, Any] = {"units": {}, "materials": {}, "operations": {}, "masks": {}, "stack": []}
    section: str | None = None
    seen: set[str] = set()
    format_seen = False
    section_names = {"UNITS": "units", "BEGIN_MATERIAL": "materials",
                     "BEGIN_OPERATION": "operations", "BEGIN_MASK": "masks", "BEGIN_STACK": "stack"}
    for line_number, raw in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", "//")):
            continue
        upper = line.upper()
        if upper == "TECHFORMAT=V2" and not format_seen and section is None:
            format_seen = True
            continue
        if upper in section_names:
            new_section = section_names[upper]
            if section is not None or new_section in seen:
                raise InputError(f"Repeated/nested LTD section at line {line_number}")
            section = new_section
            seen.add(section)
            continue
        if upper.startswith("END_"):
            expected_end = {"units": "END_UNITS", "materials": "END_MATERIAL",
                            "operations": "END_OPERATION", "masks": "END_MASK", "stack": "END_STACK"}
            if section is None or upper != expected_end[section]:
                raise InputError(f"Unmatched LTD section end at line {line_number}")
            section = None
            continue
        if section is None:
            raise InputError(f"Unsupported LTD statement outside a section at line {line_number}")
        try:
            tokens = shlex.split(line, posix=True)
        except ValueError as exc:
            raise InputError(f"Malformed LTD quoting at line {line_number}") from exc
        if section == "units":
            fields, flags = _fields(tokens)
            if flags or len(fields) != 1 or next(iter(fields)) in data[section]:
                raise InputError("Malformed or repeated LTD unit declaration")
            data[section].update(fields)
        elif section in ("materials", "operations", "masks"):
            kind = {"materials": "MATERIAL", "operations": "OPERATION", "masks": "MASK"}[section]
            if len(tokens) < 3 or tokens[0].upper() != kind:
                raise InputError(f"Malformed LTD {kind} at line {line_number}")
            key = tokens[1]
            if section == "masks":
                try:
                    key = str(int(key))
                except ValueError as exc:
                    raise InputError("A mask must have a numeric layer ID") from exc
            if key in data[section]:
                raise InputError(f"Repeated LTD {kind} name {key}")
            fields, flags = _fields(tokens[2:])
            data[section][key] = {"fields": fields, "flags": flags}
        else:
            if tokens[0].upper() not in ("TOP", "BOTTOM", "INTERFACE", "LAYER"):
                raise InputError(f"Unsupported stack statement at line {line_number}")
            fields, flags = _fields(tokens[1:])
            data["stack"].append({"kind": tokens[0].upper(), "fields": fields, "flags": flags})
    if not format_seen or section is not None or seen != set(section_names.values()):
        raise InputError("Incomplete or unsupported LTD V2 structure")
    return data


def _number(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"Missing or malformed numeric {label}") from exc
    if not math.isfinite(number):
        raise InputError(f"Nonfinite {label}")
    return number


def _near(actual: float, expected: float, absolute: float = 1e-14) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-8, abs_tol=absolute)


def _add(checks: list[dict[str, Any]], name: str, passed: bool,
         observed: Any, expected: Any) -> None:
    checks.append({"check": name, "status": "SATISFIED" if passed else "VIOLATION",
                   "observed": observed, "expected": expected})


def _check_number(checks: list[dict[str, Any]], name: str, actual: Any, expected: float) -> None:
    actual = _number(actual, name)
    _add(checks, name, _near(actual, expected), actual, expected)


def _load_contract(root: Path) -> tuple[dict[str, Any], Path]:
    manifest = tomllib.loads((root / "project.toml").read_text(encoding="utf-8-sig"))
    project = manifest["project"]
    if (project["task_id"], project["revision"], project["task_version_id"]) != (TASK_ID, 1, TASK_VERSION):
        raise InputError("Manifest identity does not match this revision-1 task")
    input_relative = Path(manifest["paths"]["inputs"])
    contract_path = (root / input_relative / "research-contract-r1.json").resolve()
    if input_relative.is_absolute() or not contract_path.is_relative_to(root):
        raise InputError("The frozen contract must be inside the task root")
    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    if contract["task_version_id"] != TASK_VERSION or contract["status"] != "frozen-before-candidate-EM":
        raise InputError("The selected contract does not identify the frozen revision-1 inputs")
    return contract, contract_path


def _check_stack(ltd: dict[str, Any], contract: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    units = ltd["units"]
    expected_units = {"DISTANCE": "METRE", "CONDUCTIVITY": "SIEMENS/M", "RESISTIVITY": "OHM.CM",
                      "PERMITTIVITY": "RELATIVETOVACUUM", "PERMEABILITY": "RELATIVETOVACUUM"}
    for key, value in expected_units.items():
        _add(checks, "source_unit_" + key.lower(), units.get(key) == value, units.get(key), value)
    stack = ltd["stack"]
    kinds = [row["kind"] for row in stack]
    expected_kinds = ["TOP"] + [kind for _ in range(10) for kind in ("INTERFACE", "LAYER")] + ["INTERFACE", "BOTTOM"]
    _add(checks, "complete_stratified_stack_topology", kinds == expected_kinds, kinds, expected_kinds)
    boundaries = [row for row in stack if row["kind"] in ("TOP", "BOTTOM")]
    expected_boundaries = [{"kind": kind, "fields": {"MATERIAL": "AIR"}, "flags": ["OPEN"]}
                           for kind in ("TOP", "BOTTOM")]
    _add(checks, "open_air_top_and_bottom", boundaries == expected_boundaries, boundaries, expected_boundaries)
    contains_pec = any("PEC" in str(row).upper() or "PERFECT" in str(row).upper() for row in stack)
    _add(checks, "no_perfect_conductor_in_stack", not contains_pec, contains_pec, False)
    layers = [row for row in stack if row["kind"] == "LAYER"]
    expected_layers: list[dict[str, Any]] = []
    for layer in reversed(contract["stack"]["dielectrics_bottom_to_top"]):
        name = "ResearchOx1" if layer["name"] == "ox1" else layer["name"]
        count = int(layer.get("count", 1))
        height_um = _number(layer.get("thickness_um", layer.get("each_thickness_um")), "contract layer height")
        for _ in range(count):
            expected_layers.append({"material": name, "height_m": height_um * 1e-6,
                                    "er": _number(layer["er"], "contract permittivity")})
    actual_layers = [{"material": row["fields"].get("MATERIAL"),
                      "height_m": _number(row["fields"].get("HEIGHT"), "stack height")}
                     for row in layers]
    expected_order = [row["material"] for row in expected_layers]
    _add(checks, "complete_dielectric_layer_order", [row["material"] for row in actual_layers] == expected_order,
         actual_layers, [{"material": row["material"], "height_m": row["height_m"]} for row in expected_layers])
    if len(actual_layers) == len(expected_layers):
        for index, (actual, expected) in enumerate(zip(actual_layers, expected_layers), start=1):
            _check_number(checks, f"dielectric_layer_{index}_height_m", actual["height_m"], expected["height_m"])
    materials = ltd["materials"]
    tangent = _number(contract["stack"]["oxide_passivation_loss_tangent"], "contract loss tangent")
    visited: set[str] = set()
    for layer in expected_layers:
        name = layer["material"]
        if name in visited:
            continue
        visited.add(name)
        if name not in materials:
            raise InputError(f"Required stack material {name} is missing")
        fields = materials[name]["fields"]
        allowed_fields = {"PERMITTIVITY", "IMAG_PERMITTIVITY", "PERMEABILITY", "IMAG_PERMEABILITY"}
        if name == "Silicon":
            allowed_fields |= {"RESISTIVITY", "DOPING"}
        _add(checks, name + "_only_frozen_material_parameters",
             set(fields).issubset(allowed_fields) and not materials[name]["flags"],
             materials[name], {"allowed_fields": sorted(allowed_fields), "flags": []})
        _check_number(checks, name + "_relative_permittivity", fields.get("PERMITTIVITY"), layer["er"])
        _check_number(checks, name + "_relative_permeability", fields.get("PERMEABILITY"), 1.0)
        _check_number(checks, name + "_imaginary_permeability", fields.get("IMAG_PERMEABILITY", "0"), 0.0)
        if name == "Silicon":
            silicon = next(row for row in contract["stack"]["dielectrics_bottom_to_top"] if row["name"] == "Silicon")
            _check_number(checks, "silicon_resistivity_ohm_cm", fields.get("RESISTIVITY"), silicon["resistivity_ohm_cm"])
            _check_number(checks, "silicon_extra_imaginary_permittivity", fields.get("IMAG_PERMITTIVITY", "0"), 0.0)
        else:
            imaginary = _number(fields.get("IMAG_PERMITTIVITY"), name + " imaginary permittivity")
            _add(checks, name + "_passive_direct_imaginary_sign", imaginary <= 0, imaginary,
                 "nonpositive direct imaginary permittivity; ADS Material Definitions")
            _check_number(checks, name + "_imaginary_permittivity", imaginary, -layer["er"] * tangent)
    active_masks: dict[str, Any] = {}
    for layer_id, name, contract_name in ((7, "Metal1", "metal1"), (35, "Metal6", "metal6")):
        try:
            mask = ltd["masks"][str(layer_id)]["fields"]
            material = materials[mask["MATERIAL"]]["fields"]
            operation = ltd["operations"][mask["OPERATION"]]
        except KeyError as exc:
            raise InputError(f"Missing active conductor mapping for layer {layer_id}") from exc
        _add(checks, name + "_mask_identity", (mask.get("NAME"), mask.get("MATERIAL")) == (name, name),
             {"name": mask.get("NAME"), "material": mask.get("MATERIAL")}, {"name": name, "material": name})
        conductor = contract["stack"][contract_name]
        _check_number(checks, name + "_conductivity_s_per_m", material.get("CONDUCTIVITY"), conductor["conductivity_s_per_m"])
        _check_number(checks, name + "_imaginary_conductivity", material.get("IMAG_CONDUCTIVITY", "0"), 0.0)
        _check_number(checks, name + "_relative_permeability", material.get("PERMEABILITY"), 1.0)
        _check_number(checks, name + "_imaginary_permeability", material.get("IMAG_PERMEABILITY", "0"), 0.0)
        _check_number(checks, name + "_thickness_m", operation["fields"].get("EXPAND"), conductor["thickness_um"] * 1e-6)
        _add(checks, name + "_finite_thickness_upward", operation["flags"] == ["UP"], operation["flags"], ["UP"])
        allowed = {"CONDUCTIVITY", "IMAG_CONDUCTIVITY", "PERMEABILITY", "IMAG_PERMEABILITY"}
        _add(checks, name + "_constant_smooth_material", set(material).issubset(allowed) and not materials[mask["MATERIAL"]]["flags"], sorted(material), sorted(allowed))
        active_stack_rows = [row["kind"] for row in stack if name in row["fields"].get("MASK", "").strip("{}").split(",")]
        _add(checks, name + "_mapped_only_at_one_interface", active_stack_rows == ["INTERFACE"], active_stack_rows, ["INTERFACE"])
        active_masks[str(layer_id)] = {"mask": mask, "material": material, "operation": operation}
    # Physical vertical placement matters as much as material table values.
    depth_m = 0.0
    interface_depths: dict[str, list[float]] = {"Metal1": [], "Metal6": []}
    for row in stack:
        if row["kind"] == "LAYER":
            depth_m += _number(row["fields"].get("HEIGHT"), "layer height")
        elif row["kind"] == "INTERFACE":
            for name in interface_depths:
                if row["fields"].get("MASK") == "{" + name + "}":
                    interface_depths[name].append(depth_m)
    expected_depths = {"Metal6": (0.7 + 1) * 1e-6, "Metal1": (0.7 + 1 + 5 * 0.8) * 1e-6}
    for name, expected_depth in expected_depths.items():
        actual_depths = interface_depths[name]
        _add(checks, name + "_interface_depth_from_top_m",
             len(actual_depths) == 1 and _near(actual_depths[0], expected_depth), actual_depths, [expected_depth])
    return {"units": units, "dielectric_layers_top_to_bottom": actual_layers,
            "materials": materials, "active_masks": active_masks,
            "active_interface_depths_from_top_m": interface_depths,
            "boundaries": boundaries, "total_dielectric_height_m": depth_m}


def _on_segment(x: float, y: float, a: tuple[float, float], b: tuple[float, float], tolerance: float) -> bool:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return math.hypot(x - a[0], y - a[1]) <= tolerance
    projection = ((x - a[0]) * dx + (y - a[1]) * dy) / (length * length)
    return (-tolerance / length <= projection <= 1 + tolerance / length
            and abs(dx * (y - a[1]) - dy * (x - a[0])) / length <= tolerance)


def point_on_metal(x: float, y: float, polygon: geometry.Polygon,
                   tolerance: float = GEOMETRY_TOLERANCE_UM) -> bool:
    """Boundary-inclusive polygon incidence with explicit export-grid tolerance."""
    points = polygon.points_um
    inside = False
    for a, b in zip(points, points[1:] + points[:1]):
        if _on_segment(x, y, a, b, tolerance):
            return True
        if (a[1] > y) != (b[1] > y):
            intersection_x = a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1])
            if x < intersection_x:
                inside = not inside
    return inside


def _bounds(polygons: list[geometry.Polygon]) -> tuple[float, float, float, float]:
    points = [point for polygon in polygons for point in polygon.points_um]
    return min(x for x, _ in points), min(y for _, y in points), max(x for x, _ in points), max(y for _, y in points)


def _rectangle(polygon: geometry.Polygon) -> tuple[float, float, float, float] | None:
    xmin, ymin, xmax, ymax = _bounds([polygon])
    corners = {(xmin, ymin), (xmin, ymax), (xmax, ymin), (xmax, ymax)}
    if set(polygon.points_um) == corners and xmax > xmin and ymax > ymin:
        return xmin, ymin, xmax, ymax
    return None


def _frame_geometry(polygons: list[geometry.Polygon]) -> dict[str, Any] | None:
    rectangles = [_rectangle(polygon) for polygon in polygons]
    if len(rectangles) != 4 or any(rectangle is None for rectangle in rectangles):
        return None
    xmin, ymin, xmax, ymax = _bounds(polygons)
    vertical = [rectangle for rectangle in rectangles if rectangle[1] == ymin and rectangle[3] == ymax]
    if len(vertical) != 2:
        return None
    left, right = sorted(vertical)
    horizontal = [rectangle for rectangle in rectangles if rectangle not in vertical]
    if len(horizontal) != 2:
        return None
    bottom, top = sorted(horizontal, key=lambda r: r[1])
    inner = (left[2], bottom[3], right[0], top[1])
    if not (xmin < inner[0] < inner[2] < xmax and ymin < inner[1] < inner[3] < ymax):
        return None
    # Verify the actual rectangle union is exactly the finite rectangular ring.
    xs = sorted({value for r in rectangles for value in (r[0], r[2])})
    ys = sorted({value for r in rectangles for value in (r[1], r[3])})
    for x1, x2 in zip(xs, xs[1:]):
        for y1, y2 in zip(ys, ys[1:]):
            x, y = (x1 + x2) / 2, (y1 + y2) / 2
            observed = any(r[0] < x < r[2] and r[1] < y < r[3] for r in rectangles)
            expected = xmin < x < xmax and ymin < y < ymax and not (inner[0] < x < inner[2] and inner[1] < y < inner[3])
            if observed != expected:
                return None
    return {"outer_bounds_um": [xmin, ymin, xmax, ymax], "inner_bounds_um": list(inner),
            "side_widths_um": [inner[0] - xmin, inner[1] - ymin, xmax - inner[2], ymax - inner[3]],
            "inner_width_um": inner[2] - inner[0], "inner_height_um": inner[3] - inner[1],
            "center_um": [(xmin + xmax) / 2, (ymin + ymax) / 2]}


def _top_linewidth(polygons: list[geometry.Polygon], x: float) -> float | None:
    intersections: list[float] = []
    for polygon in polygons:
        points = polygon.points_um
        for a, b in zip(points, points[1:] + points[:1]):
            if (a[0] <= x < b[0]) or (b[0] <= x < a[0]):
                intersections.append(a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))
    unique = sorted(set(round(value, 10) for value in intersections))
    return unique[-1] - unique[-2] if len(unique) >= 2 else None


def _check_geometry(polygons: tuple[geometry.Polygon, ...], pins: tuple[geometry.Pin, ...],
                    ports: tuple[geometry.Port, ...], contract: dict[str, Any],
                    checks: list[dict[str, Any]], frame_factor: float, sensitivity: bool,
                    construction: dict[str, Any] | None) -> dict[str, Any]:
    layers = {polygon.layer for polygon in polygons}
    _add(checks, "only_active_M1_M6_no_vias", layers == {7, 35}, sorted(layers), [7, 35])
    names = {pin.name for pin in pins}
    _add(checks, "two_signal_pins_and_finite_return_no_center_tap", names == {"P1", "P2", "P4"}, sorted(names), ["P1", "P2", "P4"])
    for pin in pins:
        expected_layer = 7 if pin.name == "P4" else 35
        _add(checks, pin.name + "_physical_layer", pin.layer == expected_layer, pin.layer, expected_layer)
        incidence = [index for index, polygon in enumerate(polygons)
                     if polygon.layer == pin.layer and point_on_metal(pin.x_um, pin.y_um, polygon)]
        _add(checks, pin.name + "_on_exported_metal", bool(incidence), incidence, "at least one polygon on the declared conductor layer")
    mapping = [{"number": p.number, "positive": list(p.plus_pins), "negative": list(p.minus_pins),
                "reference_real_ohm": p.reference_real_ohm, "reference_imag_ohm": p.reference_imag_ohm} for p in ports]
    expected_mapping = [{"number": n, "positive": [f"P{n}"], "negative": ["P4"],
                         "reference_real_ohm": 50.0, "reference_imag_ohm": 0.0} for n in (1, 2)]
    _add(checks, "actual_two_port_physical_return_mapping", mapping == expected_mapping, mapping, expected_mapping)
    metal6 = [polygon for polygon in polygons if polygon.layer == 35]
    metal1 = [polygon for polygon in polygons if polygon.layer == 7]
    if not metal6 or not metal1 or not {"P1", "P2", "P4"}.issubset(names):
        return {"pins": [asdict(pin) for pin in pins], "ports": mapping, "frame": None}
    by_name = {pin.name: pin for pin in pins}
    p, n, return_pin = (by_name[name] for name in ("P1", "P2", "P4"))
    through = any(point_on_metal(p.x_um, p.y_um, poly) and point_on_metal(n.x_um, n.y_um, poly) for poly in metal6)
    _add(checks, "p_and_n_share_continuous_exported_conductor", through, through, True)
    xmin, ymin, xmax, ymax = _bounds(metal6)
    diameter = xmax - xmin
    signal_center = (p.x_um + n.x_um) / 2
    width = _top_linewidth(metal6, signal_center)
    _add(checks, "diameter_in_frozen_search_bounds", contract["geometry"]["diameter_bounds_um"][0] <= diameter <= contract["geometry"]["diameter_bounds_um"][1],
         diameter, contract["geometry"]["diameter_bounds_um"])
    if width is not None:
        _add(checks, "top_linewidth_in_frozen_search_bounds", contract["geometry"]["width_bounds_um"][0] <= width <= contract["geometry"]["width_bounds_um"][1],
             width, contract["geometry"]["width_bounds_um"])
    else:
        _add(checks, "top_linewidth_measurable", False, None, "two transverse top-edge intersections")
    expected_factor_allowed = frame_factor in SENSITIVITY_FRAME_FACTORS if sensitivity else frame_factor == NOMINAL_FRAME_FACTOR
    _add(checks, "declared_frame_condition", expected_factor_allowed,
         {"factor": frame_factor, "sensitivity": sensitivity},
         {"nominal": NOMINAL_FRAME_FACTOR, "sensitivity_factors": list(SENSITIVITY_FRAME_FACTORS)})
    frame = _frame_geometry(metal1)
    _add(checks, "complete_finite_M1_rectangular_frame", frame is not None, frame, "four rectangles forming a finite continuous rectangular ring")
    if frame is not None:
        tolerance = GEOMETRY_TOLERANCE_UM * 3
        for name in ("inner_width_um", "inner_height_um"):
            _add(checks, "frame_" + name, _near(frame[name], frame_factor * diameter, tolerance), frame[name], frame_factor * diameter)
        expected_width = contract["return"]["frame_width_um"]
        _add(checks, "all_four_frame_widths", all(_near(value, expected_width, GEOMETRY_TOLERANCE_UM) for value in frame["side_widths_um"]),
             frame["side_widths_um"], [expected_width] * 4)
        expected_center = [signal_center, (ymax + p.y_um + contract["geometry"]["feed_extension_um"]) / 2]
        _add(checks, "frame_concentric_with_device", all(_near(a, b, GEOMETRY_TOLERANCE_UM) for a, b in zip(frame["center_um"], expected_center)),
             frame["center_um"], expected_center)
        outer = frame["outer_bounds_um"]
        inner = frame["inner_bounds_um"]
        lower_contact = inner[0] - GEOMETRY_TOLERANCE_UM <= return_pin.x_um <= inner[2] + GEOMETRY_TOLERANCE_UM and outer[1] - GEOMETRY_TOLERANCE_UM <= return_pin.y_um <= inner[1] + GEOMETRY_TOLERANCE_UM
        _add(checks, "P4_on_lower_physical_frame", lower_contact, [return_pin.x_um, return_pin.y_um], "lower finite Metal1 frame segment")
    if construction is not None:
        planned = construction["geometry"]
        for name, actual, expected in (("diameter", diameter, planned["D_um"]), ("top_linewidth", width, planned["w_um"]),
                                       ("feed_extension", -ymin, contract["geometry"]["feed_extension_um"]),
                                       ("signal_pin_gap_plus_feedwidth", n.x_um - p.x_um, planned["s_um"] + contract["geometry"]["feed_width_um"])):
            _add(checks, "construction_" + name, actual is not None and _near(actual, expected, GEOMETRY_TOLERANCE_UM), actual, expected)
        _add(checks, "construction_frame_factor", _near(planned["frame_factor"], frame_factor), planned["frame_factor"], frame_factor)
    return {"pins": [asdict(pin) for pin in pins], "ports": mapping,
            "active_geometry_layers": sorted(layers), "signal_bounds_um": [xmin, ymin, xmax, ymax],
            "derived_diameter_um": diameter, "derived_top_linewidth_um": width,
            "frame": frame, "coordinate_comparison_tolerance_um": GEOMETRY_TOLERANCE_UM}


def validate_inputs(root: str | Path, input_dir: str | Path, geometry_receipt: str | Path | None = None,
                    frame_factor: float = NOMINAL_FRAME_FACTOR, sensitivity: bool = False) -> dict[str, Any]:
    """Return strict JSON-compatible physical-input evidence, retaining failures."""
    root, input_dir = Path(root).resolve(), Path(input_dir).resolve()
    checks: list[dict[str, Any]] = []
    sources: list[Path] = []
    result: dict[str, Any] = {"schema_version": 1, "task_version_id": TASK_VERSION,
                             "checked_utc": datetime.now(timezone.utc).isoformat(),
                             "scope": "G1 physical input consistency only; no electrical acceptance",
                             "stack_classification": "explicit assumed research stack; no foundry qualification",
                             "dielectric_loss_convention": {
                                 "source": "ADS 2027 User Guide / Material Definitions / Dielectrics",
                                 "source_document": "usrguide/Material_Definitions.html",
                                 "realization": "direct er_imag = -er_real * positive TanD",
                                 "historical_positive_imaginary_inputs": "INVALID for the intended passive contract"},
                             "condition": {"frame_factor": frame_factor, "sensitivity": sensitivity},
                             "checks": checks}
    try:
        frame_factor = _number(frame_factor, "frame factor")
        contract, contract_path = _load_contract(root)
        sources.extend([root / "project.toml", contract_path])
        for name in ("proj.ltd", "proj_a", "proj.pin", "proj.prt"):
            source = input_dir / name
            if not source.is_file():
                raise InputError(f"Required solver input {name} is missing")
            sources.append(source)
        ltd = parse_ltd((input_dir / "proj.ltd").read_text(encoding="utf-8-sig"))
        result["stack"] = _check_stack(ltd, contract, checks)
        polygons, pins, ports = geometry.read_export(input_dir)
        construction = None
        if geometry_receipt is not None:
            receipt_path = Path(geometry_receipt).resolve(strict=True)
            construction = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
            sources.append(receipt_path)
        result["geometry"] = _check_geometry(polygons, pins, ports, contract, checks, frame_factor, sensitivity, construction)
    except (InputError, geometry.GeometryError, ValueError, KeyError, OSError, TypeError) as exc:
        _add(checks, "complete_supported_input_parse", False, str(exc), "complete finite solver inputs matching the frozen contract")
    result["status"] = "SATISFIED" if checks and all(check["status"] == "SATISFIED" for check in checks) else "INVALID"
    result["sources"] = [{"name": source.name, "size_bytes": source.stat().st_size,
                          "sha256": hashlib.sha256(source.read_bytes()).hexdigest()} for source in sources if source.is_file()]
    # Refuse accidental JSON NaN/Infinity even when a caller supplies bad inputs.
    try:
        factor_is_finite = math.isfinite(float(result["condition"]["frame_factor"]))
    except (TypeError, ValueError):
        factor_is_finite = False
    if not factor_is_finite:
        result["condition"]["frame_factor"] = None
    json.dumps(result, allow_nan=False)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Task root containing project.toml and frozen contract")
    parser.add_argument("--input-dir", type=Path, required=True, help="Retained actual Momentum solver-input directory")
    parser.add_argument("--output", type=Path, required=True, help="Fresh JSON receipt path")
    parser.add_argument("--geometry-receipt", type=Path, help="Optional native construction receipt for D/w/lead checks")
    parser.add_argument("--frame-factor", type=float, default=NOMINAL_FRAME_FACTOR)
    parser.add_argument("--sensitivity", action="store_true", help="Declare a frozen frame-sensitivity condition instead of nominal")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output JSON path; earlier evidence must be retained")
    result = validate_inputs(args.root, args.input_dir, args.geometry_receipt, args.frame_factor, args.sensitivity)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"Physical input consistency: {result['status']} ({len(result['checks'])} checks)")
    sys.exit(0 if result["status"] == "SATISFIED" else 2)


if __name__ == "__main__":
    main()
