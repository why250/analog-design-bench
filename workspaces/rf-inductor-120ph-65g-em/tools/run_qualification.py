"""Prepare auditable actual-point controls for one retained AFS candidate.

Planning and preparation do not control an ADS session. Execution uses the
existing synchronous Momentum runner. Numerical comparisons never establish a
physical device PASS or parent-filter acceptance. Original source and every
frequency/mesh/contact amendment remain alongside the resulting control case.
"""

from __future__ import annotations

import argparse
import bisect
from datetime import datetime, timezone
from decimal import Decimal
import io
import json
import math
from pathlib import Path
import shutil
from typing import Any, Iterable
import xml.etree.ElementTree as ET

from run_momentum import RunError, _json, _sha, _verify_completion, export_dataset, prepare_case, run_case


ANCHORS_GHZ = (5.0, 10.0, 65.0, 80.0, 100.0, 200.0)
LOW_FREQUENCY_GHZ = (0.01, 0.1, 1.0, 2.0, 3.0, 4.0, 5.0)
PORT_VARIANTS = {"pplus2": {"P1": 2.0, "P2": 2.0},
                 "pminus2": {"P1": -2.0, "P2": -2.0}, "gplus10": {"P4": 10.0}}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def select_midpoints(frequencies_hz: Iterable[float], count: int = 7,
                     minimum_band_points: int = 3) -> dict[str, Any]:
    """Select original adjacent-sample gaps, reserving the 10-65 GHz quota.

    Rank gaps by decreasing width, then increasing lower endpoint. Reserve the
    three largest gaps whose midpoint is in 10-65 GHz, then take the largest
    remaining gaps until seven are selected. No virtual bisection boundaries or
    interpolated/derived samples are treated as actual AFS points.
    """
    frequencies = [float(value) for value in frequencies_hz]
    if (len(frequencies) < 2 or any(not math.isfinite(f) or f <= 0 for f in frequencies)
            or any(a >= b for a, b in zip(frequencies, frequencies[1:]))):
        raise RunError("Actual AFS frequencies must be finite, positive, unique, and increasing")
    if type(count) is not int or type(minimum_band_points) is not int or not 0 <= minimum_band_points <= count:
        raise RunError("Midpoint count and in-band quota must be nonnegative integers")
    if frequencies[0] != 5e9 or frequencies[-1] != 200e9:
        raise RunError("This qualification profile requires actual AFS endpoints at exactly 5 and 200 GHz")
    intervals = []
    for index, (left, right) in enumerate(zip(frequencies, frequencies[1:])):
        midpoint = left + (right - left) / 2
        intervals.append({"source_interval_index": index, "lower_hz": left, "upper_hz": right,
                          "width_hz": right - left, "midpoint_hz": midpoint,
                          "midpoint_in_10_65_GHz": 10e9 <= midpoint <= 65e9})
    ranked = sorted(intervals, key=lambda item: (-item["width_hz"], item["lower_hz"]))
    for rank, interval in enumerate(ranked, 1):
        interval["global_gap_rank"] = rank
    in_band = [item for item in ranked if item["midpoint_in_10_65_GHz"]]
    if len(ranked) < count or len(in_band) < minimum_band_points:
        raise RunError("The actual AFS list has insufficient distinct gaps for seven midpoint controls with three in 10-65 GHz; no fabricated gap will be substituted")
    selected = [{**item, "selection_reason": "reserved largest in-band gap"} for item in in_band[:minimum_band_points]]
    indices = {item["source_interval_index"] for item in selected}
    for item in ranked:
        if len(selected) == count:
            break
        if item["source_interval_index"] not in indices:
            selected.append({**item, "selection_reason": "largest remaining original gap"})
            indices.add(item["source_interval_index"])
    selected.sort(key=lambda item: item["midpoint_hz"])
    return {"selection_rule": "Reserve the largest original in-band gaps, then fill by globally largest remaining original gaps; width ties use lower frequency",
            "actual_source_frequency_hz": frequencies, "all_ranked_original_gaps": ranked,
            "requested_midpoints": count, "minimum_midpoints_in_10_65_GHz": minimum_band_points,
            "selected_midpoints": selected,
            "selected_frequency_hz": [item["midpoint_hz"] for item in selected],
            "selected_in_band_count": sum(item["midpoint_in_10_65_GHz"] for item in selected),
            "virtual_or_interpolated_source_boundaries": False}


