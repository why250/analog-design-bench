"""Prepare, launch, poll and export one Momentum case without UI interaction.

All functions operate on explicit case directories.  ``prepare`` and ``launch``
need only the standard library; ``export_dataset`` imports the installed ADS
dataset API and must run in the ADS 2027 Python environment.

Run inside ADS:
    import sys; sys.path.insert(0, r"...\\tools")
    import run_momentum as rm
    receipt = rm.prepare(export_dir, case_dir, "C03_110", [110.0], mesh_um=50)
    rm.launch(case_dir)
    print(rm.status(case_dir))
    rm.export_dataset(case_dir, s2p_path, csv_path)

The solver is always started detached; poll ``status`` from a later call.  A
case is never overwritten once it has been attempted.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone

ADS_ROOT = os.environ.get("HPEESOF_DIR", "")
DATASET_SUFFIX = ".ds"
OPTION_KEYS = ("DS_DIR", "DS_NAME", "maxThreads", "SimulationMode",
               "MAXCELLSIZE", "matrixSolver")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: str) -> dict:
    data = open(path, "rb").read()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _replace_option(text: str, key: str, value: str) -> str:
    pattern = re.compile(r"(?im)^\s*" + re.escape(key) + r"\s+[^;\r\n]*;")
    text, count = pattern.subn(lambda m: f"{key} {value};", text)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {key} option, found {count}")
    return text


def prepare(export_dir: str, case_dir: str, ds_name: str,
            frequencies_ghz: list[float], *, mesh_um: float | None = None,
            matrix_solver: int | None = None, threads: int = 4,
            keep_stimulus: bool = False) -> dict:
    export_dir = os.path.abspath(export_dir)
    case_dir = os.path.abspath(case_dir)
    if not os.path.isdir(export_dir):
        raise FileNotFoundError(export_dir)
    if os.path.exists(case_dir):
        raise FileExistsError(f"Case directory already exists: {case_dir}")
    if not keep_stimulus:
        if not frequencies_ghz or any(not math.isfinite(f) or f <= 0 for f in frequencies_ghz):
            raise ValueError("Frequencies must be finite and positive")
        if any(a >= b for a, b in zip(frequencies_ghz, frequencies_ghz[1:])):
            raise ValueError("Frequencies must be strictly increasing")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", ds_name):
        raise ValueError("Dataset name must be a simple file stem")
    os.makedirs(os.path.dirname(case_dir), exist_ok=True)
    shutil.copytree(export_dir, case_dir)
    option_path = os.path.join(case_dir, "proj.opt")
    original = open(option_path, "r", encoding="utf-8-sig").read()
    text = original
    text = _replace_option(text, "DS_DIR", case_dir)
    text = _replace_option(text, "DS_NAME", ds_name)
    text = _replace_option(text, "maxThreads", str(threads))
    text = _replace_option(text, "SimulationMode", "1")
    if mesh_um is not None:
        if not (1.0 <= mesh_um <= 200.0):
            raise ValueError("Mesh size is outside the supported range")
        text = _replace_option(text, "MAXCELLSIZE", f"{mesh_um:.17g} UM")
    if matrix_solver is not None:
        if matrix_solver not in (0, 1):
            raise ValueError("matrixSolver must be 0 (compressed) or 1 (dense)")
        text = _replace_option(text, "matrixSolver", str(matrix_solver))
    open(option_path, "w", encoding="utf-8", newline="\n").write(text)
    if not keep_stimulus:
        stimulus = "".join(f"START {f:.17g} STOP {f:.17g} STEP 1;\n" for f in frequencies_ghz)
        open(os.path.join(case_dir, "proj.sti"), "w", encoding="utf-8", newline="\n").write(stimulus)
    files = {}
    for name in ("proj.opt", "proj.sti", "proj.prt", "proj.pin", "proj.ltd", "proj.sub", "proj_a"):
        path = os.path.join(case_dir, name)
        if os.path.isfile(path):
            files[name] = _sha(path)
    receipt = {
        "schema_version": 1,
        "created_utc": _utc(),
        "source_export": export_dir,
        "case_dir": case_dir,
        "dataset_name": ds_name,
        "stimulus": "exported-adaptive" if keep_stimulus else "discrete",
        "frequencies_GHz": frequencies_ghz,
        "mesh_um": mesh_um,
        "matrix_solver": matrix_solver,
        "threads": threads,
        "files": files,
        "original_proj_opt_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        "solver_root": ADS_ROOT,
    }
    with open(os.path.join(case_dir, "prepare-receipt.json"), "w",
              encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return receipt


def launch(case_dir: str) -> dict:
    case_dir = os.path.abspath(case_dir)
    if not os.path.isdir(case_dir):
        raise FileNotFoundError(case_dir)
    if os.path.exists(os.path.join(case_dir, "launch-receipt.json")):
        raise RuntimeError("This case has already been attempted; use a fresh case")
    if not ADS_ROOT:
        raise RuntimeError("Set HPEESOF_DIR to the ADS installation root")
    wrapper = os.path.join(ADS_ROOT, "bin", "adsMomWrapper.bat")
    if not os.path.isfile(wrapper):
        raise FileNotFoundError(wrapper)
    env = os.environ.copy()
    env["HPEESOF_DIR"] = ADS_ROOT
    env["PATH"] = os.path.join(ADS_ROOT, "bin") + os.pathsep + env.get("PATH", "")
    argv = [env.get("COMSPEC", "cmd.exe"), "/d", "/c", wrapper,
            "-O", "-3D", "--objMode=MW", "proj", "proj"]
    log = open(os.path.join(case_dir, "solver-console.log"), "wb")
    proc = subprocess.Popen(argv, cwd=case_dir, env=env, stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    receipt = {"schema_version": 1, "started_utc": _utc(), "pid": proc.pid,
               "argv": argv, "case_dir": case_dir}
    with open(os.path.join(case_dir, "launch-receipt.json"), "w",
              encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return receipt


def status(case_dir: str) -> dict:
    case_dir = os.path.abspath(case_dir)
    log_path = os.path.join(case_dir, "proj.log")
    text = ""
    if os.path.isfile(log_path):
        text = open(log_path, "r", encoding="utf-8", errors="replace").read()
    finished = "S-parameter simulation finished" in text and "Simulation finished on:" in text
    datasets = sorted(name for name in os.listdir(case_dir) if name.endswith(DATASET_SUFFIX))
    errors = [line.strip() for line in text.splitlines()
              if re.search(r"\b(error|fatal|failed)\b", line, re.I)]
    return {"case_dir": case_dir, "finished": finished, "datasets": datasets,
            "log_bytes": len(text), "errors": errors[-10:],
            "tail": text[-1200:]}


def wait(case_dir: str, timeout_s: float = 1800.0, interval_s: float = 5.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        state = status(case_dir)
        if state["finished"]:
            return state
        time.sleep(interval_s)
    return {"case_dir": case_dir, "finished": False, "timeout_s": timeout_s,
            **status(case_dir)}


def export_dataset(case_dir: str, s2p_path: str, csv_path: str) -> dict:
    """Export the complete complex two-port network with 50 ohm references."""
    from keysight.ads import dataset

    case_dir = os.path.abspath(case_dir)
    state = status(case_dir)
    if not state["finished"]:
        raise RuntimeError("Solver has not completed successfully")
    datasets = state["datasets"]
    if len(datasets) == 1:
        source_name = datasets[0]
    else:
        raw_candidates = [name for name in datasets if not name.endswith("_a.ds")]
        if len(raw_candidates) != 1:
            raise RuntimeError(f"Cannot identify the raw .ds dataset among {datasets}")
        source_name = raw_candidates[0]
    source = os.path.join(case_dir, source_name)
    raw = dataset.open(source)
    table = raw["data"].to_dataframe().reset_index()
    ports_table = raw["ports"].to_dataframe().reset_index()
    required = {"freq", "S[1,1]", "S[1,2]", "S[2,1]", "S[2,2]", "PORTZ[1]", "PORTZ[2]"}
    if not required.issubset(set(table.columns)):
        raise RuntimeError("Dataset lacks required frequency, S or port-impedance columns")
    if len(ports_table) != 2:
        raise RuntimeError(f"Expected two ports, found {len(ports_table)}")
    rows = []
    for _, row in table.iterrows():
        frequency = complex(row["freq"]).real
        for port in (1, 2):
            if complex(row[f"PORTZ[{port}]"]) != 50 + 0j:
                raise RuntimeError("Port reference impedance is not exactly 50 ohm")
        s = [[complex(row[f"S[{i},{j}]"]) for j in (1, 2)] for i in (1, 2)]
        rows.append((frequency, s))
    rows.sort(key=lambda item: item[0])
    os.makedirs(os.path.dirname(os.path.abspath(s2p_path)), exist_ok=True)
    with open(s2p_path, "w", encoding="ascii", newline="\n") as stream:
        stream.write("! al2o3-tf-msl-110g-em-r1 uniform microstrip line\n")
        stream.write("! ports: 1=rf_in 2=rf_out; reference planes at coupon edges\n")
        stream.write("! Zref = 50 ohm; full complex entries retained\n")
        stream.write("# Hz S RI R 50\n")
        for frequency, s in rows:
            values = [s[0][0], s[0][1], s[1][0], s[1][1]]
            fields = [format(frequency, ".17g")]
            for value in values:
                fields.extend((format(value.real, ".17g"), format(value.imag, ".17g")))
            stream.write(" ".join(fields) + "\n")
    with open(csv_path, "w", encoding="ascii", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["frequency_hz"] + [f"S{i}{j}_{part}" for i in (1, 2) for j in (1, 2)
                                            for part in ("real", "imag")])
        for frequency, s in rows:
            fields = [format(frequency, ".17g")]
            for i in (1, 2):
                for j in (1, 2):
                    fields.extend((format(s[i - 1][j - 1].real, ".17g"),
                                   format(s[i - 1][j - 1].imag, ".17g")))
            writer.writerow(fields)
    receipt = {
        "schema_version": 1, "created_utc": _utc(),
        "case_dir": case_dir, "source_dataset": os.path.basename(source),
        "all_datasets": datasets, "selected_dataset": source_name,
        "dataset_sha256": _sha(source)["sha256"],
        "frequency_hz": [row[0] for row in rows],
        "port_order": [1, 2], "port_names": ["rf_in", "rf_out"],
        "reference_ohm": 50.0, "format": "Touchstone RI",
        "s2p": _sha(s2p_path), "csv": _sha(csv_path),
        "interpolation": False, "renormalization": False, "passivity_repair": False,
    }
    with open(os.path.join(case_dir, "raw-model-receipt.json"), "w",
              encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return receipt
