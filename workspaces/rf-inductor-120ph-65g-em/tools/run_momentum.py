"""Prepare a fresh frozen-input Momentum case, solve it, and export the raw Snp.

Preparation needs only Python's standard library. Dataset export imports the
installed ADS dataset API only after a completed fullwave solve is verified.
All solver invocation is synchronous. A lock serializes sibling case directories
because the installed solver may share its substrate cache between processes.
Never overwrite an earlier attempted case; prepare a fresh directory instead.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
from typing import Any, Iterable
import xml.etree.ElementTree as ET

from convert_cti import SNetwork, write_touchstone


INPUT_FILES = (
    "proj_a", "proj.prt", "proj.pin", "proj.ltd", "proj.opt", "proj.sti",
    "proj.cfg", "proj.vpl", "proj.lcf", "proj.params", "proj.plan", "proj.toi",
    "momentum.cfg", "emStateFile.xml",
)
REQUIRED_INPUTS = ("proj_a", "proj.prt", "proj.pin", "proj.ltd", "proj.opt", "proj.sti", "proj.cfg")
DATASET_NAME = "raw_MomMW"


class RunError(RuntimeError):
    """A case lacks sufficient evidence for the requested operation."""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _replace_option(text: str, key: str, value: str) -> str:
    pattern = re.compile(r"(?im)^\s*" + re.escape(key) + r"\s+[^;\r\n]*;\s*$")
    text, count = pattern.subn(f"{key} {value};", text)
    if count != 1:
        raise RunError(f"Expected exactly one {key} option, found {count}")
    return text


def _matrix_solver_code(value: Any) -> int:
    if type(value) is not int or value not in (0, 1):
        raise RunError("Matrix solver code must be the explicitly supported integer 0 or 1")
    return value


def _native_matrix_solver_option(text: str) -> int:
    matches = re.findall(r"(?im)^\s*MATRIXSOLVER\s+([^;\r\n]+);\s*$", text)
    if len(matches) != 1 or matches[0].strip() not in ("0", "1"):
        raise RunError("Native options require exactly one supported MATRIXSOLVER 0 or 1 setting")
    return int(matches[0].strip())


def _port_definitions(path: Path) -> list[dict[str, Any]]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise RunError("Invalid exported port XML") from exc
    records = []
    for port in root.findall("./port_list/port"):
        try:
            reference = complex(float(port.findtext("impedance/real", "nan")),
                                float(port.findtext("impedance/imag", "nan")))
            identifier = int(port.attrib["id"])
        except (ValueError, KeyError) as exc:
            raise RunError("Invalid port ID or reference impedance") from exc
        if reference != 50 + 0j:
            raise RunError("Every raw port must have an explicit real 50 ohm reference")
        records.append({"number": identifier, "name": port.findtext("name"),
                        "plus": port.findtext("plus_pin"), "minus": port.findtext("minus_pin"),
                        "reference_ohm": 50.0})
    if not records or [p["number"] for p in records] != list(range(1, len(records) + 1)):
        raise RunError("Port IDs must be complete, contiguous, and in declared order")
    return records


def _guard_passive_permittivity(text: str) -> list[dict[str, Any]]:
    """Reject positive direct dielectric imaginary permittivity in this study.

    The verified ADS2027 Material Definitions convention uses a negative
    er_imag for a passive lossy dielectric. A positive direct value realizes
    gain and must never be repaired by silently reversing its sign. This check
    covers every material, including continued definition lines; lossless zero
    values and conductor definitions without dielectric loss are permitted.
    """
    materials_seen = 0
    current_material: str | None = None
    values = []
    for line_number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "!", "//")):
            continue
        material = re.match(r'^\s*MATERIAL\s+(?:"([^"]+)"|([^\s]+))\s+', line, re.I)
        if material is not None:
            current_material = material.group(1) or material.group(2)
            materials_seen += 1
        elif re.match(r"^\s*(?:END_MATERIAL|BEGIN_\w+|END_\w+)\b", line, re.I):
            current_material = None
        for match in re.finditer(r"(?<!\w)IMAG_PERMITTIVITY\s*=\s*([^\s]+)", line, re.I):
            if current_material is None:
                raise RunError(f"Line {line_number}: imaginary permittivity lacks an identified material")
            try:
                imaginary = float(match.group(1))
            except ValueError as exc:
                raise RunError(f"Material {current_material}: imaginary permittivity is not a scalar number") from exc
            if not math.isfinite(imaginary):
                raise RunError(f"Material {current_material}: imaginary permittivity must be finite")
            if imaginary > 0:
                raise RunError(f"Material {current_material}: positive IMAG_PERMITTIVITY realizes gain under the verified ADS convention; passive input required")
            values.append({"material": current_material, "imaginary_er": imaginary})
    if materials_seen == 0:
        raise RunError("No material definitions are available for the passive-permittivity guard")
    return values


def _reconcile_oxide(text: str) -> tuple[str, dict[str, Any]]:
    _guard_passive_permittivity(text)
    pattern = re.compile(r"(?im)^(\s*MATERIAL\s+ResearchOx1\s+)([^\r\n]+)$")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RunError("Expected exactly one ResearchOx1 material definition")
    line = matches[0].group(2)
    er_match = re.search(r"(?<!\w)PERMITTIVITY=([^\s]+)", line)
    imag_match = re.search(r"(?<!\w)IMAG_PERMITTIVITY=([^\s]+)", line)
    if er_match is None or imag_match is None:
        raise RunError("ResearchOx1 lacks explicit complex permittivity")
    try:
        original = (float(er_match.group(1)), float(imag_match.group(1)))
    except ValueError as exc:
        raise RunError("ResearchOx1 permittivity is not a scalar number") from exc
    if original not in ((4.0, -0.02), (4.2, -0.021)):
        raise RunError("Unexpected ResearchOx1 values; refused to alter an unreviewed material")
    corrected = re.sub(r"(?<!\w)PERMITTIVITY=[^\s]+", "PERMITTIVITY=4.2", line)
    corrected = re.sub(r"(?<!\w)IMAG_PERMITTIVITY=[^\s]+", "IMAG_PERMITTIVITY=-0.021", corrected)
    text = text[:matches[0].start(2)] + corrected + text[matches[0].end(2):]
    return text, {"material": "ResearchOx1", "before": {"er": original[0], "imaginary_er": original[1]},
                  "after": {"er": 4.2, "imaginary_er": -0.021},
                  "reason": "Reconcile stale real permittivity with the frozen research material while preserving the verified passive negative-imaginary convention; never repair a positive sign silently",
                  "changed": original != (4.2, -0.021)}


def prepare_case(export_dir: str | Path, outdir: str | Path, mesh_um: float,
                 frequencies_GHz: Iterable[float], ads_root: str | Path,
                 threads: int = 4, *, native_workspace: str | Path,
                 matrix_solver_code: int = 0) -> dict[str, Any]:
    """Snapshot the original export, then prepare a new task-owned solver case.

    Only the recognized input allowlist is copied. The original source is never
    edited. A refused preparation remains on disk with its original snapshot.
    GHz units follow the installed ADS2027 exported proj.sti format. Simulation
    mode 1 was verified by this study's actual log to select fullwave (uW);
    the CLI MW flag alone did not override an exported RF mode 2.
    Matrix solver selection must already match the native export; this runner
    does not invent an option enum or rewrite it. Code 1 remains unclassified
    until actual runtime-log evidence is reviewed.
    """
    source = Path(export_dir).resolve(strict=True)
    target = Path(outdir).resolve()
    native = Path(native_workspace).resolve(strict=True)
    installation = Path(ads_root).resolve(strict=True)
    frequencies = [float(value) for value in frequencies_GHz]
    if not source.is_dir() or not native.is_dir():
        raise RunError("Export and native-workspace paths must be directories")
    if target == source or target.is_relative_to(source) or source.is_relative_to(target):
        raise RunError("Source and output directories must not overlap")
    if not math.isfinite(mesh_um) or mesh_um <= 0:
        raise RunError("Mesh cell size must be finite and positive")
    if type(threads) is not int or threads < 1:
        raise RunError("Thread count must be a positive integer")
    matrix_solver_code = _matrix_solver_code(matrix_solver_code)
    if (not frequencies or any(not math.isfinite(f) or f < 0 for f in frequencies)
            or any(a >= b for a, b in zip(frequencies, frequencies[1:]))):
        raise RunError("Frequencies must be finite, nonnegative, unique, and increasing")
    wrapper = installation / "bin" / "adsMomWrapper.bat"
    if not wrapper.is_file():
        raise RunError("ADS Momentum wrapper does not exist in the supplied installation")
    for name in REQUIRED_INPUTS:
        if not (source / name).is_file() or (source / name).is_symlink():
            raise RunError(f"Missing or linked required solver input: {name}")
    _guard_passive_permittivity((source / "proj.ltd").read_text(encoding="utf-8-sig"))
    native_matrix_solver = _native_matrix_solver_option((source / "proj.opt").read_text(encoding="utf-8-sig"))
    if native_matrix_solver != matrix_solver_code:
        raise RunError("Requested matrix solver code must already match the original native MATRIXSOLVER export; refused to rewrite it")
    for value in (target.as_posix(), native.as_posix()):
        if any(character in value for character in (';', '\r', '\n', '"')):
            raise RunError("A solver input path contains an unsupported delimiter")
    target.mkdir(parents=True, exist_ok=False)
    original = target / "original-export"
    original.mkdir()
    snapshot = {}
    for name in INPUT_FILES:
        path = source / name
        if path.is_file():
            if path.is_symlink():
                raise RunError(f"Linked input is not a self-contained export: {name}")
            before_copy = _sha(path)
            shutil.copy2(path, original / name)
            shutil.copy2(path, target / name)
            snapshot[name] = _sha(original / name)
            if snapshot[name] != before_copy or _sha(path) != before_copy or _sha(target / name) != before_copy:
                raise RunError(f"Source changed while creating its frozen snapshot: {name}")
    _json(target / "original-export-receipt.json", {
        "schema_version": 1, "created_utc": _utc(), "source_directory": str(source),
        "files": snapshot, "source_was_modified": False,
    })
    options = (target / "proj.opt").read_text(encoding="utf-8-sig")
    for key, value in (("MAXCELLSIZE", f"{mesh_um:.17g} UM"), ("SimulationMode", "1"),
                       ("DS_DIR", target.as_posix()), ("DS_NAME", DATASET_NAME),
                       ("maxThreads", str(threads))):
        options = _replace_option(options, key, value)
    _write(target / "proj.opt", options)
    stimulus = "".join(f"START {f:.17g} STOP {f:.17g} STEP 1;\n" for f in frequencies)
    _write(target / "proj.sti", stimulus)
    configuration = (target / "proj.cfg").read_text(encoding="utf-8-sig")
    configuration, count = re.subn(r"(?im)^\s*user\s*=.*$", f"user = {native.as_posix()}", configuration)
    if count != 1:
        raise RunError("Expected exactly one user root in proj.cfg")
    _write(target / "proj.cfg", configuration)
    material, material_receipt = _reconcile_oxide((target / "proj.ltd").read_text(encoding="utf-8-sig"))
    _write(target / "proj.ltd", material)
    ports = _port_definitions(target / "proj.prt")
    if len(ports) not in (2, 3) or any(p["plus"] != f"P{p['number']}" or p["minus"] != "P4" for p in ports):
        raise RunError("The prepared device requires P1/P2[/P3] signal ports, each explicitly referenced to P4")
    prepared_inputs = target / "prepared-inputs"
    prepared_inputs.mkdir()
    for name in snapshot:
        shutil.copy2(target / name, prepared_inputs / name)
    receipt = {
        "schema_version": 1, "created_utc": _utc(), "ads_root": str(installation),
        "native_workspace": str(native), "mesh_um": mesh_um,
        "frequencies_GHz": frequencies, "mode": "Momentum fullwave", "simulation_mode_option": 1,
        "threads": threads, "dataset_name": DATASET_NAME, "ports": ports,
        "matrix_solver_code": matrix_solver_code,
        "native_export_matrix_solver_code": native_matrix_solver,
        "matrix_solver_name": "UNCLASSIFIED", "matrix_solver_classification_status": "PENDING_RUNTIME_LOG",
        "material_reconciliation": material_receipt,
        "frequency_match_tolerance": {"relative": 1e-12, "absolute_hz": 0.1},
        "source_snapshot": "original-export-receipt.json",
        "files": {name: _sha(target / name) for name in snapshot},
        "cache_policy": "Serial sibling cases; preserve installed cache configuration; no user/global settings changed",
    }
    _json(target / "prepared-case.json", receipt)
    return receipt


def _prepared_options(case: Path, receipt: dict[str, Any]) -> Path:
    """Locate a byte-verified pre-solve snapshot, recovering legacy evidence only.

    Earlier cases lack prepared-inputs. Their exact pre-solve option text can be
    reconstructed from the retained original export and original five edits.
    Recovery is allowed only when its bytes reproduce the already recorded
    prepared-case digest; the original receipt is never amended in place.
    """
    expected = receipt["files"]["proj.opt"]
    snapshot = case / "prepared-inputs" / "proj.opt"
    if snapshot.exists():
        if _sha(snapshot) != expected:
            raise RunError("Prepared option snapshot differs from its original receipt")
        return snapshot
    original = (case / "original-export" / "proj.opt").read_text(encoding="utf-8-sig")
    reconstructed = original
    for key, value in (("MAXCELLSIZE", f"{receipt['mesh_um']:.17g} UM"), ("SimulationMode", "1"),
                       ("DS_DIR", case.as_posix()), ("DS_NAME", DATASET_NAME),
                       ("maxThreads", str(receipt["threads"]))):
        reconstructed = _replace_option(reconstructed, key, value)
    reconstructed_bytes = reconstructed.encode("utf-8")
    actual = {"bytes": len(reconstructed_bytes), "sha256": hashlib.sha256(reconstructed_bytes).hexdigest()}
    if actual != expected:
        raise RunError("Legacy prepared options cannot be reconstructed with exact recorded byte identity")
    snapshot.parent.mkdir(exist_ok=True)
    with snapshot.open("xb") as stream:
        stream.write(reconstructed_bytes)
    amendment = case / "prepared-source-recovery.json"
    _json(amendment, {
        "schema_version": 1, "created_utc": _utc(), "recovered_file": "prepared-inputs/proj.opt",
        "recovery_method": "Original export plus the five originally recorded preparation edits",
        "original_prepared_receipt": _sha(case / "prepared-case.json"),
        "recovered_file_identity": actual, "matched_original_prepared_identity": True,
        "original_receipt_modified": False,
    })
    return snapshot


def _canonical_option_values(text: str, *, mesh_um: float, threads: int,
                             case_dir: Path, matrix_solver_code: int = 0) -> dict[str, Any]:
    """Validate frozen core settings despite the solver's textual normalization."""
    def value(name: str) -> str:
        matches = re.findall(r"(?im)^\s*" + re.escape(name) + r"\s+([^;\r\n]+);\s*$", text)
        if len(matches) != 1:
            raise RunError(f"Canonical options require exactly one {name} setting")
        return matches[0].strip().strip('"')

    def number(name: str, expected: float) -> float:
        try:
            actual = float(value(name))
        except ValueError as exc:
            raise RunError(f"Canonical {name} is not numeric") from exc
        if not math.isfinite(actual) or actual != expected:
            raise RunError(f"Canonical {name} differs from the frozen setting")
        return actual

    results = {"simulation_mode": number("SimulationMode", 1),
               "temperature_k": number("SimulationTemperature", 298.15),
               "threads": number("maxThreads", threads),
               "strip_model": number("MODELTYPESTRIP", 3),
               "via_model": number("MODELTYPEVIA", 3)}
    cell_text = value("MAXCELLSIZE")
    match = re.fullmatch(r"([+\-0-9.eE]+)\s+(UM|METRE|M)", cell_text, re.I)
    if match is None:
        raise RunError("Canonical mesh size has unsupported units or syntax")
    cell_m = float(match.group(1)) * (1e-6 if match.group(2).upper() == "UM" else 1.0)
    if not math.isfinite(cell_m) or not math.isclose(cell_m, mesh_um * 1e-6, rel_tol=1e-12, abs_tol=1e-18):
        raise RunError("Canonical mesh size differs from the frozen mesh")
    # Use the declared value for semantic comparison after checking the parsed
    # unit conversion, avoiding a binary rounding mismatch between equivalent
    # decimal forms such as 3 UM and 3e-6 METRE.
    results["maximum_cell_size_m"] = mesh_um * 1e-6
    if value("DS_NAME") != DATASET_NAME:
        raise RunError("Canonical dataset name differs from the prepared case")
    actual_dir = Path(value("DS_DIR")).resolve()
    if os.path.normcase(str(actual_dir)) != os.path.normcase(str(case_dir.resolve())):
        raise RunError("Canonical dataset directory is outside this case")
    results["dataset_directory"] = str(actual_dir)
    results["dataset_name"] = DATASET_NAME
    for name, expected in (("reusePreviousResults", "OFF"), ("MESH_REDUCTION", "OFF"),
                           ("EDGEMESH_BORDERWIDTH", "AUTO"), ("OVERLAPEXTRACTION", "ON"),
                           ("INCLUDEPORTSOLVER", "ON"), ("SPARAM_OUTPUTFORMAT", "SMATRIXIO")):
        if value(name).upper() != expected:
            raise RunError(f"Canonical {name} differs from the frozen setting")
        results[name] = expected
    results["matrix_solver"] = number("MATRIXSOLVER", _matrix_solver_code(matrix_solver_code))
    results["saved_currents"] = number("saveCurrentsInFile", 1)
    return results


