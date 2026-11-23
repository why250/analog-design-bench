"""Run the coarse 110 GHz width sweep on the ideal-ground candidates.

This is a detached host-side driver: it uses only the standard library plus
``run_momentum`` (prepare/launch/status) and never imports ADS.  Each case is
prepared in a fresh directory, solved sequentially, and recorded in
``work/sweep/coarse-110-status.json`` after every width.  Existing case
directories are reported, never overwritten.
"""

from __future__ import annotations

import json
import os
import sys
import time

try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # exec() inside ADS
    _HERE = os.getcwd()
ROOT = os.environ.get("MSL_WORKSPACE_ROOT") or (
    os.path.dirname(_HERE) if os.path.basename(_HERE).lower() == "tools" else _HERE
)
RUN = os.path.join(ROOT, "results", "20261119T065241Z-msl-em-execution")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import run_momentum as rm

PHASES = {
    "coarse": [
        ("MSL_Line_C14", 50.0), ("MSL_Line_C15", 75.0), ("MSL_Line_C16", 100.0),
        ("MSL_Line_C17", 125.0), ("MSL_Line_C18", 150.0), ("MSL_Line_C19", 175.0),
        ("MSL_Line_C20", 200.0), ("MSL_Line_C21", 225.0), ("MSL_Line_C22", 250.0),
        ("MSL_Line_C23", 275.0), ("MSL_Line_C24", 300.0),
    ],
    "refine": [
        ("MSL_Line_C25", 105.0), ("MSL_Line_C26", 110.0), ("MSL_Line_C27", 115.0),
        ("MSL_Line_C28", 120.0), ("MSL_Line_C29", 130.0),
    ],
}


def main() -> None:
    phase = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "coarse"
    if phase not in PHASES:
        raise SystemExit(f"Unknown phase {phase!r}; choose {sorted(PHASES)}")
    widths = PHASES[phase]
    sweep_dir = os.path.join(RUN, "work", "sweep")
    os.makedirs(sweep_dir, exist_ok=True)
    status_path = os.path.join(sweep_dir, f"{phase}-110-status.json")
    results = {}
    if os.path.isfile(status_path):
        results = json.load(open(status_path, "r", encoding="utf-8"))
    for cell, width in widths:
        if cell in results and results[cell].get("finished"):
            continue
        export_dir = os.path.join(RUN, "cases", cell[9:], "export")
        case_dir = os.path.join(RUN, "cases", cell[9:], "case_110")
        record = {"cell": cell, "width_um": width, "case_dir": case_dir}
        started = time.time()
        try:
            if os.path.exists(case_dir):
                record["existing_case"] = True
                record.update(rm.status(case_dir))
            else:
                rm.prepare(export_dir, case_dir, f"{cell}_110", [110.0],
                           mesh_um=50.0, matrix_solver=0, threads=4)
                rm.launch(case_dir)
                record.update(rm.wait(case_dir, timeout_s=1200.0, interval_s=5.0))
        except Exception as exc:  # retain the failure and continue
            record["error"] = repr(exc)
        record["elapsed_s"] = time.time() - started
        results[cell] = record
        with open(status_path, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(results, stream, indent=2)
            stream.write("\n")
        print(f"{cell} W={width} finished={record.get('finished')} "
              f"elapsed={record['elapsed_s']:.1f}s", flush=True)
    print("SWEEP_DONE", flush=True)


if __name__ == "__main__":
    if "--test" in sys.argv:
        print("import ok", sys.version)
        print("run_momentum", rm.__file__)
    else:
        main()
