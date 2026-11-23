"""Validate Stage 2 isolated device models with native ADS one-port evidence.

The schedule is a representative 55-request E1 matrix over three distinct L
values and two distinct C values. It is a synthetic model-equation validation,
not a process characterization. No simulator data is synthesized by this file.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import time

import numpy as np

try:
    from . import model, project_config
except ImportError:
    import model, project_config

TOLERANCE = 1e-6
CELL = "unit_device_sp"


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def schedule():
    """Return deterministic representative unit requests, without ADS imports."""
    requests = []

    def add(name, label, *, q=None, f_l0_hz=None, esr_ohm=0., esl_h=0.):
        manifest = model.resolve(q=q, f_l0_hz=f_l0_hz, esr_ohm=esr_ohm, esl_h=esl_h)
        element = copy.deepcopy(next(e for e in manifest["elements"] if e["name"] == name))
        requests.append({"unit_id": f"{name}_{label}", "family": "E1",
                         "element": element, "generator": manifest["generator"],
                         "element_sha256": hashlib.sha256(_json_bytes(element)).hexdigest(),
                         "provenance": "synthetic research coefficients; no PDK data"})

    for name in ("L1", "L2", "L3"):
        add(name, "ideal")
        for q in (20, 40, 80, 200):
            add(name, f"loss_q{q}", q=q)
        for frequency in (80, 100, 320, 640):
            add(name, f"cp_f{frequency}g", f_l0_hz=frequency*1e9)
        add(name, "B", q=80, f_l0_hz=320e9, esr_ohm=.1, esl_h=2e-12)
        add(name, "near", q=40, f_l0_hz=100e9, esr_ohm=.5, esl_h=10e-12)
    for name in ("C1", "C2"):
        add(name, "ideal")
        for esr in (.05, .1, .5, 2.):
            add(name, f"esr_{esr:g}".replace(".", "p"), esr_ohm=esr)
        for esl in (1, 2, 10, 40):
            add(name, f"esl_{esl}p", esl_h=esl*1e-12)
        add(name, "B", q=80, f_l0_hz=320e9, esr_ohm=.1, esl_h=2e-12)
        add(name, "near", q=40, f_l0_hz=100e9, esr_ohm=.5, esl_h=10e-12)
    if len(requests) != 55 or len({r["unit_id"] for r in requests}) != 55:
        raise AssertionError("Unexpected E1 representative schedule")
    return requests


def sweeps_for(element):
    """Include low limits, acceptance frequencies and both sides of each SRF."""
    model.validate_element(element)
    sweeps = [("SP_broad", 1e6, 120e9, 601),
              ("SP_low", 1., 1e6, 2),
              ("SP_checkpoints", 65e9, 80e9, 2)]
    diagnostics = model.device_diagnostics(element)
    targets = []
    for key in ("lossless_tuning_hz", "actual_srf_hz"):
        frequency = diagnostics.get(key)
        if frequency is not None and not any(abs(frequency-f) <= 1 for f in targets):
            targets.append(frequency)
    for index, frequency in enumerate(targets):
        sweeps.append((f"SP_res{index}_broad", .5*frequency, 1.5*frequency, 401))
        radius = min(1e6, .01*frequency)
        sweeps.append((f"SP_res{index}_exact", frequency-radius, frequency+radius, 21))
    return sweeps


def expected_s11(frequencies, element):
    """Evaluate a finite polynomial ratio even at an ideal impedance pole."""
    f = np.atleast_1d(np.asarray(frequencies, float))
    if not np.isfinite(f).all() or np.any(f < 0):
        raise ValueError("Expected finite nonnegative frequencies")
    s = 2j*math.pi*f
    if element["kind"] == "L":
        numerator = element["rs_ohm"]+s*element["value_si"]
        denominator = 1+s*element["cp_f"]*numerator
    else:
        numerator = 1+s*element["value_si"]*element["esr_ohm"]+s*s*element["value_si"]*element["esl_h"]
        denominator = s*element["value_si"]
    return (numerator-50*denominator)/(numerator+50*denominator)


def _complex_record(value, *, singular="singular"):
    finite = bool(np.isfinite(value))
    return {"status": "finite" if finite else singular,
            "real": float(value.real) if finite else None,
            "imag": float(value.imag) if finite else None}


def _ratio_record(numerator, denominator):
    if denominator == 0:
        return {"status": "undefined" if numerator == 0 else "infinite",
                "value": None, "sign": int(np.sign(numerator))}
    result = numerator/denominator
    return {"status": "finite", "value": float(result)}


def _resonance_measurement(f, z, y, element, diagnostics):
    target = diagnostics.get("actual_srf_hz")
    if target is None:
        return {"status": "no_finite_resonance", "frequency_hz": None}
    lossless_pole = element["kind"] == "L" and element["rs_ohm"] == 0
    values = y.imag if lossless_pole else z.imag
    finite = np.isfinite(values)
    window = finite & (f >= target*.95) & (f <= target*1.05)
    ids = np.flatnonzero(window)
    roots = []
    for index in ids:
        if abs(values[index]) <= 1e-14:
            roots.append(float(f[index]))
    for low, high in zip(ids[:-1], ids[1:]):
        if values[low]*values[high] < 0:
            roots.append(float(f[low]-values[low]*(f[high]-f[low])/(values[high]-values[low])))
    measured = min(roots, key=lambda v: abs(v-target)) if roots else None
    nearest = int(np.argmin(abs(f-target)))
    return {"status": "measured" if measured is not None else "no_sampled_crossing",
            "kind": "lossless_impedance_pole_via_admittance" if lossless_pole else "reactance_zero",
            "predicted_hz": target, "frequency_hz": measured,
            "frequency_error_hz": None if measured is None else abs(measured-target),
            "exact_target_sample_within_1hz": bool(abs(f[nearest]-target) <= 1),
            "target_residual": float(values[nearest]) if finite[nearest] else None,
            "target_residual_unit": "siemens" if lossless_pole else "ohm",
            "both_sides_sampled": bool(np.any(f < target) and np.any(f > target))}


def verify_unit(frequencies, reflection, element):
    """Check ADS one-port S and conditioned mixed absolute/relative Z/Y errors.

    Returns a finite JSON-safe summary and arrays for a diagnostic CSV. Infinite
    ideal impedance is a typed physical limit; its finite one-port S and Y are
    checked without comparing two infinities.
    """
    model.validate_element(element)
    f = np.asarray(frequencies, float)
    s = np.asarray(reflection, complex)
    if (f.ndim != 1 or s.shape != f.shape or len(f) < 2 or not np.isfinite(f).all()
            or not np.isfinite(s).all() or np.any(f <= 0) or np.any(np.diff(f) <= 0)):
        raise ValueError("Expected finite sorted unique positive one-port samples")
    predicted_s = expected_s11(f, element)
    z_expected = model.device_impedance(f, element)
    y_expected = model.device_admittance(f, element)
    with np.errstate(divide="ignore", invalid="ignore"):
        z_ads = 50*(1+s)/(1-s)
        y_ads = (1-s)/(50*(1+s))
    z_finite = np.isfinite(z_expected) & np.isfinite(z_ads)
    y_finite = np.isfinite(y_expected) & np.isfinite(y_ads)
    prefer_y = ~np.isfinite(z_expected) | (abs(z_expected) > 500)
    z_selected = ~prefer_y
    y_selected = prefer_y
    selected_conditioned = bool(np.all(z_finite[z_selected]) and np.all(y_finite[y_selected]))
    z_error = np.full(len(f), np.nan)
    y_error = np.full(len(f), np.nan)
    z_error[z_finite] = abs(z_ads[z_finite]-z_expected[z_finite])/np.maximum(abs(z_expected[z_finite]), 50.)
    y_error[y_finite] = abs(y_ads[y_finite]-y_expected[y_finite])/np.maximum(abs(y_expected[y_finite]), .02)
    selected = np.where(prefer_y, y_error, z_error)
    overlap = z_finite & y_finite & (abs(z_expected) >= .5) & (abs(z_expected) <= 5000)
    overlap_z = float(np.max(z_error[overlap])) if np.any(overlap) else None
    overlap_y = float(np.max(y_error[overlap])) if np.any(overlap) else None
    max_selected = float(np.max(selected)) if np.isfinite(selected).all() else None
    abs_z = float(np.max(abs(z_ads[z_selected]-z_expected[z_selected]))) if np.all(z_finite[z_selected]) and np.any(z_selected) else None
    abs_y = float(np.max(abs(y_ads[y_selected]-y_expected[y_selected]))) if np.all(y_finite[y_selected]) and np.any(y_selected) else None
    diagnostics = model.device_diagnostics(element)
    resonance = _resonance_measurement(f, z_ads, y_ads, element, diagnostics)
    exact65 = bool(np.any(abs(f-65e9) <= 1))
    exact80 = bool(np.any(abs(f-80e9) <= 1))
    dc_expected = complex(expected_s11([0], element)[0])
    dc_delta = abs(s[0]-dc_expected)
    positive_loss = element["rs_ohm"] > 0 if element["kind"] == "L" else element["esr_ohm"] > 0
    q_records = []
    for frequency in (65e9, 80e9):
        index = int(np.argmin(abs(f-frequency)))
        impedance = z_ads[index]
        numerator = impedance.imag if element["kind"] == "L" else -impedance.imag
        terminal_q = (_ratio_record(float(numerator), float(impedance.real)) if positive_loss and np.isfinite(impedance)
                      else {"status": "undefined" if abs(numerator) < 1e-14 else "infinite_ideal_limit", "value": None})
        if element["kind"] == "L":
            intrinsic_q = _ratio_record(2*math.pi*frequency*element["value_si"], element["rs_ohm"])
        else:
            intrinsic_q = _ratio_record(1/(2*math.pi*frequency*element["value_si"]), element["esr_ohm"])
        q_records.append({"frequency_hz": frequency, "nearest_ads_hz": float(f[index]),
                          "ads_impedance_ohm": _complex_record(impedance),
                          "ads_terminal_q": terminal_q, "intrinsic_loss_q": intrinsic_q})
    resonance_required = diagnostics.get("actual_srf_hz") is not None
    resonance_ok = (not resonance_required or
                    (resonance["status"] == "measured" and resonance["exact_target_sample_within_1hz"]
                     and resonance["both_sides_sampled"] and resonance["frequency_error_hz"] <= 1e6))
    checks = {"s11_equation": bool(np.max(abs(s-predicted_s)) <= TOLERANCE),
              "selected_z_y_conditioning": selected_conditioned,
              "selected_z_y_error": bool(max_selected is not None and max_selected <= TOLERANCE),
              "overlap_present": bool(np.any(overlap)),
              "overlap_z": bool(overlap_z is not None and overlap_z <= TOLERANCE),
              "overlap_y": bool(overlap_y is not None and overlap_y <= TOLERANCE),
              "passive_one_port": bool(np.max(abs(s)**2) <= 1+1e-8),
              "exact_65ghz": exact65, "exact_80ghz": exact80,
              "through_120ghz": bool(f[-1] >= 120e9-1),
              "near_dc": bool(f[0] <= 1 and dc_delta <= TOLERANCE),
              "resonance": resonance_ok}
    summary = {"state": "VALID" if all(checks.values()) else "INVALID", "checks": checks,
               "normalized_tolerance": TOLERANCE,
               "max_complex_s11_error": float(np.max(abs(s-predicted_s))),
               "max_selected_normalized_error": max_selected,
               "max_selected_absolute_z_error_ohm": abs_z,
               "max_selected_absolute_y_error_siemens": abs_y,
               "max_overlap_normalized_z_error": overlap_z,
               "max_overlap_normalized_y_error": overlap_y,
               "selected_z_count": int(np.count_nonzero(z_selected)),
               "selected_y_count": int(np.count_nonzero(y_selected)),
               "overlap_count": int(np.count_nonzero(overlap)),
               "conditioning_rule": "Y for expected |Z|>500 ohm or an ideal impedance pole; Z otherwise; both for .5<=|Z|<=5000 ohm",
               "diagnostic_impedance_pole_count": int(np.count_nonzero(~np.isfinite(z_expected))),
               "dc": {"source": "actual model analytic zero-frequency limit; ADS lowest positive sample is separate",
                      "expected_s11": _complex_record(dc_expected), "ads_lowest_hz": float(f[0]),
                      "ads_lowest_s11": _complex_record(s[0]), "complex_difference": float(dc_delta),
                      "expected_resistance_ohm": element.get("rs_ohm") if element["kind"] == "L" else None,
                      "ads_lowest_impedance_ohm": _complex_record(z_ads[0], singular="dc_open_limit")},
               "resonance": resonance, "predicted_device": diagnostics,
               "measured_q": q_records,
               "scope": "synthetic fixed-coefficient unit model; diagnostic frequencies beyond120GHz are not a physical model validity claim"}
    json.dumps(summary, allow_nan=False)
    arrays = {"frequency_hz": f, "s11_ads": s, "s11_expected": predicted_s,
              "z_ads": z_ads, "z_expected": z_expected, "y_ads": y_ads, "y_expected": y_expected,
              "selected_error": selected, "selected_mode": np.where(prefer_y, "Y", "Z")}
    return summary, arrays


def _diagnostic_csv(path, arrays):
    fields = ["freq_hz", "s11_ads_real", "s11_ads_imag", "s11_expected_real", "s11_expected_imag"]
    for name in ("z_ads", "z_expected", "y_ads", "y_expected"):
        fields.extend((name+"_real", name+"_imag", name+"_status"))
    fields.extend(("selected_mode", "selected_normalized_error"))
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        for index, frequency in enumerate(arrays["frequency_hz"]):
            row = [frequency]
            for name in ("s11_ads", "s11_expected"):
                value = arrays[name][index]
                row.extend((value.real, value.imag))
            for name in ("z_ads", "z_expected", "y_ads", "y_expected"):
                value = arrays[name][index]
                finite = bool(np.isfinite(value))
                row.extend((value.real if finite else "", value.imag if finite else "",
                            "finite" if finite else "typed_singular_limit"))
            row.extend((arrays["selected_mode"][index], arrays["selected_error"][index]))
            writer.writerow(row)


def _audit_netlist(netlist, element):
    primitives = [(element["kind"], element["name"], element["value_si"])]
    for suffix, key, kind in (("Cp", "cp_f", "C"), ("ESR", "esr_ohm", "R"), ("ESL", "esl_h", "L")):
        value = element.get(key, 0.)
        name = f'{element["name"]}_{suffix}'
        line = next((line for line in netlist.splitlines() if line.startswith(f"{kind}:{name} ")), None)
        if bool(line) != bool(value):
            raise ValueError(f"Unit zero/nonzero branch mismatch: {name}")
        if value:
            primitives.append((kind, name, value))
    for kind, name, value in primitives:
        line = next((line for line in netlist.splitlines() if line.startswith(f"{kind}:{name} ")), None)
        match = re.search(rf"\b{kind}=([^\s]+)", line or "")
        if match is None or float(match.group(1)) != value:
            raise ValueError(f"Unit literal coefficient mismatch: {name}")
        if kind == "L":
            loss = element["rs_ohm"] if name == element["name"] else 0.
            match = re.search(r"\bR=([^\s]+)", line)
            if match is None or float(match.group(1)) != loss:
                raise ValueError(f"Unit internal series resistance mismatch: {name}")
    return {"ok": True, "method": "exact native primitive literal audit; one-port S/Z/Y independently checks connections"}


def _write_s1p(path, frequencies, reflection):
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("! Synthetic Stage 2 isolated device; bare terminal reference\n# Hz S RI R 50\n")
        for frequency, value in zip(frequencies, reflection):
            stream.write(f"{frequency:.17g} {value.real:.17g} {value.imag:.17g}\n")


def _index(root, requests, runner):
    completed = []
    for request in requests:
        path = root/"units"/request["unit_id"]/"summary.json"
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            completed.append({"unit_id": request["unit_id"], "state": value["state"],
                              "max_complex_s11_error": value["max_complex_s11_error"],
                              "max_selected_normalized_error": value["max_selected_normalized_error"]})
    valid = [r for r in completed if r["state"] == "VALID"]
    index = {"updated_utc": runner.utc(), "scheduled_count": len(requests),
             "completed_count": len(completed), "valid_count": len(valid),
             "e1_complete": len(valid) == len(requests), "units": completed,
             "representative_coverage": {"inductors": ["L1", "L2", "L3"], "capacitors": ["C1", "C2"],
                 "per_inductor": "ideal; loss Q20/40/80/200; Cp fL0 80/100/320/640GHz; B; near",
                 "per_capacitor": "ideal; ESR .05/.1/.5/2ohm; ESL1/2/10/40pH; B; near"},
             "scope": "isolated synthetic model validation; full-filter scan completeness is reported separately"}
    runner.write_json(root/"unit-summary.json", index)
    checks_path = root/"study_checks.json"
    if checks_path.exists():
        checks = json.loads(checks_path.read_text(encoding="utf-8"))
        checks["e1_complete"] = index["e1_complete"]
        runner.write_json(checks_path, checks)
    return index


def run(root, workspace, limit=5):
    """Run at most ``limit`` fresh unit cases, skipping retained completed cases.

    Execute inside the ADS Python environment. An unfinished directory is never
    overwritten; diagnose and retain the failed attempt before a new invocation.
    ``root`` is the existing study run root, and ``workspace`` is the dedicated
    Stage 2 workspace. The source unit cell is rebuilt for each parameter case.
    """
    try:
        from . import build_ads, run_study as runner
    except ImportError:
        import build_ads
        import run_study as runner
    from keysight.ads import de
    from keysight.edatoolbox import ads
    root, workspace = Path(root), Path(workspace)
    if not root.is_dir():
        raise ValueError("The retained study root must already exist")
    if limit < 1:
        raise ValueError("limit must be positive")
    unit_root = root/"units"
    unit_root.mkdir(exist_ok=True)
    requests = schedule()
    schedule_path = root/"unit-requests.json"
    if schedule_path.exists():
        old = json.loads(schedule_path.read_text(encoding="utf-8"))
        if old["requests"] != requests:
            raise ValueError("The frozen unit schedule differs from current source")
    else:
        runner.write_json(schedule_path, {"created_utc": runner.utc(), "requests": requests,
            "source_hashes": runner.source_hashes(), "prediction":
            "Finite Rs changes the low-frequency resistance; Cp changes terminal Q/SRF; ESL changes capacitor reactance sign. Ideal poles retain finite S and are checked in Y."})
    results = []
    for request in requests:
        destination = unit_root/request["unit_id"]
        if (destination/"summary.json").exists():
            continue
        if destination.exists():
            raise RuntimeError(f"Preserved unfinished unit attempt requires diagnosis: {request['unit_id']}")
        destination.mkdir()
        start = time.monotonic()
        element = request["element"]
        try:
            sweeps = sweeps_for(element)
            diagnostics = model.device_diagnostics(element)
            runner.write_json(destination/"manifest.json", dict(request, task_version=model.TASK_VERSION,
                baseline_commit=model.BASELINE_COMMIT, reference_impedance_ohm=50,
                source_hashes=runner.source_hashes(), created_utc=runner.utc()))
            runner.write_json(destination/"prediction.json", {"recorded_utc": runner.utc(),
                "phase": "before ADS simulation", "device": diagnostics,
                "dc_s11": _complex_record(expected_s11([0], element)[0]),
                "diagnostic_validity": "synthetic rational model equations only; no calibrated broadband validity"})
            bench = build_ads.build_unit(workspace, element, sweeps, cell=CELL,
                overwrite=(workspace/build_ads.LIBRARY/CELL).exists())
            netlist = bench.generate_netlist()
            audit = _audit_netlist(netlist, element)
            (destination/"schematic.net").write_text(netlist, encoding="utf-8", newline="\n")
            runner.write_json(destination/"settings.json", {"created_utc": runner.utc(),
                "testbench": f"{build_ads.LIBRARY}:{CELL}:schematic", "reference_impedance_ohm": 50,
                "bookkeeping_temperature_deg_c": 25, "coefficient_temperature_law": "none",
                "native_temperature_options": [line for line in netlist.splitlines() if "Temp=" in line],
                "ads_product_version": de.product_version().strip(), "ads_python_package_version": str(de.__version__),
                "sweeps": [{"analysis": n, "start_hz": a, "stop_hz": b, "points": c} for n,a,b,c in sweeps],
                "netlist_saved_bytes_sha256": runner.sha(destination/"schematic.net"), "native_audit": audit,
                "source_hashes": runner.source_hashes()})
            inputs = destination/"source-inputs"
            inputs.mkdir()
            runner.snapshot_sources(inputs)
            helpers = inputs/"ideal-tools"
            helpers.mkdir()
            for name in ("rebuild_ads.py", "analyze.py"):
                baseline_tools = project_config.load_project()["paths"]["baseline"] / "tools"
                shutil.copyfile(baseline_tools/name, helpers/name)
            runner._native_snapshot(workspace, inputs/"native")
            ads.CircuitSimulator().run_netlist(netlist, output_dir=str(destination))
            runner._export(destination, CELL, ports=1)
            with (destination/"ads_sparameters.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            f = np.array([float(row["freq_hz"]) for row in rows])
            s = np.array([complex(float(row["s11_real"]), float(row["s11_imag"])) for row in rows])
            summary, arrays = verify_unit(f, s, element)
            summary.update({"unit_id": request["unit_id"], "family": "E1", "completed_utc": runner.utc(),
                            "elapsed_seconds": time.monotonic()-start, "raw_dataset": f"{CELL}.ds"})
            _diagnostic_csv(destination/"device-response.csv", arrays)
            _write_s1p(destination/"unit_device.s1p", f, s)
            runner.write_json(destination/"summary.json", summary)
            results.append({"unit_id": request["unit_id"], "state": summary["state"],
                            "max_selected_normalized_error": summary["max_selected_normalized_error"],
                            "max_complex_s11_error": summary["max_complex_s11_error"]})
        except Exception as exc:
            import traceback
            runner.write_json(destination/"failed-attempt.json", {"created_utc": runner.utc(),
                "error": repr(exc), "traceback": traceback.format_exc()})
            _index(root, requests, runner)
            raise
        if len(results) >= limit:
            break
    index = _index(root, requests, runner)
    return {"new_results": results, "completed": index["completed_count"],
            "valid": index["valid_count"], "scheduled": len(requests), "e1_complete": index["e1_complete"]}