def _verify_prepared(case: Path, *, postsolve: bool = False) -> dict[str, Any]:
    # Apply the material realization guard even to legacy cases whose original
    # receipts faithfully captured an invalid positive-imaginary input.
    _guard_passive_permittivity((case / "proj.ltd").read_text(encoding="utf-8-sig"))
    receipt = json.loads((case / "prepared-case.json").read_text(encoding="utf-8"))
    matrix_solver_code = _matrix_solver_code(receipt.get("matrix_solver_code", 0))
    if "proj.opt" in receipt["files"]:
        if _native_matrix_solver_option((case / "proj.opt").read_text(encoding="utf-8-sig")) != matrix_solver_code:
            raise RunError("Prepared MATRIXSOLVER differs from the recorded explicit code")
    if matrix_solver_code == 1:
        native_source = case / "original-export" / "proj.opt"
        original_receipt = json.loads((case / "original-export-receipt.json").read_text(encoding="utf-8"))
        if (_sha(native_source) != original_receipt["files"]["proj.opt"]
                or _native_matrix_solver_option(native_source.read_text(encoding="utf-8-sig")) != 1):
            raise RunError("Matrix solver code 1 lacks unchanged native-export MATRIXSOLVER 1 evidence")
    for name, expected in receipt["files"].items():
        if name == "proj.opt" and postsolve:
            continue
        if name not in INPUT_FILES or _sha(case / name) != expected:
            raise RunError(f"Prepared input changed before execution: {name}")
    if postsolve:
        snapshot = _prepared_options(case, receipt)
        original_core = _canonical_option_values(snapshot.read_text(encoding="utf-8-sig"),
                                                mesh_um=receipt["mesh_um"], threads=receipt["threads"], case_dir=case,
                                                matrix_solver_code=matrix_solver_code)
        canonical_core = _canonical_option_values((case / "proj.opt").read_text(encoding="utf-8-sig"),
                                                 mesh_um=receipt["mesh_um"], threads=receipt["threads"], case_dir=case,
                                                 matrix_solver_code=matrix_solver_code)
        if original_core != canonical_core:
            raise RunError("Solver-normalized options changed frozen core semantics")
        amendment = case / "canonical-options-receipt.json"
        original_identity = _sha(snapshot)
        canonical_identity = _sha(case / "proj.opt")
        if amendment.exists():
            prior = json.loads(amendment.read_text(encoding="utf-8"))
            if prior["original_options"] != original_identity or prior["canonical_options"] != canonical_identity:
                raise RunError("Canonical options changed after their validation receipt")
        else:
            _json(amendment, {"schema_version": 1, "created_utc": _utc(),
                              "original_options": original_identity, "canonical_options": canonical_identity,
                              "core_settings": canonical_core,
                              "permitted_change": "Solver textual canonicalization of proj.opt only",
                              "other_prepared_input_files_unchanged": True,
                              "original_prepared_receipt_modified": False})
    return receipt


