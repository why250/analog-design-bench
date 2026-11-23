"""Audit retained Stage 2 evidence and create portable, hashed ZIP handoffs.

No ADS session is opened. Saved raw data are retained, and complex exports are
rechecked from the declared coefficients. A completion ledger is an output of
the audit, never its proof. Archives exclude machine configuration and locks.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import uuid
import zipfile

import numpy as np

try:
    from . import analysis, cases, model, units, project_config
except ImportError:
    import analysis
    import cases
    import model
    import units
    import project_config

TASK = "inp-passive-lpf-65g-nonideal-lc-feasibility"
BASELINE_TASK = "inp-passive-lpf-65g-50ohm-80g-stop20"
METRICS = ("s11_worst", "s22_worst", "il_worst", "s21_80")
MANIFEST_NAME = "evidence-manifest.json"


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _read(path):
    def reject(value):
        raise ValueError("Nonfinite JSON constant: " + value)
    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Nonfinite JSON number: " + value)
        return result
    with Path(path).open(encoding="utf-8-sig") as stream:
        return json.load(stream, parse_constant=reject, parse_float=finite_float)


def _write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                          encoding="utf-8", newline="\n")


def _sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def _time(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Evidence timestamp has no UTC offset")
    return result.astimezone(timezone.utc)


def _rel(path, parent):
    return Path(path).relative_to(parent).as_posix()


def _safe_file(path, parent, *, allow_empty=False):
    path, parent = Path(path), Path(parent).resolve()
    if path.is_symlink() or path.resolve().is_relative_to(parent) is False:
        raise ValueError("Symlink or escaping file path: " + str(path))
    for ancestor in path.parents:
        if ancestor == parent:
            break
        if ancestor.is_symlink():
            raise ValueError("Symlink ancestor: " + str(path))
    if not path.is_file() or (not allow_empty and path.stat().st_size <= 0):
        raise ValueError("Missing or empty evidence file: " + str(path))
    return path


def _excluded(relative):
    p = PurePosixPath(str(relative).replace("\\", "/"))
    parts = [v.lower() for v in p.parts]
    name = p.name.lower()
    return (any(v in {".local", ".codex", ".git", "__pycache__", ".transfer"} for v in parts)
            or ".cdslck" in name or name.startswith(".ads_lock")
            or p.suffix.lower() in {".lck", ".prf", ".pyc", ".pyo"}
            or name in {"saved.wrkstate", "reproduction-workspaces.json"}
            or name.startswith(".env") or name in {"config.toml", "id_rsa", "id_ed25519"})


def _run_excluded(relative):
    """Keep live scratch and prior handoffs outside an evidence inventory."""
    parts = PurePosixPath(str(relative).replace("\\", "/")).parts
    return bool(parts and parts[0].lower() in {"handoff", "work", "legacy", "legacy-project"}) or _excluded(relative)


def _evidence_files(root, *, output_dir=None):
    """Prune excluded run subtrees before walking their potentially large data."""
    root = Path(root).resolve()
    output = Path(output_dir).resolve() if output_dir is not None else None
    for parent, directories, names in os.walk(root, followlinks=False):
        parent = Path(parent)
        directories[:] = [name for name in directories
                          if not _run_excluded(_rel(parent / name, root))
                          and not (output is not None and (parent / name).resolve().is_relative_to(output))]
        for name in sorted(names):
            path = parent / name
            if not _run_excluded(_rel(path, root)) and not (output is not None and path.resolve().is_relative_to(output)):
                yield path


def _inventory(root, *, output_dir=None):
    rows = []
    for path in sorted(_evidence_files(root, output_dir=output_dir)):
        if not path.is_file():
            continue
        relative = _rel(path, root)
        if (relative == MANIFEST_NAME and output_dir is None) or _run_excluded(relative):
            continue
        if output_dir is not None and Path(path).resolve().is_relative_to(Path(output_dir).resolve()):
            continue
        _safe_file(path, root, allow_empty=True)
        rows.append({"path": relative, "bytes": path.stat().st_size, "sha256": _sha(path)})
    return rows


def _require(directory, names):
    return [_safe_file(Path(directory) / name, directory) for name in names]


def _logs(directory):
    # edatoolbox commonly retains circ*.ckt.out rather than logFile.txt.
    result = [p for p in Path(directory).iterdir() if p.is_file() and
              (p.name.lower() in {"logfile.txt", "simulator.log", "simulation.log"}
               or p.name.lower().endswith(".ckt.out"))]
    if not result:
        raise ValueError("Missing retained ADS simulator log")
    return [_safe_file(p, directory).name for p in result]


def _sources(directory, settings):
    inputs = Path(directory) / "source-inputs"
    hashes = settings.get("source_hashes")
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("No captured Python source hashes")
    for name, expected in hashes.items():
        if Path(name).name != name:
            raise ValueError("Unsafe source hash path")
        source = _safe_file(inputs / name, directory)
        if _sha(source) != expected:
            raise ValueError("Captured source hash mismatch: " + name)
    native = inputs / "native"
    native_files = [p for p in native.rglob("*") if p.is_file()]
    if not native_files or not any(p.name == ".oalib" for p in native_files):
        raise ValueError("Native OA source or .oalib library metadata missing")
    for path in native_files:
        _safe_file(path, directory)
    testbench = settings.get("testbench", "").split(":")
    if len(testbench) != 3:
        raise ValueError("Captured testbench view is unspecified")
    library, cell, _ = testbench
    _safe_file(native / library / cell / "schematic" / "sch.oa", directory)
    if cell == "inp_lpf_sp":
        _safe_file(native / library / "inp_lpf" / "schematic" / "sch.oa", directory)
        _safe_file(native / library / "inp_lpf" / "symbol" / "symbol.oa", directory)
    return {"source_files": len(hashes), "python_sources": sum(name.endswith(".py") for name in hashes),
            "native_files": len(native_files)}


def _touchstone(path, f, s, ports=2):
    rows, option = [], None
    with Path(path).open(encoding="utf-8-sig") as stream:
        for line in stream:
            line = line.split("!", 1)[0].strip()
            if not line:
                continue
            if line.startswith("#"):
                option = line[1:].upper().split()
            elif not line.startswith("["):
                rows.extend(float(v) for v in line.split())
    if option != ["HZ", "S", "RI", "R", "50"]:
        raise ValueError("Touchstone is not explicit Hz/S/RI/50-ohm data")
    width = 9 if ports == 2 else 3
    if len(rows) % width:
        raise ValueError("Incomplete Touchstone record")
    data = np.array(rows).reshape(-1, width)
    if len(data) != len(f) or not np.isfinite(data).all():
        raise ValueError("Touchstone frequency count or finiteness differs from CSV")
    if np.max(abs(data[:, 0] - f)) > 1:
        raise ValueError("Touchstone frequencies differ from CSV")
    if ports == 2:
        actual = np.empty((len(f), 2, 2), complex)
        for j, outp, inp in ((1, 0, 0), (3, 1, 0), (5, 0, 1), (7, 1, 1)):
            actual[:, outp, inp] = data[:, j] + 1j * data[:, j + 1]
    else:
        actual = data[:, 1] + 1j * data[:, 2]
    error = float(np.max(abs(actual - s)))
    if error > 1e-8:
        raise ValueError("Touchstone complex S disagrees with CSV")
    return {"frequency_count": len(f), "maximum_complex_difference": error,
            "reference_impedance_ohm": 50}


def _native_circuit(netlist, manifest):
    match = re.search(r"define\s+inp_lpf\s*\(\s*rfin\s+rfout\s+gnd\s*\)(.*?)end\s+inp_lpf", netlist, re.S)
    if not match:
        raise ValueError("Native DUT signature or boundary differs")
    primitives = {}
    for line in match.group(1).splitlines():
        tokens = line.split()
        if tokens and re.match(r"^[A-Za-z_][\w]*:", tokens[0]):
            kind, name = tokens[0].split(":", 1)
            if kind not in {"R", "L", "C"} or len(tokens) < 3 or name in primitives:
                raise ValueError("Unexpected or duplicate DUT primitive: " + tokens[0])
            primitives[name] = (kind, tokens[1:3], line)
    expected = set()
    ladder = ["rfin", "n1", "n2", "n3", "n4", "rfout"]
    internal = []

    def primitive(name, kind, value):
        actual_kind, nodes, line = primitives[name]
        coefficient = re.search(rf"\b{kind}=([^\s]+)\s+(H|F|Ohm)\b", line)
        units_expected = {"L": "H", "C": "F", "R": "Ohm"}[kind]
        if actual_kind != kind or coefficient is None or float(coefficient.group(1)) != value or coefficient.group(2) != units_expected:
            raise ValueError("Native SI coefficient or unit mismatch: " + name)
        expected.add(name)
        return nodes, line

    for e in manifest["elements"]:
        name, kind, number = e["name"], e["kind"], int(e["name"][1:])
        nodes, line = primitive(name, kind, e["value_si"])
        if kind == "L":
            arm = {ladder[number - 1], ladder[number]}
            if set(nodes) != arm:
                raise ValueError("Native series arm connection mismatch: " + name)
            rs = re.search(r"\bR=([^\s]+)\s+Ohm\b", line)
            if rs is None or float(rs.group(1)) != e["rs_ohm"]:
                raise ValueError("Native inductor Rs mismatch: " + name)
            if e["cp_f"]:
                cp_nodes, _ = primitive(name + "_Cp", "C", e["cp_f"])
                if set(cp_nodes) != arm:
                    raise ValueError("Cp does not span its two ladder terminals")
        else:
            chain = []
            if e["esr_ohm"]:
                chain.append((name + "_ESR", "R", e["esr_ohm"]))
            if e["esl_h"]:
                chain.append((name + "_ESL", "L", e["esl_h"]))
            chain.append((name, "C", e["value_si"]))
            cursor = ladder[number]
            for index, (part, part_kind, value) in enumerate(chain):
                nodes, part_line = primitive(part, part_kind, value)
                if cursor not in nodes or nodes[0] == nodes[1]:
                    raise ValueError("Broken shunt series chain: " + part)
                cursor = nodes[1] if nodes[0] == cursor else nodes[0]
                if part_kind == "L":
                    rs = re.search(r"\bR=([^\s]+)\s+Ohm\b", part_line)
                    if rs is None or float(rs.group(1)) != 0:
                        raise ValueError("Undeclared ESL series loss")
                if index < len(chain) - 1:
                    if cursor in ladder + ["gnd"]:
                        raise ValueError("Shunt internal node shorts a DUT terminal")
                    internal.append(cursor)
            if cursor != "gnd":
                raise ValueError("Shunt branch does not return to DUT gnd")
    if set(primitives) != expected or len(internal) != len(set(internal)):
        raise ValueError("Extra primitive or shared shunt internal node")
    for port, node in ((1, "rfin"), (2, "rfout")):
        line = next((l for l in netlist.splitlines() if l.startswith(f"Port:Term{port} ")), "")
        if line.split()[1:3] != [node, "0"] or f"Num={port}" not in line or "Z=50 Ohm" not in line:
            raise ValueError("External 50-ohm bench port mismatch")
    return {"ok": True, "primitive_count": len(primitives)}


def _prediction_timing(directory, prediction, settings):
    if prediction.get("phase") != "before ADS simulation":
        raise ValueError("Original prediction is not recorded as pre-simulation")
    if _time(prediction["recorded_utc"]) > _time(settings["created_utc"]):
        raise ValueError("Prediction timestamp follows simulation settings")
    return {"prediction_utc": prediction["recorded_utc"], "settings_utc": settings["created_utc"],
            "pre_simulation_order": True}


def _case(directory, request, *, derived_recheck=True):
    directory = Path(directory)
    _require(directory, ("manifest.json", "request.json", "settings.json", "prediction.json",
                         "summary.json", "schematic.net", "ads_sparameters.csv", "inp_lpf.s2p",
                         "inp_lpf_sp.ds", "refinement-history.json", "dataset-analysis-counts.json",
                         "refinement-round-0.csv", "refinement-round-1.csv", "refinement-round-2.csv"))
    logs = _logs(directory)
    manifest, retained = _read(directory / "manifest.json"), _read(directory / "request.json")
    settings, pred, summary = (_read(directory / n) for n in ("settings.json", "prediction.json", "summary.json"))
    model.validate(manifest)
    physical = model.physical_hash(manifest)
    if physical != model.physical_hash(request["manifest"]) or retained.get("case_id") != request["case_id"]:
        raise ValueError("Retained case differs from its canonical request")
    if settings.get("physical_sha256") != physical or settings.get("reference_impedance_ohm") != 50:
        raise ValueError("Settings physical manifest or port impedance mismatch")
    if settings.get("ordered_ports") != ["rfin", "rfout", "gnd"]:
        raise ValueError("Settings ordered DUT terminals differ")
    saved_hash = _sha(directory / "schematic.net")
    if saved_hash != settings.get("netlist_saved_bytes_sha256"):
        raise ValueError("Saved generated netlist byte hash mismatch")
    native = _native_circuit((directory / "schematic.net").read_text(encoding="utf-8-sig"), manifest)
    sources = _sources(directory, settings)
    timing = _prediction_timing(directory, pred, settings)
    original_prediction_bound = pred.get("physical_sha256") == physical
    if pred.get("physical_sha256") not in (None, physical):
        raise ValueError("Original prediction is bound to a different physical case")
    if not original_prediction_bound:
        pred = analysis.predict(manifest)
    history = _read(directory / "refinement-history.json")
    if not isinstance(history, list) or len(history) < 3:
        raise ValueError("Fewer than three retained measured refinement rounds")
    recalculated_history = []
    for index, entry in enumerate(history):
        source = entry.get("source_csv", f"refinement-round-{index}.csv")
        if Path(source).name != source:
            raise ValueError("Unsafe refinement source path")
        f, s = analysis.read_csv(directory / source)
        measured = analysis.measured_round(f, s, pred, entry["maximum_spacing_hz"])
        measured["source_csv"] = source
        recalculated_history.append(measured)
    f, s = analysis.read_csv(directory / "ads_sparameters.csv")
    checked = analysis.verify(f, s, manifest, prediction=pred, refinement_history=recalculated_history)
    if checked.get("state") not in {"PASS", "FAIL"} or checked["state"] != summary.get("state"):
        raise ValueError("Current independent recheck is unresolved or differs from retained candidate state")
    if not checked.get("coverage", {}).get("continuous_band_justified") or not checked.get("physics", {}).get("ok"):
        raise ValueError("Current numerical/physical prerequisites are unresolved")
    if any(checked.get("metrics", {}).get(k, {}).get("state") not in {"PASS", "FAIL"} for k in METRICS):
        raise ValueError("At least one mandatory metric remains unresolved")
    for name in METRICS:
        before, after = summary.get("metrics", {}).get(name, {}), checked["metrics"][name]
        if before.get("state") != after.get("state") or before.get("magnitude") is None or abs(before["magnitude"] - after["magnitude"]) > 1e-8:
            raise ValueError("Retained metric disagrees with current export remeasurement: " + name)
    touchstone = _touchstone(directory / "inp_lpf.s2p", f, s)
    if derived_recheck and not original_prediction_bound:
        _write(directory / "handoff-derived-recheck.json", {
            "created_utc": _utc(), "scope": "Post-run derived audit; original pre-run prediction, raw evidence and summary remain unchanged",
            "reason": "Original prediction preceded the physical-hash binding field",
            "analysis_source_sha256": _sha(Path(analysis.__file__)),
            "original_prediction_sha256": _sha(directory / "prediction.json"),
            "original_evidence_preserved": True, "current_prediction": pred, "current_verification": checked})
    return {"case_id": request["case_id"], "state": checked["state"], "physical_sha256": physical,
            "netlist_saved_bytes_sha256": saved_hash, "sources": sources, "native": native,
            "prediction_timing": timing, "original_prediction_hash_bound": original_prediction_bound,
            "simulator_logs": logs, "touchstone": touchstone,
            "complex_crosscheck_error": checked["physics"]["complex_error_max"]}


def _unit(directory, request):
    directory = Path(directory)
    _require(directory, ("manifest.json", "settings.json", "prediction.json", "summary.json",
                         "schematic.net", "ads_sparameters.csv", "unit_device.s1p",
                         "unit_device_sp.ds", "device-response.csv", "dataset-analysis-counts.json"))
    logs = _logs(directory)
    manifest, settings, pred, summary = (_read(directory / n) for n in
                                         ("manifest.json", "settings.json", "prediction.json", "summary.json"))
    if manifest.get("element") != request["element"] or manifest.get("unit_id") != request["unit_id"]:
        raise ValueError("Retained unit element differs from frozen unit schedule")
    if settings.get("reference_impedance_ohm") != 50 or settings.get("netlist_saved_bytes_sha256") != _sha(directory / "schematic.net"):
        raise ValueError("Unit reference impedance or saved netlist hash mismatch")
    units._audit_netlist((directory / "schematic.net").read_text(encoding="utf-8-sig"), request["element"])
    sources = _sources(directory, settings)
    timing = _prediction_timing(directory, pred, settings)
    with (directory / "ads_sparameters.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["freq_hz", "s11_real", "s11_imag"]:
            raise ValueError("Unexpected one-port export columns")
        data = np.array([[float(row[k]) for k in reader.fieldnames] for row in reader])
    if data.ndim != 2 or data.shape[1] != 3:
        raise ValueError("Empty/malformed unit CSV")
    f, s = data[:, 0], data[:, 1] + 1j * data[:, 2]
    checked, _ = units.verify_unit(f, s, request["element"])
    if summary.get("state") != "VALID" or checked["state"] != "VALID":
        raise ValueError("Unit equations or numerical checks are invalid")
    touchstone = _touchstone(directory / "unit_device.s1p", f, s, ports=1)
    return {"unit_id": request["unit_id"], "state": "VALID", "sources": sources,
            "prediction_timing": timing, "simulator_logs": logs, "touchstone": touchstone,
            "maximum_complex_equation_error": checked["max_complex_s11_error"]}


def _reproduction(root, row, *, derived_recheck=True):
    repeated = root / "reproductions" / row["request_id"]
    original = root / "cases" / row["case_id"]
    checked = _case(repeated, row, derived_recheck=derived_recheck)
    _require(repeated, ("comparison.json", "settings-exact-differences.json", "portable-native-manifest.json"))
    # An exact identical netlist has an intentionally empty diff.
    _safe_file(repeated / "netlist-exact.diff", repeated, allow_empty=True)
    comparison, portable = _read(repeated / "comparison.json"), _read(repeated / "portable-native-manifest.json")
    if not comparison.get("comparison_passed") or not all(comparison.get("checks", {}).values()):
        raise ValueError("E9 comparison checks are incomplete or failed")
    if not portable.get("snapshot_after_workspace_release") or portable.get("remaining_oa_lock_files"):
        raise ValueError("E9 portable source was not released from OA locks")
    files = portable.get("files", [])
    if not files or not any(r["path"].endswith(".oalib") for r in files):
        raise ValueError("E9 portable source manifest is incomplete")
    for entry in files:
        path = PurePosixPath(entry["path"])
        if path.is_absolute() or ".." in path.parts or _excluded(path):
            raise ValueError("Unsafe portable native manifest path")
        source = _safe_file(repeated / "portable-native" / Path(*path.parts), repeated)
        if source.stat().st_size != entry["bytes"] or _sha(source) != entry["sha256"]:
            raise ValueError("Portable native source hash mismatch")
    actual_files = {_rel(p, repeated / "portable-native") for p in (repeated / "portable-native").rglob("*") if p.is_file()}
    if actual_files != {entry["path"] for entry in files}:
        raise ValueError("Portable native manifest does not cover every actual file")
    if any(_excluded(name) for name in actual_files):
        raise ValueError("Portable native snapshot includes lock/preferences/configuration")
    f0, s0 = analysis.read_csv(original / "ads_sparameters.csv")
    f1, s1 = analysis.read_csv(repeated / "ads_sparameters.csv")
    if len(f0) != len(f1) or np.max(abs(f0-f1)) > 1 or np.max(abs(s0-s1)) > 1e-6:
        raise ValueError("E9 actual complex data or frozen frequency list does not reproduce")
    original_settings, repeated_settings = _read(original / "settings.json"), _read(repeated / "settings.json")
    if original_settings.get("sweeps") != repeated_settings.get("sweeps"):
        raise ValueError("E9 resolved sweep settings differ")
    if model.physical_hash(_read(original / "manifest.json")) != checked["physical_sha256"]:
        raise ValueError("E9 actual coefficients differ")
    critical = ["model.py", "build_ads.py"]
    for name in ("ads_support.py",):
        if (original / "source-inputs" / name).exists() or (repeated / "source-inputs" / name).exists():
            critical.append(name)
    for name in critical:
        if _sha(original / "source-inputs" / name) != _sha(repeated / "source-inputs" / name):
            raise ValueError("E9 native reconstruction source differs: " + name)
    if not comparison.get("netlist", {}).get("acceptable_identity"):
        raise ValueError("E9 generated netlist identity is unresolved")
    def executable_lines(path):
        return [line for line in Path(path).read_text(encoding="utf-8-sig").splitlines()
                if line.strip() and not line.lstrip().startswith(";")]
    if executable_lines(original / "schematic.net") != executable_lines(repeated / "schematic.net"):
        raise ValueError("E9 actual executable netlist statements differ")
    if comparison["netlist"].get("original_saved_bytes_sha256") != _sha(original / "schematic.net") or comparison["netlist"].get("repeated_saved_bytes_sha256") != _sha(repeated / "schematic.net"):
        raise ValueError("E9 comparison hashes do not identify actual saved netlists")
    checked.update({"request_id": row["request_id"], "portable_native_files": len(files),
                    "maximum_frequency_difference_hz": float(np.max(abs(f0-f1))),
                    "maximum_complex_s_difference": float(np.max(abs(s0-s1)))})
    return checked


def audit(root, *, output_dir=None):
    """Recheck actual retained evidence; write inventory and derived completion flag.

    Returns a finite report with ``ok`` and detailed issues. An incomplete run
    is audited without raising merely for missing case evidence. Supplying a
    separate ``output_dir`` makes the evidence tree strictly read-only: the
    audit, inventory and derived ledger are written only to that directory.
    This mode is required when validating migrated completed records.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("Study root does not exist")
    destination = root if output_dir is None else Path(output_dir).resolve()
    if output_dir is not None and destination == root:
        raise ValueError("Read-only audit output_dir must differ from the evidence root")
    if output_dir is not None and destination.is_relative_to(root):
        if destination.relative_to(root).parts[0] not in {"handoff", "derived"}:
            raise ValueError("In-run audit outputs belong under handoff/ or derived/, outside original evidence subtrees")
    readonly = output_dir is not None
    destination.mkdir(parents=True, exist_ok=True)
    report = {"created_utc": _utc(), "ok": False, "issues": [], "cases": [],
              "units": [], "reproductions": [], "evidence_read_only": readonly,
              "scope": "Saved evidence and independent exported-data recheck; no ADS session or official verifier"}

    def check(label, function):
        try:
            return function()
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError, StopIteration, IndexError) as exc:
            report["issues"].append(label + ": " + type(exc).__name__ + ": " + str(exc))
            return None

    mapping = check("requests", lambda: _read(root / "requests.json")) or {}
    rows = mapping.get("requests", []) if isinstance(mapping, dict) else mapping
    if not isinstance(rows, list):
        report["issues"].append("requests: mapping is not a list")
        rows = []
    expected = {r["request_id"]: r for r in cases.requests()}
    actual = {r.get("request_id"): r for r in rows}
    if len(actual) != len(rows) or expected.keys() - actual.keys():
        report["issues"].append("Missing or duplicate mandatory initial request mappings")
    canonical = {}
    for row in rows:
        def validate_row(row=row):
            model.validate(row["manifest"])
            physical = model.physical_hash(row["manifest"])
            if physical != row.get("physical_sha256"):
                raise ValueError("Request physical hash differs from resolved coefficients")
            if row["request_id"] in expected and physical != expected[row["request_id"]]["physical_sha256"]:
                raise ValueError("Initial request differs from the required deterministic schedule")
            if row["case_id"] in canonical and canonical[row["case_id"]]["physical_sha256"] != physical:
                raise ValueError("Canonical case ID aliases different physical circuits")
            canonical.setdefault(row["case_id"], row)
        check("request " + str(row.get("request_id")), validate_row)
    for case_id, row in canonical.items():
        value = check("case " + case_id, lambda row=row: _case(root / "cases" / row["case_id"], row, derived_recheck=not readonly))
        if value:
            report["cases"].append(value)
    unit_mapping = check("unit schedule", lambda: _read(root / "unit-requests.json")) or {}
    unit_rows = unit_mapping.get("requests", [])
    if unit_rows != units.schedule() or len(unit_rows) != 55:
        report["issues"].append("Frozen 55-request unit schedule differs or is incomplete")
    for row in unit_rows:
        value = check("unit " + row["unit_id"], lambda row=row: _unit(root / "units" / row["unit_id"], row))
        if value:
            report["units"].append(value)
    repetitions = mapping.get("e9_repetitions", []) if isinstance(mapping, dict) else []
    expected_repetitions = (check("mandatory E9 selections", lambda: cases.repetition_requests(rows)) or []) if rows else []
    if len(repetitions) != 3 or [r.get("request_id") for r in repetitions] != [r["request_id"] for r in expected_repetitions]:
        report["issues"].append("Three frozen E9 repetition mappings missing or changed")
    for row in repetitions:
        value = check("reproduction " + row["request_id"], lambda row=row: _reproduction(root, row, derived_recheck=not readonly))
        if value:
            report["reproductions"].append(value)
    boundaries = check("boundary search", lambda: _read(root / "boundary-search.json")) or {}
    if boundaries.get("complete") is not True or set(boundaries.get("slices", {})) != {"q", "f_l0_hz", "esr_ohm", "esl_h"}:
        report["issues"].append("Four adaptive E8 slices are unresolved")
    for axis, slice_data in boundaries.get("slices", {}).items():
        selected = [r for r in rows if r.get("family") == "E8" and r.get("labels", {}).get("axis") == axis]
        expected_ids = {r["request_id"] for r in selected}
        actual_ids = {r.get("request_id") for r in slice_data.get("nodes", [])}
        adaptive_count = sum(bool(r.get("labels", {}).get("adaptive")) for r in selected)
        if not slice_data.get("complete") or not slice_data.get("valid_nodes_resolved") or expected_ids != actual_ids or slice_data.get("seed_count") != 5 or adaptive_count > 5 or slice_data.get("adaptive_count") != adaptive_count:
            report["issues"].append("E8 slice accounting differs from actual required requests: " + axis)
    aggregate = check("aggregate", lambda: _read(root / "aggregate.json")) or {}
    selections = aggregate.get("deep_dive_selections", {})
    if len(selections) != 4:
        report["issues"].append("Four required deep-dive selections missing")
    for label, selected in selections.items():
        def deep(label=label, selected=selected):
            path = root / "deep_dive" / label
            diagnostics = _read(path / "diagnostics.json")
            if not diagnostics.get("ok") or diagnostics.get("case_ids") != selected:
                raise ValueError("Deep-dive diagnostic selection/checks differ")
            for case_id in selected:
                _require(path, tuple(case_id + suffix for suffix in ("-response.png", "-inductors.png", "-poles.png")))
                item = next(c for c in diagnostics["cases"] if c["case_id"] == case_id)
                if not item.get("poles", {}).get("residuals_ok"):
                    raise ValueError("Actual rational pole residuals unresolved")
        check("deep dive " + label, deep)
    check("learning record", lambda: _safe_file(root / "learning.md", root))
    def family_predictions():
        value = _read(_safe_file(root / "pre-run-predictions.json", root))
        if set(value.get("predictions", {})) != {f"E{i}" for i in range(10)}:
            raise ValueError("All ten family predictions are not retained")
        simulation_times = [c["prediction_timing"]["settings_utc"] for c in report["cases"] + report["units"]]
        if not simulation_times or _time(value["recorded_utc"]) > min(_time(v) for v in simulation_times):
            raise ValueError("Family predictions were not recorded before the earliest retained simulation settings")
        return True
    check("pre-run family predictions", family_predictions)
    report["request_count"] = len(rows)
    report["unique_required_case_count"] = len(canonical)
    report["validated_case_count"] = len(report["cases"])
    report["validated_unit_count"] = len(report["units"])
    report["validated_reproduction_count"] = len(report["reproductions"])
    report["ok"] = bool(not report["issues"] and len(canonical) > 0 and len(report["cases"]) == len(canonical)
                         and len(report["units"]) == 55 and len(report["reproductions"]) == 3)
    ledger_path = root / "study_checks.json"
    ledger = _read(ledger_path) if ledger_path.exists() else {}
    ledger["evidence_manifest_complete"] = report["ok"]
    ledger["evidence_manifest_audit"] = {"ok": report["ok"], "audit": "handoff-audit.json",
                                         "created_utc": report["created_utc"], "issue_count": len(report["issues"])}
    _write(destination / "study_checks.json", ledger)
    _write(destination / "handoff-audit.json", report)
    inventory = _inventory(root, output_dir=destination if readonly else None)
    inventory_hash = hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    _write(destination / MANIFEST_NAME, {"created_utc": _utc(), "audit_ok": report["ok"],
        "scope": "Allowed retained evidence files; live work, prior handoffs, machine configuration and locks are excluded. Paths are relative to the evidence root.",
        "files": inventory, "file_count": len(inventory), "total_bytes": sum(r["bytes"] for r in inventory),
        "inventory_sha256": inventory_hash})
    report["manifest"] = MANIFEST_NAME
    report["file_count"] = len(inventory)
    report["total_bytes"] = sum(r["bytes"] for r in inventory)
    report["output_directory"] = str(destination)
    return report


