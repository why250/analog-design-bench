"""Export and analyze the corrected Au-cover DUT (C32/C33).

Runs inside ADS for dataset export.  Produces:
  cases/<cell>/handoff/<label>.s2p
  cases/<cell>/analysis/<label>/metrics.csv, checkpoints.json, summary.json
  cases/<cell>/analysis/<label>/branch-corrected.json for sparse cases
  handoff/model/MSL_R01_AuGND_W120um_L3mm.s2p
  handoff/model/MSL_R01_AuGND_W120um_L6mm.s2p
  handoff/metrics_augnd.csv
  work/augnd-analysis-summary.json
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys

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
import analyze_em
import branch_correct

CASES = {
    "C32_adaptive": ("C32", "case_adaptive", "C32_adaptive", 3e-3, False),
    "C32_discrete": ("C32", "case_discrete", "C32_discrete", 3e-3, True),
    "C33_adaptive": ("C33", "case_adaptive", "C33_adaptive", 6e-3, False),
    "C33_discrete": ("C33", "case_discrete", "C33_discrete", 6e-3, True),
    "C32_mesh40": ("C32", "case_mesh40", "C32_mesh40", 3e-3, True),
    "C32_mesh30": ("C32", "case_mesh30", "C32_mesh30", 3e-3, True),
    "C28_discrete": ("C28", "case_discrete", "C28_discrete", 3e-3, True),
    "C30_discrete": ("C30", "case_discrete", "C30_discrete", 6e-3, True),
}


def _at(result, ghz):
    for row in result["checkpoints"]:
        if abs(row["requested_GHz"] - ghz) < 1e-9:
            return row
    return None


def main() -> None:
    summary = {"cases": {}, "datasets": {}}
    handoff = os.path.join(RUN, "handoff")
    model = os.path.join(handoff, "model")
    os.makedirs(model, exist_ok=True)
    for label, (cell, case_name, ds_name, length, sparse) in CASES.items():
        case = os.path.join(RUN, "cases", cell, case_name)
        if not runm.status(case)["finished"]:
            summary["cases"][label] = {"error": "not finished"}
            continue
        s2p = os.path.join(RUN, "cases", cell, "handoff", label + ".s2p")
        if not os.path.isfile(s2p):
            runm.export_dataset(case, s2p, s2p[:-4] + ".csv")
        analysis_dir = os.path.join(RUN, "cases", cell, "analysis", label)
        result = analyze_em.analyze(s2p, length, analysis_dir)
        record = {"s2p": s2p, "length_m": length,
                  "summary": result["summary"],
                  "checkpoints": {str(k): _at(result, k) for k in (65.0, 110.0)}}
        if sparse:
            corrected = branch_correct.correct(s2p, length)
            with open(os.path.join(analysis_dir, "branch-corrected.json"), "w",
                      encoding="utf-8", newline="\n") as stream:
                json.dump(corrected, stream, indent=2)
                stream.write("\n")
            by_freq = {row["frequency_hz"]: row for row in corrected["rows"]}
            record["branch_corrected"] = {
                str(k): by_freq.get(k * 1e9) for k in (65.0, 110.0)}
        summary["cases"][label] = record

    # Copy the selected full-band models under clear AuGND names.
    for label, name in (("C32_adaptive", "MSL_R01_AuGND_W120um_L3mm.s2p"),
                        ("C33_adaptive", "MSL_R01_AuGND_W120um_L6mm.s2p")):
        src = os.path.join(RUN, "cases", label.split("_")[0], "handoff", label + ".s2p")
        dst = os.path.join(model, name)
        shutil.copyfile(src, dst)
        summary["datasets"][label] = {"file": os.path.join("model", name),
                                      "bytes": os.path.getsize(dst)}
    # Combined metrics for the two selected lengths.
    rows = []
    for label, length, name in (("C32_adaptive", 3.0, "MSL_R01_AuGND_W120um_L3mm.s2p"),
                                ("C33_adaptive", 6.0, "MSL_R01_AuGND_W120um_L6mm.s2p")):
        src = os.path.join(RUN, "cases", label.split("_")[0], "analysis", label, "metrics.csv")
        with open(src, "r", encoding="ascii") as stream:
            for row in csv.DictReader(stream):
                row["length_mm"] = length
                row["dataset"] = name
                rows.append(row)
    columns = ["dataset", "length_mm", "frequency_hz", "Z0_real", "Z0_imag", "eps_eff",
               "alpha_Np_per_m", "alpha_dB_per_mm", "abs_S11", "abs_S21", "passivity",
               "reciprocity_error", "group_delay_s", "A_minus_D"]
    with open(os.path.join(handoff, "metrics_augnd.csv"), "w", encoding="ascii", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    summary["metrics_augnd"] = {"file": "metrics_augnd.csv", "rows": len(rows)}

    # H2: mesh 40 vs 30 at exact 65/110.
    h2 = {}
    if "C32_mesh40" in summary["cases"] and "C32_mesh30" in summary["cases"]:
        for ghz in (65.0, 110.0):
            a = summary["cases"]["C32_mesh40"].get("branch_corrected", {}).get(str(ghz))
            b = summary["cases"]["C32_mesh30"].get("branch_corrected", {}).get(str(ghz))
            if a and b:
                h2[str(ghz)] = {
                    "Z0_40": a["Z0_real"], "Z0_30": b["Z0_real"],
                    "dZ0_pct": 100 * (b["Z0_real"] - a["Z0_real"]) / a["Z0_real"],
                    "eps_40": a["eps_eff"], "eps_30": b["eps_eff"],
                    "deps_pct": 100 * (b["eps_eff"] - a["eps_eff"]) / a["eps_eff"],
                    "alpha_40": a["alpha_dB_per_mm"], "alpha_30": b["alpha_dB_per_mm"],
                    "dalpha_pct": 100 * (b["alpha_dB_per_mm"] - a["alpha_dB_per_mm"]) / a["alpha_dB_per_mm"],
                }
    summary["H2"] = h2

    # Ground-loss delta: AuGND discrete minus PERFECT_CONDUCTOR discrete.
    ground = {}
    for dut, pc, length in (("C32_discrete", "C28_discrete", 3.0),
                            ("C33_discrete", "C30_discrete", 6.0)):
        if dut in summary["cases"] and pc in summary["cases"]:
            entry = {}
            for ghz in (65.0, 110.0):
                a = summary["cases"][dut].get("branch_corrected", {}).get(str(ghz))
                b = summary["cases"][pc].get("branch_corrected", {}).get(str(ghz))
                if a and b:
                    entry[str(ghz)] = {
                        "alpha_dut": a["alpha_dB_per_mm"], "alpha_pc": b["alpha_dB_per_mm"],
                        "alpha_ground_delta": a["alpha_dB_per_mm"] - b["alpha_dB_per_mm"],
                        "Z0_dut": a["Z0_real"], "Z0_pc": b["Z0_real"],
                        "Z0_delta_pct": 100 * (a["Z0_real"] - b["Z0_real"]) / b["Z0_real"],
                        "eps_dut": a["eps_eff"], "eps_pc": b["eps_eff"],
                    }
            ground[f"{length:g}mm"] = entry
    summary["ground_loss"] = ground

    with open(os.path.join(RUN, "work", "augnd-analysis-summary.json"), "w",
              encoding="utf-8", newline="\n") as stream:
        json.dump(summary, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"cases": list(summary["cases"]), "H2": summary["H2"],
                      "ground_loss": summary["ground_loss"]}, indent=2)[:8000])


if __name__ == "__main__":
    main()