def _verify_completion(case: Path) -> dict[str, Any]:
    _guard_passive_permittivity((case / "proj.ltd").read_text(encoding="utf-8-sig"))
    receipt = _verify_prepared(case, postsolve=True)
    execution = json.loads((case / "execution-receipt.json").read_text(encoding="utf-8"))
    if execution.get("returncode") != 0:
        raise RunError("Solver did not complete successfully")
    for name in ("solver-console.log", "proj.log"):
        text = (case / name).read_text(encoding="utf-8", errors="replace")
        modes = re.findall(r"Simulation Mode:\s*([^\r\n]+)", text)
        if not modes or any(mode.strip() not in ("uW", "MW") for mode in modes):
            raise RunError("Actual solver log does not establish fullwave mode")
        if "S-parameter simulation finished" not in text or "Simulation finished on:" not in text:
            raise RunError("Solver log is incomplete; refused partial dataset export")
    for name in ("proj.sio", f"{DATASET_NAME}.ds"):
        path = case / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RunError(f"Missing complete raw result: {name}")
    return receipt


def run_case(case_dir: str | Path, ads_root: str | Path | None = None,
             *, export_model: bool = True) -> dict[str, Any]:
    """Synchronously execute one untouched prepared case and retain failures.

    No automatic parallel execution, retries, or stale-lock removal is provided.
    A surviving lock after a process interruption needs explicit operator review.
    The caller supplies its normal licensed ADS process environment.
    """
    case = Path(case_dir).resolve(strict=True)
    prepared = _verify_prepared(case)
    if any((case / name).exists() for name in ("solver-console.log", "execution-receipt.json", "proj.sio", f"{DATASET_NAME}.ds")):
        raise RunError("This case has already been attempted; prepare a fresh case")
    installation = Path(ads_root or prepared["ads_root"]).resolve(strict=True)
    wrapper = installation / "bin" / "adsMomWrapper.bat"
    if not wrapper.is_file():
        raise RunError("Momentum wrapper is unavailable")
    if os.name != "nt":
        raise RunError("This verified runner requires the Windows ADS installation")
    lock = case.parent / ".momentum-run.lock"
    try:
        lock_stream = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise RunError("Another sibling case holds the serial Momentum lock; do not remove an active lock") from exc
    try:
        with lock_stream:
            json.dump({"created_utc": _utc(), "pid": os.getpid(), "host": socket.gethostname(), "case": str(case)}, lock_stream)
            lock_stream.flush()
            environment = os.environ.copy()
            environment["HPEESOF_DIR"] = str(installation)
            environment["PATH"] = str(installation / "bin") + os.pathsep + environment.get("PATH", "")
            argv = [environment.get("COMSPEC", "cmd.exe"), "/d", "/c", str(wrapper),
                    "-O", "-3D", "--objMode=MW", "proj", "proj"]
            started = _utc()
            try:
                with (case / "solver-console.log").open("xb") as output:
                    completed = subprocess.run(argv, cwd=case, env=environment, stdin=subprocess.DEVNULL,
                                               stdout=output, stderr=subprocess.STDOUT,
                                               creationflags=subprocess.CREATE_NO_WINDOW, check=False)
            except OSError as exc:
                _json(case / "execution-receipt.json", {
                    "schema_version": 1, "started_utc": started, "finished_utc": _utc(),
                    "argv": argv, "returncode": None, "launch_error": str(exc),
                    "input_receipt": _sha(case / "prepared-case.json"),
                    "automatic_retries": 0, "parallel_execution": False,
                })
                raise RunError("Solver process could not start; retained the launch-error receipt") from exc
            execution = {"schema_version": 1, "started_utc": started, "finished_utc": _utc(),
                         "argv": argv, "returncode": completed.returncode,
                         "console_log": _sha(case / "solver-console.log"),
                         "input_receipt": _sha(case / "prepared-case.json"),
                         "automatic_retries": 0, "parallel_execution": False}
            _json(case / "execution-receipt.json", execution)
            if completed.returncode != 0:
                raise RunError(f"Momentum returned {completed.returncode}; retained failed case and log")
            _verify_completion(case)
            if export_model:
                export_dataset(case)
            return execution
    finally:
        # Only this invocation's acquired lock is removed, never an existing lock.
        lock.unlink()


