"""Plot the selected-line metrics and the 110 GHz width search.

Reads the local handoff artifacts:
  handoff/analysis/<case>/metrics.csv
  handoff/coarse-110-metrics.json
  handoff/refine-110-metrics.json
"""

from __future__ import annotations

import csv
import json
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


def read_metrics(case: str) -> list[dict]:
    path = os.path.join(HANDOFF, "analysis", case, "metrics.csv")
    rows = []
    with open(path, "r", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            record = {key: (None if value in ("", "None") else float(value))
                      for key, value in row.items()}
            rows.append(record)
    return rows


def plot_lines() -> None:
    cases = {
        "3.0 mm": ("C28_adaptive", "tab:blue"),
        "6.0 mm": ("C30_adaptive", "tab:orange"),
    }
    figures = {
        "z0_vs_f": ("Z0 (ohm)", "Characteristic impedance"),
        "eps_eff_vs_f": ("epsilon_eff", "Effective permittivity"),
        "alpha_vs_f": ("alpha (dB/mm)", "Attenuation"),
        "group_delay": ("group delay (ns)", "Group delay"),
    }
    for name, (ylabel, title) in figures.items():
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        for label, (case, color) in cases.items():
            rows = read_metrics(case)
            freq = [r["frequency_hz"] / 1e9 for r in rows]
            if name == "z0_vs_f":
                ax.plot(freq, [r["Z0_real"] for r in rows], color=color, label=f"{label} real")
                ax.plot(freq, [r["Z0_imag"] for r in rows], color=color, linestyle="--",
                        label=f"{label} imag")
            elif name == "eps_eff_vs_f":
                ax.plot(freq, [r["eps_eff"] for r in rows], color=color, label=label)
            elif name == "alpha_vs_f":
                ax.plot(freq, [r["alpha_dB_per_mm"] for r in rows], color=color, label=label)
            elif name == "group_delay":
                pairs = [(f, r["group_delay_s"] * 1e9) for f, r in zip(freq, rows)
                         if r["group_delay_s"] is not None]
                ax.plot([p[0] for p in pairs], [p[1] for p in pairs], color=color, label=label)
        if name == "z0_vs_f":
            ax.axhspan(47.5, 52.5, color="green", alpha=0.10, label="H1 window")
            ax.axhline(50.0, color="gray", linewidth=0.8)
        if name == "eps_eff_vs_f":
            ax.axhline(6.659, color="gray", linestyle=":", linewidth=1.0,
                       label="quasi-static HJ (W=121.3 um)")
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
    for label, (case, color) in cases.items():
        rows = read_metrics(case)
        freq = [r["frequency_hz"] / 1e9 for r in rows]
        ax.plot(freq, [r["abs_S11"] for r in rows], color=color, label=f"{label} |S11|")
        ax.plot(freq, [r["abs_S21"] for r in rows], color=color, linestyle="--",
                label=f"{label} |S21|")
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("Magnitude")
    ax.set_title("S-parameter magnitudes")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "s_parameters.png"), dpi=160)
    plt.close(fig)


def plot_width_search() -> None:
    points = []
    for name in ("coarse-110-metrics.json", "refine-110-metrics.json"):
        data = json.load(open(os.path.join(HANDOFF, name), "r", encoding="utf-8"))
        points.extend(data["rows"])
    points.sort(key=lambda row: row["width_um"])
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.plot([p["width_um"] for p in points], [p["Z0_real"] for p in points],
            "o-", color="tab:blue", markersize=3, label="simulated at 110 GHz")
    ax.axhspan(47.5, 52.5, color="green", alpha=0.12, label="H1 window")
    ax.axhline(50.0, color="gray", linewidth=0.8)
    ax.axvline(120.0, color="tab:red", linestyle="--", linewidth=1.0, label="selected W=120 um")
    ax.set_xlabel("Line width W (um)")
    ax.set_ylabel("Z0 real at 110 GHz (ohm)")
    ax.set_title("Bounded width search, ideal-ground model")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "width_search_110.png"), dpi=160)
    plt.close(fig)


def main() -> None:
    os.makedirs(PLOTS, exist_ok=True)
    plot_lines()
    plot_width_search()
    print(json.dumps({"plots": sorted(os.listdir(PLOTS))}, indent=2))


if __name__ == "__main__":
    main()
