"""Synthesize and independently verify the revision-2 ideal ADS LC low-pass filter.

This is engineering verification, not an official analog-design-bench scorer.
The verification command consumes simulator-exported complex data; it does not
generate or substitute simulated evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

ORDER = 9
Z0_OHM = 50.0
PASSBAND_EDGE_HZ = 65e9
STOP_CHECK_HZ = 80e9
RETURN_LOSS_TARGET_DB = 21.0
COMPLEX_TOLERANCE = 1e-6
PHYSICS_TOLERANCE = 1e-8
FREQUENCY_TOLERANCE_HZ = 1.0
MAX_PASSBAND_STEP_HZ = 50e6
LOCAL_RADIUS_HZ = 1e6
CSV_FIELDS = ["freq_hz", "s11_real", "s11_imag", "s21_real", "s21_imag",
              "s12_real", "s12_imag", "s22_real", "s22_imag"]


def synthesize() -> dict[str, Any]:
    """Return the equal-termination, odd-order Chebyshev-I ladder prototype."""
    ripple_db = -10.0 * math.log10(1.0 - 10.0 ** (-RETURN_LOSS_TARGET_DB / 10.0))
    epsilon = math.sqrt(10.0 ** (ripple_db / 10.0) - 1.0)
    gamma = math.sinh(math.asinh(1.0 / epsilon) / ORDER)
    a = [0.0] + [math.sin((2 * k - 1) * math.pi / (2 * ORDER))
                   for k in range(1, ORDER + 1)]
    b = [0.0] + [gamma * gamma + math.sin(k * math.pi / ORDER) ** 2
                   for k in range(1, ORDER + 1)]
    g = [1.0, 2.0 * a[1] / gamma]
    for k in range(2, ORDER + 1):
        g.append(4.0 * a[k - 1] * a[k] / (b[k - 1] * g[k - 1]))
    g.append(1.0)
    omega_p = 2.0 * math.pi * PASSBAND_EDGE_HZ
    elements = []
    for k in range(1, ORDER + 1):
        is_l = bool(k % 2)
        kind = "L" if is_l else "C"
        value = Z0_OHM * g[k] / omega_p if is_l else g[k] / (Z0_OHM * omega_p)
        elements.append({"name": f"{kind}{(k + 1) // 2}", "kind": kind,
                         "position": k, "value_si": value,
                         "unit": "H" if is_l else "F",
                         "connection": "series" if is_l else "shunt_to_ground"})
    return {"order": ORDER, "z0_ohm": Z0_OHM,
            "passband_edge_hz": PASSBAND_EDGE_HZ,
            "return_loss_target_db": RETURN_LOSS_TARGET_DB,
            "ripple_db": ripple_db, "epsilon": epsilon, "g": g,
            "elements": elements,
            "reflection_extrema_hz": reflection_extrema_hz().tolist()}


def reflection_extrema_hz() -> np.ndarray:
    """All positive-frequency reflection maxima of T_9(f/fp), including fp."""
    return np.sort(PASSBAND_EDGE_HZ * np.cos(np.arange((ORDER + 1) // 2) * math.pi / ORDER))


def abcd_s(freq_hz: np.ndarray, design: dict[str, Any] | None = None) -> np.ndarray:
    """Cascade independent series-Z/shunt-Y matrices; return S[f, output, input]."""
    design = synthesize() if design is None else design
    frequencies = np.atleast_1d(np.asarray(freq_hz, dtype=float))
    omega = 2.0 * math.pi * frequencies
    matrices = np.broadcast_to(np.eye(2, dtype=complex), (len(frequencies), 2, 2)).copy()
    for element in design["elements"]:
        stage = np.broadcast_to(np.eye(2, dtype=complex), matrices.shape).copy()
        if element["kind"] == "L":
            stage[:, 0, 1] = 1j * omega * element["value_si"]
        elif element["kind"] == "C":
            stage[:, 1, 0] = 1j * omega * element["value_si"]
        else:
            raise ValueError(f"Unsupported ideal element: {element['kind']}")
        matrices = matrices @ stage
    a, b = matrices[:, 0, 0], matrices[:, 0, 1]
    c, d = matrices[:, 1, 0], matrices[:, 1, 1]
    z0 = design["z0_ohm"]
    denominator = a + b / z0 + c * z0 + d
    result = np.empty_like(matrices)
    result[:, 0, 0] = (a + b / z0 - c * z0 - d) / denominator
    result[:, 1, 0] = 2.0 / denominator
    result[:, 0, 1] = 2.0 * (a * d - b * c) / denominator
    result[:, 1, 1] = (-a + b / z0 - c * z0 + d) / denominator
    return result


def magnitude_db(values: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore"):
        return 20.0 * np.log10(np.abs(values))


def finite_db(value: complex) -> float | None:
    result = float(magnitude_db(np.asarray(value)))
    return result if math.isfinite(result) else None


def load_csv(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != CSV_FIELDS:
            raise ValueError(f"Expected CSV header: {','.join(CSV_FIELDS)}")
        rows = [[float(row[field]) for field in CSV_FIELDS] for row in reader]
    if not rows:
        raise ValueError("Input CSV is empty")
    data = np.asarray(rows, dtype=float)
    if not np.isfinite(data).all() or np.any(data[:, 0] <= 0):
        raise ValueError("Frequencies must be positive and all complex samples finite")
    data = data[np.argsort(data[:, 0], kind="stable")]
    result = np.empty((len(data), 2, 2), dtype=complex)
    for real_col, out_port, in_port in [(1, 0, 0), (3, 1, 0), (5, 0, 1), (7, 1, 1)]:
        result[:, out_port, in_port] = data[:, real_col] + 1j * data[:, real_col + 1]
    unique_freq, unique_index, counts = np.unique(data[:, 0], return_index=True, return_counts=True)
    for index, count in zip(unique_index, counts):
        if count > 1 and np.max(np.abs(result[index:index + count] - result[index])) > 1e-8:
            raise ValueError(f"Conflicting duplicate samples at {data[index, 0]:.17g} Hz")
    return unique_freq, result[unique_index]


def verify_data(freq_hz: np.ndarray, s: np.ndarray) -> dict[str, Any]:
    f = np.asarray(freq_hz, dtype=float)
    s = np.asarray(s, dtype=complex)
    if f.ndim != 1 or len(f) < 2 or s.shape != (len(f), 2, 2):
        raise ValueError("Expected >=2 frequencies and S array with shape (n, 2, 2)")
    if not np.isfinite(f).all() or not np.isfinite(s).all() or np.any(f <= 0) or np.any(np.diff(f) <= 0):
        raise ValueError("Samples must be finite, positive, unique and sorted")
    passband = (f <= PASSBAND_EDGE_HZ + FREQUENCY_TOLERANCE_HZ)
    pf = f[passband]
    if not len(pf):
        raise ValueError("Input has no passband samples")
    predicted = abcd_s(f)
    error_per_sample = np.max(np.abs(s - predicted), axis=(1, 2))
    worst_error_index = int(np.argmax(error_per_sample))
    reciprocity_error = float(np.max(np.abs(s[:, 1, 0] - s[:, 0, 1])))
    identity = np.eye(2, dtype=complex)[None, :, :]
    unitary_error = float(np.max(np.abs(np.swapaxes(s.conj(), 1, 2) @ s - identity)))
    power_gain_excess = float(max(0.0, np.max(np.abs(s) ** 2) - 1.0))
    extrema = []
    for target in reflection_extrema_hz():
        near_index = int(np.argmin(np.abs(pf - target)))
        exact = abs(float(pf[near_index] - target)) <= FREQUENCY_TOLERANCE_HZ
        below = bool(np.any((pf < target - FREQUENCY_TOLERANCE_HZ) & (pf >= target - LOCAL_RADIUS_HZ - FREQUENCY_TOLERANCE_HZ)))
        above = bool(np.any((pf > target + FREQUENCY_TOLERANCE_HZ) & (pf <= target + LOCAL_RADIUS_HZ + FREQUENCY_TOLERANCE_HZ)))
        endpoint = abs(target - PASSBAND_EDGE_HZ) <= FREQUENCY_TOLERANCE_HZ
        extrema.append({"target_hz": float(target), "nearest_sample_hz": float(pf[near_index]),
                        "exact_sample": bool(exact), "local_below": below,
                        "local_above": above, "covered": bool(exact and below and (above or endpoint))})
    exact65 = bool(np.any(np.abs(f - PASSBAND_EDGE_HZ) <= FREQUENCY_TOLERANCE_HZ))
    exact80 = np.flatnonzero(np.abs(f - STOP_CHECK_HZ) <= FREQUENCY_TOLERANCE_HZ)
    max_gap = float(np.max(np.diff(pf))) if len(pf) > 1 else None
    coverage = {"near_dc_sample": bool(f[0] <= 1e6 + FREQUENCY_TOLERANCE_HZ),
                "exact_65ghz": exact65, "exact_80ghz": bool(len(exact80)),
                "broadband_through_120ghz": bool(f[-1] >= 120e9 - FREQUENCY_TOLERANCE_HZ),
                "max_passband_step_hz": max_gap,
                "passband_step_ok": bool(max_gap is not None and max_gap <= MAX_PASSBAND_STEP_HZ + FREQUENCY_TOLERANCE_HZ),
                "all_reflection_extrema_refined": bool(all(item["covered"] for item in extrema)),
                "extrema": extrema}
    coverage_ok = all(coverage[key] for key in ["near_dc_sample", "exact_65ghz", "exact_80ghz",
                      "broadband_through_120ghz", "passband_step_ok", "all_reflection_extrema_refined"])
    metrics = {}
    for name, values, limit, inclusive in [
        ("s11_worst", magnitude_db(s[passband, 0, 0]), -20.0, False),
        ("s22_worst", magnitude_db(s[passband, 1, 1]), -20.0, False),
        ("il_worst", -magnitude_db(s[passband, 1, 0]), 1.0, False),
    ]:
        index = int(np.argmax(values))
        value = float(values[index])
        metrics[name] = {"value_db": value if math.isfinite(value) else None,
                         "frequency_hz": float(pf[index]), "limit_db": limit,
                         "comparison": "<= " if inclusive else "< ",
                         "pass": bool(math.isfinite(value) and (value <= limit if inclusive else value < limit))}
    stop_db = float(magnitude_db(s[exact80[0], 1, 0])) if len(exact80) else None
    metrics["s21_80ghz"] = {"value_db": stop_db if stop_db is not None and math.isfinite(stop_db) else None,
                            "frequency_hz": STOP_CHECK_HZ, "limit_db": -20.0, "comparison": "<= ",
                            "pass": bool(stop_db is not None and math.isfinite(stop_db) and stop_db <= -20.0)}
    numerical = {"max_complex_s_error": float(error_per_sample[worst_error_index]),
                 "max_complex_s_error_frequency_hz": float(f[worst_error_index]),
                 "complex_s_tolerance": COMPLEX_TOLERANCE,
                 "reciprocity_error": reciprocity_error, "unitarity_error": unitary_error,
                 "power_gain_excess": power_gain_excess, "physics_tolerance": PHYSICS_TOLERANCE}
    crosscheck_ok = (numerical["max_complex_s_error"] <= COMPLEX_TOLERANCE
                     and reciprocity_error <= PHYSICS_TOLERANCE
                     and unitary_error <= PHYSICS_TOLERANCE
                     and power_gain_excess <= PHYSICS_TOLERANCE)
    return {"engineering_verification_pass": bool(coverage_ok and crosscheck_ok and all(m["pass"] for m in metrics.values())),
            "official_benchmark_score": None, "sample_count": len(f),
            "frequency_range_hz": [float(f[0]), float(f[-1])],
            "metrics": metrics, "coverage": coverage, "crosscheck": numerical,
            "crosscheck_pass": bool(crosscheck_ok), "coverage_pass": bool(coverage_ok),
            "low_frequency_sample": {"frequency_hz": float(f[0]),
                "s21_db": finite_db(s[0, 1, 0]),
                "s11_db": finite_db(s[0, 0, 0]),
                "s22_db": finite_db(s[0, 1, 1])},
            "dc_limit": {"method": "Series inductors become shorts and shunt capacitors opens as f approaches zero.",
                         "s21": 1.0, "s12": 1.0, "s11": 0.0, "s22": 0.0,
                         "simulated_at_zero_hz": False},
            "synthesis": synthesize()}


def write_touchstone(path: Path, freq_hz: np.ndarray, s: np.ndarray) -> None:
    with path.open("w", encoding="ascii", newline="\n") as handle:
        handle.write("! Ideal LC LPF; exported sampled ADS complex S parameters\n")
        handle.write("! Order: frequency, S11, S21, S12, S22 (real imaginary)\n# Hz S RI R 50\n")
        for freq, values in zip(freq_hz, s):
            row = [f"{freq:.17g}"]
            for output, input_ in [(0, 0), (1, 0), (0, 1), (1, 1)]:
                row.extend([f"{values[output, input_].real:.17g}", f"{values[output, input_].imag:.17g}"])
            handle.write(" ".join(row) + "\n")


def write_plots(directory: Path, freq_hz: np.ndarray, s: np.ndarray) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titleweight": "bold", "figure.facecolor": "white"})
    ghz = freq_hz / 1e9
    s11 = np.maximum(magnitude_db(s[:, 0, 0]), -120)
    s22 = np.maximum(magnitude_db(s[:, 1, 1]), -120)
    s21 = np.maximum(magnitude_db(s[:, 1, 0]), -120)
    fig, axes = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True, layout="constrained")
    axes[0].plot(ghz, s21, color="#1261A0", linewidth=1.8, label="ADS S21")
    axes[0].axhline(-20, color="#BB4430", linestyle="--", linewidth=1, label="80 GHz checkpoint: -20 dB")
    axes[0].scatter([80], [float(np.interp(80, ghz, s21))], s=35, color="#BB4430", zorder=3)
    axes[0].set(title="Nine-stage ideal LC low-pass | 50 ohm ports", ylabel="Transmission (dB)", ylim=(-75, 2))
    axes[1].plot(ghz, s11, color="#17846B", linewidth=1.8, label="ADS S11")
    axes[1].plot(ghz, s22, color="#7555A4", linewidth=1, linestyle="--", label="ADS S22")
    axes[1].set(ylabel="Reflection (dB)", xlabel="Frequency (GHz)", ylim=(-85, 2), xlim=(0, 120))
    for ax in axes:
        ax.axvspan(0, 65, color="#E8F2F9", alpha=.6, zorder=-2)
        ax.axvline(65, color="#536674", linewidth=.9, linestyle=":")
        ax.axvline(80, color="#BB4430", linewidth=.9, linestyle=":")
        ax.grid(alpha=.18)
        ax.legend(loc="lower left", frameon=False)
    fig.savefig(directory / "sparameters_broadband.png", dpi=180)
    plt.close(fig)

    mask = freq_hz <= PASSBAND_EDGE_HZ + FREQUENCY_TOLERANCE_HZ
    fig, axes = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True, layout="constrained")
    axes[0].plot(ghz[mask], s11[mask], color="#17846B", linewidth=1.8, label="ADS S11")
    axes[0].plot(ghz[mask], s22[mask], color="#7555A4", linestyle="--", linewidth=1, label="ADS S22")
    axes[0].axhline(-20, color="#BB4430", linestyle="--", linewidth=1, label="Strict acceptance: < -20 dB")
    extremum_indices = [int(np.argmin(abs(freq_hz - target))) for target in reflection_extrema_hz()]
    axes[0].scatter(ghz[extremum_indices], s11[extremum_indices], s=28, color="#17846B", zorder=3)
    axes[0].set(title="Passband detail | exact extrema included", ylabel="Reflection (dB)", ylim=(-65, -17))
    axes[1].plot(ghz[mask], -s21[mask], color="#1261A0", linewidth=1.8, label="ADS insertion loss")
    axes[1].set(ylabel="Insertion loss (dB)", xlabel="Frequency (GHz)", ylim=(-.002, .04), xlim=(0, 65))
    axes[1].text(.02, .93, "Acceptance: IL < 1 dB", transform=axes[1].transAxes, color="#536674", va="top")
    for ax in axes:
        ax.grid(alpha=.18)
        ax.legend(loc="lower left", frameon=False)
    fig.savefig(directory / "sparameters_passband.png", dpi=180)
    plt.close(fig)


def write_report(path: Path, summary: dict[str, Any]) -> None:
    design = summary["synthesis"]
    lines = ["# Ideal LC low-pass filter verification", "",
             f"Engineering verification: **{'PASS' if summary['engineering_verification_pass'] else 'FAIL'}**.", "",
             "This is revision-2 ideal schematic verification, not an official benchmark score or a physical InP feasibility claim.", "",
             "## Synthesis", "",
             "Chebyshev-I, order 9, series-L/shunt-C ladder, equal real 50 ohm terminations, 65 GHz passband edge.", "",
             f"Return-loss design target: 21 dB; passband ripple: {design['ripple_db']:.12g} dB; epsilon: {design['epsilon']:.12g}.", "",
             "Use epsilon = sqrt(10^(ripple/10)-1), gamma = sinh(asinh(1/epsilon)/n),",
             "a_k = sin((2k-1)pi/(2n)), b_k = gamma^2 + sin(k*pi/n)^2,",
             "g_1 = 2*a_1/gamma, g_k = 4*a_(k-1)*a_k/(b_(k-1)*g_(k-1)).",
             "With omega_p = 2*pi*65 GHz: L_k = 50*g_k/omega_p, C_k = g_k/(50*omega_p). g_0 = g_10 = 1.", "",
             "| Element | Connection | SI value | Display value |", "| --- | --- | ---: | ---: |"]
    for item in design["elements"]:
        scale, unit = (1e12, "pH") if item["kind"] == "L" else (1e15, "fF")
        lines.append(f"| {item['name']} | {item['connection']} | {item['value_si']:.17g} {item['unit']} | {item['value_si'] * scale:.10g} {unit} |")
    lines += ["", "## Electrical acceptance", "", "| Metric | Worst value (dB) | Frequency (GHz) | Requirement | Result |",
              "| --- | ---: | ---: | --- | --- |"]
    for name, metric in summary["metrics"].items():
        value = "missing/nonfinite" if metric["value_db"] is None else f"{metric['value_db']:.10g}"
        lines.append(f"| {name} | {value} | {metric['frequency_hz']/1e9:.12g} | {metric['comparison']}{metric['limit_db']:g} dB | {'PASS' if metric['pass'] else 'FAIL'} |")
    checks = summary["crosscheck"]
    lines += ["", "## Coverage and independent cross-check", "",
              f"- {summary['sample_count']} unique positive-frequency samples, {summary['frequency_range_hz'][0]/1e6:g} MHz to {summary['frequency_range_hz'][1]/1e9:g} GHz.",
              f"- Coverage checks: {'PASS' if summary['coverage_pass'] else 'FAIL'}; maximum passband spacing: {summary['coverage']['max_passband_step_hz']} Hz.",
              "- Positive reflection maxima occur at f = 65 GHz*cos(k*pi/9), k = 0..4. Every maximum requires an exact sample (within 1 Hz) and local samples within 1 MHz on both available passband sides.",
              "- The Chebyshev polynomial bounds the entire ideal passband, including frequencies below the first positive ADS sample; dense ADS sampling and local extrema checks confirm this synthesized network.",
              f"- Maximum complex ADS-versus-ABCD S error: {checks['max_complex_s_error']:.6g} (limit {COMPLEX_TOLERANCE:g}).",
              f"- Maximum reciprocity error: {checks['reciprocity_error']:.6g}; unitarity error: {checks['unitarity_error']:.6g}; excess power gain: {checks['power_gain_excess']:.6g} (limit {PHYSICS_TOLERANCE:g}).",
              "- Independent cascade uses series matrices [[1,jwL],[0,1]] and shunt matrices [[1,0],[jwC,1]], converted to equal-reference-impedance S parameters.",
              "- At DC, all series inductors are shorts and shunt capacitors opens: S21=S12=1, S11=S22=0. No zero-Hz S-parameter simulation is claimed.",
              "- 80 GHz is the only stopband acceptance point; the 120 GHz sweep is diagnostic.", "",
              "## Evidence", "",
              "The input CSV is simulator-exported complex S data. The Touchstone file preserves that data in Hz, real/imaginary format, 50 ohm reference impedance.", "",
              f"Input SHA-256: `{summary.get('input_sha256', 'unavailable')}`.", "",
              "Simulation settings and software versions:", "", "```json",
              json.dumps(summary.get("simulation_settings", {}), indent=2), "```", "",
              "![Broadband S parameters](sparameters_broadband.png)", "",
              "![Passband detail](sparameters_passband.png)", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    synthesis_parser = subparsers.add_parser("synthesize", help="Print derived ideal component values as JSON")
    synthesis_parser.add_argument("--output", type=Path)
    verify_parser = subparsers.add_parser("verify", help="Verify an ADS-exported complex S-parameter CSV")
    verify_parser.add_argument("csv", type=Path)
    verify_parser.add_argument("--output-dir", type=Path, required=True)
    verify_parser.add_argument("--settings", type=Path, help="JSON recording ADS version and simulation settings")
    args = parser.parse_args(argv)
    if args.command == "synthesize":
        payload = json.dumps(synthesize(), indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        frequencies, parameters = load_csv(args.csv)
        summary = verify_data(frequencies, parameters)
        summary["input_sha256"] = hashlib.sha256(args.csv.read_bytes()).hexdigest()
        summary["input_file"] = args.csv.name
        summary["simulation_settings"] = json.loads(args.settings.read_text(encoding="utf-8-sig")) if args.settings else {}
        write_touchstone(args.output_dir / "inp_lpf.s2p", frequencies, parameters)
        write_plots(args.output_dir, frequencies, parameters)
        write_report(args.output_dir / "report.md", summary)
    except (ValueError, OSError, KeyError, TypeError) as error:
        summary = {"engineering_verification_pass": False, "official_benchmark_score": None,
                   "error": str(error)}
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"engineering_verification_pass": summary["engineering_verification_pass"],
                      "summary": str(args.output_dir / "summary.json")}, indent=2))
    return 0 if summary["engineering_verification_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
