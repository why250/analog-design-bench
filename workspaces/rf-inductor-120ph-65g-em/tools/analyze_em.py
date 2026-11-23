"""Analyze the complete raw N-port under the frozen Icm=0 device contract.

Touchstone 1, equal real references, and RI/MA/DB S data are supported. Ports
1/2 are p/n; every additional signal port is OPEN (its current is zero).
No interpolation, fitting, passivity repair, or matrix regularization is used.

Optional uncertainty JSON keys: L_absolute_pH, reactance_absolute_ohm,
coverage_10_65, coverage_through_80, and checks (mesh, port, boundary, material,
dc_low_frequency, reproduction). All check/coverage values must explicitly be
true before a passing device conclusion is possible. These operator statements
must be backed by retained evidence; the analyzer does not certify them.

Final qualification explicitly supplies --assembly-receipt and --protocol.
The native AFS amendment additionally requires physics_revision=passive-loss-r1,
checks.afs=true, actual-source boundaries/LF probes, and a reactance_frequency_envelope
with validation_kind=actual-control-comparisons, interpolation_rule=interval-max-equivalent-L,
points=[{frequency_hz,direct_X_absolute_ohm,L_absolute_pH},...], evidence_files.
Use this envelope instead of reactance_absolute_ohm. It includes the global
observed L bound and interpolation reserve, with no manufacturing error inferred.
The independent low_frequency_limit object requires status=SUPPORTED_BY_DC_AND_ACTUAL_LF,
first_actual_frequency_hz, inductive_limit_positive=true, evidence_files.
Evidence paths resolve relative to the uncertainty JSON; source identities are
retained. No frequency-error extrapolation is used below its first control.
Without an explicit protocol the CLI reports characterization only.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

import numpy as np


PASSIVITY_TOLERANCE = 1e-6
RECIPROCITY_TOLERANCE = 1e-6
CONDITION_WARNING = 1e12
FINAL_MAXIMUM_STEP_HZ = 1e9
REQUIRED_CHECKS = ("mesh", "port", "boundary", "material", "dc_low_frequency", "reproduction")
PASSIVE_PHYSICS_REVISION = "passive-loss-r1"


class NetworkError(ValueError):
    """Raw network input cannot be interpreted without losing information."""


@dataclass(frozen=True)
class Network:
    frequency_hz: np.ndarray
    s: np.ndarray
    reference_ohm: float

    @property
    def port_count(self) -> int:
        return int(self.s.shape[1])


def parse_touchstone(text: str, port_count: int) -> Network:
    """Parse complete Touchstone 1 S matrices, preserving sample association."""
    if port_count < 2:
        raise NetworkError("At least two signal ports are required")
    options = ("GHZ", "S", "MA", 50.0)
    option_seen = False
    data_seen = False
    numbers: list[float] = []
    for line_number, raw in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        line = raw.split("!", 1)[0].strip()
        if not line:
            continue
        if line.startswith("["):
            raise NetworkError("Touchstone 2 keywords are unsupported; retain the original file")
        if line.startswith("#"):
            if option_seen or data_seen:
                raise NetworkError("Repeated or misplaced option line")
            tokens = line[1:].upper().split()
            if len(tokens) != 5 or tokens[3] != "R":
                raise NetworkError("Expected # frequency-unit S RI|MA|DB R resistance")
            try:
                reference = float(tokens[4])
            except ValueError as exc:
                raise NetworkError("Invalid reference resistance") from exc
            options = (tokens[0], tokens[1], tokens[2], reference)
            option_seen = True
            continue
        data_seen = True
        try:
            values = [float(token.replace("D", "E").replace("d", "e")) for token in line.split()]
        except ValueError as exc:
            raise NetworkError(f"Line {line_number}: invalid numeric data") from exc
        if not all(math.isfinite(value) for value in values):
            raise NetworkError(f"Line {line_number}: nonfinite numeric data")
        numbers.extend(values)
    unit, parameter, representation, reference = options
    if unit not in ("HZ", "KHZ", "MHZ", "GHZ") or parameter != "S" or representation not in ("RI", "MA", "DB"):
        raise NetworkError("Unsupported frequency unit, network parameter, or representation")
    if not math.isfinite(reference) or reference <= 0:
        raise NetworkError("A finite positive equal real reference is required")
    width = 1 + 2 * port_count**2
    if not numbers or len(numbers) % width:
        raise NetworkError("Missing or extra matrix entries; noise tables are unsupported")
    table = np.asarray(numbers, dtype=float).reshape(-1, width)
    frequency = table[:, 0] * {"HZ": 1, "KHZ": 1e3, "MHZ": 1e6, "GHZ": 1e9}[unit]
    if np.any(frequency < 0) or np.any(np.diff(frequency) <= 0):
        raise NetworkError("Frequencies must be nonnegative and strictly increasing")
    pairs = table[:, 1:].reshape(-1, port_count**2, 2)
    if representation == "RI":
        values = pairs[:, :, 0] + 1j * pairs[:, :, 1]
    else:
        magnitude = pairs[:, :, 0] if representation == "MA" else 10 ** (pairs[:, :, 0] / 20)
        if representation == "MA" and np.any(magnitude < 0):
            raise NetworkError("Magnitude cannot be negative")
        values = magnitude * np.exp(1j * np.deg2rad(pairs[:, :, 1]))
    matrix = values.reshape(-1, port_count, port_count)
    # The legacy two-port sequence is S11,S21,S12,S22. N>=3 uses rows.
    if port_count == 2:
        matrix = matrix.transpose(0, 2, 1)
    if not np.all(np.isfinite(matrix)):
        raise NetworkError("Decoded network contains nonfinite values")
    return Network(frequency, matrix, reference)


def read_touchstone(path: Path) -> Network:
    match = re.fullmatch(r"\.s([1-9][0-9]*)p", path.suffix, re.I)
    if not match:
        raise NetworkError("Port count must be declared by a .sNp filename")
    return parse_touchstone(path.read_text(encoding="utf-8-sig"), int(match.group(1)))


def read_assembly_receipt(path: Path, model_path: Path, network: Network) -> dict[str, Any]:
    """Verify the assembled file identity before using its per-point provenance."""
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict) or not isinstance(document.get("output"), dict):
        raise NetworkError("An assembly receipt must identify its complete output model")
    content = model_path.read_bytes()
    expected = document["output"]
    digest = hashlib.sha256(content).hexdigest()
    if expected.get("bytes") != len(content) or expected.get("sha256") != digest:
        raise NetworkError("Assembly output integrity does not match the analyzed model")
    decoded = read_touchstone(model_path)
    if (decoded.reference_ohm != network.reference_ohm or not np.array_equal(decoded.frequency_hz, network.frequency_hz)
            or not np.array_equal(decoded.s, network.s)):
        raise NetworkError("The analyzed network differs from the verified assembly output")
    raw_receipt = path.read_bytes()
    result = {"assembly": document, "model_output_identity_verified": True,
              "assembly_receipt_source": {"path": str(path.resolve()), "bytes": len(raw_receipt),
                                          "sha256": hashlib.sha256(raw_receipt).hexdigest()}}
    _point_provenance(network, result)
    return result


def _point_provenance(network: Network, verified: dict[str, Any] | None) -> list[dict[str, Any]]:
    if verified is None:
        return [{"frequency_hz": float(f), "kind": "UNSPECIFIED", "source_identity_verified": False} for f in network.frequency_hz]
    document = verified.get("assembly")
    if not isinstance(document, dict) or (document.get("port_count"), document.get("reference_ohm"), document.get("samples")) != (
            network.port_count, network.reference_ohm, len(network.frequency_hz)):
        raise NetworkError("Assembly dimensions or references do not match the complete analyzed N-port")
    provenance = document.get("point_provenance")
    if not isinstance(provenance, list) or len(provenance) != len(network.frequency_hz):
        raise NetworkError("Assembly point provenance is incomplete")
    sources = document.get("source_segments")
    if not isinstance(sources, list):
        raise NetworkError("Assembly source segments are missing")
    if any(not isinstance(item, dict) or type(item.get("segment_index")) is not int
           or item["segment_index"] < 0 or type(item.get("samples")) is not int or item["samples"] < 1 for item in sources):
        raise NetworkError("Assembly source segment/sample indices are invalid")
    source_map = {item["segment_index"]: item for item in sources}
    if len(source_map) != len(sources):
        raise NetworkError("Assembly source segment indices are not unique")
    result = []
    for frequency, item in zip(network.frequency_hz, provenance, strict=True):
        if not isinstance(item, dict) or item.get("frequency_hz") != float(frequency):
            raise NetworkError("Assembly frequency/sample association differs from the model")
        kind = item.get("kind")
        if kind in ("actual", "AFS-derived"):
            source = source_map.get(item.get("segment_index"))
            if (not isinstance(source, dict) or source.get("kind") != kind or type(item.get("source_sample_index")) is not int
                    or not 0 <= item["source_sample_index"] < source["samples"]):
                raise NetworkError("Assembly point provenance does not agree with its source kind")
        elif kind == "DC-series-R-derived-anchor":
            if float(frequency) != 0 or document.get("DC_anchor", {}).get("included") is not True:
                raise NetworkError("A derived DC point lacks its explicit DC anchor receipt")
        else:
            raise NetworkError("An assembly point has an unsupported or unspecified source kind")
        result.append({**item, "source_identity_verified": verified.get("model_output_identity_verified") is True})
    if document.get("contains_AFS_derived_samples") is not any(item["kind"] == "AFS-derived" for item in result):
        raise NetworkError("Assembly AFS classification conflicts with its selected point provenance")
    return result


def _protocol_checks(protocol: dict[str, Any] | None) -> tuple[bool, list[tuple[str, float, float, float]], tuple[float, ...], tuple[float, ...], float]:
    original = [("flatness_10_65", 10e9, 65e9, 1e9), ("inductive_5_80", 5e9, 80e9, 1e9)]
    if protocol is None:
        return False, original, (0.01e9, 0.1e9, 1e9, 5e9), (65e9, 80e9), 0.0
    if not isinstance(protocol, dict) or protocol.get("schema_version") != 1 or protocol.get("native_afs", {}).get("range_GHz") != [5, 200]:
        raise NetworkError("The supplied protocol is not the supported revision-1 native AFS amendment")
    try:
        low = tuple(float(f) * 1e9 for f in protocol["low_frequency"]["exact_GHz"])
        exact = tuple(float(f) * 1e9 for f in protocol["independent_frequency_validation"]["required_exact_GHz"])
        reserve = float(protocol["independent_frequency_validation"]["reserved_L_uncertainty_fraction"])
    except (KeyError, TypeError, ValueError) as exc:
        raise NetworkError("The AFS protocol lacks low-frequency, actual-point or uncertainty rules") from exc
    if (not low or not exact or any(not math.isfinite(f) or f <= 0 for f in low + exact)
            or not math.isfinite(reserve) or reserve < 0 or not {65e9, 80e9}.issubset(exact)):
        raise NetworkError("The AFS protocol contains invalid numerical definitions")
    return True, original + [("AFS_5_100", 5e9, 100e9, 1e9), ("AFS_100_200", 100e9, 200e9, 5e9)], low, exact, reserve


def _complex(value: complex) -> dict[str, float]:
    return {"real_ohm": float(value.real), "imag_ohm": float(value.imag)}


def _solve_observable(a: np.ndarray, b: np.ndarray, observable: np.ndarray) -> dict[str, Any]:
    """Identify a unique observable, including exact singular gauge limits.

    The numerical rank threshold is the conventional machine-precision SVD
    rank test. An exact nullspace is permitted only when the RHS is compatible
    and the measured voltage difference annihilates that nullspace. No small
    diagonal, chosen conductance, or regularized inverse is introduced.
    """
    u, singular, vh = np.linalg.svd(a)
    eps = np.finfo(float).eps
    threshold = eps * max(a.shape) * singular[0] if singular.size else 0.0
    rank = int(np.count_nonzero(singular > threshold))
    dimension = a.shape[1]
    result: dict[str, Any] = {"rank": rank, "dimension": dimension}
    result["condition_number"] = float(singular[0] / singular[-1]) if rank == dimension else None
    if rank == dimension:
        solution = np.linalg.solve(a, b)
        value = complex(observable @ solution)
        result.update(status="FINITE", value=value, residual_norm=float(np.linalg.norm(a @ solution - b)))
        result["ill_conditioned"] = result["condition_number"] > CONDITION_WARNING
        return result
    left_null = u[:, rank:]
    right_null = vh[rank:, :].conj().T
    compatibility = float(np.linalg.norm(left_null.conj().T @ b))
    gauge = float(np.linalg.norm(observable @ right_null))
    compatibility_limit = 64 * eps * max(a.shape) * max(1.0, float(np.linalg.norm(b)))
    gauge_limit = 64 * eps * max(a.shape) * max(1.0, float(np.linalg.norm(observable)))
    result.update(rhs_nullspace_residual=compatibility, observable_nullspace_residual=gauge,
                  rhs_compatibility_tolerance=compatibility_limit, observable_tolerance=gauge_limit,
                  ill_conditioned=False)
    if compatibility > compatibility_limit:
        result.update(status="INCOMPATIBLE_CURRENT_OPEN_LIMIT", value=None)
    elif gauge > gauge_limit:
        result.update(status="UNIDENTIFIABLE_VOLTAGE_LIMIT", value=None)
    else:
        solution = vh[:rank, :].conj().T @ ((u[:, :rank].conj().T @ b) / singular[:rank])
        result.update(status="CONSTRAINED_FINITE", value=complex(observable @ solution),
                      residual_norm=float(np.linalg.norm(a @ solution - b)))
    return result


def _metric(impedance: complex | None, frequency: float, status: str) -> dict[str, Any]:
    if impedance is None:
        return {"status": status, "impedance": None, "L_h": None, "R_ohm": None,
                "Q": {"status": "UNDEFINED_IMPEDANCE", "value": None}}
    if not (math.isfinite(impedance.real) and math.isfinite(impedance.imag)):
        return {"status": "NONFINITE_DERIVED_VALUE", "impedance": None, "L_h": None,
                "R_ohm": None, "Q": {"status": "UNDEFINED_IMPEDANCE", "value": None}}
    resistance, reactance = impedance.real, impedance.imag
    if resistance > 0:
        ratio = float(reactance / resistance)
        q = {"status": "FINITE", "value": ratio} if math.isfinite(ratio) else {"status": "NUMERIC_OVERFLOW_LIMIT", "value": None}
    elif resistance == 0 and reactance != 0:
        q = {"status": "POSITIVE_INFINITY_LIMIT" if reactance > 0 else "NEGATIVE_INFINITY_LIMIT", "value": None}
    elif resistance == 0:
        q = {"status": "ZERO_OVER_ZERO_LIMIT", "value": None}
    else:
        q = {"status": "NEGATIVE_DISSIPATION", "value": None}
    inductance = float(reactance / (2 * np.pi * frequency)) if frequency > 0 else None
    if inductance is not None and not math.isfinite(inductance):
        inductance, status = None, "NONFINITE_DERIVED_INDUCTANCE"
    return {"status": status, "impedance": _complex(impedance),
            "L_h": inductance,
            "R_ohm": float(resistance), "Q": q}


def point_metrics(frequency: float, s: np.ndarray, reference: float) -> dict[str, Any]:
    s = np.asarray(s, dtype=complex)
    if s.ndim != 2 or s.shape[0] != s.shape[1] or s.shape[0] < 2 or not np.all(np.isfinite(s)):
        raise NetworkError("Expected a complete finite square S matrix")
    if not math.isfinite(frequency) or frequency < 0 or not math.isfinite(reference) or reference <= 0:
        raise NetworkError("Frequency and equal real reference must be finite and physically valid")
    n = s.shape[0]
    identity = np.eye(n, dtype=complex)
    a, b_matrix = identity - s, reference * (identity + s)
    current = np.zeros(n, dtype=complex)
    current[0], current[1] = 1, -1
    differential = _solve_observable(a, b_matrix @ current, current)
    z_info = {key: value for key, value in differential.items() if key != "value"}
    # Full Z is retained when it exists; a singular full Z does not invalidate S.
    if differential["rank"] == n:
        z = np.linalg.solve(a, b_matrix)
        if np.all(np.isfinite(z)):
            z_info.update(status="FINITE", matrix_ohm=[[_complex(complex(v)) for v in row] for row in z])
        else:
            z_info.update(status="NONFINITE_DERIVED_FULL_Z", matrix_ohm=None)
    else:
        z_info.update(status="SINGULAR_FULL_Z", matrix_ohm=None)
    # Ground p/n terminal 2 while every auxiliary signal current remains zero.
    grounded_a = np.zeros((n + 1, n + 1), dtype=complex)
    grounded_a[:n, :n], grounded_a[:n, n], grounded_a[n, 1] = a, -b_matrix[:, 1], 1
    grounded_b = np.r_[b_matrix[:, 0], 0j]
    observable = np.zeros(n + 1, dtype=complex)
    observable[0] = 1
    grounded = _solve_observable(grounded_a, grounded_b, observable)
    loss = identity - s.conj().T @ s
    minimum_passivity = float(np.linalg.eigvalsh((loss + loss.conj().T) / 2)[0])
    reciprocity = float(np.max(np.abs(s - s.T)))
    return {
        "frequency_hz": float(frequency),
        "differential": _metric(differential["value"], frequency, differential["status"]),
        "grounded_terminal_2": _metric(grounded["value"], frequency, grounded["status"]),
        "s_to_z": z_info,
        "differential_solver": {k: v for k, v in differential.items() if k != "value"},
        "grounded_solver": {k: v for k, v in grounded.items() if k != "value"},
        "passivity": {"minimum_eigenvalue": minimum_passivity,
                      "state": "PASS" if minimum_passivity >= -PASSIVITY_TOLERANCE else "FAIL"},
        "reciprocity": {"maximum_absolute_S_error": reciprocity,
                        "state": "PASS" if reciprocity <= RECIPROCITY_TOLERANCE else "FAIL"},
    }


def _interval_state(value: float, uncertainty: float | None, low: float, high: float) -> str:
    if uncertainty is None:
        return "INDETERMINATE"
    if value - uncertainty >= low and value + uncertainty <= high:
        return "PASS"
    if value + uncertainty < low or value - uncertainty > high:
        return "FAIL"
    return "INDETERMINATE"


def _uncertainty(data: dict[str, Any], key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise NetworkError(f"{key} must be a finite nonnegative absolute uncertainty")
    return float(value)


def read_operator_evidence(path: Path) -> dict[str, Any]:
    """Resolve retained numerical/DC evidence relative to its operator JSON."""
    raw = path.read_bytes()
    evidence = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(evidence, dict):
        raise NetworkError("Uncertainty input must be a JSON object")
    for field in ("reactance_frequency_envelope", "low_frequency_limit"):
        section = evidence.get(field)
        if section is None:
            continue
        if not isinstance(section, dict):
            raise NetworkError(f"{field} must be a JSON object")
        names = section.get("evidence_files")
        if not isinstance(names, list) or not names or any(not isinstance(name, str) or not name for name in names):
            raise NetworkError(f"{field} needs retained evidence_files")
        records = []
        for name in names:
            source = Path(name)
            source = (path.parent / source).resolve(strict=True) if not source.is_absolute() else source.resolve(strict=True)
            if not source.is_file():
                raise NetworkError("An uncertainty evidence entry is not a retained file")
            content = source.read_bytes()
            records.append({"path": str(source), "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        section["evidence_file_records"] = records
    evidence["operator_evidence_source"] = {"path": str(path.resolve()), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return evidence


def _reactance_uncertainties(rows: list[dict[str, Any]], evidence: dict[str, Any],
                             global_L_pH: float | None, uniform_X_ohm: float | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Bound X with explicit validated-frequency support and no extrapolation.

    Each control node contributes max(direct dX/(2*pi*f), observed dL, global
    qualified dL). Between control nodes use the larger equivalent-L bound and
    scale it at the requested frequency. The rule is a declared conservative
    envelope assumption between controls, not a fitted error function.
    """
    envelope = evidence.get("reactance_frequency_envelope")
    if envelope is None:
        return [{"status": "FINITE" if uniform_X_ohm is not None else "MISSING_UNCERTAINTY",
                 "frequency_hz": row["frequency_hz"], "absolute_uncertainty_ohm": uniform_X_ohm,
                 "method": "legacy uniform absolute reactance bound"} for row in rows], {
                     "method": "legacy uniform absolute bound", "frequency_dependent_evidence": False}
    if uniform_X_ohm is not None:
        raise NetworkError("Choose a frequency envelope or legacy reactance_absolute_ohm; do not silently override either")
    if (not isinstance(envelope, dict) or envelope.get("validation_kind") != "actual-control-comparisons"
            or envelope.get("interpolation_rule") != "interval-max-equivalent-L"):
        raise NetworkError("Unsupported reactance envelope or control-validation convention")
    points = envelope.get("points")
    if not isinstance(points, list) or len(points) < 2:
        raise NetworkError("A reactance frequency envelope needs at least two actual control nodes")
    nodes = []
    for point in points:
        if not isinstance(point, dict):
            raise NetworkError("Each reactance envelope node must be an object")
        frequency = _uncertainty(point, "frequency_hz")
        direct = _uncertainty(point, "direct_X_absolute_ohm")
        delta_l = _uncertainty(point, "L_absolute_pH")
        if frequency is None or frequency <= 0 or direct is None or delta_l is None:
            raise NetworkError("Each control node needs positive f, direct dX and inductance uncertainty")
        equivalent_l = max(delta_l, global_L_pH or 0.0, direct / (2 * math.pi * frequency) * 1e12)
        nodes.append({"frequency_hz": frequency, "direct_X_absolute_ohm": direct, "L_absolute_pH": delta_l,
                      "global_L_absolute_pH_included": global_L_pH, "equivalent_L_envelope_pH": equivalent_l})
    frequencies = np.asarray([node["frequency_hz"] for node in nodes])
    if np.any(np.diff(frequencies) <= 0):
        raise NetworkError("Actual reactance-control frequencies must be unique and strictly increasing")
    bounds = []
    for row in rows:
        frequency = row["frequency_hz"]
        if frequency == 0:
            bounds.append({"status": "NOT_APPLICABLE_AT_DC", "frequency_hz": 0,
                           "absolute_uncertainty_ohm": None, "method": "No RF-error extrapolation to DC"})
            continue
        position = int(np.searchsorted(frequencies, frequency))
        if position < len(nodes) and frequencies[position] == frequency:
            selected = [nodes[position]]
        elif position == 0 or position == len(nodes):
            bounds.append({"status": "OUTSIDE_VALIDATED_CONTROL_DOMAIN", "frequency_hz": frequency,
                           "absolute_uncertainty_ohm": None, "method": "No extrapolation"})
            continue
        else:
            selected = [nodes[position - 1], nodes[position]]
        bound_l = max(node["equivalent_L_envelope_pH"] for node in selected)
        bounds.append({"status": "FINITE", "frequency_hz": frequency,
                       "absolute_uncertainty_ohm": 2 * math.pi * frequency * bound_l * 1e-12,
                       "equivalent_L_envelope_pH": bound_l,
                       "control_bracket_frequency_hz": [node["frequency_hz"] for node in selected],
                       "endpoint_equivalent_L_envelope_pH": [node["equivalent_L_envelope_pH"] for node in selected],
                       "method": "interval-max-equivalent-L; deltaX(f)=2*pi*f*deltaL_envelope"})
    return bounds, {"method": "interval-max-equivalent-L", "frequency_dependent_evidence": True,
                    "validated_control_domain_hz": [float(frequencies[0]), float(frequencies[-1])], "actual_control_nodes": nodes,
                    "extrapolation": False, "DC_and_sub_first_point": "Require separate DC/actual-LF supported-limit evidence",
                    "scope": "Observed numerical controls plus qualified interpolation allowance; no manufacturing uncertainty is inferred"}


