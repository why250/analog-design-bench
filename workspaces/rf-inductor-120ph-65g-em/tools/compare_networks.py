"""Compare complete N-port numerical controls without changing either model.

All candidate frequencies must be compared. By default the reference must have
the exact same parsed-Hz points. Explicit linear reference interpolation is
allowed only when --reference-kind AFS-derived is declared; complex S entries
are interpolated before metric extraction. Every bracket and weight is retained,
and extrapolation is forbidden. The result never calls an interpolated point an
actual solve. No fitting, renormalization or passivity repair is performed.

Profiles use frozen inclusive numerical limits: canonical/afs: max|dS| 1e-4,
relative L .002, relative Q .01; reproduction: max|dS| 1e-5, relative L .002,
Q report only; mesh: relative L .02, relative Q .05, S report only. Port/return
profiles report changes without inventing acceptance limits. Relative changes
use the absolute reference value as denominator. A zero or undefined reference
has a typed undefined relative change, not an artificial denominator floor.
L/Q comparisons at exactly DC are not applicable; finite S/R/Z still remain.
These are numerical-control conclusions, not device or full-filter acceptance.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from analyze_em import Network, point_metrics, read_touchstone


PROFILES = {
    "canonical": {"maximum_absolute_S": 1e-4, "relative_L": 0.002, "relative_Q": 0.01},
    "afs": {"maximum_absolute_S": 1e-4, "relative_L": 0.002, "relative_Q": 0.01},
    "reproduction": {"maximum_absolute_S": 1e-5, "relative_L": 0.002, "relative_Q": None},
    "mesh": {"maximum_absolute_S": None, "relative_L": 0.02, "relative_Q": 0.05},
    "port": {"maximum_absolute_S": None, "relative_L": None, "relative_Q": None},
    "return": {"maximum_absolute_S": None, "relative_L": None, "relative_Q": None},
}


class ComparisonError(ValueError):
    """The requested control cannot compare all candidate points faithfully."""


def _kind(value: str) -> str:
    kinds = {"actual": "actual", "afs-derived": "AFS-derived"}
    if value.casefold() not in kinds:
        raise ComparisonError("Model kind must be actual or AFS-derived")
    return kinds[value.casefold()]


def _record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _validate(network: Network) -> None:
    if network.reference_ohm != 50:
        raise ComparisonError("Every complete N-port must use real equal 50 ohm references")
    if (network.s.ndim != 3 or network.s.shape[1] < 2 or network.s.shape[1] != network.s.shape[2]
            or network.frequency_hz.ndim != 1 or len(network.s) != len(network.frequency_hz)
            or not len(network.frequency_hz) or not np.all(np.isfinite(network.s))
            or not np.all(np.isfinite(network.frequency_hz)) or np.any(network.frequency_hz < 0)
            or np.any(np.diff(network.frequency_hz) <= 0)):
        raise ComparisonError("Networks need complete finite matrices and unique increasing nonnegative frequencies")


def _reference_sample(reference: Network, frequency: float, interpolation: str,
                      kind: str) -> tuple[np.ndarray, dict[str, Any]]:
    position = int(np.searchsorted(reference.frequency_hz, frequency))
    if position < len(reference.frequency_hz) and float(reference.frequency_hz[position]) == frequency:
        return reference.s[position], {"kind": kind, "interpolated": False, "source_indices": [position],
                                       "source_frequencies_hz": [frequency], "weights": [1.0]}
    if interpolation != "linear":
        raise ComparisonError(f"Reference lacks exact candidate frequency {frequency:.17g} Hz; comparison is incomplete")
    if kind != "AFS-derived":
        raise ComparisonError("Reference interpolation is permitted only for an explicitly AFS-derived reference")
    if position == 0 or position == len(reference.frequency_hz):
        raise ComparisonError(f"Reference interpolation would extrapolate at {frequency:.17g} Hz")
    low, high = position - 1, position
    first, second = float(reference.frequency_hz[low]), float(reference.frequency_hz[high])
    weight_high = (frequency - first) / (second - first)
    weight_low = 1 - weight_high
    matrix = weight_low * reference.s[low] + weight_high * reference.s[high]
    return matrix, {"kind": "linearly interpolated AFS-derived reference", "interpolated": True,
                    "source_indices": [low, high], "source_frequencies_hz": [first, second],
                    "weights": [weight_low, weight_high], "method": "linear interpolation of every complete complex S entry"}


def _difference(reference: float | None, candidate: float | None) -> dict[str, Any]:
    result: dict[str, Any] = {"reference": reference, "candidate": candidate}
    if reference is None or candidate is None:
        result.update(status="UNDEFINED_DERIVED_VALUE", signed_difference=None, absolute_difference=None,
                      absolute_relative_difference=None, relative_status="UNDEFINED_DERIVED_VALUE")
        return result
    delta = candidate - reference
    if not math.isfinite(delta):
        result.update(status="NONFINITE_NUMERIC_DIFFERENCE", signed_difference=None, absolute_difference=None,
                      absolute_relative_difference=None, relative_status="NUMERIC_OVERFLOW")
        return result
    relative = abs(delta) / abs(reference) if reference != 0 else None
    if relative is not None and not math.isfinite(relative):
        relative = None
    result.update(status="FINITE", signed_difference=float(delta), absolute_difference=float(abs(delta)),
                  absolute_relative_difference=float(relative) if relative is not None else None,
                  relative_status="FINITE" if relative is not None else "ZERO_REFERENCE_LIMIT" if reference == 0 else "NUMERIC_OVERFLOW")
    return result


def _threshold(value: float | None, limit: float | None, *, applicable: bool = True,
               numerically_usable: bool = True) -> dict[str, Any]:
    if not applicable:
        return {"state": "NOT_APPLICABLE_AT_DC", "value": value, "inclusive_limit": limit, "signed_margin": None}
    if limit is None:
        return {"state": "REPORT_ONLY", "value": value, "inclusive_limit": None, "signed_margin": None}
    if value is None or not numerically_usable:
        return {"state": "INDETERMINATE", "value": value, "inclusive_limit": limit, "signed_margin": None,
                "reason": "Undefined relative metric or ill-conditioned constrained extraction"}
    return {"state": "PASS" if value <= limit else "FAIL", "value": value,
            "inclusive_limit": limit, "signed_margin": float(limit - value)}


def _state(states: list[str]) -> str:
    if "FAIL" in states:
        return "FAIL"
    if "INDETERMINATE" in states:
        return "INDETERMINATE"
    if "PASS" in states:
        return "PASS"
    return "REPORT_ONLY"


def _maximum(rows: list[dict[str, Any]], field: str, metric: str) -> dict[str, Any]:
    finite = [(row["frequency_hz"], row[field][metric]) for row in rows if row[field][metric] is not None]
    if not finite:
        return {"status": "NO_FINITE_COMPARISONS", "value": None, "frequency_hz": None}
    frequency, value = max(finite, key=lambda pair: pair[1])
    return {"status": "FINITE", "value": value, "frequency_hz": frequency}


def compare_networks(reference: Network, candidate: Network, profile: str,
                     reference_interpolation: str = "none", reference_kind: str = "actual",
                     candidate_kind: str = "actual") -> dict[str, Any]:
    """Compare every candidate sample; reject missing points or N-port mismatch."""
    _validate(reference)
    _validate(candidate)
    if candidate.port_count != reference.port_count:
        raise ComparisonError("Complete port counts differ; no truncation or unexplained reduction is allowed")
    if profile not in PROFILES:
        raise ComparisonError(f"Unknown numerical-control profile {profile!r}")
    reference_kind, candidate_kind = _kind(reference_kind), _kind(candidate_kind)
    if reference_interpolation not in ("none", "linear"):
        raise ComparisonError("Reference interpolation must be none or linear")
    if reference_interpolation == "linear" and reference_kind != "AFS-derived":
        raise ComparisonError("Explicit linear reference interpolation requires kind AFS-derived")
    limits = PROFILES[profile].copy()
    rows = []
    for frequency, candidate_s in zip(candidate.frequency_hz, candidate.s, strict=True):
        frequency = float(frequency)
        reference_s, provenance = _reference_sample(reference, frequency, reference_interpolation, reference_kind)
        reference_metrics = point_metrics(frequency, reference_s, 50)
        candidate_metrics = point_metrics(frequency, candidate_s, 50)
        rd, cd = reference_metrics["differential"], candidate_metrics["differential"]
        delta_s = candidate_s - reference_s
        maximum_s = float(np.max(np.abs(delta_s)))
        if not math.isfinite(maximum_s):
            raise ComparisonError("The finite input matrices produce a nonfinite numeric S difference")
        l = _difference(rd["L_h"] * 1e12 if rd["L_h"] is not None else None,
                        cd["L_h"] * 1e12 if cd["L_h"] is not None else None)
        r = _difference(rd["R_ohm"], cd["R_ohm"])
        q = _difference(rd["Q"]["value"], cd["Q"]["value"])
        q.update(reference_Q_status=rd["Q"]["status"], candidate_Q_status=cd["Q"]["status"])
        if rd["impedance"] is not None and cd["impedance"] is not None:
            dz_real = cd["impedance"]["real_ohm"] - rd["impedance"]["real_ohm"]
            dz_imag = cd["impedance"]["imag_ohm"] - rd["impedance"]["imag_ohm"]
            magnitude = math.hypot(dz_real, dz_imag)
            z = {"status": "FINITE", "signed_real_difference_ohm": float(dz_real),
                 "signed_imag_difference_ohm": float(dz_imag), "absolute_difference_ohm": magnitude} if math.isfinite(magnitude) else {
                     "status": "NONFINITE_NUMERIC_DIFFERENCE", "signed_real_difference_ohm": None,
                     "signed_imag_difference_ohm": None, "absolute_difference_ohm": None}
        else:
            z = {"status": "UNDEFINED_IMPEDANCE_LIMIT", "signed_real_difference_ohm": None,
                 "signed_imag_difference_ohm": None, "absolute_difference_ohm": None}
        usable = not (reference_metrics["differential_solver"].get("ill_conditioned") or candidate_metrics["differential_solver"].get("ill_conditioned"))
        checks = {"maximum_absolute_S": _threshold(maximum_s, limits["maximum_absolute_S"]),
                  "relative_L": _threshold(l["absolute_relative_difference"], limits["relative_L"], applicable=frequency > 0, numerically_usable=usable),
                  "relative_Q": _threshold(q["absolute_relative_difference"], limits["relative_Q"], applicable=frequency > 0, numerically_usable=usable)}
        rows.append({"frequency_hz": frequency, "candidate_kind": candidate_kind, "reference_sample": provenance,
                     "comparison_state": _state([item["state"] for item in checks.values()]), "checks": checks,
                     "S": {"maximum_absolute_difference": maximum_s,
                           "complete_complex_candidate_minus_reference": [[[float(v.real), float(v.imag)] for v in row] for row in delta_s]},
                     "L_pH": l, "R_ohm": r, "Q": q, "Zd": z,
                     "reference_metrics": reference_metrics, "candidate_metrics": candidate_metrics})
    report = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
              "control_profile": profile, "inclusive_limits": limits,
              "control_result": _state([row["comparison_state"] for row in rows]),
              "complete_comparison": True, "all_candidate_points_compared": True,
              "port_count": candidate.port_count, "reference_ohm": 50.0,
              "selection_domain": {"candidate_samples": len(rows), "candidate_frequency_hz": list(map(float, candidate.frequency_hz)),
                                   "candidate_range_hz": [float(candidate.frequency_hz[0]), float(candidate.frequency_hz[-1])],
                                   "reference_samples": len(reference.frequency_hz),
                                   "reference_range_hz": [float(reference.frequency_hz[0]), float(reference.frequency_hz[-1])],
                                   "candidate_points_omitted": 0},
              "reference_kind": reference_kind, "candidate_kind": candidate_kind,
              "kind_assignment": "Caller-supplied and retained; does not certify the original solver/AFS provenance",
              "reference_interpolation_permission": reference_interpolation,
              "reference_interpolation_performed": any(row["reference_sample"]["interpolated"] for row in rows),
              "interpolated_reference_is_actual_solve": False,
              "fitting": False, "renormalization": False, "passivity_repair": False,
              "physical_identity_assumption": "Caller verifies ordered physical ports, reference planes, geometry and material identities from source receipts",
              "conclusion_scope": "Numerical control only; device targets and parent-filter acceptance are separate",
              "maxima": {"absolute_S_difference": {"value": max(row["S"]["maximum_absolute_difference"] for row in rows),
                                                     "frequency_hz": max(rows, key=lambda row: row["S"]["maximum_absolute_difference"])["frequency_hz"]},
                         "absolute_L_difference_pH": _maximum(rows, "L_pH", "absolute_difference"),
                         "relative_L_difference": _maximum(rows, "L_pH", "absolute_relative_difference"),
                         "absolute_R_difference_ohm": _maximum(rows, "R_ohm", "absolute_difference"),
                         "absolute_Q_difference": _maximum(rows, "Q", "absolute_difference"),
                         "relative_Q_difference": _maximum(rows, "Q", "absolute_relative_difference"),
                         "absolute_Zd_difference_ohm": _maximum(rows, "Zd", "absolute_difference_ohm")},
              "points": rows}
    json.dumps(report, allow_nan=False)
    return report


def compare_files(reference_path: str | Path, candidate_path: str | Path, profile: str,
                  output_dir: str | Path, *, reference_interpolation: str = "none",
                  reference_kind: str = "actual", candidate_kind: str = "actual", csv_output: bool = False,
                  physics_revision: str | None = None) -> dict[str, Any]:
    reference_path, candidate_path = Path(reference_path).resolve(strict=True), Path(candidate_path).resolve(strict=True)
    output = Path(output_dir).resolve()
    if output.exists():
        raise FileExistsError("Use a fresh comparison output directory")
    snapshots = {"reference": _record(reference_path), "candidate": _record(candidate_path)}
    report = compare_networks(read_touchstone(reference_path), read_touchstone(candidate_path), profile,
                              reference_interpolation, reference_kind, candidate_kind)
    if physics_revision is not None and (not isinstance(physics_revision, str) or not physics_revision.strip()):
        raise ComparisonError("Physics revision must be a nonempty declared identifier")
    report["physics_revision"] = physics_revision
    report["physics_revision_assignment"] = "Caller-declared; numerical agreement does not establish physical validity of either input"
    if _record(reference_path) != snapshots["reference"] or _record(candidate_path) != snapshots["candidate"]:
        raise ComparisonError("A source model changed during comparison")
    report["source_models"] = snapshots
    serialized = json.dumps(report, indent=2, allow_nan=False) + "\n"
    output.mkdir(parents=True, exist_ok=False)
    (output / "comparison.json").write_text(serialized, encoding="utf-8")
    if csv_output:
        with (output / "comparison.csv").open("x", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["frequency_hz", "comparison_state", "candidate_kind", "reference_kind", "reference_interpolated",
                             "maximum_absolute_dS", "S_margin", "reference_L_pH", "candidate_L_pH", "signed_dL_pH", "absolute_relative_dL", "L_margin",
                             "reference_R_ohm", "candidate_R_ohm", "signed_dR_ohm", "reference_Q_status", "candidate_Q_status",
                             "reference_Q", "candidate_Q", "signed_dQ", "absolute_relative_dQ", "Q_margin", "absolute_dZd_ohm"])
            for row in report["points"]:
                writer.writerow([row["frequency_hz"], row["comparison_state"], row["candidate_kind"], row["reference_sample"]["kind"], row["reference_sample"]["interpolated"],
                                 row["S"]["maximum_absolute_difference"], row["checks"]["maximum_absolute_S"]["signed_margin"],
                                 row["L_pH"]["reference"], row["L_pH"]["candidate"], row["L_pH"]["signed_difference"], row["L_pH"]["absolute_relative_difference"], row["checks"]["relative_L"]["signed_margin"],
                                 row["R_ohm"]["reference"], row["R_ohm"]["candidate"], row["R_ohm"]["signed_difference"], row["Q"]["reference_Q_status"], row["Q"]["candidate_Q_status"],
                                 row["Q"]["reference"], row["Q"]["candidate"], row["Q"]["signed_difference"], row["Q"]["absolute_relative_difference"], row["checks"]["relative_Q"]["signed_margin"], row["Zd"]["absolute_difference_ohm"]])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--profile", choices=PROFILES, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reference-kind", default="actual", help="actual or AFS-derived")
    parser.add_argument("--candidate-kind", default="actual", help="actual or AFS-derived")
    parser.add_argument("--reference-interpolation", choices=("none", "linear"), default="none")
    parser.add_argument("--csv", action="store_true")
    parser.add_argument("--physics-revision", help="Declared common physical-model revision; validate both source decks independently")
    args = parser.parse_args()
    try:
        report = compare_files(args.reference, args.candidate, args.profile, args.output_dir,
                               reference_interpolation=args.reference_interpolation, reference_kind=args.reference_kind,
                               candidate_kind=args.candidate_kind, csv_output=args.csv, physics_revision=args.physics_revision)
    except (ComparisonError, ValueError, OSError, np.linalg.LinAlgError) as exc:
        parser.error(str(exc))
    print(f"Compared all {len(report['points'])} candidate points and {report['port_count']} ports; {report['control_result']}")


if __name__ == "__main__":
    main()
