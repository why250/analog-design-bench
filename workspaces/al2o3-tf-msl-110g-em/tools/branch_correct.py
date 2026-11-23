"""Branch-corrected epsilon_eff for sparse two-port line data.

``acosh((A+D)/2)`` returns the principal propagation phase, which can differ
from the true ``beta*L`` by an integer multiple of 2*pi when the line is
electrically long and the frequency grid is sparse.  Z0 and alpha do not need
this correction.  This tool keeps the principal phase and chooses the 2*pi*n
branch whose effective permittivity lies in a declared physical window
(default 6.0-8.5 for the 127 um Al2O3 stack) and is closest to a smooth
reference trend.

The raw Touchstone file is never modified.  The output JSON is a derived
artifact and records the selected branch.
"""

from __future__ import annotations

import argparse
import cmath
import json
import math
import os

import analyze_em

C0 = 299792458.0


def correct(s2p: str, length_m: float, eps_low: float = 6.0,
            eps_high: float = 8.5, eps_ref_110: float = 7.37,
            eps_ref_low: float = 6.9) -> dict:
    frequencies, matrices = analyze_em.read_touchstone(s2p)
    rows = []
    for frequency, s in zip(frequencies, matrices):
        s11, s12, s21, s22 = s[0][0], s[0][1], s[1][0], s[1][1]
        a, b, c, d = analyze_em.s_to_abcd(s)
        z0 = cmath.sqrt(b / c)
        if z0.real < 0:
            z0 = -z0
        gamma_l = cmath.acosh((a + d) / 2.0)
        beta_principal = gamma_l.imag
        alpha = gamma_l.real / length_m
        reference = eps_ref_low + (eps_ref_110 - eps_ref_low) * (frequency / 110e9)
        candidates = []
        for n in range(0, 40):
            beta_l = beta_principal + 2.0 * math.pi * n
            eps = (beta_l / length_m * C0 / (2.0 * math.pi * frequency)) ** 2
            if eps_low <= eps <= eps_high:
                candidates.append({"n": n, "eps_eff": eps, "beta_L": beta_l})
        chosen = min(candidates, key=lambda item: abs(item["eps_eff"] - reference)) if candidates else None
        rows.append({
            "frequency_hz": frequency,
            "Z0_real": z0.real, "Z0_imag": z0.imag,
            "alpha_Np_per_m": alpha,
            "alpha_dB_per_mm": alpha * 8.6858896 / 1000.0,
            "beta_L_principal": beta_principal,
            "branch_candidates": len(candidates),
            "selected_branch_n": None if chosen is None else chosen["n"],
            "eps_eff": None if chosen is None else chosen["eps_eff"],
            "beta_L": None if chosen is None else chosen["beta_L"],
            "passivity": abs(s11) ** 2 + abs(s21) ** 2,
            "abs_S11": abs(s11), "abs_S21": abs(s21),
            "reciprocity_error": abs(s21 - s12),
        })
    return {"source": os.path.abspath(s2p), "length_m": length_m,
            "eps_window": [eps_low, eps_high], "reference_trend": [eps_ref_low, eps_ref_110],
            "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("s2p")
    parser.add_argument("--length-mm", type=float, required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--eps-low", type=float, default=6.0)
    parser.add_argument("--eps-high", type=float, default=8.5)
    parser.add_argument("--eps-ref-110", type=float, default=7.37)
    parser.add_argument("--eps-ref-low", type=float, default=6.9)
    args = parser.parse_args()
    result = correct(args.s2p, args.length_mm * 1e-3, args.eps_low, args.eps_high,
                     args.eps_ref_110, args.eps_ref_low)
    with open(args.output, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    for row in result["rows"]:
        if row["eps_eff"] is not None:
            print(f"{row['frequency_hz']/1e9:>8.4f} GHz  Z0={row['Z0_real']:.4f}{row['Z0_imag']:+.4f}j  "
                  f"eps={row['eps_eff']:.4f}  alpha={row['alpha_dB_per_mm']:.5f} dB/mm  n={row['selected_branch_n']}")


if __name__ == "__main__":
    main()
