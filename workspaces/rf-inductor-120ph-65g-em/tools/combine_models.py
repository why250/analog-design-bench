"""Assemble a provenance-preserving frequency union of complete Snp segments.

Each --segment is KIND PATH, with KIND actual or AFS-derived. Frequencies are
compared by their exact parsed Hz values: no new frequency is invented, no near
samples are collapsed, and this tool performs no interpolation or fitting.
Actual samples win at exact duplicates; input order resolves equal-kind ties.
Every duplicate comparison retains the complete complex difference matrix.

DC is absent by default. --include-dc requires --dc-resistance-json and
--lf-agreement-json. The latter must contain state=AGREEMENT_ESTABLISHED,
dc_resistance_ohm, rf_frequency_hz, rf_resistance_ohm,
absolute_tolerance_ohm, reference_planes_consistent=true,
contact_model_reviewed=true, low_frequency_justification, and evidence_files.
The reported RF resistance is checked against an actual input sample under
the Icm=0 extraction; evidence_files resolve relative to that JSON file.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from analyze_em import Network, parse_touchstone, point_metrics
from convert_cti import SNetwork, write_touchstone


FROZEN_ACTUAL_CONFLICT_TOLERANCE = 1e-5


class CombinationError(ValueError):
    """The inputs cannot form an unambiguous, provenance-preserving network."""


@dataclass(frozen=True)
class Segment:
    kind: str
    path: Path
    network: Network
    source: dict[str, Any]


def normalize_kind(kind: str) -> str:
    values = {"actual": "actual", "afs-derived": "AFS-derived"}
    try:
        return values[kind.casefold()]
    except KeyError as exc:
        raise CombinationError("Segment kind must be actual or AFS-derived") from exc


def _file_record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def load_segment(kind: str, path: str | Path) -> Segment:
    import re
    path = Path(path).resolve(strict=True)
    match = re.fullmatch(r"\.s([1-9][0-9]*)p", path.suffix, re.I)
    if match is None:
        raise CombinationError("Every segment must declare its full port count with .sNp")
    content = path.read_bytes()
    network = parse_touchstone(content.decode("utf-8-sig"), int(match.group(1)))
    if network.reference_ohm != 50:
        raise CombinationError("All ports in every segment must use the same real 50 ohm reference")
    source = {"path": str(path), "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    return Segment(normalize_kind(kind), path, network, source)


def dc_series_matrix(resistance_ohm: float) -> np.ndarray:
    """Two-port DC series resistance with an open common mode, both refs 50 ohm."""
    if not math.isfinite(resistance_ohm) or resistance_ohm < 0:
        raise CombinationError("DC series resistance must be finite and nonnegative")
    reflection = resistance_ohm / (100 + resistance_ohm)
    transmission = 100 / (100 + resistance_ohm)
    return np.array([[reflection, transmission], [transmission, reflection]], dtype=complex)


def combine_networks(segments: Sequence[Segment], actual_conflict_tolerance: float = 1e-5) -> tuple[Network, dict[str, Any]]:
    if not segments:
        raise CombinationError("At least one complete segment is required")
    if not math.isfinite(actual_conflict_tolerance) or actual_conflict_tolerance < 0:
        raise CombinationError("Actual-sample conflict tolerance must be finite and nonnegative")
    if actual_conflict_tolerance > FROZEN_ACTUAL_CONFLICT_TOLERANCE:
        raise CombinationError("The actual-sample conflict tolerance cannot exceed the frozen 1e-5 limit")
    ports = segments[0].network.port_count
    grouped: dict[float, list[dict[str, Any]]] = {}
    source_records = []
    for segment_index, segment in enumerate(segments):
        kind = normalize_kind(segment.kind)
        network = segment.network
        if network.port_count != ports or network.reference_ohm != 50:
            raise CombinationError("All segments must preserve the same complete N-port and real 50 ohm references")
        if network.s.shape != (len(network.frequency_hz), ports, ports) or not np.all(np.isfinite(network.s)):
            raise CombinationError("A segment has incomplete or nonfinite complex matrices")
        if (not len(network.frequency_hz) or not np.all(np.isfinite(network.frequency_hz))
                or np.any(network.frequency_hz < 0) or np.any(np.diff(network.frequency_hz) <= 0)):
            raise CombinationError("Segment frequencies must be finite, nonnegative, unique and increasing")
        source_records.append({"segment_index": segment_index, "kind": kind, **segment.source,
                               "samples": len(network.frequency_hz), "port_count": ports})
        for sample_index, (frequency, matrix) in enumerate(zip(network.frequency_hz, network.s, strict=True)):
            grouped.setdefault(float(frequency), []).append({"segment_index": segment_index, "source_sample_index": sample_index,
                                                            "kind": kind, "matrix": matrix})
    frequencies, matrices, provenance, duplicates = [], [], [], []
    for frequency, candidates in sorted(grouped.items()):
        actual = [item for item in candidates if item["kind"] == "actual"]
        # Check all pairs, not merely every sample against a favorable reference.
        for i, first in enumerate(actual):
            for second in actual[i + 1:]:
                difference = float(np.max(np.abs(first["matrix"] - second["matrix"])))
                if difference > actual_conflict_tolerance:
                    raise CombinationError(f"Conflicting actual matrices at {frequency:.17g} Hz exceed the specified absolute S tolerance")
        selected = actual[0] if actual else candidates[0]
        frequencies.append(frequency)
        matrices.append(selected["matrix"])
        provenance.append({"frequency_hz": frequency, "kind": selected["kind"],
                           "segment_index": selected["segment_index"], "source_sample_index": selected["source_sample_index"]})
        if len(candidates) > 1:
            comparisons = []
            for other in candidates:
                if other is selected:
                    continue
                delta = selected["matrix"] - other["matrix"]
                comparisons.append({"other_segment_index": other["segment_index"], "other_source_sample_index": other["source_sample_index"],
                                    "other_kind": other["kind"], "maximum_absolute_S_difference": float(np.max(np.abs(delta))),
                                    "delta_convention": "selected minus other",
                                    "complete_complex_delta_S": [[[float(z.real), float(z.imag)] for z in row] for row in delta]})
            duplicates.append({"frequency_hz": frequency, "selected_segment_index": selected["segment_index"],
                               "selected_kind": selected["kind"], "selection_rule": "actual preferred; equal-kind ties use earlier input segment",
                               "comparisons": comparisons})
    network = Network(np.asarray(frequencies), np.asarray(matrices), 50.0)
    receipt = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
               "artifact_role": "derived frequency-union assembly; original solver/model segments remain authoritative",
               "port_count": ports, "reference_ohm": 50.0, "samples": len(frequencies),
               "frequency_union_rule": "exact parsed Hz equality; no near-frequency grouping",
               "actual_conflict_absolute_S_tolerance": actual_conflict_tolerance,
               "interpolation_performed_by_this_tool": False, "fitting": False,
               "renormalization": False, "passivity_repair": False,
               "kind_assignment": "Caller-supplied; this tool does not certify actual-solver or AFS provenance",
               "physical_identity_check": "Caller must verify common geometry, stack, physical port order and reference planes from retained source receipts",
               "contains_AFS_derived_samples": any(item["kind"] == "AFS-derived" for item in provenance),
               "source_segments": source_records, "point_provenance": provenance,
               "duplicate_frequency_comparisons": duplicates, "DC_anchor": {"included": False}}
    return network, receipt


def _finite_number(data: dict[str, Any], key: str, *, positive: bool = False) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise CombinationError(f"{key} must be a finite {'positive' if positive else 'nonnegative'} number")
    return float(value)


def include_dc_anchor(network: Network, receipt: dict[str, Any], dc_path: str | Path,
                      agreement_path: str | Path) -> tuple[Network, dict[str, Any]]:
    """Append a separately derived DC realization only after explicit LF review."""
    if network.port_count != 2:
        raise CombinationError("The series-R DC realization is defined only for the complete two-port device")
    if 0 in network.frequency_hz:
        raise CombinationError("An existing zero-Hz sample must not be replaced by a derived anchor")
    dc_path, agreement_path = Path(dc_path).resolve(strict=True), Path(agreement_path).resolve(strict=True)
    dc = json.loads(dc_path.read_text(encoding="utf-8-sig"))
    agreement = json.loads(agreement_path.read_text(encoding="utf-8-sig"))
    if not isinstance(dc, dict) or not isinstance(agreement, dict) or dc.get("status") != "NUMERICAL_DC_SHEET_ESTIMATE":
        raise CombinationError("An independent DC sheet report and an LF-agreement JSON object are required")
    resistance = _finite_number(dc, "finest_R_ohm", positive=True)
    if (agreement.get("state") != "AGREEMENT_ESTABLISHED" or agreement.get("reference_planes_consistent") is not True
            or agreement.get("contact_model_reviewed") is not True
            or not isinstance(agreement.get("low_frequency_justification"), str) or not agreement["low_frequency_justification"].strip()):
        raise CombinationError("Explicit contact/plane and low-frequency agreement evidence is required")
    declared_dc = _finite_number(agreement, "dc_resistance_ohm", positive=True)
    rf_frequency = _finite_number(agreement, "rf_frequency_hz", positive=True)
    declared_rf = _finite_number(agreement, "rf_resistance_ohm", positive=True)
    tolerance = _finite_number(agreement, "absolute_tolerance_ohm")
    if not math.isclose(declared_dc, resistance, rel_tol=1e-12, abs_tol=1e-15):
        raise CombinationError("The LF evidence DC value differs from the independent report")
    matches = [i for i, value in enumerate(network.frequency_hz) if float(value) == rf_frequency]
    if len(matches) != 1 or receipt["point_provenance"][matches[0]]["kind"] != "actual":
        raise CombinationError("LF agreement must refer to an actual solved input sample")
    row = point_metrics(rf_frequency, network.s[matches[0]], 50)
    if (row["differential_solver"].get("ill_conditioned") or row["passivity"]["state"] != "PASS"
            or row["reciprocity"]["state"] != "PASS"):
        raise CombinationError("LF agreement requires a numerically usable passive reciprocal actual input sample")
    observed_rf = row["differential"]["R_ohm"]
    if observed_rf is None or not math.isclose(declared_rf, observed_rf, rel_tol=1e-12, abs_tol=1e-12):
        raise CombinationError("The LF evidence RF value differs from the actual Icm=0 input sample")
    if abs(observed_rf - resistance) > tolerance:
        raise CombinationError("DC and actual LF resistance do not meet the declared agreement tolerance")
    evidence_files = agreement.get("evidence_files")
    if not isinstance(evidence_files, list) or not evidence_files or any(not isinstance(name, str) or not name for name in evidence_files):
        raise CombinationError("At least one retained LF evidence file must be identified")
    evidence_receipts = []
    for name in evidence_files:
        path = Path(name)
        path = (agreement_path.parent / path).resolve(strict=True) if not path.is_absolute() else path.resolve(strict=True)
        if not path.is_file():
            raise CombinationError("LF evidence entries must identify retained files")
        evidence_receipts.append(_file_record(path))
    network = Network(np.r_[0.0, network.frequency_hz], np.concatenate((dc_series_matrix(resistance)[None, :, :], network.s)), 50.0)
    receipt["point_provenance"].insert(0, {"frequency_hz": 0.0, "kind": "DC-series-R-derived-anchor", "segment_index": None, "source_sample_index": None})
    receipt["samples"] += 1
    receipt["DC_anchor"] = {"included": True, "kind": "independent sheet-R analytical two-port realization",
                            "resistance_ohm": resistance, "model": "S11=S22=R/(100+R); S12=S21=100/(100+R); common mode open",
                            "EM_DC_solve_claimed": False, "low_frequency_RF_sample_hz": rf_frequency,
                            "observed_RF_resistance_ohm": observed_rf, "absolute_tolerance_ohm": tolerance,
                            "DC_report": _file_record(dc_path), "LF_agreement": _file_record(agreement_path),
                            "LF_evidence_files": evidence_receipts,
                            "limitations": "Derived endpoint only; interpolation between zero and the first RF sample belongs to the consuming simulator and needs its own validity assessment"}
    return network, receipt


def assemble(segment_specs: Sequence[tuple[str, str | Path]], output: str | Path, receipt_path: str | Path,
             actual_conflict_tolerance: float = 1e-5, *, include_dc: bool = False,
             dc_resistance_json: str | Path | None = None, lf_agreement_json: str | Path | None = None,
             physics_revision: str | None = None) -> dict[str, Any]:
    output, receipt_path = Path(output).resolve(), Path(receipt_path).resolve()
    if output == receipt_path or output.exists() or receipt_path.exists():
        raise FileExistsError("Output network and receipt must be distinct fresh files")
    if include_dc and (dc_resistance_json is None or lf_agreement_json is None):
        raise CombinationError("--include-dc requires independent DC and LF agreement files")
    if not include_dc and (dc_resistance_json is not None or lf_agreement_json is not None):
        raise CombinationError("DC inputs do not enable an anchor implicitly; explicitly use --include-dc")
    segments = [load_segment(kind, path) for kind, path in segment_specs]
    network, receipt = combine_networks(segments, actual_conflict_tolerance)
    if physics_revision is not None and (not isinstance(physics_revision, str) or not physics_revision.strip()):
        raise CombinationError("Physics revision must be a nonempty declared identifier")
    receipt["physics_revision"] = physics_revision
    receipt["physics_revision_assignment"] = "Caller-declared; must be supported by each source input-validation and solver receipt"
    if include_dc:
        network, receipt = include_dc_anchor(network, receipt, dc_resistance_json, lf_agreement_json)
    if output.suffix.casefold() != f".s{network.port_count}p":
        raise CombinationError("Output suffix must preserve the complete input N-port count")
    if receipt_path.suffix.casefold() != ".json":
        raise CombinationError("The machine-readable assembly receipt must use .json")
    if receipt["contains_AFS_derived_samples"]:
        label = "COMPOSITE_CONTAINING_AFS_DERIVED_SAMPLES"
    else:
        label = "UNION_OF_ACTUAL_SOLVED_SAMPLES"
    if include_dc:
        label += "_AND_DERIVED_DC_ANCHOR"
    receipt["model_classification"] = label
    matrix = tuple(tuple(tuple(complex(z) for z in row) for row in item) for item in network.s)
    buffer = io.StringIO()
    write_touchstone(SNetwork(tuple(map(float, network.frequency_hz)), matrix, "frequency_union"), buffer, 50.0)
    # The generic writer's raw-data comment does not describe an AFS composite.
    payload = "\n".join(buffer.getvalue().splitlines()[1:]) + "\n"
    payload = f"! {label}\n! Derived frequency union; consult the assembly JSON for every point's source.\n! This tool performs no interpolation, fitting, renormalization, or passivity repair.\n" + payload
    encoded = payload.encode("ascii")
    receipt["output"] = {"path": str(output), "bytes": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()}
    serialized = json.dumps(receipt, indent=2, allow_nan=False) + "\n"
    # Read-only sources must still agree with their captured input snapshots.
    for segment in segments:
        if _file_record(segment.path) != segment.source:
            raise CombinationError("A source segment changed during assembly")
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(encoded)
    with receipt_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(serialized)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment", nargs=2, action="append", required=True, metavar=("KIND", "PATH"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--actual-conflict-tolerance", type=float, default=1e-5)
    parser.add_argument("--include-dc", action="store_true")
    parser.add_argument("--dc-resistance-json", type=Path)
    parser.add_argument("--lf-agreement-json", type=Path)
    parser.add_argument("--physics-revision", help="Declared common physical-model revision; source validation remains required")
    args = parser.parse_args()
    try:
        report = assemble(args.segment, args.output, args.receipt, args.actual_conflict_tolerance,
                          include_dc=args.include_dc, dc_resistance_json=args.dc_resistance_json,
                          lf_agreement_json=args.lf_agreement_json, physics_revision=args.physics_revision)
    except (CombinationError, ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"Assembled {report['samples']} points, {report['port_count']} ports; {report['model_classification']}")


if __name__ == "__main__":
    main()
