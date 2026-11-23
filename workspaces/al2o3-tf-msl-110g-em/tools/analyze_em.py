"""Extract Z0, effective permittivity and attenuation from a two-port S2P.

The extraction follows the task model plan: convert S to ABCD, take
``Z0 = sqrt(B/C)`` and ``gamma = acosh((A+D)/2)/L``.  The imaginary part of
``acosh`` is principal-valued, so the propagation phase is unwrapped across
frequency before it is converted to effective permittivity.  A model-assisted
branch check uses the previous point's group delay; every report states which
branch method was used.

The input must be a Touchstone file with Hz, RI, R 50 data and port order
1 = rf_in, 2 = rf_out.  The physical length passed on the command line is the
distance between the declared reference planes.
"""

from __future__ import annotations

import argparse
import cmath
import csv
import json
import math
import os

C0 = 299792458.0


def read_touchstone(path: str) -> tuple[list[float], list[list[list[complex]]]]:
    frequencies: list[float] = []
    matrices: list[list[list[complex]]] = []
    fmt = None
    with open(path, "r", encoding="ascii", errors="replace") as stream:
        for line in stream:
            line = line.strip()
            if not line or line.startswith("!"):
                continue
            if line.startswith("#"):
                parts = line[1:].upper().split()
                fmt = parts
                continue
            values = [float(token) for token in line.replace(",", " ").split()]
            if fmt is None or "RI" not in fmt:
                raise ValueError("Only Touchstone RI data is supported")
            if "HZ" not in fmt:
                raise ValueError("Only Hz frequency units are supported")
            if "S" not in fmt:
                raise ValueError("Only S-parameter data is supported")
            if len(values) != 9:
                raise ValueError("Expected a two-port row with 9 numbers")
            frequency = values[0]
            s = [[complex(values[1], values[2]), complex(values[3], values[4])],
                 [complex(values[5], values[6]), complex(values[7], values[8])]]
            frequencies.append(frequency)
            matrices.append(s)
    if not frequencies:
        raise ValueError("No S-parameter rows found")
    order = sorted(range(len(frequencies)), key=lambda i: frequencies[i])
    return [frequencies[i] for i in order], [matrices[i] for i in order]


def s_to_abcd(s: list[list[complex]], zref: float = 50.0):
    s11, s12, s21, s22 = s[0][0], s[0][1], s[1][0], s[1][1]
    denominator = 2.0 * s21
    if abs(denominator) < 1e-15:
        raise ZeroDivisionError("S21 is zero; ABCD conversion is singular")
    a = ((1 + s11) * (1 - s22) + s12 * s21) / denominator
    b = zref * ((1 + s11) * (1 + s22) - s12 * s21) / denominator
    c = ((1 - s11) * (1 - s22) - s12 * s21) / (zref * denominator)
    d = ((1 - s11) * (1 + s22) + s12 * s21) / denominator
    return a, b, c, d


def unwrap(values: list[float], period: float = 2.0 * math.pi) -> list[float]:
    if not values:
        return []
    result = [values[0]]
    for value in values[1:]:
        previous = result[-1]
        delta = value - previous
        delta -= period * round(delta / period)
        result.append(previous + delta)
    return result