def plan_coverage_fill(actual_frequencies_hz: Iterable[float],
                       dense_frequencies_hz: Iterable[float]) -> dict[str, Any]:
    """Plan actual solves filling gaps in the unchanged original model grids.

    Original actual and ADS-derived dense samples retain distinct provenance.
    A requested solve is not evidence until its independent run completes.
    Split an original interval at 100 GHz when necessary, then use the smallest
    integer equal subdivision satisfying each side's frozen spacing limit.
    """
    sources = {"actual_EM": [float(value) for value in actual_frequencies_hz],
               "ADS-derived_dense_AFS": [float(value) for value in dense_frequencies_hz]}
    for kind, frequencies in sources.items():
        if (len(frequencies) < 2 or any(not math.isfinite(f) or f <= 0 for f in frequencies)
                or any(a >= b for a, b in zip(frequencies, frequencies[1:]))
                or frequencies[0] != 5e9 or frequencies[-1] != 200e9):
            raise RunError(f"Coverage source {kind} must be finite, unique, increasing, and span exactly 5-200 GHz")
    actual, dense = set(sources["actual_EM"]), set(sources["ADS-derived_dense_AFS"])
    union = sorted(actual | dense)

    def endpoint(frequency: float) -> dict[str, Any]:
        kinds = (["actual_EM"] if frequency in actual else []) + (["ADS-derived_dense_AFS"] if frequency in dense else [])
        return {"frequency_hz": frequency, "original_source_kinds": kinds,
                "is_original_actual_EM_sample": frequency in actual,
                "dense_source_is_not_actual_EM_evidence": frequency in dense and frequency not in actual,
                "planned_required_actual_boundary": frequency == 100e9 and frequency not in actual}

    planned = {100e9} if 100e9 not in actual else set()
    intervals = []
    for index, (left, right) in enumerate(zip(union, union[1:])):
        boundaries = [left] + ([100e9] if left < 100e9 < right else []) + [right]
        pieces = []
        interval_points = []
        for lower, upper in zip(boundaries, boundaries[1:]):
            limit = 1e9 if upper <= 100e9 else 5e9
            divisions = math.ceil((upper - lower) / limit)
            points = [lower + (upper - lower) * fraction / divisions for fraction in range(1, divisions)]
            planned.update(points)
            interval_points.extend(points)
            pieces.append({"lower_endpoint": endpoint(lower), "upper_endpoint": endpoint(upper),
                           "original_or_boundary_split_width_hz": upper - lower,
                           "maximum_spacing_hz": limit, "equal_subdivision_count": divisions,
                           "planned_actual_frequency_hz": points,
                           "planned_spacing_hz": (upper - lower) / divisions})
        intervals.append({"original_union_interval_index": index,
                          "original_lower_endpoint": endpoint(left), "original_upper_endpoint": endpoint(right),
                          "original_width_hz": right - left, "split_at_required_100_GHz_boundary": len(boundaries) == 3,
                          "subintervals": pieces, "planned_internal_actual_frequency_hz": interval_points})
    return {"selection_rule": "For each original actual+dense union interval, split at the required actual 100 GHz boundary, then use ceil(width/frozen limit) equal subdivisions; schedule internal points as independent actual solves only",
            "source_frequency_hz": sources, "original_union_frequency_hz": union,
            "original_union_endpoints": [endpoint(frequency) for frequency in union],
            "original_union_intervals": intervals,
            "maximum_spacing_hz_through_100_GHz": 1e9, "maximum_spacing_hz_above_100_GHz": 5e9,
            "required_actual_boundary_hz": 100e9, "required_boundary_already_actual": 100e9 in actual,
            "planned_actual_frequency_hz": sorted(planned),
            "status": "PLANNED_ACTUAL_SOLVES_NOT_COMPLETED_EVIDENCE",
            "original_networks_unchanged": True, "derived_samples_are_not_actual_EM_samples": True,
            "fitting_interpolation_or_resampling_performed": False,
            "coverage_achieved_by_this_plan_alone": False}