def _archive(path, files, extra=None):
    """Write a fresh ZIP and a member manifest, rejecting escaping/duplicate names."""
    path = Path(path)
    if path.exists():
        raise FileExistsError("Archive already exists: " + str(path))
    seen, members = set(), []
    def safe_member(name):
        member = PurePosixPath(name)
        if "\\" in name or member.is_absolute() or ".." in member.parts or not member.parts or ":" in member.parts[0] or _excluded(member):
            raise ValueError("Unsafe archive member: " + name)
        if name in seen or name == "bundle-manifest.json":
            raise ValueError("Duplicate or reserved archive member: " + name)
        seen.add(name)
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for source, name in sorted(files, key=lambda item: item[1]):
            safe_member(name)
            if Path(source).is_symlink():
                raise ValueError("Symlink cannot be archived")
            archive.write(source, arcname=name)
            members.append({"path": name, "bytes": Path(source).stat().st_size, "sha256": _sha(source)})
        for name, value in (extra or {}).items():
            safe_member(name)
            data = value.encode("utf-8")
            archive.writestr(name, data)
            members.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        manifest = {"created_utc": _utc(), "files": members, "file_count": len(members),
                    "scope": "Exact ZIP members except bundle-manifest.json itself"}
        archive.writestr("bundle-manifest.json", json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    with zipfile.ZipFile(path) as archive:
        corrupt = archive.testzip()
        if corrupt is not None:
            raise ValueError("Archive CRC verification failed: " + corrupt)
        for row in members:
            if hashlib.sha256(archive.read(row["path"])).hexdigest() != row["sha256"]:
                raise ValueError("Archive member hash verification failed")
    return {"path": str(path.resolve()), "sha256": _sha(path), "bytes": path.stat().st_size,
            "size": str(path.stat().st_size) + " bytes",
            "member_count": len(members) + 1, "crc_and_member_hashes_verified": True}


def _task_specification(project, task_name, snapshot):
    """Find a declared frozen snapshot or the repository's task package."""
    candidates = [Path(snapshot)]
    candidates.extend(parent / "tasks" / task_name for parent in Path(project).parents)
    folder = next((p for p in candidates if (p / "instruction.md").is_file()), None)
    if folder is None:
        raise ValueError("Self-contained task inputs missing: " + task_name)
    return folder


def _project_assets(config, root):
    """Collect only portable authored source, frozen inputs and one native DUT."""
    project, paths = config["project_root"], config["paths"]
    prefix = "workspaces/" + config["task_id"] + "/"
    assets = []
    for name in ("project.toml", "README.md", ".gitignore"):
        assets.append((_safe_file(project / name, project), prefix + name))
    for key in ("tools", "tests", "docs", "baseline", "specification_snapshot"):
        folder = paths[key]
        if not folder.is_dir():
            raise ValueError("Required portable project directory is missing: " + key)
        for path in sorted(folder.rglob("*")):
            if path.is_file() and not _excluded(_rel(path, project)):
                _safe_file(path, project, allow_empty=True)
                assets.append((path, prefix + _rel(path, project)))
    baseline = paths["baseline"]
    synthesized = _read(_safe_file(baseline / "synthesis.json", project))
    actual_values = {e["name"]: e["value_si"] for e in synthesized.get("elements", [])}
    expected_values = {e["name"]: e["value_si"] for e in model.baseline()["elements"]}
    if actual_values != expected_values:
        raise ValueError("Baseline snapshot does not contain the pinned full-precision L/C values")
    _native_circuit(_safe_file(baseline / "schematic.net", project).read_text(encoding="utf-8-sig"), model.baseline())
    for task_name, snapshot in ((config["task_id"], paths["specification_snapshot"]),
                                 (BASELINE_TASK, paths["baseline_specification_snapshot"])):
        folder = _task_specification(project, task_name, snapshot)
        for path in sorted(folder.rglob("*")):
            if path.is_file() and not _excluded(_rel(path, folder)):
                assets.append((_safe_file(path, folder, allow_empty=True), "tasks/" + task_name + "/" + _rel(path, folder)))
    for name in ("ads-mcp-workflow.md", "engineering-workspace-layout.md", "evaluation-results.md"):
        candidates = [parent / "docs" / name for parent in project.parents]
        candidates.append(project / "inputs" / "shared-docs" / name)
        source = next((path for path in candidates if path.is_file()), None)
        if source is None:
            raise ValueError("Required portable shared guide is missing: " + name)
        assets.append((_safe_file(source, source.parent), "docs/" + name))
    mapping_path = Path(root) / "requests.json"
    mapping = _read(mapping_path) if mapping_path.is_file() else {}
    selected_case = config.get("selected_case_id")
    replay = next((row for row in mapping.get("e9_repetitions", []) if row.get("case_id") == selected_case), None)
    released = (Path(root) / "reproductions" / replay["request_id"] / "portable-native") if replay else None
    native = released if released is not None and released.is_dir() else paths["ads"]
    if not native.is_dir() or not any(p.name == ".oalib" for p in native.rglob("*")):
        raise ValueError("Released native ADS source or OA library metadata is missing")
    locks = [p for p in native.rglob("*") if p.is_file() and
             (".cdslck" in p.name.lower() or p.suffix.lower() == ".lck" or p.name.startswith(".ads_lock"))]
    if locks:
        raise ValueError("Native source must be released from OA locks before packaging")
    definitions = _safe_file(native / "lib.defs", native).read_text(encoding="utf-8-sig")
    for line in definitions.splitlines():
        tokens = line.split()
        if tokens and tokens[0].upper() == "DEFINE" and len(tokens) >= 3:
            if tokens[2].startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", tokens[2]):
                raise ValueError("Native library definitions must be project-relative")
    native_prefix = prefix + _rel(paths["ads"], project) + "/"
    for path in sorted(native.rglob("*")):
        if path.is_file() and not _excluded(_rel(path, native)):
            assets.append((_safe_file(path, native, allow_empty=True), native_prefix + _rel(path, native)))
    return assets, {"source": "released E9 snapshot for the configured case" if native == released else "released canonical authored workspace",
                    "case_id": selected_case, "destination": _rel(paths["ads"], project)}


def package(project, root):
    """Create a new handoff revision without changing completed evidence.

    ``project`` must be the stable task-owned directory with project.toml.
    Existing ZIPs remain unchanged. New ZIPs and read-only audit outputs belong
    to a fresh ``results/<run-id>/handoff/<UTC-id>/`` directory. Live work and
    historical staging projects are excluded from both evidence archives.
    """
    config = project_config.load_project(project)
    project, root = config["project_root"], Path(root).resolve()
    if config["task_id"] != TASK or not root.is_relative_to(config["paths"]["results"]):
        raise ValueError("Handoff project identity or run ownership differs")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    destination = root / "handoff" / stamp
    destination.mkdir(parents=True, exist_ok=False)
    checked = audit(root, output_dir=destination / "audit")
    if not checked["ok"]:
        raise ValueError("Cannot package an incomplete evidence audit: " + "; ".join(checked["issues"][:6]))
    full_files = [(p, _rel(p, root)) for p in sorted(_evidence_files(root))
                  if p.is_file() and _rel(p, root) != "bundle-manifest.json" and not _run_excluded(_rel(p, root))]
    selected_files, native_selection = _project_assets(config, root)
    prefix = "workspaces/" + config["task_id"] + "/"
    aggregate = _read(root / "aggregate.json")
    chosen = {case_id for ids in aggregate["deep_dive_selections"].values() for case_id in ids}
    evidence_prefix = prefix + _rel(root, project) + "/"
    for path, relative in full_files:
        parts = PurePosixPath(relative).parts
        include = len(parts) == 1 or parts[0] in {"deep_dive", "reproductions"} or (parts[0] == "cases" and len(parts) > 1 and parts[1] in chosen)
        if include:
            selected_files.append((_safe_file(path, root, allow_empty=True), evidence_prefix + relative))
    for name in ("handoff-audit.json", MANIFEST_NAME, "study_checks.json"):
        source = destination / "audit" / name
        relative = "derived/normalized-handoff-audit/" + name
        full_files.append((source, relative))
        selected_files.append((source, evidence_prefix + relative))
    readme = ("# Task-owned Stage 2 portable handoff\n\n"
              "All coefficients and envelopes are synthetic research assumptions; no InP process or official benchmark acceptance is claimed.\n\n"
              "The full-study ZIP retains the original filter/unit/reproduction evidence. The selected bundle contains the task-owned project manifest, tools, tests, documentation, frozen baseline inputs, task specifications, one released editable ADS workspace, all four deep-dive selections and all three E9 repetitions. Unselected raw data remain in the separately hashed full-study ZIP.\n\n"
              f"Open {prefix}README.md and project.toml after extraction. No Stage 1 working tree or timestamp-named engineering project is required.\n\n"
              "Original completed records and original ZIPs were not rewritten. A fresh read-only packaging audit is included under derived/normalized-handoff-audit/. Live work, previous handoffs, historical staging projects, machine configuration and locks are excluded.\n\n"
              "Verify each ZIP SHA-256 after transfer, then every member against bundle-manifest.json. Its paths describe the members of that ZIP only.\n")
    full = _archive(destination / "full-study.zip", full_files)
    selected = _archive(destination / "selected-handoff.zip", selected_files, {"HANDOFF.md": readme})
    result = {"created_utc": _utc(), "task_id": config["task_id"], "task_revision": config["revision"],
              "audit_ok": True, "original_evidence_preserved": True,
              "full_study": full, "selected_handoff": selected,
              "selected_case_ids": sorted(chosen), "native_source": native_selection,
              "excluded_machine_configuration": True, "audit": "audit/handoff-audit.json"}
    receipt = destination / "receipt.json"
    portable_receipt = json.loads(json.dumps(result))
    for key in ("full_study", "selected_handoff"):
        portable_receipt[key]["path"] = Path(portable_receipt[key]["path"]).name
    _write(receipt, portable_receipt)
    result["receipt"] = str(receipt)
    return result