def analyze_network(network: Network, uncertainty: dict[str, Any] | None = None,
                    assembly_receipt: dict[str, Any] | None = None,
                    protocol: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence = uncertainty or {}
    if network.frequency_hz.ndim != 1 or not len(network.frequency_hz) or network.s.shape != (len(network.frequency_hz), network.port_count, network.port_count):
        raise NetworkError("Network sample and matrix dimensions are inconsistent")
    if not np.all(np.isfinite(network.frequency_hz)) or np.any(network.frequency_hz < 0) or np.any(np.diff(network.frequency_hz) <= 0):
        raise NetworkError("Network frequencies must be finite, nonnegative, and strictly increasing")
    ul = _uncertainty(evidence, "L_absolute_pH")
    ux = _uncertainty(evidence, "reactance_absolute_ohm")
    afs_protocol, intervals, low_probes, actual_required, reserve = _protocol_checks(protocol)
    provenance = _point_provenance(network, assembly_receipt)
    rows = [point_metrics(float(f), s, network.reference_ohm) for f, s in zip(network.frequency_hz, network.s, strict=True)]
    for row, origin in zip(rows, provenance, strict=True):
        row["sample_source"] = origin
    gaps = [f"Missing qualified {name} evidence" for name in REQUIRED_CHECKS if evidence.get("checks", {}).get(name) is not True]
    x_bounds, x_envelope = _reactance_uncertainties(rows, evidence, ul, ux)
    for row, bound in zip(rows, x_bounds, strict=True):
        row["reactance_uncertainty"] = bound
    assembly = assembly_receipt.get("assembly", {}) if assembly_receipt else {}
    if afs_protocol:
        if assembly_receipt is None or assembly_receipt.get("model_output_identity_verified") is not True:
            gaps.append("The final AFS protocol requires a verified assembly receipt linked to this exact model")
        if assembly.get("physics_revision") != PASSIVE_PHYSICS_REVISION or evidence.get("physics_revision") != PASSIVE_PHYSICS_REVISION:
            gaps.append("Final qualification requires the corrected passive-loss-r1 physical-model revision in both assembly and operator evidence")
        if evidence.get("checks", {}).get("afs") is not True:
            gaps.append("Missing independent AFS frequency/midpoint validation evidence")
        envelope = evidence.get("reactance_frequency_envelope", {})
        if not x_envelope["frequency_dependent_evidence"] or not envelope.get("evidence_file_records"):
            gaps.append("Final qualification needs frequency-dependent reactance bounds linked to actual numerical control receipts")
        low_limit = evidence.get("low_frequency_limit", {})
        first_actual = next((item["frequency_hz"] for item in provenance if item["frequency_hz"] > 0 and item["kind"] == "actual"), None)
        if (not isinstance(low_limit, dict) or low_limit.get("status") != "SUPPORTED_BY_DC_AND_ACTUAL_LF"
                or low_limit.get("inductive_limit_positive") is not True or first_actual is None
                or low_limit.get("first_actual_frequency_hz") != first_actual or not low_limit.get("evidence_file_records")):
            gaps.append("The interval below the first RF point needs separate DC/actual-LF consistency and positive-inductance-limit evidence")
        if ul is not None and ul < reserve * 120:
            gaps.append("Inductance uncertainty does not include the protocol's reserved interpolation allowance")
    if assembly_receipt is not None or afs_protocol:
        for frequency in sorted(set(actual_required + low_probes)):
            match = [item for item in provenance if item["frequency_hz"] == frequency and item["kind"] == "actual"
                     and item["source_identity_verified"]]
            if not match:
                gaps.append(f"Missing verified actual-solve source at {frequency:.17g} Hz")
    sampling: dict[str, Any] = {}
    for label, lower, upper, required_step in intervals:
        subset = network.frequency_hz[(network.frequency_hz >= lower) & (network.frequency_hz <= upper)]
        maximum_step = float(np.max(np.diff(subset))) if len(subset) > 1 else None
        coverage = len(subset) > 1 and float(subset[0]) == lower and float(subset[-1]) == upper and maximum_step <= required_step
        sampling[label] = {"samples": len(subset), "maximum_step_hz": maximum_step,
                           "required_maximum_step_hz": required_step, "grid_complete": bool(coverage)}
        if not coverage:
            gaps.append(f"Final {label} sample grid is incomplete or exceeds its frozen frequency step")
    missing_low = [float(f) for f in low_probes if f not in network.frequency_hz]
    sampling["missing_low_frequency_probe_hz"] = missing_low
    if missing_low:
        gaps.append("Frozen low-frequency probes are missing; a positive RF point is not DC evidence")
    if ul is None:
        gaps.append("Inductance uncertainty is not established")
    if ux is None and not x_envelope["frequency_dependent_evidence"]:
        gaps.append("Reactance uncertainty is not established")
    if evidence.get("coverage_10_65") is not True:
        gaps.append("Continuous 10-65 GHz coverage/extrema qualification is not established")
    if evidence.get("coverage_through_80") is not True:
        gaps.append("Positive-frequency interval through 80 GHz, including the low-frequency limit, is not qualified")
    qualified = not gaps
    exact: dict[str, Any] = {}
    for ghz in (65, 80):
        found = [r for r in rows if r["frequency_hz"] == ghz * 1e9]
        exact[str(ghz)] = found[0] if found else {"status": "MISSING_EXACT_FREQUENCY", "frequency_hz": ghz * 1e9}
        if not found:
            gaps.append(f"Missing exact {ghz} GHz solve")
    band = [r for r in rows if 10e9 <= r["frequency_hz"] <= 65e9]
    band_valid = [r for r in band if r["differential"]["L_h"] is not None]
    l65 = exact["65"].get("differential", {}).get("L_h")
    criteria: dict[str, Any] = {}
    if l65 is None:
        criteria["L65"] = {"state": "INDETERMINATE", "nominal_state": "UNAVAILABLE"}
    else:
        lp = l65 * 1e12
        criteria["L65"] = {"value_pH": lp, "bounds_pH_inclusive": [114, 126], "uncertainty_pH": ul,
                            "signed_margin_pH": min(lp - 114, 126 - lp),
                            "nominal_state": "PASS" if 114 <= lp <= 126 else "FAIL",
                            "state": _interval_state(lp, ul, 114, 126) if qualified else "INDETERMINATE"}
    endpoints = {r["frequency_hz"] for r in band}
    if len(band_valid) != len(band) or not {10e9, 65e9}.issubset(endpoints):
        criteria["L10_65"] = {"state": "INDETERMINATE", "nominal_state": "UNCOVERED_BAND"}
        gaps.append("Missing band endpoint or finite in-band inductance sample")
    else:
        minimum = min(band_valid, key=lambda r: r["differential"]["L_h"])
        maximum = max(band_valid, key=lambda r: r["differential"]["L_h"])
        low_value, high_value = minimum["differential"]["L_h"] * 1e12, maximum["differential"]["L_h"] * 1e12
        states = [_interval_state(v, ul, 108, 132) for v in (low_value, high_value)]
        criteria["L10_65"] = {"sampled_minimum_pH": low_value, "sampled_minimum_frequency_hz": minimum["frequency_hz"],
                              "sampled_maximum_pH": high_value, "sampled_maximum_frequency_hz": maximum["frequency_hz"],
                              "bounds_pH_inclusive": [108, 132], "uncertainty_pH": ul,
                              "signed_margin_pH": min(low_value - 108, 132 - high_value),
                              "nominal_state": "PASS" if low_value >= 108 and high_value <= 132 else "FAIL",
                              "state": ("FAIL" if "FAIL" in states else "PASS" if all(s == "PASS" for s in states) else "INDETERMINATE") if qualified else "INDETERMINATE"}
    inductive = [r for r in rows if 0 < r["frequency_hz"] <= 80e9]
    finite_inductive = [r for r in inductive if r["differential"]["impedance"] is not None]
    if len(finite_inductive) != len(inductive) or not finite_inductive or exact["80"].get("status") == "MISSING_EXACT_FREQUENCY":
        criteria["inductive_through_80"] = {"state": "INDETERMINATE", "nominal_state": "UNCOVERED_INTERVAL"}
        gaps.append("Missing finite reactance within the requested inductive interval")
    else:
        nominal_worst = min(finite_inductive, key=lambda r: r["differential"]["impedance"]["imag_ohm"])
        covered = [row for row in finite_inductive if row["reactance_uncertainty"]["status"] == "FINITE"]
        if len(covered) != len(finite_inductive):
            gaps.append("Reactance uncertainty does not cover every supported positive-frequency sample through 80 GHz")
        limiting = min(covered, key=lambda r: r["differential"]["impedance"]["imag_ohm"] - r["reactance_uncertainty"]["absolute_uncertainty_ohm"]) if covered else nominal_worst
        x = limiting["differential"]["impedance"]["imag_ohm"]
        bound = limiting["reactance_uncertainty"]["absolute_uncertainty_ohm"]
        margin = x - bound if bound is not None else None
        supported_violation = any(row["differential"]["impedance"]["imag_ohm"] + row["reactance_uncertainty"]["absolute_uncertainty_ohm"] <= 0 for row in covered)
        state = "INDETERMINATE" if not qualified or len(covered) != len(finite_inductive) else "PASS" if margin is not None and margin > 0 else "FAIL" if supported_violation else "INDETERMINATE"
        criteria["inductive_through_80"] = {"sampled_minimum_reactance_ohm": nominal_worst["differential"]["impedance"]["imag_ohm"],
                                            "frequency_hz": limiting["frequency_hz"], "limiting_point_reactance_ohm": x,
                                            "uncertainty_ohm": bound, "signed_margin_ohm": margin,
                                            "uncertainty_convention": x_envelope["method"],
                                            "nominal_state": "PASS" if nominal_worst["differential"]["impedance"]["imag_ohm"] > 0 else "FAIL", "state": state}
    bad_physics = [r["frequency_hz"] for r in rows if r["passivity"]["state"] == "FAIL" or r["reciprocity"]["state"] == "FAIL"
                   or r["differential"]["Q"]["status"] == "NEGATIVE_DISSIPATION"]
    ill = [r["frequency_hz"] for r in rows if r["differential_solver"].get("ill_conditioned")]
    if bad_physics:
        gaps.append("Full-matrix passivity, reciprocity, or negative terminal dissipation requires investigation")
    if ill:
        gaps.append("Ill-conditioned impedance extraction requires investigation")
    crossings = []
    for first, second in zip(rows, rows[1:]):
        z1, z2 = first["differential"]["impedance"], second["differential"]["impedance"]
        if z1 is not None and z2 is not None and z1["imag_ohm"] > 0 and z2["imag_ohm"] <= 0:
            crossings.append({"lower_frequency_hz": first["frequency_hz"], "upper_frequency_hz": second["frequency_hz"],
                              "status": "BRACKET_ONLY_ZERO_OR_POLE_REQUIRES_REFINEMENT"})
    finite = [r for r in rows if r["differential"]["impedance"] is not None]
    peak = max(finite, key=lambda r: math.hypot(*r["differential"]["impedance"].values())) if finite else None
    if gaps:
        result = "INDETERMINATE"
        # No isolated criterion may look qualified while global material,
        # provenance, passivity, or conditioning evidence remains unresolved.
        for criterion in criteria.values():
            if criterion["state"] in ("PASS", "FAIL"):
                criterion["unqualified_numeric_state"] = criterion["state"]
                criterion["state"] = "INDETERMINATE"
    elif any(c["state"] == "FAIL" for c in criteria.values()):
        result = "FAIL"
    elif all(c["state"] == "PASS" for c in criteria.values()):
        result = "PASS"
    else:
        result = "INDETERMINATE"
    return {"schema_version": 1, "task_version_id": "rf-inductor-120ph-65g-em-r1",
            "network": {"ports": network.port_count, "reference_ohm": network.reference_ohm, "samples": len(rows),
                        "frequency_minimum_hz": float(network.frequency_hz[0]), "frequency_maximum_hz": float(network.frequency_hz[-1]),
                        "complete_N_port_preserved": True,
                        "data_classification": assembly.get("model_classification", "SOURCE_PROVENANCE_NOT_SUPPLIED"),
                        "complete_raw_network_preserved": bool(assembly_receipt) and all(item["kind"] == "actual" for item in provenance)},
            "extraction": {"definition": "Zd=Z11+Z22-Z12-Z21; I1=1 A,I2=-1 A; Icm=0",
                           "auxiliary_condition": "All additional signal port currents zero (open circuit)",
                           "grounded_diagnostic": "V2=0; I1=1 A; auxiliary currents zero; a different experiment",
                           "condition_warning": CONDITION_WARNING},
            "limits": {"passivity_eigenvalue_tolerance": PASSIVITY_TOLERANCE, "reciprocity_absolute_S_tolerance": RECIPROCITY_TOLERANCE},
            "sampling": sampling,
            "reactance_uncertainty_model": x_envelope,
            "frequency_protocol": {"name": "native-AFS-amendment-r1" if afs_protocol else "original-explicit-interface",
                                   "supplied_protocol": protocol, "reserved_L_uncertainty_fraction": reserve,
                                   "required_actual_frequency_hz": list(actual_required),
                                   "final_qualification_requires_explicit_protocol": True},
            "final_qualification_status": result if afs_protocol else "LEGACY_NUMERIC_INTERFACE_ONLY",
            "model_provenance": assembly_receipt if assembly_receipt is not None else {"status": "NOT_SUPPLIED"},
            "exact_GHz": exact, "criteria": criteria, "device_target_result": result,
            "study_completion": "INCOMPLETE" if gaps else "COMPLETE", "gaps": gaps,
            "full_filter_acceptance": "NOT EVALUATED", "InP_qualification": "NOT CLAIMED",
            "resonance": {"crossing_brackets": crossings, "first_terminal_SRF": "UNRESOLVED_BRACKET" if crossings else "NO_CROSSING_OBSERVED_AT_SAMPLES",
                          "searched_sample_range_hz": [float(network.frequency_hz[0]), float(network.frequency_hz[-1])],
                          "sampled_impedance_peak_frequency_hz": peak["frequency_hz"] if peak else None,
                          "sampled_impedance_peak_ohm": math.hypot(*peak["differential"]["impedance"].values()) if peak else None,
                          "note": "Samples do not establish a continuous SRF lower bound or distinguish a zero from a pole"},
            "physics_investigation_frequencies_hz": bad_physics, "ill_conditioned_frequencies_hz": ill,
            "operator_uncertainty_input": evidence, "points": rows}


def write_outputs(report: dict[str, Any], output: Path, plots: bool = True) -> None:
    output.mkdir(parents=True, exist_ok=False)
    (output / "analysis.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with (output / "metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["frequency_hz", "extraction_status", "L_pH", "R_ohm", "X_ohm", "Q_status", "Q", "grounded_L_pH", "passivity_min_eigenvalue", "reciprocity_max_S_error"])
        for row in report["points"]:
            d, g = row["differential"], row["grounded_terminal_2"]
            writer.writerow([row["frequency_hz"], d["status"], d["L_h"] * 1e12 if d["L_h"] is not None else "", d["R_ohm"],
                             d["impedance"]["imag_ohm"] if d["impedance"] else "", d["Q"]["status"], d["Q"]["value"],
                             g["L_h"] * 1e12 if g["L_h"] is not None else "", row["passivity"]["minimum_eigenvalue"], row["reciprocity"]["maximum_absolute_S_error"]])
    if plots:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return
        frequency = [r["frequency_hz"] / 1e9 for r in report["points"]]
        fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
        for ax, key, label, factor in [(axes[0, 0], "L_h", "End-to-end L (pH)", 1e12), (axes[0, 1], "R_ohm", "End-to-end R (ohm)", 1)]:
            ax.plot(frequency, [r["differential"][key] * factor if r["differential"][key] is not None else np.nan for r in report["points"]], marker=".")
            ax.set_ylabel(label)
        axes[0, 0].axhspan(114, 126, color="green", alpha=0.12)
        axes[1, 0].plot(frequency, [r["differential"]["Q"]["value"] if r["differential"]["Q"]["value"] is not None else np.nan for r in report["points"]], marker=".")
        axes[1, 0].set_ylabel("Signed impedance Q")
        axes[1, 1].plot(frequency, [r["differential"]["impedance"]["imag_ohm"] if r["differential"]["impedance"] else np.nan for r in report["points"]], marker=".")
        axes[1, 1].set_ylabel("End-to-end reactance (ohm)")
        axes[1, 1].axhline(0, color="black", linewidth=0.6)
        for ax in axes.flat:
            ax.set_xlabel("Frequency (GHz)")
            ax.grid(alpha=0.25)
            ax.axvline(65, color="gray", linewidth=0.6)
            ax.axvline(80, color="gray", linewidth=0.6, linestyle="--")
        fig.suptitle("Icm=0; auxiliary signal ports open; assumed research stack")
        fig.savefig(output / "characterization.png", dpi=180)
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--uncertainty-json", type=Path)
    parser.add_argument("--assembly-receipt", type=Path, help="Assembly receipt whose output integrity and per-point origins match this model")
    parser.add_argument("--protocol", type=Path, help="Explicit adopted frequency protocol; final qualification uses the native AFS amendment")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    try:
        network = read_touchstone(args.input)
        uncertainty = read_operator_evidence(args.uncertainty_json) if args.uncertainty_json else None
        if uncertainty is not None and not isinstance(uncertainty, dict):
            raise NetworkError("Uncertainty input must be a JSON object")
        assembly = read_assembly_receipt(args.assembly_receipt, args.input, network) if args.assembly_receipt else None
        protocol = json.loads(args.protocol.read_text(encoding="utf-8-sig")) if args.protocol else None
        if protocol is not None:
            if not isinstance(protocol, dict):
                raise NetworkError("The supplied protocol must be a JSON object")
            source = args.protocol.read_bytes()
            protocol["protocol_source"] = {"path": str(args.protocol.resolve()), "bytes": len(source), "sha256": hashlib.sha256(source).hexdigest()}
        if assembly is None:
            header = args.input.read_text(encoding="utf-8-sig").split("#", 1)[0].upper()
            if "COMPOSITE" in header or "DERIVED_DC_ANCHOR" in header or ("AFS" in header and any(word in header for word in ("DERIVED", "RATIONAL", "INTERPOLATED"))):
                raise NetworkError("A derived/composite model requires its assembly receipt; do not treat its display grid as actual solves")
        report = analyze_network(network, uncertainty, assembly_receipt=assembly, protocol=protocol)
        if protocol is None:
            report["legacy_numeric_target_result"] = report["device_target_result"]
            report["device_target_result"] = "INDETERMINATE"
            report["study_completion"] = "INCOMPLETE"
            report["final_qualification_status"] = "NOT_EVALUATED_WITHOUT_EXPLICIT_PROTOCOL"
            report["gaps"].append("Final qualification requires the explicit adopted frequency protocol; this invocation is characterization only")
            for criterion in report["criteria"].values():
                if criterion["state"] in ("PASS", "FAIL"):
                    criterion["unqualified_numeric_state"] = criterion["state"]
                    criterion["state"] = "INDETERMINATE"
        # Validate serialization before creating any output.
        json.dumps(report, allow_nan=False)
        write_outputs(report, args.output_dir, plots=not args.no_plots)
    except (NetworkError, ValueError, OSError, np.linalg.LinAlgError) as exc:
        parser.error(str(exc))
    print(f"Analyzed {network.port_count} ports, {len(network.frequency_hz)} samples; device {report['device_target_result']}")


if __name__ == "__main__":
    main()