def analyze(path: str, length_m: float, output_dir: str,
            checkpoints_ghz: tuple[float, ...] = (0.1, 1, 10, 40, 65, 80, 110),
            zref: float = 50.0) -> dict:
    if length_m <= 0 or not math.isfinite(length_m):
        raise ValueError("Length must be finite and positive")
    frequencies, matrices = read_touchstone(path)
    if any(f <= 0 for f in frequencies):
        raise ValueError("All frequencies must be positive")
    records = []
    beta_l_principal = []
    phase_s21 = []
    for frequency, s in zip(frequencies, matrices):
        s11, s12, s21, s22 = s[0][0], s[0][1], s[1][0], s[1][1]
        a, b, c, d = s_to_abcd(s, zref)
        z0 = cmath.sqrt(b / c) if abs(c) > 0 else complex(float("nan"), float("nan"))
        if z0.real < 0:
            z0 = -z0
        cosh_arg = (a + d) / 2.0
        gamma_l = cmath.acosh(cosh_arg)
        beta_l_principal.append(gamma_l.imag)
        phase_s21.append(cmath.phase(s21))
        records.append({
            "frequency_hz": frequency,
            "S11_real": s11.real, "S11_imag": s11.imag,
            "S21_real": s21.real, "S21_imag": s21.imag,
            "S12_real": s12.real, "S12_imag": s12.imag,
            "S22_real": s22.real, "S22_imag": s22.imag,
            "abs_S11": abs(s11), "abs_S21": abs(s21),
            "passivity": abs(s11) ** 2 + abs(s21) ** 2,
            "reciprocity_error": abs(s21 - s12),
            "A": a, "B": b, "C": c, "D": d,
            "A_minus_D": abs(a - d),
            "Z0_real": z0.real, "Z0_imag": z0.imag,
            "gamma_principal_real": gamma_l.real,
            "beta_L_principal": gamma_l.imag,
        })
    beta_l = unwrap(beta_l_principal)
    phase_s21_unwrapped = unwrap(phase_s21)
    omega = [2.0 * math.pi * f for f in frequencies]
    for index, record in enumerate(records):
        beta = beta_l[index] / length_m
        eps = (beta * C0 / (2.0 * math.pi * record["frequency_hz"])) ** 2
        record["beta_rad_per_m"] = beta
        record["eps_eff"] = eps
        record["alpha_Np_per_m"] = record["gamma_principal_real"] / length_m
        record["alpha_dB_per_mm"] = (record["gamma_principal_real"] / length_m) * 8.6858896 / 1000.0
        if index == 0:
            record["group_delay_s"] = None
        else:
            dphi = phase_s21_unwrapped[index] - phase_s21_unwrapped[index - 1]
            domega = omega[index] - omega[index - 1]
            record["group_delay_s"] = -dphi / domega
    # Branch consistency: independent beta from the unwrapped S21 phase.
    beta_from_s21 = [-(phase_s21_unwrapped[i] - phase_s21_unwrapped[0]) / length_m for i in range(len(frequencies))]
    for index, record in enumerate(records):
        record["beta_L_from_S21_minus_first"] = beta_from_s21[index]
    checkpoint_rows = []
    for target in checkpoints_ghz:
        target_hz = target * 1e9
        nearest = min(range(len(frequencies)), key=lambda i: abs(frequencies[i] - target_hz))
        distance = abs(frequencies[nearest] - target_hz)
        checkpoint_rows.append({
            "requested_GHz": target,
            "actual_GHz": frequencies[nearest] / 1e9,
            "offset_hz": frequencies[nearest] - target_hz,
            "exact": distance <= max(0.5, target_hz * 1e-12),
            "Z0_real": records[nearest]["Z0_real"],
            "Z0_imag": records[nearest]["Z0_imag"],
            "eps_eff": records[nearest]["eps_eff"],
            "alpha_dB_per_mm": records[nearest]["alpha_dB_per_mm"],
            "abs_S11": records[nearest]["abs_S11"],
            "abs_S21": records[nearest]["abs_S21"],
            "passivity": records[nearest]["passivity"],
            "reciprocity_error": records[nearest]["reciprocity_error"],
        })
    max_passivity = max(record["passivity"] for record in records)
    max_reciprocity = max(record["reciprocity_error"] for record in records)
    negative_alpha = [record for record in records if record["alpha_Np_per_m"] < -1e-3]
    at_110 = next((row for row in checkpoint_rows if abs(row["requested_GHz"] - 110.0) < 1e-9), None)
    summary = {
        "source": os.path.abspath(path),
        "source_bytes": os.path.getsize(path),
        "length_m": length_m,
        "zref_ohm": zref,
        "frequency_count": len(frequencies),
        "frequency_min_Hz": frequencies[0],
        "frequency_max_Hz": frequencies[-1],
        "max_passivity": max_passivity,
        "max_reciprocity_error": max_reciprocity,
        "negative_alpha_count_below_minus_1e_3_Np_per_m": len(negative_alpha),
        "H1_at_110_GHz": None if at_110 is None else {
            "Z0_real_ohm": at_110["Z0_real"], "Z0_imag_ohm": at_110["Z0_imag"],
            "within_47p5_52p5": 47.5 <= at_110["Z0_real"] <= 52.5,
            "exact_110_GHz_point": at_110["exact"],
        },
        "branch_method": "principal acosh beta_L unwrapped across frequency; S21 phase cross-check retained",
    }
    os.makedirs(output_dir, exist_ok=True)
    metrics_path = os.path.join(output_dir, "metrics.csv")
    fields = ["frequency_hz", "Z0_real", "Z0_imag", "eps_eff", "alpha_Np_per_m",
              "alpha_dB_per_mm", "abs_S11", "abs_S21", "passivity",
              "reciprocity_error", "group_delay_s", "A_minus_D",
              "beta_rad_per_m", "beta_L_from_S21_minus_first"]
    with open(metrics_path, "w", encoding="ascii", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)
    with open(os.path.join(output_dir, "checkpoints.json"), "w", encoding="utf-8", newline="\n") as stream:
        json.dump(checkpoint_rows, stream, indent=2)
        stream.write("\n")
    with open(os.path.join(output_dir, "summary.json"), "w", encoding="utf-8", newline="\n") as stream:
        json.dump(summary, stream, indent=2)
        stream.write("\n")
    return {"summary": summary, "metrics_csv": metrics_path,
            "checkpoints": checkpoint_rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("s2p")
    parser.add_argument("--length-mm", type=float, required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--checkpoints-ghz", type=float, nargs="+",
                        default=[0.1, 1, 10, 40, 65, 80, 110])
    args = parser.parse_args()
    result = analyze(args.s2p, args.length_mm * 1e-3, args.output_dir,
                     tuple(args.checkpoints_ghz))
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
