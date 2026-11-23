"""Synthesize, simulate, and verify an equal-termination ideal low-pass ladder."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np


CSV_FIELDS = (
    "freq_hz", "s11_real", "s11_imag", "s21_real", "s21_imag",
    "s12_real", "s12_imag", "s22_real", "s22_imag",
)
PORT_ORDER = ((0, 0), (1, 0), (0, 1), (1, 1))
COMPLEX_TOLERANCE = 1e-6
PHYSICS_TOLERANCE = 1e-8


def synthesize(spec):
    """Select the lowest supported odd Chebyshev-I order and scale its ladder."""
    edge = spec["passband_hz"]
    impedance = spec["impedance_ohm"]
    return_loss = -min(spec["s11_max_db"], spec["s22_max_db"])
    il_limit = spec["insertion_loss_max_db"]
    if il_limit is not None:
        power_reflection = -math.expm1(-il_limit * math.log(10.0) / 10.0)
        return_loss = max(return_loss, -10.0 * math.log10(power_reflection))
    # Leave numerical room for a strict inequality when the requested margin is zero.
    return_loss += max(spec.get("return_loss_margin_db", 1.0), 1e-8)
    reflection_power = 10.0 ** (-return_loss / 10.0)
    epsilon = math.sqrt(reflection_power / (1.0 - reflection_power))
    ripple_db = 10.0 / math.log(10.0) * math.log1p(epsilon * epsilon)

    bounds = []
    for stop in spec["stopbands"]:
        rejection = math.expm1(-stop["s21_max_db"] * math.log(10.0) / 10.0)
        bounds.append(
            math.acosh(max(1.0, math.sqrt(rejection) / epsilon))
            / math.acosh(stop["frequency_hz"] / edge)
        )
    order_bound = max(bounds)
    order = max(1, math.ceil(order_bound))
    if order % 2 == 0:
        order += 1
    if order > spec.get("max_order", 15):
        raise ValueError(
            f"Chebyshev-I synthesis needs odd order {order}, above the configured maximum."
        )

    gamma = math.sinh(math.asinh(1.0 / epsilon) / order)
    a = [math.sin((2 * k - 1) * math.pi / (2 * order)) for k in range(1, order + 1)]
    b = [gamma**2 + math.sin(k * math.pi / order)**2 for k in range(1, order)]
    prototype = [1.0, 2.0 * a[0] / gamma]
    for k in range(2, order + 1):
        prototype.append(4.0 * a[k - 2] * a[k - 1] / (b[k - 2] * prototype[k - 1]))
    prototype.append(1.0)

    omega = 2.0 * math.pi * edge
    elements = []
    for k in range(1, order + 1):
        series = k % 2 == 1
        kind = "L" if series else "C"
        value = impedance * prototype[k] / omega if series else prototype[k] / (impedance * omega)
        elements.append({
            "name": f"{kind}{(k + 1) // 2}",
            "kind": kind,
            "value": value,
            "unit": "H" if series else "F",
            "connection": "series" if series else "shunt_to_ground",
        })
    extrema = sorted(edge * math.cos(k * math.pi / order) for k in range((order + 1) // 2))
    return {
        "family": "chebyshev_i_series_first",
        "order": order,
        "order_bound": order_bound,
        "impedance_ohm": impedance,
        "passband_hz": edge,
        "return_loss_target_db": return_loss,
        "ripple_db": ripple_db,
        "epsilon": epsilon,
        "prototype": prototype,
        "elements": elements,
        "reflection_extrema_hz": extrema,
    }


def abcd_s(freq_hz, design):
    """Cascade independent ABCD sections and return S[f, output, input]."""
    frequencies = np.atleast_1d(np.asarray(freq_hz, dtype=float))
    omega = 2.0 * math.pi * frequencies
    identity = np.broadcast_to(np.eye(2, dtype=complex), (len(frequencies), 2, 2))
    matrices = identity.copy()
    for element in design["elements"]:
        section = identity.copy()
        if element["kind"] == "L":
            section[:, 0, 1] = 1j * omega * element["value"]
        elif element["kind"] == "C":
            section[:, 1, 0] = 1j * omega * element["value"]
        else:
            raise ValueError(f"Unsupported ideal element: {element['kind']}")
        matrices = matrices @ section
    a, b = matrices[:, 0, 0], matrices[:, 0, 1]
    c, d = matrices[:, 1, 0], matrices[:, 1, 1]
    z = design["impedance_ohm"]
    denominator = a + b / z + c * z + d
    result = np.empty_like(matrices)
    result[:, 0, 0] = (a + b / z - c * z - d) / denominator
    result[:, 1, 1] = (-a + b / z - c * z + d) / denominator
    result[:, 1, 0] = 2.0 / denominator
    # Each series or shunt section has determinant one, as does their cascade.
    result[:, 0, 1] = result[:, 1, 0]
    return result


def _frequency_tolerance(target):
    return min(1.0, target * 1e-10)


def _checkpoint(freq, target, other_targets=()):
    index = int(np.argmin(np.abs(freq - target)))
    distance = abs(float(freq[index]) - target)
    nearest_target = min((abs(value - target) for value in other_targets if value != target), default=math.inf)
    if distance <= _frequency_tolerance(target) and distance < nearest_target / 2:
        return index
    return None


def _db(values):
    with np.errstate(divide="ignore"):
        return 20.0 * np.log10(np.abs(values))


def _metric(value, frequency, limit, operator):
    passes = None
    if limit is not None:
        passes = bool(value is not None and (value <= limit if operator == "<=" else value < limit))
    return {
        "value_db": value if value is not None and math.isfinite(value) else None,
        "frequency_hz": frequency,
        "limit_db": limit,
        "operator": operator if limit is not None else None,
        "passes": passes,
    }


def measure(spec, freq_hz, s):
    """Evaluate the sampled passband and exact stop checkpoints of a two-port."""
    freq = np.asarray(freq_hz, dtype=float)
    samples = np.asarray(s, dtype=complex)
    if freq.ndim != 1 or not len(freq) or samples.shape != (len(freq), 2, 2):
        raise ValueError("Expected frequency samples and S array shaped (n, 2, 2).")
    if (not np.isfinite(freq).all() or not np.isfinite(samples).all()
            or np.any(freq <= 0) or np.any(np.diff(freq) <= 0)):
        raise ValueError("Samples must be finite, positive, unique and sorted by frequency.")

    edge = spec["passband_hz"]
    required_frequencies = [edge, *(stop["frequency_hz"] for stop in spec["stopbands"])]
    edge_index = _checkpoint(freq, edge, required_frequencies)
    passband = freq <= edge
    if edge_index is not None:
        passband[edge_index] = True
    pb = freq[passband]
    metrics = {}
    for key, values, limit in (
        ("s11_worst", _db(samples[passband, 0, 0]), spec["s11_max_db"]),
        ("s22_worst", _db(samples[passband, 1, 1]), spec["s22_max_db"]),
        ("il_worst", -_db(samples[passband, 1, 0]), spec["insertion_loss_max_db"]),
    ):
        index = int(np.argmax(values)) if len(values) else None
        value = float(values[index]) if index is not None else None
        frequency = float(pb[index]) if index is not None else None
        metrics[key] = _metric(value, frequency, limit, "<")
    stop_metrics = []
    for stop in spec["stopbands"]:
        frequency = stop["frequency_hz"]
        index = _checkpoint(freq, frequency, required_frequencies)
        value = float(_db(samples[index, 1, 0])) if index is not None else None
        metric = _metric(value, frequency, stop["s21_max_db"], "<=")
        metric["sample_hz"] = float(freq[index]) if index is not None else None
        stop_metrics.append(metric)
    metrics["stopbands"] = stop_metrics
    coverage = {
        "passband_edge_present": edge_index is not None,
        "stopbands_present": all(stop["sample_hz"] is not None for stop in stop_metrics),
        "max_passband_step_hz": float(np.max(np.diff(pb))) if len(pb) > 1 else None,
    }
    passes = (
        coverage["passband_edge_present"] and coverage["stopbands_present"]
        and all(metrics[key]["passes"] is not False for key in ("s11_worst", "s22_worst", "il_worst"))
        and all(stop["passes"] for stop in stop_metrics)
    )
    return {"passes": passes, "metrics": metrics, "coverage": coverage}


def sweep_plan(spec, design):
    """Use identical grids for the ADS controllers and the analytical run."""
    edge = spec["passband_hz"]
    first = min(1e6, edge / 65_000)
    upper = 1.5 * max(stop["frequency_hz"] for stop in spec["stopbands"])
    sweeps = [
        ("SP_broad", first, upper, 2401),
        ("SP_passband", first, edge, 1301),
    ]
    for index, stop in enumerate(spec["stopbands"], 1):
        sweeps.append((f"SP_stop{index}", edge, stop["frequency_hz"], 2))
    for index, frequency in enumerate(design["reflection_extrema_hz"], 1):
        radius = min(1e6, edge / 65_000, (frequency - first) / 4.0)
        if frequency == edge:
            sweeps.append((f"SP_ext{index}", frequency - radius, frequency, 11))
        else:
            radius = min(radius, (edge - frequency) / 2.0)
            sweeps.append((f"SP_ext{index}", frequency - radius, frequency + radius, 21))
    return sweeps


def _verify(spec, design, sweeps, freq, samples):
    result = measure(spec, freq, samples)
    edge = spec["passband_hz"]
    coverage = result["coverage"]
    tolerance = _frequency_tolerance(edge)
    coverage["near_dc_sample"] = bool(freq[0] <= sweeps[0][1] + tolerance)
    coverage["diagnostic_sweep_present"] = bool(freq[-1] >= sweeps[0][2] - tolerance)
    gap = coverage["max_passband_step_hz"]
    coverage["passband_spacing_passes"] = bool(gap is not None and gap <= edge / 1300 + tolerance)
    coverage["reflection_extrema_present"] = all(
        _checkpoint(freq, target) is not None for target in design["reflection_extrema_hz"]
    )
    local_sweeps = [sweep for sweep in sweeps if sweep[0].startswith("SP_ext")]
    coverage["reflection_extrema_refined"] = all(
        _checkpoint(freq, start) is not None and _checkpoint(freq, stop) is not None
        for _, start, stop, _ in local_sweeps
    )

    predicted = abcd_s(freq, design)
    coefficients = [0] * design["order"] + [1]
    polynomial = np.polynomial.chebyshev.chebval(freq / edge, coefficients)
    expected_power = 1.0 / (1.0 + (design["epsilon"] * polynomial)**2)
    crosscheck = {
        "complex_abcd_error": float(np.max(np.abs(samples - predicted))),
        "chebyshev_power_error": float(np.max(np.abs(np.abs(samples[:, 1, 0])**2 - expected_power))),
        "reciprocity_error": float(np.max(np.abs(samples[:, 1, 0] - samples[:, 0, 1]))),
        "unitarity_error": float(np.max(np.abs(samples.conj().swapaxes(1, 2) @ samples - np.eye(2)))),
    }
    result["crosscheck"] = crosscheck
    result["crosscheck_passes"] = (
        crosscheck["complex_abcd_error"] <= COMPLEX_TOLERANCE
        and crosscheck["chebyshev_power_error"] <= COMPLEX_TOLERANCE
        and crosscheck["reciprocity_error"] <= PHYSICS_TOLERANCE
        and crosscheck["unitarity_error"] <= PHYSICS_TOLERANCE
    )
    result["passes"] = bool(
        result["passes"] and result["crosscheck_passes"]
        and all(value for key, value in coverage.items() if key != "max_passband_step_hz")
    )
    return result


def _write_sparameters(out, freq, samples, impedance, source):
    with (out / "sparameters.csv").open("w", newline="", encoding="utf-8") as csv_stream, (
        out / "sparameters.s2p"
    ).open("w", encoding="ascii", newline="\n") as touchstone:
        writer = csv.writer(csv_stream)
        writer.writerow(CSV_FIELDS)
        touchstone.write(f"! Ideal LC low-pass filter. Source: {source}.\n# Hz S RI R {impedance:.17g}\n")
        for frequency, matrix in zip(freq, samples):
            values = [float(frequency)]
            for i, j in PORT_ORDER:
                values.extend((float(matrix[i, j].real), float(matrix[i, j].imag)))
            writer.writerow(values)
            touchstone.write(" ".join(f"{value:.17g}" for value in values) + "\n")


def _write_plot(out, spec, freq, samples, source):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    scale = 1e9 if freq[-1] >= 1e9 else 1e6 if freq[-1] >= 1e6 else 1.0
    unit = {1e9: "GHz", 1e6: "MHz", 1.0: "Hz"}[scale]
    edge = spec["passband_hz"]
    pb = freq <= edge + _frequency_tolerance(edge)
    figure = Figure(figsize=(8.5, 6.5), layout="constrained")
    FigureCanvasAgg(figure)
    broad, match, loss = figure.subplots(3, 1)
    broad.plot(freq / scale, _db(samples[:, 1, 0]), label="S21")
    for stop in spec["stopbands"]:
        broad.plot(stop["frequency_hz"] / scale, stop["s21_max_db"], "x", color="tab:red")
    broad.axvline(edge / scale, color="0.5", linestyle=":")
    broad.set(ylabel="S21 (dB)", title=f"Ideal LC low-pass response ({source})")
    match.plot(freq[pb] / scale, _db(samples[pb, 0, 0]), label="S11")
    match.plot(freq[pb] / scale, _db(samples[pb, 1, 1]), "--", label="S22")
    match.axhline(spec["s11_max_db"], color="0.5", linestyle=":")
    if spec["s22_max_db"] != spec["s11_max_db"]:
        match.axhline(spec["s22_max_db"], color="0.5", linestyle="--")
    match.set(ylabel="Reflection (dB)")
    match.legend()
    loss.plot(freq[pb] / scale, -_db(samples[pb, 1, 0]))
    loss.set(ylabel="Insertion loss (dB)", xlabel=f"Frequency ({unit})")
    for axis in (broad, match, loss):
        axis.grid(alpha=0.25)
    figure.savefig(out / "sparameters.png", dpi=180)


def _write_report(out, spec, report):
    design = report["design"]
    result = report["measurement"]
    source = "ADS circuit simulation" if report["verification"] == "ads" else "Analytical prediction"
    lines = [
        "# Ideal LC low-pass filter",
        "",
        f"{source}. Electrical and evidence checks **{'PASS' if report['passed'] else 'FAIL'}**.",
        "",
        f"Chebyshev-I order {design['order']} at {spec['impedance_ohm']:g} Ω. "
        f"The passband edge is {spec['passband_hz'] / 1e9:g} GHz.",
        "",
        "| Metric | Value (dB) | Frequency (GHz) | Criterion (dB) | Margin (dB) |",
        "| --- | ---: | ---: | --- | ---: |",
    ]
    metrics = result["metrics"]
    rows = [(label, metrics[key]) for label, key in (
        ("Worst S11", "s11_worst"), ("Worst S22", "s22_worst"), ("Worst insertion loss", "il_worst"),
    )]
    rows += [("S21 at stop checkpoint", item) for item in metrics["stopbands"]]
    for name, item in rows:
        value = "Unavailable" if item["value_db"] is None else f"{item['value_db']:.8g}"
        frequency = "Unavailable" if item["frequency_hz"] is None else f"{item['frequency_hz'] / 1e9:.10g}"
        criterion = "Report only" if item["limit_db"] is None else f"{item['operator']} {item['limit_db']:g}"
        margin = "—"
        if item["limit_db"] is not None and item["value_db"] is not None:
            margin = f"{item['limit_db'] - item['value_db']:.6g}"
        lines.append(f"| {name} | {value} | {frequency} | {criterion} | {margin} |")
    lines.extend(["", "| Instance | Synthesized value |", "| --- | ---: |"])
    for element in design["elements"]:
        scale, unit = (1e12, "pH") if element["kind"] == "L" else (1e15, "fF")
        lines.append(f"| {element['name']} | {element['value'] * scale:.6g} {unit} |")
    lines.extend([
        "",
        "The series inductors provide a DC path. S-parameter evidence starts at a positive frequency.",
        "",
        "![S-parameter sweeps](sparameters.png)",
        "",
    ])
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def run_ideal(spec, out: Path, ads_workspace: Path | None = None):
    """Retain one ideal-stage attempt with explicit analytical or ADS provenance."""
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    stage_files = ("ideal.json", "design.json", "report.md", "sparameters.csv",
                   "sparameters.s2p", "sparameters.png", "ads-simulation")
    if any((out / name).exists() for name in stage_files):
        raise FileExistsError(f"Ideal-stage evidence already exists in {out}. Use a fresh attempt directory.")
    design = synthesize(spec)
    sweeps = sweep_plan(spec, design)
    (out / "design.json").write_text(json.dumps(design, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    if ads_workspace is None:
        freq = np.unique(np.concatenate([np.linspace(low, high, count) for _, low, high, count in sweeps]))
        samples = abcd_s(freq, design)
        verification = "analytic"
        source = "analytical ABCD cascade"
        ads_settings = None
    else:
        from .ads_ideal import simulate_ideal

        freq, samples, ads_settings = simulate_ideal(spec, design, sweeps, ads_workspace, out / "ads-simulation")
        verification = "ads"
        source = "ADS circuit simulation"

    result = _verify(spec, design, sweeps, freq, samples)
    report = {
        "passed": result["passes"],
        "verification": verification,
        "design": design,
        "measurement": result,
        "sample_count": len(freq),
        "frequency_range_hz": [float(freq[0]), float(freq[-1])],
        "sweeps": [
            {"analysis": name, "start_hz": low, "stop_hz": high, "points": count}
            for name, low, high, count in sweeps
        ],
        "ads": ads_settings,
    }
    _write_sparameters(out, freq, samples, spec["impedance_ohm"], source)
    _write_plot(out, spec, freq, samples, source)
    _write_report(out, spec, report)
    (out / "ideal.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report
