"""Run the corrected Au-cover DUT: full band, checkpoints and mesh controls.

Host-side detached driver.  Cases:
  C32 (3.0 mm) and C33 (6.0 mm): adaptive 0.1-110 GHz and 7 discrete checkpoints.
  C32 mesh 40 um and 30 um: 65/110 GHz for H2.

All cases use the Al2O3_MSL_AuGND substrate (bottom Au cover, 4.5 um,
groundplane=1), top-only line and TML ports.
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
import run_momentum as runm

CHECKPOINTS = [0.1, 1.0, 10.0, 40.0, 65.0, 80.0, 110.0]
CASES = [
    {"label": "C32_adaptive", "cell": "C32", "case": "case_adaptive",
     "dataset": "C32_adaptive", "keep_stimulus": True, "frequencies": [], "mesh_um": 50.0},
    {"label": "C32_discrete", "cell": "C32", "case": "case_discrete",
     "dataset": "C32_discrete", "keep_stimulus": False, "frequencies": CHECKPOINTS, "mesh_um": 50.0},
    {"label": "C33_adaptive", "cell": "C33", "case": "case_adaptive",
     "dataset": "C33_adaptive", "keep_stimulus": True, "frequencies": [], "mesh_um": 50.0},
    {"label": "C33_discrete", "cell": "C33", "case": "case_discrete",
     "dataset": "C33_discrete", "keep_stimulus": False, "frequencies": CHECKPOINTS, "mesh_um": 50.0},
    {"label": "C32_mesh40", "cell": "C32", "case": "case_mesh40",
     "dataset": "C32_mesh40", "keep_stimulus": False, "frequencies": [65.0, 110.0], "mesh_um": 40.0},
    {"label": "C32_mesh30", "cell": "C32", "case": "case_mesh30",
     "dataset": "C32_mesh30", "keep_stimulus": False, "frequencies": [65.0, 110.0], "mesh_um": 30.0},
]


def main() -> None:
    sweep_dir = os.path.join(RUN, "work", "sweep")
    os.makedirs(sweep_dir, exist_ok=True)
    status_path = os.path.join(sweep_dir, "augnd-status.json")
    results = {}
    if os.path.isfile(status_path):
        results = json.load(open(status_path, "r", encoding="utf-8"))
    for item in CASES:
        label = item["label"]
        if label in results and results[label].get("finished"):
            continue
        case_dir = os.path.join(RUN, "cases", item["cell"], item["case"])
        export_dir = os.path.join(RUN, "cases", item["cell"], "export")
        record = {key: value for key, value in item.items() if key != "case"}
        record["case_dir"] = case_dir
        started = time.time()
        try:
            if os.path.exists(case_dir):
                record["existing_case"] = True
                record.update(runm.status(case_dir))
            else:
                runm.prepare(export_dir, case_dir, item["dataset"], item["frequencies"],
                             mesh_um=item["mesh_um"], matrix_solver=0, threads=4,
                             keep_stimulus=item["keep_stimulus"])
                runm.launch(case_dir)
                record.update(runm.wait(case_dir, timeout_s=600.0, interval_s=5.0))
        except Exception as exc:
            record["error"] = repr(exc)
        record["elapsed_s"] = time.time() - started
        results[label] = record
        with open(status_path, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(results, stream, indent=2)
            stream.write("\n")
        print(f"{label} finished={record.get('finished')} elapsed={record['elapsed_s']:.1f}s",
              flush=True)
    print("AUGND_DONE", flush=True)


if __name__ == "__main__":
    if "--test" in sys.argv:
        print("import ok", sys.version)
    else:
        main()