def track_actual_extrema(points: list[dict[str, Any]], *,
                          source_kind: str = "actual discrete EM samples only") -> dict[str, Any]:
    """Track finite observed extrema only, retaining unavailable metric states."""
    definitions = (
        ("minimum_L10_65", "L_h", 10e9, 65e9, "min"),
        ("maximum_L10_65", "L_h", 10e9, 65e9, "max"),
        ("maximum_R10_80", "R_ohm", 10e9, 80e9, "max"),
        ("minimum_Q10_80", "Q", 10e9, 80e9, "min"),
        ("maximum_Q10_80", "Q", 10e9, 80e9, "max"),
        ("minimum_X5_80", "X_ohm", 5e9, 80e9, "min"),
        ("maximum_absolute_Z5_200", "abs_Z_ohm", 5e9, 200e9, "max"),
    )
    tracked = []
    for name, field, lower, upper, direction in definitions:
        usable = []
        unavailable = []
        for point in points:
            frequency = point["frequency_hz"]
            if not lower <= frequency <= upper:
                continue
            differential = point["differential"]
            if field == "Q":
                value = differential["Q"]["value"]
            elif field in ("X_ohm", "abs_Z_ohm"):
                impedance = differential.get("impedance")
                value = (impedance["imag_ohm"] if field == "X_ohm" else math.hypot(impedance["real_ohm"], impedance["imag_ohm"])) if impedance is not None else None
            else:
                value = differential.get(field)
            if value is None or not math.isfinite(value):
                unavailable.append({"frequency_hz": frequency, "status": differential["Q"]["status"] if field == "Q" else differential["status"]})
            else:
                usable.append((float(value), frequency))
        result: dict[str, Any] = {"name": name, "metric": field, "sampled_band_hz": [lower, upper],
                                  "unavailable_actual_samples": unavailable, "continuous_extremum_proven": False}
        if usable:
            chosen = (min if direction == "min" else max)(usable, key=lambda pair: pair[0])
            result.update(status="OBSERVED_ACTUAL_SAMPLE" if source_kind.startswith("actual") else "OBSERVED_AFS_DERIVED_SAMPLE",
                          value=chosen[0], frequency_hz=chosen[1])
        else:
            result.update(status="NO_FINITE_ACTUAL_VALUE", value=None, frequency_hz=None)
        tracked.append(result)
    return {"tracked": tracked, "source_kind": source_kind,
            "frequency_hz": sorted({item["frequency_hz"] for item in tracked if item["frequency_hz"] is not None})}


def track_dense_extrema(points: list[dict[str, Any]]) -> dict[str, Any]:
    """Retain global and internal extrema of the ADS-derived dense curve.

    Every strict internal turning point is retained; no smoothing or numerical
    magnitude floor removes a feature. These are model predictions requiring
    actual controls, not actual EM extrema or continuous-band proofs.
    """
    result = track_actual_extrema(points, source_kind="ADS-derived dense AFS model; not actual EM samples")
    internal = []
    for metric, lower, upper in (("L_h", 10e9, 65e9), ("R_ohm", 10e9, 80e9),
                                  ("Q", 10e9, 80e9), ("X_ohm", 5e9, 80e9),
                                  ("abs_Z_ohm", 5e9, 200e9)):
        values = []
        for point in points:
            frequency = point["frequency_hz"]
            if not lower <= frequency <= upper:
                continue
            d = point["differential"]
            if metric == "Q":
                value = d["Q"]["value"]
            elif metric in ("X_ohm", "abs_Z_ohm"):
                z = d.get("impedance")
                value = (z["imag_ohm"] if metric == "X_ohm" else math.hypot(z["real_ohm"], z["imag_ohm"])) if z else None
            else:
                value = d.get(metric)
            values.append((frequency, value if value is not None and math.isfinite(value) else None))
        for first, middle, last in zip(values, values[1:], values[2:]):
            if any(pair[1] is None for pair in (first, middle, last)):
                continue
            before, after = middle[1] - first[1], last[1] - middle[1]
            if before * after < 0:
                internal.append({"metric": metric, "kind": "maximum" if before > 0 else "minimum",
                                 "frequency_hz": middle[0], "value": middle[1],
                                 "neighbor_frequencies_hz": [first[0], last[0]],
                                 "neighbor_values": [first[1], last[1]], "source_kind": "AFS-derived prediction"})
    result["internal_extrema"] = internal
    result["frequency_hz"] = sorted(set(result["frequency_hz"]) | {item["frequency_hz"] for item in internal})
    return result


