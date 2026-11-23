"""Deterministic E8 local sampling with retained nonmonotonic windows.

``next_request(root)`` updates requests.json before returning a new request.
The runner must evaluate that request's canonical case and call again. Every
call writes boundary-search.json, including missing evidence and completion.
Only adjacent retained nodes are split; no monotonic or global-bound claim is
made. After valid PASS/FAIL brackets, the declared literal *signed* electrical
margin orders intervals (most negative endpoint minimum first).
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from typing import Any

try:
    from . import cases, model
except ImportError:
    import cases
    import model

AXES = ("q", "f_l0_hz", "esr_ohm", "esl_h")
MAX_ADDITIONAL_PER_SLICE = 5
METRIC_NAMES = ("s11_worst", "s22_worst", "il_worst", "s21_80")
POLICY = ("Split adjacent valid PASS/FAIL intervals first; then smallest signed endpoint electrical margin "
          "in dB (most negative first), not smallest absolute threshold distance; retain all observed windows")


def _read(path: Path, default=None):
    if not path.is_file():
        return default
    def reject_constant(value):
        raise ValueError(f"Nonfinite JSON constant: {value}")
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream, parse_constant=reject_constant)


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8", newline="\n")
    for attempt in range(6):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            # Windows indexers/scanners can briefly hold a just-written target.
            # Preserve atomic replacement and the staged bytes on final failure.
            if attempt == 5:
                raise
            time.sleep(.05*2**attempt)


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _metric_margin(name: str, metric: dict) -> tuple[float | None, str]:
    if _finite(metric.get("signed_margin_db")):
        return float(metric["signed_margin_db"]), "finite"
    if metric.get("magnitude") == 0:
        return (None, "negative_infinity") if name == "il_worst" else (None, "positive_infinity")
    return None, "unavailable"


def _score(margin: float | None, status: str) -> float:
    return float(margin) if margin is not None else -math.inf if status == "negative_infinity" else math.inf


def _node(root: Path, row: dict) -> dict:
    directory = root/"cases"/row["case_id"]
    problems = []
    try:
        summary = _read(directory/"summary.json", {})
        manifest = _read(directory/"manifest.json")
        if not isinstance(summary, dict) or (manifest is not None and not isinstance(manifest, dict)):
            raise ValueError("Summary and manifest must be JSON objects")
        if manifest is None:
            problems.append("Missing retained resolved manifest")
        else:
            model.validate(manifest)
            if model.physical_hash(manifest) != row["physical_sha256"]:
                problems.append("Retained physical coefficients conflict with request")
            declared = model.resolve(**dict(cases.E8_REFERENCE, **{row["labels"]["axis"]: row["labels"]["coordinate"]}))
            if model.physical_hash(manifest) != model.physical_hash(declared):
                problems.append("Retained coefficients conflict with declared E8 slice coordinate")
    except (ValueError, OSError, TypeError, KeyError) as exc:
        summary, manifest = {}, None
        problems.append(f"Unreadable or invalid evidence: {exc}")
    state = summary.get("state", "MISSING")
    metrics = summary.get("metrics", {})
    margins = []
    for name in METRIC_NAMES:
        metric = metrics.get(name, {})
        margin, status = _metric_margin(name, metric)
        if status != "unavailable":
            margins.append((_score(margin, status), name, margin, status))
        if metric.get("state") not in ("PASS", "FAIL"):
            problems.append(f"Unresolved metric: {name}")
    if state not in ("PASS", "FAIL"):
        problems.append(f"Unresolved candidate state: {state}")
    if not summary.get("physics", {}).get("ok"):
        problems.append("Independent physical checks missing or failed")
    if not summary.get("coverage", {}).get("continuous_band_justified"):
        problems.append("Continuous-band numerical coverage unresolved")
    limiting = min(margins) if margins else None
    return {"request_id": row["request_id"], "case_id": row["case_id"],
            "coordinate": row["labels"]["coordinate"], "state": state,
            "valid_completed": not problems, "issues": problems,
            "adaptive": bool(row["labels"].get("adaptive")),
            "manifest": manifest, "metrics": metrics,
            "limiting_metric": limiting[1] if limiting else None,
            "limiting_signed_margin_db": limiting[2] if limiting else None,
            "limiting_margin_status": limiting[3] if limiting else "unavailable",
            "limiting_uncertainty_magnitude": metrics.get(limiting[1], {}).get("uncertainty_magnitude") if limiting else None,
            "inductor_diagnostics": [model.device_diagnostics(e) for e in (manifest or {}).get("elements", []) if e["kind"] == "L"]}


def _midpoint(axis: str, left: float, right: float) -> float:
    return math.sqrt(left*right) if axis in ("q", "f_l0_hz") else left+(right-left)/2


def _interval(axis: str, left: dict, right: dict) -> dict:
    bracket = bool(left["valid_completed"] and right["valid_completed"] and {left["state"], right["state"]} == {"PASS", "FAIL"})
    score = min(_score(left["limiting_signed_margin_db"], left["limiting_margin_status"]),
                _score(right["limiting_signed_margin_db"], right["limiting_margin_status"]))
    midpoint = _midpoint(axis, left["coordinate"], right["coordinate"])
    result = {"lower_coordinate": left["coordinate"], "upper_coordinate": right["coordinate"],
              "width": right["coordinate"]-left["coordinate"], "midpoint": midpoint,
              "midpoint_method": "geometric" if axis in ("q", "f_l0_hz") else "arithmetic",
              "left_request_id": left["request_id"], "right_request_id": right["request_id"],
              "left_case_id": left["case_id"], "right_case_id": right["case_id"],
              "left_state": left["state"], "right_state": right["state"],
              "valid_adjacent_pass_fail_bracket": bracket,
              "endpoints_valid": left["valid_completed"] and right["valid_completed"],
              "left_manifest": left["manifest"], "right_manifest": right["manifest"],
              "limiting_metrics": {"left": left["limiting_metric"], "right": right["limiting_metric"]},
              "endpoint_signed_margins_db": {"left": left["limiting_signed_margin_db"], "right": right["limiting_signed_margin_db"]},
              "endpoint_margin_status": {"left": left["limiting_margin_status"], "right": right["limiting_margin_status"]},
              "endpoint_numerical_uncertainty_magnitude": {"left": {key: value.get("uncertainty_magnitude") for key, value in left["metrics"].items()},
                                                          "right": {key: value.get("uncertainty_magnitude") for key, value in right["metrics"].items()}},
              "selection_signed_margin_db": score if math.isfinite(score) else None,
              "selection_margin_status": "finite" if math.isfinite(score) else "negative_infinity" if score < 0 else "unavailable",
              "interior_status": "UNSEARCHED; only retained endpoint states established"}
    if axis == "f_l0_hz" and left["manifest"] and right["manifest"]:
        before = {e["name"]: e["cp_f"] for e in left["manifest"]["elements"] if e["kind"] == "L"}
        after = {e["name"]: e["cp_f"] for e in right["manifest"]["elements"] if e["kind"] == "L"}
        result["cp_intervals_f"] = {name: sorted([before[name], after[name]]) for name in before}
    return result


def summarize(root: str | Path, mapping=None) -> dict[str, Any]:
    """Write the current E8 evidence accounting; does not schedule a case."""
    root = Path(root)
    mapping = _read(root/"requests.json", []) if mapping is None else mapping
    rows = mapping.get("requests", []) if isinstance(mapping, dict) else mapping
    if not isinstance(rows, list):
        raise ValueError("requests.json must contain a request list")
    expected = {axis: {row["request_id"] for row in cases.requests()
                       if row["family"] == "E8" and row["labels"]["axis"] == axis} for axis in AXES}
    slices = {}
    for axis in AXES:
        selected = [row for row in rows if row.get("family") == "E8" and row.get("labels", {}).get("axis") == axis]
        selected.sort(key=lambda row: row["labels"]["coordinate"])
        nodes = [_node(root, row) for row in selected]
        intervals = [_interval(axis, left, right) for left, right in zip(nodes[:-1], nodes[1:])]
        adaptive_count = sum(node["adaptive"] for node in nodes)
        seed_count = sum(not node["adaptive"] for node in nodes)
        seed_ids = {node["request_id"] for node in nodes if not node["adaptive"]}
        candidates = [interval for interval in intervals if interval["endpoints_valid"]
                      and interval["lower_coordinate"] < interval["midpoint"] < interval["upper_coordinate"]]
        resolved = len(nodes) >= 5 and seed_count == 5 and seed_ids == expected[axis] and all(node["valid_completed"] for node in nodes)
        budget_done = adaptive_count >= MAX_ADDITIONAL_PER_SLICE
        no_interval_possible = resolved and not candidates
        states = {node["state"] for node in nodes if node["valid_completed"]}
        brackets = [interval for interval in intervals if interval["valid_adjacent_pass_fail_bracket"]]
        if not resolved:
            outcome = "INCOMPLETE: mandatory node evidence unresolved"
        elif brackets:
            outcome = "Retained adjacent PASS/FAIL brackets; all observed windows preserved"
        elif "PASS" not in states:
            outcome = "No feasible sample in this slice"
        elif states == {"PASS"}:
            outcome = "All retained samples pass; no outer limit established"
        else:
            outcome = "No valid adjacent PASS/FAIL bracket"
        slices[axis] = {"seed_count": seed_count, "adaptive_count": adaptive_count,
                        "missing_seed_request_ids": sorted(expected[axis]-seed_ids),
                        "unexpected_seed_request_ids": sorted(seed_ids-expected[axis]),
                        "adaptive_budget": MAX_ADDITIONAL_PER_SLICE,
                        "nodes": nodes, "intervals": intervals, "brackets": brackets,
                        "valid_nodes_resolved": resolved, "budget_exhausted": budget_done,
                        "no_interval_possible": no_interval_possible,
                        "complete": bool(resolved and (budget_done or no_interval_possible)),
                        "outcome": outcome,
                        "budget_unsearched_intervals": intervals if budget_done else [],
                        "scope": "Conditional sampled local intervals; no monotonicity or global threshold claim"}
    report = {"experiment": "E8", "policy": POLICY, "reference_coordinates": dict(cases.E8_REFERENCE),
              "complete": all(value["complete"] for value in slices.values()),
              "seed_requests_required": 20, "additional_requests_maximum": 20,
              "additional_requests_retained": sum(value["adaptive_count"] for value in slices.values()),
              "slices": slices,
              "scope": "Synthetic fixed-coefficient circuit samples; full-filter electrical results decide feasibility"}
    _write(root/"boundary-search.json", report)
    return report


def next_request(root: str | Path) -> dict[str, Any] | None:
    """Persist and return one adaptive request, or None when no request is ready.

    None does not itself mean completion: inspect boundary-search.json.complete.
    Missing, invalid or indeterminate node evidence must be repaired by the
    runner; it cannot be treated as an electrically failing endpoint.
    """
    root = Path(root)
    mapping = _read(root/"requests.json", [])
    rows = mapping.get("requests", []) if isinstance(mapping, dict) else mapping
    if not isinstance(rows, list):
        raise ValueError("requests.json must contain a request list")
    report = summarize(root, mapping)
    for axis in AXES:
        data = report["slices"][axis]
        if data["complete"] or not data["valid_nodes_resolved"] or data["adaptive_count"] >= MAX_ADDITIONAL_PER_SLICE:
            continue
        candidates = [interval for interval in data["intervals"] if interval["endpoints_valid"]
                      and interval["lower_coordinate"] < interval["midpoint"] < interval["upper_coordinate"]]
        if not candidates:
            continue
        def priority(interval):
            return (0 if interval["valid_adjacent_pass_fail_bracket"] else 1,
                    _score(interval["selection_signed_margin_db"], interval["selection_margin_status"]),
                    interval["lower_coordinate"])
        chosen = min(candidates, key=priority)
        coordinate = chosen["midpoint"]
        coordinates = dict(cases.E8_REFERENCE, **{axis: coordinate})
        manifest = model.resolve(**coordinates)
        digest = model.physical_hash(manifest)
        request_id = f"e8-{axis}-adaptive{data['adaptive_count']+1:02d}"
        if any(row["request_id"] == request_id for row in rows):
            raise ValueError(f"Adaptive request ID conflict: {request_id}")
        canonical = next((row["case_id"] for row in rows if row.get("physical_sha256") == digest), request_id)
        row = {"request_id": request_id, "case_id": canonical, "family": "E8", "physical_sha256": digest,
               "manifest": manifest, "labels": {"axis": axis, "coordinate": coordinate, **coordinates,
                    "seed": False, "adaptive": True,
                    "refinement": chosen["midpoint_method"], "selection_policy": POLICY,
                    "parent_left_request_id": chosen["left_request_id"], "parent_right_request_id": chosen["right_request_id"],
                    "priority_pass_fail_bracket": chosen["valid_adjacent_pass_fail_bracket"],
                    "selection_signed_margin_db": chosen["selection_signed_margin_db"],
                    "selection_margin_status": chosen["selection_margin_status"]},
               "research_metadata": dict(cases.SYNTHETIC_METADATA),
               "scheduled_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        rows.append(copy.deepcopy(row))
        # Commit the request before the simulator is invoked by the caller.
        _write(root/"requests.json", mapping)
        summarize(root, mapping)
        return row
    return None
