"""Plot the corrected Au-cover DUT and the ground-loss delta vs the PC control."""

from __future__ import annotations

import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # exec() inside ADS
    _HERE = os.getcwd()
ROOT = os.environ.get("MSL_WORKSPACE_ROOT") or (
    os.path.dirname(_HERE) if os.path.basename(_HERE).lower() == "tools" else _HERE
)
RUN = os.path.join(ROOT, "results", "20261119T065241Z-msl-em-execution")
HANDOFF = os.path.join(RUN, "handoff")
PLOTS = os.path.join(HANDOFF, "plots")


def read_metrics(path: str) -> list[dict]:
    rows = []
    with open(path, "r", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            rows.append({key: (None if value in ("", "None") else float(value))
                         for key, value in row.items()})
    rows.sort(key=lambda item: item["frequency_hz"])
    return rows


def interp(x: float, xs: list[float], ys: list[float]) -> float:
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            t = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
            return ys[i - 1] + t * (ys[i] - ys[i - 1])
    return ys[-1]


def main() -> None:
    os.makedirs(PLOTS, exist_ok=True)
    cases = {
        "3.0 mm, Au cover": ("AuGND_L3mm", "C28_adaptive", "tab:blue"),
        "6.0 mm, Au cover": ("AuGND_L6mm", "C30_adaptive", "tab:orange"),
    }
    figures = {
        "augnd_z0_vs_f": ("Z0 (ohm)", "Corrected DUT: characteristic impedance"),
        "augnd_eps_eff_vs_f": ("epsilon_eff", "Corrected DUT: effective permittivity"),
        "augnd_alpha_vs_f": ("alpha (dB/mm)", "Corrected DUT: attenuation"),
    }
    for name, (ylabel, title) in figures.items():
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        for label, (case, _, color) in cases.items():
            rows = read_metrics(os.path.join(HANDOFF, "analysis", case, "metrics.csv"))
            freq = [r["frequency_hz"] / 1e9 for r in rows]
            if name == "augnd_z0_vs_f":
                ax.plot(freq, [r["Z0_real"] for r in rows], color=color, label=f"{label} real")
                ax.plot(freq, [r["Z0_imag"] for r in rows], color=color, linestyle="--",
                        label=f"{label} imag")
            elif name == "augnd_eps_eff_vs_f":
                ax.plot(freq, [r["eps_eff"] for r in rows], color=color, label=label)
            else:
                ax.plot(freq, [r["alpha_dB_per_mm"] for r in rows], color=color, label=label)
        if name == "augnd_z0_vs_f":
            ax.axhspan(47.5, 52.5, color="green", alpha=0.10, label="H1 window")
            ax.axhline(50.0, color="gray", linewidth=0.8)
        if name == "augnd_eps_eff_vs_f":
            ax.axhline(6.659, color="gray", linestyle=":", linewidth=1.0,
                       label="quasi-static HJ")
        ax.set_xlabel("Frequency (GHz)")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(os.path.join(PLOTS, name + ".png"), dpi=160)
        plt.close(fig)

    # S-parameters
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for label, (case, _, color) in cases.items():
        rows = read_metrics(os.path.join(HANDOFF, "analysis", case, "metrics.csv"))
        freq = [r["frequency_hz"] / 1e9 for r in rows]
        ax.plot(freq, [r["abs_S11"] for r in rows], color=color, label=f"{label} |S11|")
        ax.plot(freq, [r["abs_S21"] for r in rows], color=color, linestyle="--",
                label=f"{label} |S21|")
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("Magnitude")
    ax.set_title("Corrected DUT: S-parameter magnitudes")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "augnd_s_parameters.png"), dpi=160)
    plt.close(fig)

    # Ground-loss delta: AuGND alpha minus interpolated PC alpha.
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for label, (dut, pc, color) in cases.items():
        dut_rows = read_metrics(os.path.join(HANDOFF, "analysis", dut, "metrics.csv"))
        pc_rows = read_metrics(os.path.join(HANDOFF, "analysis", pc, "metrics.csv"))
        pc_x = [r["frequency_hz"] for r in pc_rows]
        pc_y = [r["alpha_dB_per_mm"] for r in pc_rows]
        freq = [r["frequency_hz"] / 1e9 for r in dut_rows]
        delta = [r["alpha_dB_per_mm"] - interp(r["frequency_hz"], pc_x, pc_y) for r in dut_rows]
        ax.plot(freq, delta, color=color, label=label)
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("alpha(Au cover) - alpha(PERFECT_CONDUCTOR) (dB/mm)")
    ax.set_title("Ground-loss contribution of the 4.5 um Au cover")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "ground_loss_vs_f.png"), dpi=160)
    plt.close(fig)
    print({"plots": sorted(os.listdir(PLOTS))})


if __name__ == "__main__":
    main()
