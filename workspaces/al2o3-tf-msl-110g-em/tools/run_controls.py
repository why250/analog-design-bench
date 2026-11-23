"""Run the selected-candidate numerical and physical controls.

Controls (all on C28, the 120 um / 3.0 mm selected candidate, unless noted):
  - mesh 40 um and 30 um at 65/110 GHz
  - lossless-metal and lossless-dielectric decks at 65/110 GHz
  - 9 um top-metal thickness treatment at 65/110 GHz
  - Direct-port ideal-ground probe at 65/110 GHz (port sensitivity)

Each control is a fresh case; the applied ``proj.ltd`` amendment and its
before/after SHA-256 are retained in ``control-amendment.json``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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

CASES = [
    {"label": "C28_mesh40", "export": os.path.join(RUN, "cases", "C28", "export"),
     "case": os.path.join(RUN, "cases", "C28", "case_mesh40"),
     "dataset": "C28_mesh40", "frequencies": [65.0, 110.0], "mesh_um": 40.0},
    {"label": "C28_mesh30", "export": os.path.join(RUN, "cases", "C28", "export"),
     "case": os.path.join(RUN, "cases", "C28", "case_mesh30"),
     "dataset": "C28_mesh30", "frequencies": [65.0, 110.0], "mesh_um": 30.0},
    {"label": "C28_lossless_metal", "export": os.path.join(RUN, "cases", "C28", "export"),
     "case": os.path.join(RUN, "cases", "C28", "case_lossless_metal"),
     "dataset": "C28_lossless_metal", "frequencies": [65.0, 110.0], "mesh_um": 50.0,
     "patch": "lossless_metal"},
    {"label": "C28_lossless_diel", "export": os.path.join(RUN, "cases", "C28", "export"),
     "case": os.path.join(RUN, "cases", "C28", "case_lossless_diel"),
     "dataset": "C28_lossless_diel", "frequencies": [65.0, 110.0], "mesh_um": 50.0,
     "patch": "lossless_diel"},
    {"label": "C28_thick9", "export": os.path.join(RUN, "cases", "C28", "export"),
     "case": os.path.join(RUN, "cases", "C28", "case_thick9"),
     "dataset": "C28_thick9", "frequencies": [65.0, 110.0], "mesh_um": 50.0,
     "patch": "thick9"},
    {"label": "port_direct", "export": os.path.join(RUN, "work", "port_direct", "export"),
     "case": os.path.join(RUN, "work", "port_direct", "case_65_110"),
     "dataset": "port_direct_65_110", "frequencies": [65.0, 110.0], "mesh_um": 50.0},
]


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def patch_ltd(case_dir: str, kind: str) -> dict:
    path = os.path.join(case_dir, "proj.ltd")
    original = open(path, "r", encoding="utf-8-sig").read()
    if kind == "lossless_metal":
        pattern = r"(MATERIAL Au CONDUCTIVITY=)([^ ]+)"
        replacement = r"\g<1>1e20"
    elif kind == "lossless_diel":
        pattern = r"(MATERIAL Al2O3_MSL PERMITTIVITY=9\.9 LOSSTANGENT=)([^ ]+)"
        replacement = r"\g<1>0"
    elif kind == "thick9":
        pattern = r"(OPERATION OperationThickness_cond EXPAND=)([^ ]+)"
        replacement = r"\g<1>9e-06"
    else:
        raise ValueError(kind)
    text, count = re.subn(pattern, replacement, original)
    if count != 1:
        raise RuntimeError(f"Expected one {kind} substitution, found {count}")
    open(path, "w", encoding="utf-8", newline="\n").write(text)
    receipt = {
        "kind": kind, "file": "proj.ltd",
        "before_sha256": _sha_text(original), "after_sha256": _sha_text(text),
        "substitutions": count,
    }
    with open(os.path.join(case_dir, "control-amendment.json"), "w",
              encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return receipt


def main() -> None:
    sweep_dir = os.path.join(RUN, "work", "sweep")
    os.makedirs(sweep_dir, exist_ok=True)
    status_path = os.path.join(sweep_dir, "controls-status.json")
    results = {}
    if os.path.isfile(status_path):
        results = json.load(open(status_path, "r", encoding="utf-8"))
    for case in CASES:
        label = case["label"]
        if label in results and results[label].get("finished"):
            continue
        record = {key: value for key, value in case.items() if key != "case"}
        started = time.time()
        try:
            if os.path.exists(case["case"]):
                record["existing_case"] = True
                record.update(rm.status(case["case"]))
            else:
                rm.prepare(case["export"], case["case"], case["dataset"],
                           case["frequencies"], mesh_um=case["mesh_um"],
                           matrix_solver=0, threads=4)
                if "patch" in case:
                    record["amendment"] = patch_ltd(case["case"], case["patch"])
                rm.launch(case["case"])
                record.update(rm.wait(case["case"], timeout_s=1800.0, interval_s=5.0))
        except Exception as exc:
            record["error"] = repr(exc)
        record["elapsed_s"] = time.time() - started
        results[label] = record
        with open(status_path, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(results, stream, indent=2)
            stream.write("\n")
        print(f"{label} finished={record.get('finished')} elapsed={record['elapsed_s']:.1f}s",
              flush=True)
    print("CONTROLS_DONE", flush=True)


if __name__ == "__main__":
    if "--test" in sys.argv:
        print("import ok", sys.version)
    else:
        main()
