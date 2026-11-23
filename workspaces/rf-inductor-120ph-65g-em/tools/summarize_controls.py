"""Snapshot existing numerical-control comparisons without qualifying a device.

Example: python tools/summarize_controls.py --run-root results/ACTIVE_RUN
--output results/ACTIVE_RUN/control-summary.json [--upstream-manifest FILE]

Only comparison.json files already present at discovery are read. Every original
point, complete N-port difference matrix, reference interpolation record and
source identity is retained. Observed maxima are not continuous-band bounds.
The proposed L budget uses only 10--65 GHz observations: the sum of the maxima
for mesh, port, return, canonical, reproduction and explicit-skin, plus the
larger of 0.6 pH and the observed AFS error in the same band. It describes
numerical uncertainty, not manufacturing variation. Missing terms remain null.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any


PHYSICS_REVISION = "passive-loss-r1"
BUDGET_CATEGORIES = ("mesh", "port", "return", "canonical", "reproduction", "explicit-skin")
CATEGORIES = (*BUDGET_CATEGORIES, "AFS", "unclassified")
METRICS = ("absolute_L_difference_pH", "absolute_X_difference_ohm", "absolute_R_difference_ohm",
           "absolute_relative_Q_difference", "maximum_absolute_complete_S_difference")
DOMAINS = {
    "L_band_10_65_GHz": {"lower_hz": 10e9, "upper_hz": 65e9, "lower_inclusive": True, "upper_inclusive": True},
    "reactance_positive_through_80_GHz": {"lower_hz": 0.0, "upper_hz": 80e9, "lower_inclusive": False, "upper_inclusive": True},
    "diagnostic_above_80_GHz": {"lower_hz": 80e9, "upper_hz": None, "lower_inclusive": False, "upper_inclusive": False},
    "low_frequency_below_10_GHz": {"lower_hz": 0.0, "upper_hz": 10e9, "lower_inclusive": True, "upper_inclusive": False},
}


class SummaryError(ValueError):
    """A retained comparison cannot be faithfully summarized."""


def _finite(value: Any, label: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SummaryError(f"{label} must be a finite number")
    if nonnegative and value < 0:
        raise SummaryError(f"{label} must be nonnegative")
    return float(value)


def _optional(value: Any, label: str, *, absolute: bool = False) -> float | None:
    if value is None:
        return None
    result = _finite(value, label, nonnegative=not absolute)
    return abs(result) if absolute else result


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SummaryError(f"Duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    data = path.read_bytes()
    document = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(SummaryError(f"Nonfinite JSON constant {value}")))
    if not isinstance(document, dict):
        raise SummaryError("Expected a JSON object")
    # Also catches overflowing JSON number literals such as 1e999.
    json.dumps(document, allow_nan=False)
    return document, {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def classify(relative_path: str, profile: str) -> tuple[str, str]:
    """Classify specific perturbations before the generic numerical profile."""
    parts = tuple(part.casefold() for part in relative_path.replace("\\", "/").split("/"))
    directories = parts[:-1]
    if any("canonical" in part for part in directories):
        return "canonical", "canonical control directory"
    if any(part.startswith("repro") for part in directories):
        return "reproduction", "reproduction control directory"
    if any("skin" in part for part in directories):
        return "explicit-skin", "explicit skin comparison directory"
    if any("frame" in part for part in directories):
        return "return", "finite return-frame comparison directory"
    if "controls-r2" in directories:
        index = directories.index("controls-r2")
        case = directories[index + 1] if index + 1 < len(directories) else ""
        mapping = {"a4": "AFS", "m3": "mesh", "pplus2": "port", "pminus2": "port", "gplus10": "port"}
        if case in mapping:
            return mapping[case], f"controls-r2 case {case}"
    if "low-frequency-checks" in directories:
        index = directories.index("low-frequency-checks")
        case = directories[index + 1] if index + 1 < len(directories) else ""
        mapping = {"mesh3": "mesh", "pplus2": "port", "pminus2": "port", "gplus10": "port"}
        if case in mapping:
            return mapping[case], f"low-frequency case {case}"
    mapping = {"canonical": "canonical", "reproduction": "reproduction", "mesh": "mesh",
               "port": "port", "return": "return", "afs": "AFS"}
    return mapping.get(profile, "unclassified"), "declared control_profile fallback"


def _in_domain(frequency: float, domain: str) -> bool:
    limits = DOMAINS[domain]
    lower = frequency >= limits["lower_hz"] if limits["lower_inclusive"] else frequency > limits["lower_hz"]
    upper = limits["upper_hz"]
    return lower and (upper is None or (frequency <= upper if limits["upper_inclusive"] else frequency < upper))


def _point_metrics(point: dict[str, Any], ports: int) -> dict[str, float | None]:
    matrix = point["S"]["complete_complex_candidate_minus_reference"]
    if not isinstance(matrix, list) or len(matrix) != ports or any(not isinstance(row, list) or len(row) != ports for row in matrix):
        raise SummaryError("Every S difference must retain the complete declared N by N matrix")
    magnitudes = []
    for row in matrix:
        for entry in row:
            if not isinstance(entry, list) or len(entry) != 2:
                raise SummaryError("A complex S difference must be [real, imaginary]")
            magnitude = math.hypot(_finite(entry[0], "S real part"), _finite(entry[1], "S imaginary part"))
            magnitudes.append(_finite(magnitude, "absolute S difference", nonnegative=True))
    maximum_s = max(magnitudes)
    reported_s = _finite(point["S"]["maximum_absolute_difference"], "reported maximum S difference", nonnegative=True)
    if not math.isclose(maximum_s, reported_s, rel_tol=1e-12, abs_tol=1e-15):
        raise SummaryError("Reported S maximum disagrees with the complete difference matrix")
    return {
        "absolute_L_difference_pH": _optional(point["L_pH"].get("absolute_difference"), "absolute L difference"),
        "absolute_X_difference_ohm": _optional(point["Zd"].get("signed_imag_difference_ohm"), "signed X difference", absolute=True),
        "absolute_R_difference_ohm": _optional(point["R_ohm"].get("absolute_difference"), "absolute R difference"),
        "absolute_relative_Q_difference": _optional(point["Q"].get("absolute_relative_difference"), "relative Q difference"),
        "maximum_absolute_complete_S_difference": maximum_s,
    }


def _load_report(document: dict[str, Any], source: dict[str, Any], relative: str, revision: str) -> dict[str, Any]:
    ports = document["port_count"]
    if isinstance(ports, bool) or not isinstance(ports, int) or ports < 2 or document["reference_ohm"] != 50:
        raise SummaryError("Comparison must declare complete N >= 2 ports and real equal 50 ohm references")
    points = document["points"]
    if not isinstance(points, list) or not points:
        raise SummaryError("Comparison has no retained points")
    if document.get("complete_comparison") is not True or document.get("all_candidate_points_compared") is not True:
        raise SummaryError("Comparison must explicitly retain all candidate points")
    selection = document["selection_domain"]
    if selection.get("candidate_points_omitted") != 0 or selection.get("candidate_samples") != len(points):
        raise SummaryError("Candidate selection does not account for every retained point")
    frequencies = [_finite(point["frequency_hz"], "frequency", nonnegative=True) for point in points]
    if any(second <= first for first, second in zip(frequencies, frequencies[1:])):
        raise SummaryError("Comparison frequencies must be strictly increasing and unique")
    if selection.get("candidate_frequency_hz") != frequencies:
        raise SummaryError("Candidate selection frequencies disagree with retained points")
    category, classification = classify(relative, document.get("control_profile", ""))
    reasons = []
    if category == "unclassified":
        reasons.append("Unclassified numerical control")
    if document.get("candidate_kind") != "actual":
        reasons.append("Candidate is not explicitly an actual solve")
    if document.get("reference_kind") not in ("actual", "AFS-derived"):
        reasons.append("Reference kind is not declared actual or AFS-derived")
    expected_profile = {"AFS": "afs", "mesh": "mesh", "port": "port", "return": "return",
                        "canonical": "canonical", "reproduction": "reproduction"}.get(category)
    if expected_profile is not None and document.get("control_profile") != expected_profile:
        reasons.append("Classified control category conflicts with the declared numerical profile")
    if category == "AFS" and document.get("reference_kind") != "AFS-derived":
        reasons.append("An AFS error observation requires an explicitly AFS-derived reference")
    if category != "AFS" and document.get("reference_kind") != "actual":
        reasons.append("An AFS-derived reference is not an independent non-AFS control")
    declared = document.get("physics_revision")
    if declared is not None and declared != revision:
        reasons.append("Declared physics revision differs from the requested revision")
    if not isinstance(document.get("source_models"), dict) or not all(key in document["source_models"] for key in ("reference", "candidate")):
        reasons.append("Source model identity records are missing")
    derived = []
    for index, point in enumerate(points):
        if point.get("candidate_kind") != document.get("candidate_kind"):
            raise SummaryError("Point and report candidate kinds disagree")
        reference = point["reference_sample"]
        if not isinstance(reference.get("interpolated"), bool):
            raise SummaryError("Reference interpolation must be explicitly declared per point")
        if reference["interpolated"] and (category != "AFS" or document.get("reference_kind") != "AFS-derived"):
            reasons.append(f"Point {index} has reference interpolation outside an AFS control")
        expected_reference_kind = ("linearly interpolated AFS-derived reference" if reference["interpolated"] else "AFS-derived") if category == "AFS" else "actual"
        if reference.get("kind") != expected_reference_kind:
            reasons.append(f"Point {index} reference kind conflicts with the classified control")
        derived.append({"source_point_index": index, "frequency_hz": frequencies[index],
                        "metrics": _point_metrics(point, ports), "comparison": point})
    return {"source": source, "relative_path": relative, "category": category, "classification_basis": classification,
            "physics_revision": declared, "physics_revision_state": "UNDECLARED" if declared is None else "MATCHES_DECLARED_REVISION" if declared == revision else "MISMATCH",
            "numerical_observations_usable": not reasons, "observation_exclusion_reasons": sorted(set(reasons)),
            "provenance_review_required": True,
            "metadata": {key: value for key, value in document.items() if key != "points"}, "points": derived}


def _aggregate(observations: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"point_count": len(observations), "frequencies_hz": sorted({row["frequency_hz"] for row in observations}),
                              "comparison_state_counts": {}, "maxima": {}}
    for row in observations:
        state = row["comparison_state"]
        result["comparison_state_counts"][state] = result["comparison_state_counts"].get(state, 0) + 1
    for metric in METRICS:
        finite = [row for row in observations if row["metrics"][metric] is not None]
        witness = max(finite, key=lambda row: row["metrics"][metric]) if finite else None
        result["maxima"][metric] = {
            "status": "OBSERVED_FINITE_MAXIMUM" if witness else "NO_FINITE_OBSERVATIONS",
            "value": witness["metrics"][metric] if witness else None,
            "finite_point_count": len(finite), "undefined_point_count": len(observations) - len(finite),
            "witness": {key: witness[key] for key in ("report_index", "source_point_index", "frequency_hz")} if witness else None,
            "undefined_points": [{key: row[key] for key in ("report_index", "source_point_index", "frequency_hz")} for row in observations if row["metrics"][metric] is None],
        }
    return result


def _expected_cases(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expected = []
    for case in ("a4", "m3", "pplus2", "pminus2", "gplus10"):
        for band in ("application", "diagnostic"):
            suffix = f"qualification/controls-r2/{case}/comparison-{band}/comparison.json"
            matches = [index for index, report in enumerate(reports) if report["relative_path"].casefold() == suffix]
            expected.append({"case": suffix, "report_indices": matches, "state": "REPORT_PRESENT" if matches else "NOT_FOUND_NOT_ASSUMED_COMPLETE"})
    for case in ("mesh3", "pplus2", "pminus2", "gplus10", "frame15", "frame22"):
        prefix = f"qualification/low-frequency-checks/{case}/"
        matches = [index for index, report in enumerate(reports) if report["relative_path"].casefold().startswith(prefix)]
        expected.append({"case": prefix + "**/comparison.json", "report_indices": matches,
                         "state": "REPORT_PRESENT" if matches else "NOT_FOUND_NOT_ASSUMED_COMPLETE"})
    return expected


def summarize(run_root: str | Path, *, upstream_manifest: str | Path | None = None,
              physics_revision: str = PHYSICS_REVISION) -> dict[str, Any]:
    """Read a fixed inventory of existing reports and propose observed budgets."""
    root = Path(run_root).resolve(strict=True)
    if not root.is_dir():
        raise SummaryError("Active run root must be a directory")
    if not isinstance(physics_revision, str) or not physics_revision.strip():
        raise SummaryError("Expected physics revision must be a nonempty identifier")
    inventory = sorted(root.rglob("comparison.json"))
    reports, errors = [], []
    for path in inventory:
        relative = path.relative_to(root).as_posix()
        try:
            if not path.resolve(strict=True).is_relative_to(root):
                raise SummaryError("Comparison resolves outside the requested active run root")
            document, source = _read(path)
            reports.append(_load_report(document, source, relative, physics_revision))
        except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError) as exc:
            errors.append({"path": str(path), "relative_path": relative, "error_type": type(exc).__name__, "error": str(exc)})
    upstream = None
    if upstream_manifest is not None:
        path = Path(upstream_manifest).resolve(strict=True)
        document, source = _read(path)
        upstream = {"source": source, "manifest": document,
                    "binding_state": "RETAINED_FOR_OPERATOR_REVIEW_NOT_AUTOMATICALLY_CERTIFIED"}
    observations = []
    for report_index, report in enumerate(reports):
        for point in report["points"]:
            observations.append({"report_index": report_index, "source_point_index": point["source_point_index"],
                                 "frequency_hz": point["frequency_hz"], "category": report["category"],
                                 "usable": report["numerical_observations_usable"], "metrics": point["metrics"],
                                 "comparison_state": point["comparison"].get("comparison_state", "UNDECLARED")})
    categories = {}
    for category in CATEGORIES:
        rows = [row for row in observations if row["category"] == category]
        categories[category] = {"report_indices": [index for index, report in enumerate(reports) if report["category"] == category],
                                "domains": {domain: {"all_reported": _aggregate([row for row in rows if _in_domain(row["frequency_hz"], domain)]),
                                                       "usable_numerical_observations": _aggregate([row for row in rows if row["usable"] and _in_domain(row["frequency_hz"], domain)])}
                                            for domain in DOMAINS}}
    def l_term(category: str) -> dict[str, Any]:
        return categories[category]["domains"]["L_band_10_65_GHz"]["usable_numerical_observations"]["maxima"]["absolute_L_difference_pH"]
    terms = {category: l_term(category) for category in BUDGET_CATEGORIES}
    missing = [category for category, term in terms.items() if term["value"] is None]
    undefined = [category for category in (*BUDGET_CATEGORIES, "AFS") if l_term(category)["undefined_point_count"]]
    observed_afs = l_term("AFS")
    reserve = max(0.6, observed_afs["value"]) if observed_afs["value"] is not None else 0.6
    term_count = sum(term["value"] is not None for term in terms.values())
    partial_sum = math.fsum(term["value"] for term in terms.values() if term["value"] is not None) if term_count else None
    proposed = math.fsum([partial_sum, reserve]) if not missing and not undefined and observed_afs["value"] is not None else None
    application_issues = [{key: row[key] for key in ("report_index", "source_point_index", "frequency_hz", "comparison_state")}
                          for row in observations if row["frequency_hz"] <= 80e9 and row["comparison_state"] not in ("PASS", "REPORT_ONLY")]
    expected_cases = _expected_cases(reports)
    blockers: list[dict[str, Any]] = [{"kind": "INDEPENDENT_APPLICABILITY_REVIEW_REQUIRED",
                                     "reason": "Observed maxima do not certify continuous coverage, source physics or the applicability of perturbation magnitudes"}]
    if errors:
        blockers.append({"kind": "REPORT_INGESTION_ERRORS", "count": len(errors)})
    if missing or observed_afs["value"] is None:
        blockers.append({"kind": "MISSING_BUDGET_CATEGORIES", "categories": missing + (["AFS"] if observed_afs["value"] is None else [])})
    if undefined:
        blockers.append({"kind": "UNDEFINED_L_OBSERVATIONS", "categories": undefined})
    if application_issues:
        blockers.append({"kind": "APPLICATION_CONTROL_ISSUES", "points": application_issues})
    unbound = [index for index, report in enumerate(reports) if report["physics_revision_state"] != "MATCHES_DECLARED_REVISION"]
    if unbound:
        blockers.append({"kind": "PHYSICS_REVISION_REQUIRES_UPSTREAM_REVIEW", "report_indices": unbound})
    missing_cases = [case["case"] for case in expected_cases if not case["report_indices"]]
    if missing_cases:
        blockers.append({"kind": "EXPECTED_REPORTS_NOT_FOUND", "cases": missing_cases,
                         "reason": "Absence is not assumed complete or assumed to mean that a diagnostic band has no points"})
    summary = {
        "schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(), "active_run_root": str(root),
        "requested_physics_revision": physics_revision,
        "scope": "Observed numerical controls only; no continuous-band, device, manufacturing, foundry or parent-filter acceptance is established",
        "device_target_result": "NOT_EVALUATED", "continuous_band_coverage": "NOT_ESTABLISHED_BY_THIS_SUMMARY",
        "inventory_policy": "Snapshot of existing comparison.json files discovered recursively; no solver, fitting or interpolation is performed",
        "discovered_report_count": len(inventory), "retained_report_count": len(reports), "ingestion_errors": errors,
        "domain_definitions": DOMAINS, "reports": reports, "categories": categories,
        "expected_control_reports": expected_cases, "upstream_manifest": upstream,
        "provenance_gaps": [{"report_index": index, "physics_revision_state": report["physics_revision_state"],
                              "source_models_present": isinstance(report["metadata"].get("source_models"), dict)}
                             for index, report in enumerate(reports) if report["physics_revision_state"] != "MATCHES_DECLARED_REVISION"],
        "application_control_issues": application_issues,
        "L_budget_proposal": {
            "status": "OBSERVED_NUMERICAL_PROPOSAL_REQUIRES_COVERAGE_AND_PROVENANCE_REVIEW" if proposed is not None else "INCOMPLETE_OBSERVED_NUMERICAL_TERMS",
            "ready_for_qualification": False, "adoption_blockers": blockers,
            "frequency_domain": "10 GHz <= f <= 65 GHz; no 80 GHz or higher-frequency L maximum enters this scalar budget",
            "interpretation": "Conservative sum of observed numerical differences, not manufacturing variation or a certified continuous bound",
            "class_aggregation": "maximum within each class, then sum classes; duplicate reports do not add a second term",
            "category_terms_pH": terms, "missing_categories": missing, "categories_with_undefined_L": undefined,
            "observed_AFS_error_pH": observed_afs, "AFS_floor_pH": 0.6, "AFS_reserve_pH": reserve,
            "AFS_evidence_state": "OBSERVED" if observed_afs["value"] is not None else "MISSING_NOT_REPLACED_BY_FLOOR",
            "observed_non_AFS_term_count": term_count, "observed_non_AFS_partial_sum_pH": partial_sum, "proposed_L_absolute_pH": proposed,
            "qualification_adoption": "REQUIRES_OPERATOR_EVIDENCE_AND_PROTOCOL_CHECKS; never copied as device PASS",
        },
    }
    json.dumps(summary, allow_nan=False)
    return summary


def write_summary(run_root: str | Path, output: str | Path, **kwargs: Any) -> dict[str, Any]:
    """Write a fresh snapshot; never overwrite an existing receipt or report."""
    destination = Path(output).resolve()
    if destination.exists():
        raise FileExistsError("Use a fresh summary JSON path")
    if destination.name.casefold() == "comparison.json":
        raise SummaryError("A summary must not be named comparison.json")
    report = summarize(run_root, **kwargs)
    serialized = json.dumps(report, indent=2, allow_nan=False) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(serialized)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="Fresh JSON path; existing files are never overwritten")
    parser.add_argument("--upstream-manifest", type=Path, help="Retain the explicit upstream provenance chain for operator review")
    parser.add_argument("--physics-revision", default=PHYSICS_REVISION)
    args = parser.parse_args()
    try:
        report = write_summary(args.run_root, args.output, upstream_manifest=args.upstream_manifest, physics_revision=args.physics_revision)
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        parser.error(str(exc))
    print(f"Retained {report['retained_report_count']} numerical-control reports; {report['L_budget_proposal']['status']}; device not evaluated")


if __name__ == "__main__":
    main()
