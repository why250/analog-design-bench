"""Run the selected 3 mm and 6 mm full-band cases (adaptive and discrete).

Host-side detached driver.  Uses only the standard library plus
``run_momentum`` and records progress after every case.
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

CHECKPOINTS = [0.1, 1.0, 10.0, 40.0, 65.0, 80.0, 110.0]
CASES = [
    {"label": "C28_adaptive", "export": os.path.join(RUN, "cases", "C28", "export"),
     "case": os.path.join(RUN, "cases", "C28", "case_adaptive"),
     "dataset": "C28_adaptive", "keep_stimulus": True, "frequencies": []},
    {"label": "C28_discrete", "export": os.path.join(RUN, "cases", "C28", "export"),
     "case": os.path.join(RUN, "cases", "C28", "case_discrete"),
     "dataset": "C28_discrete", "keep_stimulus": False, "frequencies": CHECKPOINTS},
    {"label": "C30_adaptive", "export": os.path.join(RUN, "cases", "C30", "export"),
     "case": os.path.join(RUN, "cases", "C30", "case_adaptive"),
     "dataset": "C30_adaptive", "keep_stimulus": True, "frequencies": []},
    {"label": "C30_discrete", "export": os.path.join(RUN, "cases", "C30", "export"),
     "case": os.path.join(RUN, "cases", "C30", "case_discrete"),
     "dataset": "C30_discrete", "keep_stimulus": False, "frequencies": CHECKPOINTS},
]


def main() -> None:
    sweep_dir = os.path.join(RUN, "work", "sweep")
    os.makedirs(sweep_dir, exist_ok=True)
    status_path = os.path.join(sweep_dir, "fullband-status.json")
    results = {}
    if os.path.isfile(status_path):
        results = json.load(open(status_path, "r", encoding="utf-8"))
    for case in CASES:
        label = case["label"]
        if label in results and results[label].get("finished"):
            continue
        record = dict(case)
        started = time.time()
        try:
            if os.path.exists(case["case"]):
                record["existing_case"] = True
                record.update(rm.status(case["case"]))
            else:
                rm.prepare(case["export"], case["case"], case["dataset"],
                           case["frequencies"], mesh_um=50.0, matrix_solver=0,
                           threads=4, keep_stimulus=case["keep_stimulus"])
                rm.launch(case["case"])
                record.update(rm.wait(case["case"], timeout_s=1800.0, interval_s=10.0))
        except Exception as exc:
            record["error"] = repr(exc)
        record["elapsed_s"] = time.time() - started
        results[label] = record
        with open(status_path, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(results, stream, indent=2)
            stream.write("\n")
        print(f"{label} finished={record.get('finished')} elapsed={record['elapsed_s']:.1f}s",
              flush=True)
    print("FULLBAND_DONE", flush=True)


if __name__ == "__main__":
    if "--test" in sys.argv:
        print("import ok", sys.version)
    else:
        main()
