"""Deterministic E0-E8 request mappings and E9 reproduction selections.

Requests remain separate when physical cases deduplicate. The manifest hash
uses resolved coefficients, not generating labels, and is stable across runs.
All coordinates are synthetic research assumptions, never process statistics.
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

try:
    from . import model
except ImportError:
    import model

ANCHOR_B = {"q": 80., "f_l0_hz": 320e9, "esr_ohm": .1, "esl_h": 2e-12}
NEAR_RESONANCE = {"q": 40., "f_l0_hz": 100e9, "esr_ohm": .5, "esl_h": 10e-12}
E8_REFERENCE = {"q": 200., "f_l0_hz": 640e9, "esr_ohm": .1, "esl_h": 2e-12}
SYNTHETIC_METADATA = MappingProxyType({"provenance": "synthetic research assumptions; no PDK data",
                      "statistics": "deterministic; no probability, corner, tolerance or yield claim",
                      "optional_leakage": "disabled", "optional_extra_capacitance": "disabled",
                      "temperature_deg_c": 25., "temperature_law": "none; bookkeeping only"})


def _targeted(kind: str, name: str, **coordinates: float) -> dict[str, Any]:
    result, source = model.baseline(), model.resolve(**coordinates)
    for index, element in enumerate(result["elements"]):
        if element["name"] == name:
            result["elements"][index] = source["elements"][index]
    result["generator"] = {"targeted_element": name, "kind": kind, "coordinates": coordinates}
    return result


def _scale_groups(l_scale: float, c_scale: float) -> dict[str, float]:
    return {name: l_scale if name.startswith("L") else c_scale for name in model.ELEMENT_NAMES}


def requests() -> list[dict[str, Any]]:
    """Return 205 mandatory initial requests (185 E0-E7 and 20 E8 seeds).

    ``request_id`` names each experiment coordinate. ``case_id`` identifies the
    first request with identical resolved coefficients. Each returned manifest
    is a fresh independent object so callers cannot mutate another request.
    E1 unit cells and E8 adaptive nodes are retained separately by the runner.
    """
    rows: list[dict[str, Any]] = []
    canonical: dict[str, str] = {}

    def add(request_id: str, family: str, manifest: dict[str, Any], **labels: Any) -> None:
        model.validate(manifest)
        digest = model.physical_hash(manifest)
        case_id = canonical.setdefault(digest, request_id)
        rows.append({"request_id": request_id, "case_id": case_id, "family": family,
                     "physical_sha256": digest, "manifest": copy.deepcopy(manifest),
                     "labels": labels, "research_metadata": dict(SYNTHETIC_METADATA)})

    add("e0-ideal", "E0", model.baseline(), selection="E9 ideal reproduction")
    for q in (10, 20, 30, 40, 60, 100, 200):
        add(f"e2-q{q}", "E2", model.resolve(q=q), q_l_ref=q)
    for name in ("L2", "L3", "L4"):
        add(f"e2-only-{name.lower()}-q40", "E2", _targeted("L", name, q=40), element=name, q_l_ref=40)
    for ghz in (80, 100, 120, 160, 240, 480):
        add(f"e3-fl0-{ghz}g", "E3", model.resolve(f_l0_hz=ghz*1e9), f_l0_hz=ghz*1e9)
    for name in ("L2", "L3", "L4"):
        add(f"e3-only-{name.lower()}-100g", "E3", _targeted("L", name, f_l0_hz=100e9), element=name, f_l0_hz=100e9)
    for esr in (.05, .1, .25, .5, 1., 2.):
        add(f"e4-esr-{esr:g}", "E4", model.resolve(esr_ohm=esr), esr_ohm=esr)
    for ph in (1, 2, 5, 10, 20, 40):
        add(f"e4-esl-{ph}p", "E4", model.resolve(esl_h=ph*1e-12), esl_h=ph*1e-12)
    add("e4-esr1-esl20p", "E4", model.resolve(esr_ohm=1, esl_h=20e-12), esr_ohm=1., esl_h=20e-12)
    for name in ("C1", "C2", "C3", "C4"):
        add(f"e4-only-{name.lower()}", "E4", _targeted("C", name, esr_ohm=.5, esl_h=10e-12), element=name)
    for name, percent in itertools.product(model.ELEMENT_NAMES, (-10, -5, -1, 1, 5, 10)):
        add(f"e5-{name.lower()}-{percent:+d}pct", "E5", model.perturb(model.baseline(), {name: 1+percent/100}),
            element=name, fractional_change=percent/100)
    for l_pct, c_pct in itertools.product((-5, 0, 5), repeat=2):
        if (l_pct, c_pct) != (0, 0):
            add(f"e5-common-l{l_pct:+d}-c{c_pct:+d}", "E5",
                model.perturb(model.baseline(), _scale_groups(1+l_pct/100, 1+c_pct/100)),
                l_scale=1+l_pct/100, c_scale=1+c_pct/100)
    for q, ghz, esr, ph in itertools.product((20, 40, 80, 160), (100, 160, 320, 640), (.1, .5), (2, 10)):
        coordinates = {"q": q, "f_l0_hz": ghz*1e9, "esr_ohm": esr, "esl_h": ph*1e-12}
        is_b = coordinates == ANCHOR_B
        is_near = coordinates == NEAR_RESONANCE
        add(f"e6-q{q}-fl0-{ghz}g-esr{esr:g}-esl{ph}p", "E6", model.resolve(**coordinates),
            **coordinates, anchor_b=is_b, e9_near_resonance=is_near)
    for name, percent in itertools.product(model.ELEMENT_NAMES, (-1, 1)):
        add(f"e7-{name.lower()}-{percent:+d}pct", "E7", model.perturb(model.resolve(**ANCHOR_B), {name: 1+percent/100}),
            element=name, fractional_change=percent/100, anchor="B", coefficient_policy="frozen")
    for l_pct, c_pct in itertools.product((-5, 5), repeat=2):
        add(f"e7-common-l{l_pct:+d}-c{c_pct:+d}", "E7",
            model.perturb(model.resolve(**ANCHOR_B), _scale_groups(1+l_pct/100, 1+c_pct/100)),
            l_scale=1+l_pct/100, c_scale=1+c_pct/100, anchor="B", coefficient_policy="frozen")
    axes = {"q": (10., 20., 40., 80., 200.), "f_l0_hz": (80e9, 120e9, 200e9, 360e9, 640e9),
            "esr_ohm": (0., .1, .5, 1., 2.), "esl_h": (0., 2e-12, 10e-12, 20e-12, 40e-12)}
    for axis, values in axes.items():
        for index, value in enumerate(values):
            coordinates = dict(E8_REFERENCE, **{axis: value})
            add(f"e8-{axis}-seed{index}", "E8", model.resolve(**coordinates),
                axis=axis, coordinate=value, refinement="geometric" if axis in ("q", "f_l0_hz") else "arithmetic",
                seed=True, **coordinates)
    assert len(rows) == 205
    return rows


def unique_cases(rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows = requests() if rows is None else rows
    result = {}
    for row in rows:
        result.setdefault(row["case_id"], row)
    return list(result.values())


def repetition_requests(rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """E9 repeats in fresh workspaces, keeping original resolved case identity."""
    rows = requests() if rows is None else rows
    selected = [rows[0], next(row for row in rows if row["labels"].get("anchor_b")),
                next(row for row in rows if row["labels"].get("e9_near_resonance"))]
    result = []
    for label, row in zip(("ideal", "anchor-b", "near-resonance"), selected):
        repeated = copy.deepcopy(row)
        repeated.update({"request_id": f"e9-{label}", "family": "E9", "reproduces_request_id": row["request_id"],
                         "fresh_workspace_required": True, "frozen_frequency_list_required": True})
        result.append(repeated)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = requests()
    result = {"task_version": model.TASK_VERSION, "baseline_commit": model.BASELINE_COMMIT,
              "initial_request_count": len(rows), "unique_case_count": len(unique_cases(rows)),
              "requests": rows, "e9_repetitions": repetition_requests(rows)}
    content = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8", newline="\n")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