def create_plan(afs_case_dir: str | Path, output: str | Path) -> dict[str, Any]:
    """Write a fresh plan from a completed passive fullwave AFS case."""
    case = Path(afs_case_dir).resolve(strict=True)
    prepared = _verify_completion(case)
    if prepared["mesh_um"] != 4:
        raise RunError("The requested mesh-control protocol requires the retained baseline to use 4 um cells")
    receipt_path = case / "afs-model-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    for name, identity in receipt["files"].items():
        if Path(name).name != name or _sha(case / name) != identity:
            raise RunError("Retained AFS source differs from its model export receipt")
    if receipt.get("raw_discrete_network") != "raw-discrete.s2p" or receipt.get("derived_ADS_dense_network") != "dense-afs.s2p":
        raise RunError("Qualification requires separately identified complete actual and AFS-derived two-port models")
    # Delay scientific imports so --help and gap/contact unit checks remain
    # usable with standard Python and no ADS environment.
    from analyze_em import point_metrics, read_touchstone

    network = read_touchstone(case / "raw-discrete.s2p")
    frequencies = list(map(float, network.frequency_hz))
    if network.port_count != 2 or network.reference_ohm != 50 or frequencies != receipt["actual_EM_samples_hz"]:
        raise RunError("Actual source network and AFS receipt disagree on complete ports, references, or samples")
    midpoint_selection = select_midpoints(frequencies)
    points = [point_metrics(float(frequency), matrix, 50) for frequency, matrix in zip(network.frequency_hz, network.s, strict=True)]
    extrema = track_actual_extrema(points)
    dense_network = read_touchstone(case / "dense-afs.s2p")
    if dense_network.port_count != 2 or dense_network.reference_ohm != 50:
        raise RunError("Dense AFS source does not retain the complete frozen two-port reference convention")
    coverage_fill = plan_coverage_fill(frequencies, dense_network.frequency_hz)
    dense_points = [point_metrics(float(frequency), matrix, 50) for frequency, matrix in zip(dense_network.frequency_hz, dense_network.s, strict=True)]
    dense_extrema = track_dense_extrema(dense_points)
    neighbors = []
    for frequency in dense_extrema["frequency_hz"]:
        index = bisect.bisect_left(frequencies, frequency)
        if index < len(frequencies) and frequencies[index] == frequency:
            indices = [index]
        else:
            if index == 0 or index == len(frequencies):
                raise RunError("A dense extremum is outside the actual AFS source range")
            indices = [index - 1, index]
        neighbors.append({"dense_predicted_extremum_hz": frequency, "actual_source_indices": indices,
                          "actual_neighbor_frequencies_hz": [frequencies[i] for i in indices],
                          "already_an_actual_solve": len(indices) == 1,
                          "independent_actual_control_required": True})
    mesh_hz = sorted({10e9, 65e9, 80e9} | set(extrema["frequency_hz"]) | set(dense_extrema["frequency_hz"]))
    forced_exact_hz = {float(frequency) * 1e9 for frequency in prepared["frequency_profile"]["forced_exact_GHz"]}
    actual_control_hz = sorted({frequency * 1e9 for frequency in ANCHORS_GHZ} | forced_exact_hz
                               | set(midpoint_selection["selected_frequency_hz"]) | set(mesh_hz)
                               | set(coverage_fill["planned_actual_frequency_hz"]))
    plan = {
        "schema_version": 1, "created_utc": _utc(), "task_version_id": "rf-inductor-120ph-65g-em-r1",
        "source_afs_case": str(case), "source_models": {"actual": "raw-discrete.s2p", "AFS-derived": "dense-afs.s2p"},
        "source_receipt": _sha(receipt_path), "source_model_identities": receipt["files"],
        "source_prepared_receipt": _sha(case / "prepared-case.json"),
        "frozen_solver_input_identities": {name: _sha(case / name) for name in ("proj_a", "proj.ltd", "proj.pin", "proj.prt")},
        "midpoint_selection": midpoint_selection, "tracked_actual_extrema": extrema,
        "coverage_fill": coverage_fill,
        "tracked_dense_AFS_predicted_extrema": dense_extrema, "dense_extrema_actual_neighbors": neighbors,
        "mesh_baseline_policy": "a4 independently solves every m3 frequency, including dense-predicted extrema absent from the original actual list",
        "gate_policy": "Compare complete matrices at every control point; gate application frequencies through 80 GHz separately from diagnostic frequencies above 80 GHz. Numerical thresholds are unchanged.",
        "cases": {
            "a4": {"purpose": "Independent actual solves validating the AFS-derived model", "mesh_um": 4,
                   "frequency_hz": actual_control_hz, "comparison_profile": "afs", "reference_kind": "AFS-derived", "reference_model": "dense-afs.s2p", "reference_interpolation": "linear", "reference_location": "source", "gate_split_hz": 80e9},
            "m3": {"purpose": "Refine 4 um mesh to 3 um at key points and all tracked actual/dense predicted extrema", "mesh_um": 3,
                   "frequency_hz": mesh_hz, "comparison_profile": "mesh", "reference_kind": "actual", "reference_model": "a4/raw.s2p", "reference_interpolation": "none", "reference_location": "suite", "gate_split_hz": 80e9},
            "lf4": {"purpose": "Actual low-frequency probes; no point is claimed to be a DC solve", "mesh_um": 4,
                    "frequency_hz": [frequency * 1e9 for frequency in LOW_FREQUENCY_GHZ], "comparison_profile": None},
        },
        "optional_contact_cases": {name: {"x_shift_um": shifts, "mesh_um": 4, "frequency_hz": mesh_hz,
                                         "comparison_profile": "port", "reference_kind": "actual", "reference_model": "a4/raw.s2p", "reference_interpolation": "none", "reference_location": "suite", "gate_split_hz": 80e9}
                                   for name, shifts in PORT_VARIANTS.items()},
        "contact_interpretation": "Transverse x contact shifts only; every y coordinate, layer, net, polygon and port reference mapping must remain unchanged; prove the entire shift stays on one original conductor polygon",
        "AFS_warning_markers": receipt.get("AFS_warning_markers", []),
        "status": "PLANNED_NUMERICAL_CONTROLS_NO_PHYSICAL_PASS",
        "continuous_band_qualification": "NOT ESTABLISHED by midpoint probes alone",
        "device_target_result": "NOT_DECIDED", "parent_filter_acceptance": "NOT EVALUATED",
    }
    output = Path(output).resolve()
    if output == receipt_path or output.parent == case and output.name in ("prepared-case.json", "afs-model-receipt.json"):
        raise RunError("The qualification plan must not overwrite a retained source receipt")
    _json(output, plan)
    return plan