def _frequency_realization(requested_hz: Iterable[float], actual_hz: Iterable[float],
                           *, native_ten_digit_realization: bool = False) -> dict[str, Any]:
    """Validate raw coordinates; optionally recognize exact native .10g values."""
    requested, actual = list(map(float, requested_hz)), list(map(float, actual_hz))
    if type(native_ten_digit_realization) is not bool:
        raise RunError("The native ten-digit frequency policy requires an explicit Boolean opt-in")
    if (len(actual) != len(requested) or not requested
            or any(not math.isfinite(f) or f < 0 for f in requested + actual)
            or any(a >= b for a, b in zip(requested, requested[1:]))
            or any(a >= b for a, b in zip(actual, actual[1:]))):
        raise RunError("Actual solved frequency points differ from the requested explicit list")
    if not native_ten_digit_realization:
        if any(not math.isclose(a, b, rel_tol=1e-12, abs_tol=0.1) for a, b in zip(actual, requested)):
            raise RunError("Actual solved frequency points differ from the requested explicit list")
        return {"policy": "original_strict_frequency_match", "requested_frequency_hz": requested,
                "actual_frequency_hz": actual}
    canonical = [float(format(frequency, ".10g")) for frequency in requested]
    if actual != canonical:
        raise RunError("Actual frequencies must exactly equal the native ten-significant-digit .10g realization; no tolerance is applied")
    points = []
    for index, (requested_value, actual_value, canonical_value) in enumerate(zip(requested, actual, canonical)):
        exact_ten_digit = requested_value == canonical_value
        key_exact = requested_value in (65e9, 80e9)
        if (exact_ten_digit or key_exact) and actual_value != requested_value:
            raise RunError("Ten-digit-representable and key 65/80 GHz points must remain exact")
        points.append({"index": index, "requested_hz": requested_value, "actual_hz": actual_value,
                       "native_ten_digit_canonical_hz": canonical_value,
                       "actual_minus_requested_hz": actual_value - requested_value,
                       "requested_is_exactly_ten_digit_representable": exact_ten_digit,
                       "key_65_or_80_GHz": key_exact,
                       "status": "UNCHANGED_EXACT" if actual_value == requested_value else "EXACT_NATIVE_TEN_DIGIT_REALIZATION"})
    return {"policy": "explicit_opt_in_exact_native_ten_digit_realization",
            "canonicalization_expression": "float(format(requested_hz, '.10g'))",
            "requested_frequency_hz": requested, "actual_frequency_hz": actual,
            "native_ten_digit_canonical_frequency_hz": canonical,
            "actual_minus_requested_hz": [a - b for a, b in zip(actual, requested)],
            "points": points, "changed_point_count": sum(a != b for a, b in zip(actual, requested)),
            "maximum_absolute_deviation_hz": max(abs(a - b) for a, b in zip(actual, requested)),
            "ten_digit_representable_requested_points_remain_exact": True,
            "requested_key_65_80_GHz_points_remain_exact": True,
            "frequency_tolerance_applied": False,
            "frequency_interpolation": False, "frequency_resampling": False,
            "raw_frequency_coordinates_modified": False,
            "electrical_acceptance_thresholds_modified": False}


