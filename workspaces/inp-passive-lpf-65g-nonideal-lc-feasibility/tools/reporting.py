"""Aggregate retained ADS evidence into the Stage 2 research handoff.

Integration API: ``aggregate(run_dir)`` reads requests.json (a request list or
an object with a requests list), cases/<case_id>/{manifest,prediction,summary}.json,
and ads_sparameters.csv. Optional root-owned study_checks.json records explicit
completion evidence: e1_complete, e8_complete, e9_complete,
evidence_manifest_complete, pre_run_predictions_complete. Missing checks leave
the study INCOMPLETE. This module never creates raw simulation evidence or
promotes sampled data to continuous-band acceptance.

Optional stage-decision.json may document an operator engineering judgment with
decision="TOPOLOGY REVIEW REQUIRED", nonempty rationale/scope strings and a
nonempty evidence_case_ids list of known PASS/FAIL cases. The judgment can
change readiness only after study completion; criterion_based_readiness remains
visible. The exact decision document and its saved-byte SHA-256 are retained
in machine-readable metadata; the narrative report links to the document.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

try:
    from . import analysis, cases, model
except ImportError:
    import analysis
    import cases
    import model

METRIC_NAMES = ("s11_worst", "s22_worst", "il_worst", "s21_80")
SHORT = {"s11_worst": "S11", "s22_worst": "S22", "il_worst": "IL", "s21_80": "80G"}
CHECKS = ("e1_complete", "e8_complete", "e9_complete", "evidence_manifest_complete", "pre_run_predictions_complete")
COLORS = {"PASS": "#3e916b", "FAIL": "#b94c4c", "INDETERMINATE": "#d3a344", "INVALID": "#8e9095", "MISSING": "#dadce0"}


def _read(path: Path, default=None):
    if not path.is_file():
        return default
    def reject_constant(value):
        raise ValueError(f"Nonfinite JSON constant: {value}")
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream, parse_constant=reject_constant)


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8", newline="\n")


def _csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _format(value, suffix="", digits=6) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}g}{suffix}"
    return str(value)


def _metric_text(metric) -> str:
    if not metric:
        return "unavailable"
    value = _format(metric.get("value_db"), " dB") if metric.get("db_status", "finite") == "finite" else metric.get("db_status")
    return f"{value} at {_format((metric.get('frequency_hz') or 0)/1e9, ' GHz')}; {metric.get('state', 'unavailable')}"


def _stage_decision(run: Path, records: dict[str, dict], study_state: str,
                    criterion_based_readiness: str) -> tuple[str, dict | None]:
    """Apply only validated, documented topology-review judgment after closure."""
    source = run/"stage-decision.json"
    if not source.is_file():
        return criterion_based_readiness, None
    details = {"source_file": "stage-decision.json", "source_sha256": None,
               "document": None, "validation_issues": [], "applied": False}
    try:
        details["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        document = _read(source)
        details["document"] = document
        if not isinstance(document, dict):
            raise ValueError("Stage decision must be a JSON object")
        if document.get("decision") != "TOPOLOGY REVIEW REQUIRED":
            details["validation_issues"].append("Only an explicit TOPOLOGY REVIEW REQUIRED engineering judgment is supported")
        for key in ("rationale", "scope"):
            if not isinstance(document.get(key), str) or not document[key].strip():
                details["validation_issues"].append(f"Nonempty {key} is required")
        evidence = document.get("evidence_case_ids")
        if not isinstance(evidence, list) or not evidence or any(not isinstance(case_id, str) for case_id in evidence):
            details["validation_issues"].append("evidence_case_ids must be a nonempty list of case IDs")
        else:
            if len(evidence) != len(set(evidence)):
                details["validation_issues"].append("Evidence case IDs must be unique")
            for case_id in evidence:
                if case_id not in records:
                    details["validation_issues"].append(f"Unknown evidence case: {case_id}")
                elif records[case_id]["state"] not in ("PASS", "FAIL"):
                    details["validation_issues"].append(f"Evidence case is unresolved or invalid: {case_id}")
    except (OSError, ValueError, TypeError) as exc:
        details["validation_issues"].append(str(exc))
    if details["validation_issues"]:
        details["status"] = "REJECTED: invalid decision evidence; criterion-based readiness retained"
        return criterion_based_readiness, details
    if study_state != "COMPLETE":
        details["status"] = "PENDING: incomplete study retains NOT READY precedence"
        return "NOT READY", details
    details["applied"] = True
    details["status"] = "APPLIED: documented engineering judgment after study completion"
    return "TOPOLOGY REVIEW REQUIRED", details


def _load_records(run: Path, requests: list[dict]) -> dict[str, dict]:
    records = {}
    for row in requests:
        case_id = row["case_id"]
        if case_id in records:
            continue
        directory = run/"cases"/case_id
        record = {"case_id": case_id, "directory": directory, "requests": [], "issues": []}
        for name in ("manifest", "summary", "prediction"):
            try:
                record[name] = _read(directory/f"{name}.json")
            except (OSError, ValueError) as exc:
                record[name] = None
                record["issues"].append(f"Unreadable {name}.json: {exc}")
        if record["manifest"] is None:
            record["issues"].append("Missing retained manifest.json")
        else:
            try:
                model.validate(record["manifest"])
                if row.get("physical_sha256") and model.physical_hash(record["manifest"]) != row["physical_sha256"]:
                    record["issues"].append("Resolved manifest does not match request physical hash")
            except (ValueError, TypeError, KeyError) as exc:
                record["issues"].append(f"Invalid retained manifest: {exc}")
        record["state"] = (record["summary"] or {}).get("state", "MISSING")
        if record["state"] not in ("PASS", "FAIL", "INDETERMINATE", "INVALID", "MISSING"):
            record["issues"].append("Unknown summary result state")
            record["state"] = "INVALID"
        if record["issues"] and record["state"] != "MISSING":
            record["state"] = "INVALID"
        records[case_id] = record
    for row in requests:
        records[row["case_id"]]["requests"].append(row)
    return records


def _sensitivity(requests: list[dict], records: dict[str, dict]) -> list[dict]:
    pairs = defaultdict(dict)
    for row in requests:
        labels = row.get("labels", {})
        change = labels.get("fractional_change")
        if row["family"] in ("E5", "E7") and labels.get("element") and change in (-.01, .01):
            pairs[(row["family"], labels["element"])][change] = row
    result = []
    for (family, element), pair in sorted(pairs.items()):
        for metric_name in METRIC_NAMES:
            row = {"family": family, "element": element, "metric": metric_name,
                   "units": "dB per unit fractional value change", "coefficient_policy": "frozen"}
            available = True
            metrics = {}
            for sign, key in ((-.01, "minus"), (.01, "plus")):
                request = pair.get(sign)
                record = records.get(request["case_id"]) if request else None
                metric = ((record or {}).get("summary") or {}).get("metrics", {}).get(metric_name, {})
                metrics[key] = metric
                row[f"{key}_case_id"] = request["case_id"] if request else None
                row[f"{key}_state"] = metric.get("state")
                row[f"{key}_value_db"] = metric.get("value_db")
                row[f"{key}_frequency_hz"] = metric.get("frequency_hz")
                if not record or record["state"] in ("INVALID", "MISSING") or not metric:
                    available = False
            plus, minus = metrics["plus"], metrics["minus"]
            if available and plus.get("value_db") is not None and minus.get("value_db") is not None:
                row["secant_db_per_fraction"] = (plus["value_db"]-minus["value_db"])/.02
                row["secant_db_per_percent"] = row["secant_db_per_fraction"]/100
                row["status"] = "available"
            else:
                row["status"] = "undefined_db_or_missing_valid_pair"
            if available and plus.get("magnitude") is not None and minus.get("magnitude") is not None:
                row["secant_magnitude_per_fraction"] = (plus["magnitude"]-minus["magnitude"])/.02
            result.append(row)
    for family in ("E5", "E7"):
        for metric in METRIC_NAMES:
            ranked = sorted((r for r in result if r["family"] == family and r["metric"] == metric and r.get("secant_db_per_fraction") is not None),
                            key=lambda r: abs(r["secant_db_per_fraction"]), reverse=True)
            for index, row in enumerate(ranked, 1):
                row["absolute_secant_rank"] = index
    return result


def _reflection_asymmetry(requests: list[dict], records: dict[str, dict]) -> list[dict]:
    """Measure complex and magnitude asymmetry from retained four-S CSVs."""
    result = []
    selections = sorted({(row["family"], row["case_id"]) for row in requests if row["family"] in ("E5", "E7")})
    for family, case_id in selections:
        record = records[case_id]
        row = {"family": family, "case_id": case_id,
               "source": f"cases/{case_id}/ads_sparameters.csv",
               "scope": "all exported positive-frequency samples; passband subset reported separately",
               "status": "unavailable"}
        if record["state"] in ("INVALID", "MISSING"):
            row["reason"] = f"Candidate evidence state: {record['state']}"
            result.append(row)
            continue
        try:
            frequency, scattering = analysis.read_csv(record["directory"]/"ads_sparameters.csv")
            difference = abs(scattering[:, 0, 0]-scattering[:, 1, 1])
            magnitude_difference = abs(abs(scattering[:, 0, 0])-abs(scattering[:, 1, 1]))
            complex_index, magnitude_index = int(np.argmax(difference)), int(np.argmax(magnitude_difference))
            passband = frequency <= 65e9+1
            row.update({"status": "available", "sample_count": len(frequency),
                        "frequency_min_hz": float(frequency[0]), "frequency_max_hz": float(frequency[-1]),
                        "max_abs_s11_minus_s22": float(difference[complex_index]),
                        "complex_max_frequency_hz": float(frequency[complex_index]),
                        "max_abs_magnitude_s11_minus_s22": float(magnitude_difference[magnitude_index]),
                        "magnitude_max_frequency_hz": float(frequency[magnitude_index]),
                        "passband_max_abs_s11_minus_s22": float(np.max(difference[passband])) if np.any(passband) else None,
                        "passband_max_abs_magnitude_s11_minus_s22": float(np.max(magnitude_difference[passband])) if np.any(passband) else None})
            if family == "E5":
                row["lossless_magnitude_equality_within_1e8"] = row["max_abs_magnitude_s11_minus_s22"] <= 1e-8
        except (OSError, ValueError, ArithmeticError) as exc:
            row["reason"] = str(exc)
        result.append(row)
    return result


def _boundary_slices(requests: list[dict], records: dict[str, dict]) -> dict:
    axes = defaultdict(dict)
    for row in requests:
        labels = row.get("labels", {})
        if row["family"] == "E8" and labels.get("axis") and labels.get("coordinate") is not None:
            axes[labels["axis"]][labels["coordinate"]] = row
    result = {}
    for axis, nodes in sorted(axes.items()):
        samples = []
        for coordinate, request in sorted(nodes.items()):
            record = records[request["case_id"]]
            metrics = (record.get("summary") or {}).get("metrics", {})
            available = {key: metric for key, metric in metrics.items() if metric.get("signed_margin_db") is not None}
            limiting = min(available, key=lambda key: available[key]["signed_margin_db"]) if available else None
            samples.append({"coordinate": coordinate, "case_id": request["case_id"], "request_id": request["request_id"],
                            "state": record["state"], "limiting_metric": limiting,
                            "limiting_margin_db": available[limiting]["signed_margin_db"] if limiting else None,
                            "metrics": metrics, "manifest": record.get("manifest"),
                            "inductor_diagnostics": [model.device_diagnostics(e) for e in (record.get("manifest") or {}).get("elements", []) if e["kind"] == "L"]})
        brackets, unsearched = [], []
        for left, right in zip(samples[:-1], samples[1:]):
            interval = {"lower_coordinate": left["coordinate"], "upper_coordinate": right["coordinate"],
                        "width": right["coordinate"]-left["coordinate"],
                        "left_case_id": left["case_id"], "right_case_id": right["case_id"],
                        "left_state": left["state"], "right_state": right["state"]}
            if {left["state"], right["state"]} == {"PASS", "FAIL"}:
                interval.update({"left_manifest": left["manifest"], "right_manifest": right["manifest"],
                                 "left_limiting_metric": left["limiting_metric"], "right_limiting_metric": right["limiting_metric"],
                                 "endpoint_metric_uncertainties": {"left": {k: v.get("uncertainty_magnitude") for k, v in left["metrics"].items()},
                                                                   "right": {k: v.get("uncertainty_magnitude") for k, v in right["metrics"].items()}}})
                if axis == "f_l0_hz":
                    left_l = {e["name"]: e for e in left["manifest"]["elements"] if e["kind"] == "L"}
                    right_l = {e["name"]: e for e in right["manifest"]["elements"] if e["kind"] == "L"}
                    interval["cp_intervals_f"] = {name: sorted([left_l[name]["cp_f"], right_l[name]["cp_f"]]) for name in left_l}
                brackets.append(interval)
            unsearched.append(interval)
        states = {row["state"] for row in samples}
        outcome = ("sampled PASS/FAIL brackets" if brackets else "no feasible sample in this slice" if "PASS" not in states
                   else "all retained samples pass; no outer limit established" if states == {"PASS"}
                   else "no valid adjacent PASS/FAIL bracket; retain unresolved states")
        result[axis] = {"samples": samples, "brackets": brackets, "outcome": outcome,
                        "unsearched_interval_interiors": unsearched,
                        "scope": "Sampled local intervals only; no monotonicity or unique global boundary claim"}
    return result


def _plot_module():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.facecolor": "white"})
    return plt


def _e6_plot(path: Path, requests: list[dict], records: dict[str, dict]) -> None:
    plt = _plot_module()
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    selected = [r for r in requests if r["family"] == "E6"]
    if not selected:
        return
    q_values = sorted({r["labels"]["q"] for r in selected})
    f_values = sorted({r["labels"]["f_l0_hz"] for r in selected})
    groups = sorted({(r["labels"]["esr_ohm"], r["labels"]["esl_h"]) for r in selected})
    states = list(COLORS)
    figure, axes = plt.subplots(2, 2, figsize=(12, 9), squeeze=False)
    for axis, (esr, esl) in zip(axes.flat, groups):
        grid = np.full((len(q_values), len(f_values)), states.index("MISSING"))
        for row in selected:
            labels = row["labels"]
            if (labels["esr_ohm"], labels["esl_h"]) != (esr, esl):
                continue
            record = records[row["case_id"]]
            i, j = q_values.index(labels["q"]), f_values.index(labels["f_l0_hz"])
            grid[i, j] = states.index(record["state"])
            failed = [SHORT[k] for k, v in (record.get("summary") or {}).get("metrics", {}).items() if v.get("state") == "FAIL" and k in SHORT]
            text = record["state"]+(("\n"+"/".join(failed)) if failed else "")
            axis.text(j, i, text, ha="center", va="center", fontsize=7, color="white" if record["state"] in ("PASS", "FAIL", "INVALID") else "#222222")
        axis.imshow(grid, cmap=ListedColormap([COLORS[s] for s in states]), vmin=-.5, vmax=len(states)-.5, origin="lower", aspect="auto")
        axis.set(xticks=range(len(f_values)), xticklabels=[f"{f/1e9:g}" for f in f_values],
                 yticks=range(len(q_values)), yticklabels=[f"{q:g}" for q in q_values],
                 xlabel="Lossless tuning label fL0 (GHz)", ylabel="RL-branch Q label at 65 GHz",
                 title=f"ESR={esr:g} ohm; ESL={esl*1e12:g} pH")
    figure.suptitle("E6 conditional feasibility under synthetic fixed coefficients")
    figure.legend(handles=[Patch(color=COLORS[s], label=s) for s in states], loc="lower center", ncol=len(states))
    figure.tight_layout(rect=(0, .04, 1, .96))
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _deep_selection(requests: list[dict], records: dict[str, dict], boundaries: dict) -> dict[str, list[str]]:
    selection = {}
    for label, predicate in (("ideal", lambda r: r["family"] == "E0"),
                             ("anchor-b", lambda r: r.get("labels", {}).get("anchor_b")),
                             ("near-resonance", lambda r: r.get("labels", {}).get("e9_near_resonance"))):
        row = next((r for r in requests if predicate(r)), None)
        if row:
            selection[label] = [row["case_id"]]
    brackets = [(axis, bracket) for axis, value in boundaries.items() for bracket in value["brackets"]]
    if brackets:
        axis, bracket = min(brackets, key=lambda x: x[1]["width"]/max(abs(x[1]["upper_coordinate"]), 1e-30))
        selection[f"e8-{axis}-bracket"] = [bracket["left_case_id"], bracket["right_case_id"]]
    else:
        candidates = [sample for value in boundaries.values() for sample in value["samples"]
                      if sample["state"] in ("PASS", "FAIL") and sample["limiting_margin_db"] is not None]
        if candidates:
            closest = min(candidates, key=lambda sample: abs(sample["limiting_margin_db"]))
            selection["e8-no-bracket-closest"] = [closest["case_id"]]
    return selection


def _e8_plot(path: Path, boundaries: dict) -> None:
    if not boundaries:
        return
    plt = _plot_module()
    figure, axes = plt.subplots(2, 2, figsize=(11, 7), squeeze=False)
    for axis, (name, data) in zip(axes.flat, sorted(boundaries.items())):
        scale, unit = ((1e9, "GHz") if name == "f_l0_hz" else
                       (1e-12, "pH") if name == "esl_h" else (1., "ohm") if name == "esr_ohm" else (1., "Q label"))
        for sample in data["samples"]:
            margin = sample["limiting_margin_db"]
            if margin is not None:
                axis.scatter(sample["coordinate"]/scale, margin, color=COLORS[sample["state"]], s=35)
        axis.axhline(0, color="grey", linestyle=":")
        if name in ("q", "f_l0_hz"):
            axis.set_xscale("log")
        axis.set(xlabel=f"{name} ({unit})", ylabel="Smallest signed metric margin (dB)", title=data["outcome"])
        axis.grid(alpha=.2)
    figure.suptitle("E8 retained sample nodes; unsampled interiors are unresolved")
    figure.tight_layout(rect=(0, 0, 1, .95))
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _deep_dive(run: Path, label: str, case_ids: list[str], records: dict[str, dict], baseline_record: dict | None) -> dict:
    directory = run/"deep_dive"/label
    directory.mkdir(parents=True, exist_ok=True)
    output = {"selection": label, "case_ids": case_ids, "cases": [], "ok": True, "issues": []}
    baseline_data = None
    if baseline_record:
        try:
            baseline_data = analysis.read_csv(baseline_record["directory"]/"ads_sparameters.csv")
        except (OSError, ValueError) as exc:
            output["issues"].append(f"Ideal ADS overlay unavailable: {exc}")
    else:
        output["issues"].append("Ideal ADS baseline unavailable")
    for case_id in case_ids:
        record = records[case_id]
        if record.get("manifest") is None or record["state"] in ("INVALID", "MISSING"):
            output["issues"].append(f"{case_id}: valid retained model/data unavailable")
            continue
        try:
            frequencies, scattering = analysis.read_csv(record["directory"]/"ads_sparameters.csv")
            pole_data = analysis.poles(record["manifest"])
            devices = [model.device_diagnostics(e) for e in record["manifest"]["elements"] if e["kind"] == "L"]
            case_data = {"case_id": case_id, "state": record["state"], "summary": record["summary"],
                         "devices": devices, "poles": pole_data,
                         "predicted_extrema_hz": (record.get("prediction") or {}).get("all_extrema_hz"),
                         "physical_scope": "Device resonance, transfer poles, reflection extrema and transmission zeros are distinct"}
            output["cases"].append(case_data)
            if not pole_data.get("residuals_ok"):
                output["issues"].append(f"{case_id}: rational pole residual check failed")
            plt = _plot_module()
            figure, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
            def response(f, s, style, prefix):
                with np.errstate(divide="ignore"):
                    axes[0].plot(f/1e9, np.maximum(20*np.log10(abs(s[:, 1, 0])), -100), style, label=f"{prefix} S21")
                    axes[1].plot(f/1e9, np.maximum(20*np.log10(abs(s[:, 0, 0])), -100), style, label=f"{prefix} S11")
                    axes[1].plot(f/1e9, np.maximum(20*np.log10(abs(s[:, 1, 1])), -100), style, alpha=.6, label=f"{prefix} S22")
                axes[2].plot(f/1e9, 1-abs(s[:, 0, 0])**2-abs(s[:, 1, 0])**2, style, label=f"{prefix} A1")
                axes[2].plot(f/1e9, 1-abs(s[:, 1, 1])**2-abs(s[:, 0, 1])**2, style, alpha=.6, label=f"{prefix} A2")
            if baseline_data:
                response(*baseline_data, "--", "Ideal ADS")
            response(frequencies, scattering, "-", "Case ADS")
            for axis in axes:
                axis.axvline(65, color="grey", alpha=.4)
                axis.axvline(80, color="grey", alpha=.4)
                axis.grid(alpha=.2)
                axis.legend(loc="best", fontsize=7)
            axes[0].axhline(-1, color="grey", linestyle=":")
            axes[0].set(ylabel="Transmission (dB)", title=f"{case_id}: retained ADS response (display floor -100 dB)")
            axes[1].axhline(-20, color="grey", linestyle=":")
            axes[1].set(ylabel="Reflection (dB)")
            axes[2].set(xlabel="Frequency (GHz)", ylabel="Absorbed incident power", xlim=(0, 120))
            figure.tight_layout()
            figure.savefig(directory/f"{case_id}-response.png", dpi=150)
            plt.close(figure)
            figure, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
            largest_resonance = max([120e9]+[d["actual_srf_hz"] or 0 for d in devices])
            diagnostic_f = np.unique(np.r_[np.linspace(1e6, 120e9, 1601),
                                          np.linspace(120e9, 1.1*largest_resonance, 801)])
            for element in record["manifest"]["elements"]:
                if element["kind"] != "L":
                    continue
                z = model.device_impedance(diagnostic_f, element)
                central = element["name"] in ("L2", "L3", "L4")
                linestyle, alpha = ("-", 1) if central else ("--", .5)
                finite = np.isfinite(z)
                axes[0].plot(diagnostic_f[finite]/1e9, z[finite].real, linestyle, alpha=alpha, label=element["name"]+" Re(Z)")
                axes[1].plot(diagnostic_f[finite]/1e9, z[finite].imag, linestyle, alpha=alpha, label=element["name"]+" Im(Z)")
                if element["rs_ohm"] > 0:
                    omega = 2*math.pi*diagnostic_f
                    value, rs, cp = element["value_si"], element["rs_ohm"], element["cp_f"]
                    terminal_q = omega*value/rs*(1-cp*rs*rs/value-omega*omega*value*cp)
                    axes[2].plot(diagnostic_f/1e9, terminal_q, linestyle, alpha=alpha, label=element["name"])
            for axis in axes:
                axis.set_yscale("symlog", linthresh=1)
                axis.axhline(0, color="grey", alpha=.3)
                axis.grid(alpha=.2)
                if axis.get_legend_handles_labels()[0]:
                    axis.legend(loc="best", fontsize=7)
            axes[0].set(ylabel="Re(Z), ohm", title="Independent declared-device diagnostics; synthetic validity only")
            axes[1].set(ylabel="Im(Z), ohm")
            axes[2].set(xlabel="Frequency (GHz)", ylabel="Signed terminal Q")
            if all(e.get("rs_ohm", 0) == 0 for e in record["manifest"]["elements"]):
                axes[2].text(.02, .5, "Lossless Q is infinite/undefined; no finite curve is assigned", transform=axes[2].transAxes)
            figure.tight_layout()
            figure.savefig(directory/f"{case_id}-inductors.png", dpi=150)
            plt.close(figure)
            figure, axis = plt.subplots(figsize=(7, 5))
            roots = pole_data["poles"]
            axis.scatter([r["s_real_per_s"]/(2*math.pi*1e9) for r in roots],
                         [r["s_imag_rad_per_s"]/(2*math.pi*1e9) for r in roots], marker="x", label="Denominator roots")
            candidates = [r for r in roots if r["possible_cancellation"]]
            if candidates:
                axis.scatter([r["s_real_per_s"]/(2*math.pi*1e9) for r in candidates],
                             [r["s_imag_rad_per_s"]/(2*math.pi*1e9) for r in candidates], facecolors="none", edgecolors="grey", s=80, label="Cancellation candidate")
            axis.axvline(0, color="grey", alpha=.4)
            axis.axhline(0, color="grey", alpha=.4)
            axis.set(xlabel="Real(s)/(2 pi), GHz", ylabel="Imag(s)/(2 pi), GHz", title=f"{case_id}: rational transfer poles")
            axis.legend()
            axis.grid(alpha=.2)
            figure.tight_layout()
            figure.savefig(directory/f"{case_id}-poles.png", dpi=150)
            plt.close(figure)
        except (OSError, ValueError, ArithmeticError, KeyError) as exc:
            output["issues"].append(f"{case_id}: {type(exc).__name__}: {exc}")
    output["ok"] = bool(not output["issues"] and len(output["cases"]) == len(case_ids))
    _write(directory/"diagnostics.json", output)
    return output


def _learning(run: Path, requests: list[dict], records: dict[str, dict], sensitivity: list[dict], boundaries: dict,
              reflection_asymmetry: list[dict]) -> None:
    explanations = {
        "E0": "With every parasitic branch absent, the declared model reduces to the pinned Chebyshev ladder. Compare its complex response and all four metrics with the retained ideal anchor.",
        "E2": "Fixed Rs lowers the DC transmission and dissipates power. Reduced reflection can arise from absorption; assess IL and A1/A2 together. The DC bound is necessary, not sufficient for RF feasibility.",
        "E3": "Terminal Cp bypasses each RL arm. Below lossless resonance it raises effective inductance; near resonance it creates strong reactance distortion. Zero absorption in the lossless limit distinguishes this mechanism from Rs.",
        "E4": "ESR dissipates energy; ESL moves the shunt branch toward series resonance and makes it inductive beyond resonance. Their effects on extrema and individual metrics need not be monotonic.",
        "E5": "Independent nominal-value changes can break mirror symmetry and change the reflection phases/complex values while switching the active worst-case reflection peak. Reciprocity and losslessness with equal real port impedances still require |S11|=|S22| at every frequency; structural asymmetry alone does not create unequal reflection magnitudes here. Central secants describe deterministic local sensitivity, not process variation or yield.",
        "E6": "Combined loss and parasitics interact through altered currents, reactive loading and damping. Conditional feasibility belongs to complete frozen coefficient sets; Q or an isolated notch alone cannot decide it.",
        "E7": "Loss and parasitics remain fixed when L/C vary, so their derived Q and resonance move. In this lossy reciprocal network, asymmetric perturbations can produce unequal reflection magnitudes as well as unequal complex reflections; symmetric cases may retain equality. Compare the nonideal central secants with E5 and retain peak frequencies on both sides.",
        "E8": "Adjacent valid PASS/FAIL samples bound a sampled local transition. Retain separate windows and unsearched interiors; no monotonicity or global component limit follows from this slice budget."}
    lines = ["# Stage 2 learning record", "", "Predictions must be read from the separately retained pre-run record. The text below is a post-run observation and physical interpretation; its existence does not establish prediction timing.", ""]
    for family, explanation in explanations.items():
        rows = [r for r in requests if r["family"] == family]
        counts = Counter(records[r["case_id"]]["state"] for r in rows)
        lines.extend([f"## {family}", "", f"Physical explanation: {explanation}", "",
                      "Observation: "+", ".join(f"{state}={count}" for state, count in sorted(counts.items()))+" request mappings.", ""])
        family_cases = {row["case_id"] for row in rows}
        for metric_name in METRIC_NAMES:
            observations = [(case_id, (records[case_id].get("summary") or {}).get("metrics", {}).get(metric_name, {})) for case_id in family_cases]
            finite = [(case_id, metric) for case_id, metric in observations if metric.get("value_db") is not None and records[case_id]["state"] not in ("INVALID", "MISSING")]
            if finite:
                low, high = min(finite, key=lambda row: row[1]["value_db"]), max(finite, key=lambda row: row[1]["value_db"])
                lines.append(f"- {metric_name}: observed range {_format(low[1]['value_db'])} to {_format(high[1]['value_db'])} dB; endpoint evidence cases/{low[0]}/summary.json and cases/{high[0]}/summary.json. Associated worst-case frequencies are {_format(low[1].get('frequency_hz'))} and {_format(high[1].get('frequency_hz'))} Hz.")
        lines.append("")
        if family in ("E5", "E7"):
            available_asymmetry = [row for row in reflection_asymmetry if row["family"] == family and row["status"] == "available"]
            if available_asymmetry:
                complex_peak = max(available_asymmetry, key=lambda row: row["max_abs_s11_minus_s22"])
                magnitude_peak = max(available_asymmetry, key=lambda row: row["max_abs_magnitude_s11_minus_s22"])
                lines.append(f"- Raw-CSV reflection comparison over all exported frequencies: maximum |S11-S22|={_format(complex_peak['max_abs_s11_minus_s22'])} at {_format(complex_peak['complex_max_frequency_hz'])} Hz in {complex_peak['source']}; maximum ||S11|-|S22||={_format(magnitude_peak['max_abs_magnitude_s11_minus_s22'])} at {_format(magnitude_peak['magnitude_max_frequency_hz'])} Hz in {magnitude_peak['source']}. Per-case and passband comparisons are retained in reflection-asymmetry.csv.")
            else:
                lines.append("- Numerical reflection-asymmetry comparison is unavailable; consult reflection-asymmetry.json for missing or invalid raw-CSV evidence.")
            for metric in METRIC_NAMES:
                ranked = sorted((r for r in sensitivity if r["family"] == family and r["metric"] == metric and r.get("absolute_secant_rank")), key=lambda r: r["absolute_secant_rank"])
                if ranked:
                    lines.append(f"- {metric}: largest absolute local secant is {ranked[0]['element']}, {_format(ranked[0]['secant_db_per_percent'])} dB per 1% value change; both observed peak frequencies are retained in sensitivity.csv.")
            lines.append("")
        if family == "E8":
            for axis, value in boundaries.items():
                lines.append(f"- {axis}: {value['outcome']}; {len(value['brackets'])} retained adjacent brackets.")
            lines.append("")
        lines.extend(["Decision: retain complete metric failures and uncertainty; use resolved valid cases to constrain the next data-mapping decision. Resolve missing or indeterminate mandatory evidence before closing this work package.", ""])
    lines.extend(["## E1 and E9", "", "Unit-device validation and fresh-workspace reproduction are determined by their retained evidence and the completion ledger. Filter overlays cannot substitute for either requirement.", ""])
    (run/"learning.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def aggregate(run_dir: str | Path) -> dict[str, Any]:
    """Create transparent research exports; missing evidence remains incomplete."""
    run = Path(run_dir)
    mapping = _read(run/"requests.json", [])
    requests = mapping.get("requests", []) if isinstance(mapping, dict) else mapping
    if not isinstance(requests, list):
        raise ValueError("requests.json must contain a request list")
    records = _load_records(run, requests)
    ledger = _read(run/"study_checks.json", {})
    reproduction = _read(run/"reproduction.json")
    sensitivity = _sensitivity(requests, records)
    reflection_asymmetry = _reflection_asymmetry(requests, records)
    _write(run/"reflection-asymmetry.json", reflection_asymmetry)
    _csv(run/"reflection-asymmetry.csv", reflection_asymmetry,
         ["family", "case_id", "status", "source", "scope", "reason", "sample_count", "frequency_min_hz", "frequency_max_hz",
          "max_abs_s11_minus_s22", "complex_max_frequency_hz", "max_abs_magnitude_s11_minus_s22", "magnitude_max_frequency_hz",
          "passband_max_abs_s11_minus_s22", "passband_max_abs_magnitude_s11_minus_s22", "lossless_magnitude_equality_within_1e8"])
    boundaries = _boundary_slices(requests, records)
    _write(run/"boundaries.json", boundaries)
    _csv(run/"sensitivity.csv", sensitivity,
         ["family", "element", "metric", "absolute_secant_rank", "status", "units", "coefficient_policy",
          "secant_db_per_fraction", "secant_db_per_percent", "secant_magnitude_per_fraction",
          "minus_case_id", "minus_state", "minus_value_db", "minus_frequency_hz",
          "plus_case_id", "plus_state", "plus_value_db", "plus_frequency_hz"])
    metric_rows = []
    mandatory_issues = []
    for case_id, record in records.items():
        summary = record.get("summary") or {}
        valid_state = record["state"] in ("PASS", "FAIL")
        if not valid_state:
            mandatory_issues.append(f"{case_id}: {record['state']}")
        if not summary.get("physics", {}).get("ok"):
            mandatory_issues.append(f"{case_id}: missing/failed independent physical checks")
        if not summary.get("coverage", {}).get("continuous_band_justified"):
            mandatory_issues.append(f"{case_id}: continuous-band coverage unresolved")
        for metric_name in METRIC_NAMES:
            metric = summary.get("metrics", {}).get(metric_name, {})
            if metric.get("state") not in ("PASS", "FAIL"):
                mandatory_issues.append(f"{case_id}: {metric_name} unresolved")
            metric_rows.append({"case_id": case_id, "requests": ";".join(r["request_id"] for r in record["requests"]),
                                "families": ";".join(sorted({r["family"] for r in record["requests"]})),
                                "case_state": record["state"], "metric": metric_name, **metric})
    _csv(run/"case_metrics.csv", metric_rows,
         ["case_id", "requests", "families", "case_state", "metric", "state", "value_db", "db_status",
          "magnitude", "frequency_hz", "signed_margin_db", "signed_margin_magnitude", "uncertainty_magnitude"])
    baseline_record = next((record for record in records.values() if any(r["family"] == "E0" for r in record["requests"])), None)
    selection = _deep_selection(requests, records, boundaries)
    deep_dives = {}
    for label, case_ids in selection.items():
        deep_dives[label] = _deep_dive(run, label, case_ids, records, baseline_record)
    if len(selection) != 4 or not all(value["ok"] for value in deep_dives.values()):
        mandatory_issues.append("Four required deep-dive selections are not all resolved")
    for key in CHECKS:
        value = ledger.get(key)
        passed = value is True or (isinstance(value, dict) and value.get("ok") is True)
        if not passed:
            mandatory_issues.append(f"Completion ledger missing or unresolved: {key}")
    expected_ids = {r["request_id"] for r in cases.requests()}
    actual_ids = {r["request_id"] for r in requests}
    if expected_ids-actual_ids:
        mandatory_issues.append(f"Missing {len(expected_ids-actual_ids)} mandatory initial request mappings")
    if not requests:
        mandatory_issues.append("No request mappings retained")
    if not {"q", "f_l0_hz", "esr_ohm", "esl_h"} <= {row.get("labels", {}).get("axis") for row in requests if row["family"] == "E8"}:
        mandatory_issues.append("Four E8 slices are not all mapped")
    nonideal_passes = [record["case_id"] for record in records.values() if record["state"] == "PASS" and record.get("manifest")
                      and any(e.get(k, 0) != 0 for e in record["manifest"]["elements"] for k in ("rs_ohm", "cp_f", "esr_ohm", "esl_h"))]
    study_state = "INCOMPLETE" if mandatory_issues else "COMPLETE"
    criterion_based_readiness = "NOT READY" if mandatory_issues else "READY FOR DATA MAPPING" if nonideal_passes else "TOPOLOGY REVIEW REQUIRED"
    readiness, operator_decision = _stage_decision(run, records, study_state, criterion_based_readiness)
    result = {"task_version": model.TASK_VERSION, "study_state": study_state, "pdk_readiness": readiness,
              "criterion_based_readiness": criterion_based_readiness, "operator_decision": operator_decision,
              "unique_case_count": len(records), "request_mapping_count": len(requests),
              "case_state_counts": dict(Counter(record["state"] for record in records.values())),
              "nonideal_passing_cases": nonideal_passes, "completion_issues": mandatory_issues,
              "completion_ledger": ledger, "deep_dive_selections": selection,
              "reproduction_evidence": reproduction,
              "deep_dive_checks": {k: {"ok": v["ok"], "issues": v["issues"]} for k, v in deep_dives.items()},
              "boundaries": boundaries, "official_benchmark_score": None,
              "scope": "Synthetic fixed-coefficient RLC; completion, conditional electrical behavior and process capability are separate"}
    _write(run/"aggregate.json", result)
    if any(row["family"] == "E6" for row in requests):
        _e6_plot(run/"e6-feasibility.png", requests, records)
    _e8_plot(run/"e8-slices.png", boundaries)
    _learning(run, requests, records, sensitivity, boundaries, reflection_asymmetry)
    lines = ["# Stage 2 conditional feasibility study", "", f"Study: **{study_state}**. PDK readiness: **{readiness}**.", "",
             f"Retained mappings: {len(requests)}; unique physical cases: {len(records)}. States: "+", ".join(f"{key}={value}" for key, value in sorted(result["case_state_counts"].items()))+".", "",
             "All coordinates are synthetic research assumptions. No result establishes InP process capability, tolerance, yield, layout/EM closure or official benchmark acceptance.", "",
             "The untuned five-series/four-shunt ladder and original electrical thresholds remain fixed. All individual metric failures are retained in case_metrics.csv.", "",
             "## Evidence and numerical status", ""]
    if mandatory_issues:
        lines.extend(["Required evidence remains unresolved:", ""]+[f"- {issue}" for issue in mandatory_issues]+[""])
    else:
        lines.extend(["All mandatory experiment mappings, numerical checks, device validations, boundary accounting, deep dives and fresh-workspace reproductions are resolved under the retained completion ledger.", ""])
    if operator_decision is not None:
        lines.extend(["## Documented stage decision", "",
                      f"Criterion-based readiness: **{criterion_based_readiness}**. Primary readiness: **{readiness}**.", "",
                      "Decision evidence: [stage-decision.json](stage-decision.json).", "",
                      operator_decision["status"]+".", ""])
        document = operator_decision.get("document")
        if isinstance(document, dict):
            lines.extend(["Rationale: "+str(document.get("rationale", "unavailable")), "",
                          "Scope: "+str(document.get("scope", "unavailable")), ""])
            evidence = document.get("evidence_case_ids")
            if isinstance(evidence, list):
                lines.extend(["Cited cases: "+", ".join(str(case_id) for case_id in evidence)+".", ""])
        if operator_decision["validation_issues"]:
            lines.extend(["Decision validation issues:", ""]+[f"- {issue}" for issue in operator_decision["validation_issues"]]+[""])
    lines.extend(["## Selected cases", "", "| Selection | Case | State | Worst S11 | Worst S22 | Worst IL | S21 at 80 GHz |", "| --- | --- | --- | --- | --- | --- | --- |"])
    for label, ids in selection.items():
        for case_id in ids:
            record = records[case_id]
            metrics = (record.get("summary") or {}).get("metrics", {})
            lines.append("| "+" | ".join([label, case_id, record["state"]]+[_metric_text(metrics.get(name)) for name in METRIC_NAMES])+" |")
    lines.extend(["", "Device curves and transfer pole residuals are retained under deep_dive/. Denominator roots with possible transmission-zero cancellation remain explicitly marked. Response peaks are not counted as poles.", "",
                  "## Boundary slices", ""])
    for axis, value in boundaries.items():
        lines.extend([f"### {axis}", "", value["outcome"]+". These are sampled local intervals; unsearched interiors and all endpoint manifests remain in boundaries.json.", "",
                      "| Coordinate | Case | State | Limiting metric | Signed margin (dB) |", "| --- | --- | --- | --- | --- |"])
        for sample in value["samples"]:
            lines.append(f"| {_format(sample['coordinate'])} | {sample['case_id']} | {sample['state']} | {sample['limiting_metric'] or 'unavailable'} | {_format(sample['limiting_margin_db'])} |")
        for bracket in value["brackets"]:
            lines.append(f"\nAdjacent bracket: [{_format(bracket['lower_coordinate'])}, {_format(bracket['upper_coordinate'])}], width {_format(bracket['width'])}; endpoints {bracket['left_case_id']} / {bracket['right_case_id']}.")
            if bracket.get("cp_intervals_f"):
                lines.append("Corresponding Cp intervals: "+"; ".join(f"{name} [{_format(lo*1e15)}, {_format(hi*1e15)}] fF" for name, (lo, hi) in bracket["cp_intervals_f"].items())+".")
        lines.append("")
    lines.extend(["## Sensitivity and physical learning", "", "sensitivity.csv retains E5/E7 central secants [m(+1%)-m(-1%)]/0.02, dB per unit fraction and dB per 1%, ranks by metric, both extremum frequencies and linear-magnitude alternatives. Peak switching can make worst-case metrics nonsmooth. E5's reciprocal lossless equal-impedance network retains equal reflection magnitudes despite possible complex/phase differences; E7's losses permit magnitude differences under asymmetric perturbations. reflection-asymmetry.csv measures both differences directly from the retained raw CSVs. See learning.md for observations and physical explanations.", "",
                  "## Prioritized PDK data request", "", "1. Available inductor/capacitor value ranges and authorized de-embedded complex impedance or S data covering DC/low frequency through 120 GHz, with actual validity range and reference planes.",
                  "2. Inductor DCR/R(f), intrinsic and terminal Q(f), actual SRF and terminal-to-terminal/substrate parasitics, especially for the 239–249 pH central arms.",
                  "3. Capacitor ESR/ESL, density, frequency dispersion and model topology; metal/substrate/ground-return and mutual-coupling information.",
                  "4. Geometry-linked coefficient co-variation and later process/temperature/mismatch model definitions. Deterministic Stage 2 perturbations supply no statistical assumptions.", "",
                  "A readiness decision authorizes comparison with data only. A separate topology study, layout/EM and robustness stages retain their own scope.", ""])
    (run/"report.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    arguments = parser.parse_args()
    summary = aggregate(arguments.run_dir)
    print(json.dumps({key: summary[key] for key in ("study_state", "pdk_readiness", "case_state_counts")}, indent=2))