def propose_pin_shift(input_dir: str | Path, variant: str) -> tuple[bytes, dict[str, Any]]:
    """Prove a transverse shift remains on its original conductor, in memory."""
    if variant not in PORT_VARIANTS:
        raise RunError("Unknown frozen contact sensitivity variant")
    from plot_geometry import read_export
    from validate_inputs import point_on_metal

    directory = Path(input_dir).resolve(strict=True)
    polygons, pins, ports = read_export(directory)
    if {pin.name for pin in pins} != {"P1", "P2", "P4"} or len(ports) != 2:
        raise RunError("Contact sensitivity requires exactly P1/P2 and finite-return P4")
    xml = ET.parse(directory / "proj.pin")
    shifts = PORT_VARIANTS[variant]
    evidence = []
    for pin in pins:
        if pin.name not in shifts:
            continue
        dx = shifts[pin.name]
        target_x = pin.x_um + dx
        low, high = sorted((pin.x_um, target_x))
        proof = None
        for polygon_index, polygon in enumerate(polygons):
            if polygon.layer != pin.layer:
                continue
            critical = {low, high}
            points = polygon.points_um
            for first, second in zip(points, points[1:] + points[:1]):
                if first[1] == second[1] == pin.y_um:
                    critical.update(x for x in (first[0], second[0]) if low <= x <= high)
                elif first[1] != second[1] and min(first[1], second[1]) <= pin.y_um <= max(first[1], second[1]):
                    crossing = first[0] + (pin.y_um - first[1]) * (second[0] - first[0]) / (second[1] - first[1])
                    if low <= crossing <= high:
                        critical.add(crossing)
            ordered = sorted(critical)
            probes = ordered + [(a + b) / 2 for a, b in zip(ordered, ordered[1:])]
            if all(point_on_metal(x, pin.y_um, polygon) for x in probes):
                proof = {"original_polygon_index": polygon_index, "layer": pin.layer,
                         "horizontal_partition_probes_um": sorted(set(probes)), "incidence_tolerance_um": 0.005}
                break
        if proof is None:
            raise RunError(f"Contact shift for {pin.name} is not proven to remain on one original conductor polygon")
        nodes = [node for node in xml.getroot().findall("pin") if node.findtext("name", "").strip() == pin.name]
        if len(nodes) != 1:
            raise RunError("Pin XML is ambiguous")
        coordinate = nodes[0].find("layout/shape/point/x")
        if coordinate is None or coordinate.text is None:
            raise RunError("Pin has no explicit x coordinate")
        old_x = coordinate.text
        coordinate.text = format(Decimal(old_x) + Decimal(str(dx)) * Decimal("0.000001"), "f")
        evidence.append({"pin": pin.name, "x_shift_um": dx, "before_x_m": old_x,
                         "after_x_m": coordinate.text, "unchanged_y_um": pin.y_um,
                         "same_original_conductor_proof": proof})
    buffer = io.BytesIO()
    xml.write(buffer, encoding="utf-8", xml_declaration=True)
    return buffer.getvalue(), {"variant": variant, "changes": evidence,
                               "only_x_coordinates_changed_semantically": True,
                               "signal_reference_plane_y_unchanged": True,
                               "geometry_layers_nets_and_port_mapping_unchanged": True,
                               "scope": "Transverse contact/physical-return sensitivity; no de-embedding or acceptance claim"}