def export_dataset(case_dir: str | Path, *, native_ten_digit_realization: bool = False) -> dict[str, Any]:
    """Export all raw S entries, with optional exact native frequency realization.

    The default frequency policy is unchanged. Explicit opt-in accepts only the
    exact .10g canonical coordinates and retains an independent immutable
    amendment; no requested input or actual dataset coordinate is rewritten.
    """
    case = Path(case_dir).resolve(strict=True)
    prepared = _verify_completion(case)
    if (case / "raw-model-receipt.json").exists():
        raise RunError("An export already exists; retain it rather than overwrite")
    # Delayed import keeps --help and case preparation usable without ADS.
    from keysight.ads import dataset

    source = case / f"{DATASET_NAME}.ds"
    raw = dataset.open(str(source))
    table = raw["data"].to_dataframe().reset_index()
    port_table = raw["ports"].to_dataframe().reset_index()
    ports = len(prepared["ports"])
    required_columns = {"freq"} | {f"S[{i},{j}]" for i in range(1, ports + 1) for j in range(1, ports + 1)} | {f"PORTZ[{i}]" for i in range(1, ports + 1)}
    if not required_columns.issubset(set(table.columns)):
        raise RunError("Raw dataset is missing frequency, complex S entries, or port impedances")
    actual_s_columns = {str(column) for column in table.columns if str(column).startswith("S[")}
    if actual_s_columns != {column for column in required_columns if column.startswith("S[")}:
        raise RunError("Raw dataset port count differs from the frozen setup")
    if not {"Ports", "PlusPins", "MinusPins"}.issubset(set(port_table.columns)) or len(port_table) != ports:
        raise RunError("Raw dataset port mapping is incomplete")
    port_records = []
    for k, (_, row) in enumerate(port_table.iterrows(), 1):
        values = {name: str(row[name]).strip() for name in ("Ports", "PlusPins", "MinusPins")}
        if values != {"Ports": f"P{k}", "PlusPins": f"P{k}", "MinusPins": "P4"}:
            raise RunError("Raw dataset has unexpected signal/physical-return mapping")
        port_records.append({"number": k, **values, "reference_ohm": 50.0})
    frequencies = tuple(float(value) for value in table["freq"])
    requested = [f * 1e9 for f in prepared["frequencies_GHz"]]
    realization = _frequency_realization(requested, frequencies,
                                         native_ten_digit_realization=native_ten_digit_realization)
    for port in range(1, ports + 1):
        if any(complex(value) != 50 + 0j for value in table[f"PORTZ[{port}]"]):
            raise RunError("Raw port references are not all real 50 ohm values")
    matrices = tuple(tuple(tuple(complex(row[f"S[{i},{j}]"]) for j in range(1, ports + 1))
                           for i in range(1, ports + 1)) for _, row in table.iterrows())
    network = SNetwork(frequencies, matrices, DATASET_NAME)
    rendered = io.StringIO()
    write_touchstone(network, rendered, 50.0)
    realization_amendment = None
    if native_ten_digit_realization:
        amendment_path = case / "native-frequency-realization.json"
        amendment = {"schema_version": 1, "created_utc": _utc(), **realization,
                     "prepared_case_receipt": _sha(case / "prepared-case.json"),
                     "requested_stimulus": _sha(case / "proj.sti"),
                     "source_dataset": {"path": source.name, **_sha(source)},
                     "source_raw_solver_network": {"path": "proj.sio", **_sha(case / "proj.sio")},
                     "original_prepared_receipt_modified": False,
                     "original_stimulus_modified": False, "source_dataset_modified": False}
        _json(amendment_path, amendment)
        realization_amendment = {"path": amendment_path.name, **_sha(amendment_path)}
    touchstone = case / f"raw.s{ports}p"
    with touchstone.open("x", encoding="ascii", newline="\n") as stream:
        stream.write(rendered.getvalue())
    csv_path = case / "raw-complex-s.csv"
    with csv_path.open("x", encoding="ascii", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["frequency_hz"] + [name for i in range(1, ports + 1) for j in range(1, ports + 1)
                                           for name in (f"S{i}{j}_real", f"S{i}{j}_imag")])
        for frequency, matrix in zip(frequencies, matrices):
            writer.writerow([format(frequency, ".17g")] + [format(value, ".17g") for row in matrix for z in row for value in (z.real, z.imag)])
    receipt = {"schema_version": 1, "created_utc": _utc(), "source_dataset": source.name,
               "requested_frequency_hz": requested, "actual_frequency_hz": list(frequencies), "ports": port_records,
               "frequency_match_policy": realization["policy"],
               "frequency_realization_amendment": realization_amendment,
               "frequency_interpolation": False, "renormalization": False,
               "fitting": False, "passivity_repair": False,
               "files": {path.name: _sha(path) for path in (source, case / "proj.sio", touchstone, csv_path)},
               "prepared_case_receipt": _sha(case / "prepared-case.json"),
               "execution_receipt": _sha(case / "execution-receipt.json")}
    _json(case / "raw-model-receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="Snapshot an export and prepare a fresh solver case")
    prepare.add_argument("export_dir", type=Path)
    prepare.add_argument("outdir", type=Path)
    prepare.add_argument("--ads-root", type=Path, required=True)
    prepare.add_argument("--native-workspace", type=Path, required=True)
    prepare.add_argument("--mesh-um", type=float, required=True)
    prepare.add_argument("--frequency-ghz", type=float, nargs="+", required=True)
    prepare.add_argument("--threads", type=int, default=4)
    prepare.add_argument("--matrix-solver-code", type=int, choices=(0, 1), default=0,
                         help="Require this already native-exported matrix code; code 1 needs runtime-log classification")
    solve = subparsers.add_parser("solve", help="Solve one prepared case synchronously and export its complete raw network")
    solve.add_argument("case_dir", type=Path)
    solve.add_argument("--ads-root", type=Path)
    solve.add_argument("--skip-export", action="store_true", help="Retain the completed raw dataset for a later export command")
    export = subparsers.add_parser("export", help="Export a previously completed raw dataset using the ADS Python environment")
    export.add_argument("case_dir", type=Path)
    export.add_argument("--native-ten-digit-realization", action="store_true",
                        help="Explicitly accept only exact native .10g frequency coordinates and retain an immutable amendment")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare_case(args.export_dir, args.outdir, args.mesh_um, args.frequency_ghz, args.ads_root,
                     args.threads, native_workspace=args.native_workspace, matrix_solver_code=args.matrix_solver_code)
        print("Prepared a fresh case; original inputs and all applied changes are retained")
    elif args.command == "solve":
        run_case(args.case_dir, args.ads_root, export_model=not args.skip_export)
        print("Completed the verified fullwave solve" + (" and complete raw network export" if not args.skip_export else ""))
    else:
        export_dataset(args.case_dir, native_ten_digit_realization=args.native_ten_digit_realization)
        print("Exported the complete raw network with verified physical-return mapping")


if __name__ == "__main__":
    main()