def _amend_pin(case: Path, variant: str) -> None:
    content, proof = propose_pin_shift(case, variant)
    snapshot = case / "pre-contact-amendment"
    snapshot.mkdir()
    for name in ("proj.pin", "prepared-case.json"):
        shutil.copy2(case / name, snapshot / name)
    for path in (case / "proj.pin", case / "prepared-inputs" / "proj.pin"):
        path.write_bytes(content)
    receipt_path = case / "prepared-case.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["files"]["proj.pin"] = _sha(case / "proj.pin")
    receipt["contact_amendment"] = "contact-amendment.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    _json(case / "contact-amendment.json", {"schema_version": 1, "created_utc": _utc(), **proof,
                                            "original_pin": _sha(snapshot / "proj.pin"), "amended_pin": _sha(case / "proj.pin"),
                                            "original_prepared_receipt": _sha(snapshot / "prepared-case.json"),
                                            "amended_prepared_receipt": _sha(receipt_path), "original_source_modified": False})


def prepare_controls(plan_path: str | Path, outdir: str | Path, ads_root: str | Path,
                      *, native_workspace: str | Path, include_ports: bool = True,
                      threads: int = 4) -> dict[str, Any]:
    """Prepare a fresh self-contained serial suite from the retained AFS deck."""
    plan_path = Path(plan_path).resolve(strict=True)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    source = Path(plan["source_afs_case"]).resolve(strict=True)
    _verify_completion(source)
    if _sha(source / "afs-model-receipt.json") != plan["source_receipt"]:
        raise RunError("The source AFS receipt changed after frequency selection")
    for name, identity in plan["frozen_solver_input_identities"].items():
        if _sha(source / name) != identity:
            raise RunError("Source physical input changed after qualification planning")
    destination = Path(outdir).resolve()
    if destination == source or source.is_relative_to(destination) or destination.is_relative_to(source):
        raise RunError("The qualification suite must be separate from its retained source case")
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copy2(plan_path, destination / "qualification-plan.json")
    specifications = dict(plan["cases"])
    if include_ports:
        specifications.update(plan["optional_contact_cases"])
    entries = {}
    for name, specification in specifications.items():
        case = destination / name
        prepare_case(source, case, specification["mesh_um"], [f / 1e9 for f in specification["frequency_hz"]],
                     ads_root, threads, native_workspace=native_workspace)
        for physical, identity in plan["frozen_solver_input_identities"].items():
            if _sha(case / physical) != identity:
                raise RunError(f"Prepared control {name} changed the selected candidate's physical input {physical}")
        if name in PORT_VARIANTS:
            _amend_pin(case, name)
        entries[name] = {**specification, "relative_case_directory": name,
                         "prepared_receipt": _sha(case / "prepared-case.json")}
        if name in PORT_VARIANTS:
            entries[name]["contact_amendment_identity"] = _sha(case / "contact-amendment.json")
    suite = {"schema_version": 1, "created_utc": _utc(), "source_afs_case": str(source),
             "plan_identity": _sha(destination / "qualification-plan.json"), "cases": entries,
             "execution_order": list(entries), "parallel_execution": False,
             "source_input_snapshots": "Each control retains original-export and prepared-inputs",
             "status": "PREPARED_NUMERICAL_CONTROLS", "device_target_result": "NOT_DECIDED",
             "parent_filter_acceptance": "NOT EVALUATED"}
    _json(destination / "qualification-suite.json", suite)
    return suite


def _compare_bands(reference_path: Path, candidate_path: Path, specification: dict[str, Any],
                    case: Path) -> dict[str, Any]:
    """Compare all complete matrices, separating application and diagnostic gates."""
    from analyze_em import Network, read_touchstone
    from compare_networks import compare_networks

    reference, candidate = read_touchstone(reference_path), read_touchstone(candidate_path)
    split = specification["gate_split_hz"]
    results = {}
    for name, mask in (("application", candidate.frequency_hz <= split),
                       ("diagnostic", candidate.frequency_hz > split)):
        indices = [int(i) for i, included in enumerate(mask) if included]
        if not indices:
            results[name] = {"control_result": "NO_CONTROL_POINTS_IN_BAND", "required_application_gate": name == "application"}
            continue
        selected = Network(candidate.frequency_hz[mask], candidate.s[mask], candidate.reference_ohm)
        report = compare_networks(reference, selected, specification["comparison_profile"],
                                  specification["reference_interpolation"], specification["reference_kind"], "actual")
        report.update(qualification_band=name, required_application_gate=name == "application",
                      split_frequency_hz=split, candidate_indices_in_complete_raw_network=indices,
                      full_candidate_sample_count=len(candidate.frequency_hz),
                      full_raw_network_unchanged=True,
                      source_models={"reference": {"path": str(reference_path), **_sha(reference_path)},
                                     "candidate": {"path": str(candidate_path), **_sha(candidate_path)}},
                      device_target_result="NOT_DECIDED", parent_filter_acceptance="NOT EVALUATED")
        output = case / f"comparison-{name}"
        output.mkdir(exist_ok=False)
        _json(output / "comparison.json", report)
        results[name] = {"control_result": report["control_result"],
                         "required_application_gate": name == "application",
                         "report": str(output.relative_to(case) / "comparison.json")}
    return results


def execute_controls(suite_dir: str | Path, case_names: list[str] | None = None,
                      *, ads_root: str | Path | None = None,
                      native_ten_digit_realization: bool = False) -> dict[str, Any]:
    """Execute fresh controls with the original strict policy unless opted in.

    Native frequency realization is recorded before each new solve and checked
    exactly by the raw exporter. Existing attempted controls remain untouched.
    """
    if type(native_ten_digit_realization) is not bool:
        raise RunError("Native ten-digit realization requires an explicit Boolean opt-in")
    suite_dir = Path(suite_dir).resolve(strict=True)
    suite = json.loads((suite_dir / "qualification-suite.json").read_text(encoding="utf-8"))
    if _sha(suite_dir / "qualification-plan.json") != suite["plan_identity"]:
        raise RunError("The selected qualification plan has changed")
    plan = json.loads((suite_dir / "qualification-plan.json").read_text(encoding="utf-8"))
    names = case_names or suite["execution_order"]
    if len(set(names)) != len(names) or any(name not in suite["cases"] for name in names):
        raise RunError("Requested control names are unknown or duplicated")
    source = Path(suite["source_afs_case"]).resolve(strict=True)
    _verify_completion(source)
    if source != Path(plan["source_afs_case"]).resolve(strict=True) or _sha(source / "afs-model-receipt.json") != plan["source_receipt"]:
        raise RunError("The retained qualification reference has changed")
    for name, identity in plan["source_model_identities"].items():
        if Path(name).name != name or _sha(source / name) != identity:
            raise RunError("A source model changed after qualification planning")
    results = []
    for name in names:
        specification = suite["cases"][name]
        case = (suite_dir / specification["relative_case_directory"]).resolve(strict=True)
        if case.parent != suite_dir:
            raise RunError("Control directory escapes its retained suite")
        result: dict[str, Any] = {"case": name, "started_utc": _utc()}
        if (case / "execution-receipt.json").exists() or (case / "solver-console.log").exists():
            result.update(status="RETAINED_PREVIOUS_ATTEMPT_NOT_REEXECUTED", reason="Use the original retained attempt or prepare a fresh suite")
            results.append(result)
            continue
        if _sha(case / "prepared-case.json") != specification["prepared_receipt"]:
            raise RunError("A prepared control receipt changed before execution")
        if name in PORT_VARIANTS:
            amendment = json.loads((case / "contact-amendment.json").read_text(encoding="utf-8"))
            if (_sha(case / "contact-amendment.json") != specification["contact_amendment_identity"]
                    or amendment["amended_pin"] != _sha(case / "proj.pin") or amendment["amended_prepared_receipt"] != _sha(case / "prepared-case.json")):
                raise RunError("Contact sensitivity evidence changed before execution")
        try:
            if native_ten_digit_realization:
                prepared = json.loads((case / "prepared-case.json").read_text(encoding="utf-8"))
                requested = [float(value) * 1e9 for value in prepared["frequencies_GHz"]]
                canonical = [float(format(value, ".10g")) for value in requested]
                if (not requested or any(not math.isfinite(f) or f < 0 for f in requested)
                        or any(a >= b for a, b in zip(requested, requested[1:]))
                        or any(a >= b for a, b in zip(canonical, canonical[1:]))):
                    raise RunError("Requested frequencies do not have a unique increasing native ten-digit realization")
                policy_path = case / "native-frequency-realization-policy.json"
                _json(policy_path, {
                    "schema_version": 1, "created_utc": _utc(),
                    "policy": "explicit_opt_in_exact_native_ten_digit_realization",
                    "canonicalization_expression": "float(format(requested_hz, '.10g'))",
                    "requested_frequency_hz": requested,
                    "planned_native_ten_digit_canonical_frequency_hz": canonical,
                    "protected_exact_frequency_hz": [r for r, c in zip(requested, canonical) if r == c],
                    "protected_key_frequency_hz": [value for value in (65e9, 80e9) if value in requested],
                    "acceptance_rule": "Every actual frequency must exactly equal its planned native .10g value; ten-digit-representable requests and requested 65/80 GHz points must remain exact",
                    "prepared_case_receipt": _sha(case / "prepared-case.json"),
                    "requested_stimulus": _sha(case / "proj.sti"),
                    "qualification_plan": _sha(suite_dir / "qualification-plan.json"),
                    "status": "RECORDED_BEFORE_SOLVE_NOT_ACTUAL_FREQUENCY_EVIDENCE",
                    "requested_frequencies_or_stimulus_modified": False,
                    "frequency_interpolation_or_resampling": False,
                    "electrical_thresholds_modified": False,
                })
                result["pre_solve_frequency_policy"] = {"path": policy_path.name, **_sha(policy_path)}
                run_case(case, ads_root, export_model=False)
                export_dataset(case, native_ten_digit_realization=True)
            else:
                run_case(case, ads_root, export_model=True)
            result.update(status="ACTUAL_FULLWAVE_DATA_RETAINED", raw_model="raw.s2p")
            if specification["comparison_profile"] is not None:
                reference_root = suite_dir if specification["reference_location"] == "suite" else source
                bands = _compare_bands(reference_root / specification["reference_model"], case / "raw.s2p", specification, case)
                result.update(comparison_bands=bands,
                              application_numerical_control_result=bands["application"]["control_result"],
                              diagnostic_numerical_control_result=bands["diagnostic"]["control_result"],
                              diagnostic_result_does_not_replace_application_result=True)
            else:
                result.update(numerical_control_result="LOW_FREQUENCY_DATA_ONLY", dc_solver_claim=False)
        except Exception as exc:
            result.update(status="CONTROL_OR_COMPARISON_INCOMPLETE", error_type=type(exc).__name__, error=str(exc),
                          evidence="Original inputs, execution receipt, raw solver output, and any completed exports are retained")
        result["finished_utc"] = _utc()
        results.append(result)
        _json(case / "qualification-control-result.json", result)
    receipt = {"schema_version": 1, "created_utc": _utc(), "results": results,
               "parallel_execution": False, "physical_device_PASS_claimed": False,
               "native_ten_digit_realization_opt_in_for_new_solves": native_ten_digit_realization,
               "continuous_band_coverage_proven": False, "device_target_result": "NOT_DECIDED",
               "parent_filter_acceptance": "NOT EVALUATED"}
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    _json(suite_dir / f"qualification-execution-{identifier}.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="Select auditable gaps and observed extrema from a completed actual AFS source")
    plan.add_argument("afs_case_dir", type=Path)
    plan.add_argument("--output", type=Path, required=True)
    prepare = subparsers.add_parser("prepare", help="Prepare fresh actual-point, mesh, low-frequency and optional contact cases")
    prepare.add_argument("plan", type=Path)
    prepare.add_argument("outdir", type=Path)
    prepare.add_argument("--ads-root", type=Path, required=True)
    prepare.add_argument("--native-workspace", type=Path, required=True)
    prepare.add_argument("--threads", type=int, default=4)
    prepare.add_argument("--skip-ports", action="store_true")
    execute = subparsers.add_parser("execute", help="Run chosen fresh controls serially using the existing Momentum runner")
    execute.add_argument("suite_dir", type=Path)
    execute.add_argument("--case", action="append", dest="cases")
    execute.add_argument("--ads-root", type=Path)
    execute.add_argument("--native-ten-digit-realization", action="store_true",
                         help="Record the exact native .10g frequency policy before new solves and opt in to its raw export validation")
    args = parser.parse_args()
    if args.command == "plan":
        create_plan(args.afs_case_dir, args.output)
        print("Retained the actual AFS gap/extrema selection; no qualification result is claimed")
    elif args.command == "prepare":
        prepare_controls(args.plan, args.outdir, args.ads_root, native_workspace=args.native_workspace,
                         include_ports=not args.skip_ports, threads=args.threads)
        print("Prepared fresh numerical controls and source/contact amendment receipts")
    else:
        execute_controls(args.suite_dir, args.cases, ads_root=args.ads_root,
                         native_ten_digit_realization=args.native_ten_digit_realization)
        print("Retained numerical control outcomes; physical device and parent-filter acceptance remain separate")


if __name__ == "__main__":
    main()
