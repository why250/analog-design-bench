"""Real ADS 2027 integration acceptance runner for ads-project-kit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import ads_project_kit_runtime as runtime  # noqa: E402
from scripts.lpf.ideal import run_ideal  # noqa: E402

ACCEPTANCE_SPEC = {
    "schema_version": 1,
    "impedance_ohm": 50.0,
    "passband_hz": 10e9,
    "s11_max_db": -15.0,
    "s22_max_db": -15.0,
    "stopbands": [{"frequency_hz": 20e9, "s21_max_db": -20.0}],
    "insertion_loss_max_db": 1.0,
    "return_loss_margin_db": 1.0,
    "max_order": 15,
}


def run_acceptance(
    *,
    workspace_dir: Path,
    run_dir: Path,
    ads_project_kit_src: Path | None = None,
) -> dict:
    """Execute preflight, native creation, schematic/TB build, reopen, and SP simulation."""
    ads_wrk = workspace_dir / "ads" / "design_wrk"
    ads_wrk.parent.mkdir(parents=True, exist_ok=True)
    out_dir = run_dir / "ideal-output"

    preflight = runtime.preflight_ads_runtime(
        ads_wrk,
        allow_existing=False,
        require_ads=True,
        src_path=ads_project_kit_src,
    )
    if preflight["status"] != "PASS":
        raise runtime.AdsProjectKitError("Preflight failed: " + json.dumps(preflight, indent=2))

    # Simulate via scripts.lpf.ideal.run_ideal -> ads_ideal.simulate_ideal -> ads_project_kit
    from scripts.lpf import ads_ideal

    original_simulate = ads_ideal.simulate_ideal

    def _simulate_with_src(spec, design, sweeps, workspace_path, output):
        return original_simulate(
            spec,
            design,
            sweeps,
            workspace_path,
            output,
            ads_project_kit_src=ads_project_kit_src,
        )

    ads_ideal.simulate_ideal = _simulate_with_src
    try:
        ideal_report = run_ideal(ACCEPTANCE_SPEC, out_dir, ads_wrk)
    finally:
        ads_ideal.simulate_ideal = original_simulate

    # Verify saved designs reopen cleanly via keysight.ads.de and db_uu
    from keysight.ads import de  # type: ignore[import-not-found]
    from keysight.ads.de import db_uu  # type: ignore[import-not-found]

    reopen_checks = {}
    opened = de.open_workspace(ads_wrk)
    try:
        for lib, cell, view in (
            ("LPF_R01_lib", "LPF_Ideal", "schematic"),
            ("LPF_R01_lib", "LPF_Ideal", "symbol"),
            ("LPF_R01_tb_lib", "TB_LPF_Ideal_SP", "schematic"),
        ):
            exists = bool(de.cellview_exists(lib, cell, view))
            design_obj = db_uu.open_design(f"{lib}:{cell}:{view}")
            is_valid = (
                bool(design_obj.is_schematic)
                if view == "schematic"
                else bool(design_obj.is_symbol)
            )
            design_obj.close_design()
            reopen_checks[f"{lib}:{cell}:{view}"] = {
                "cellview_exists": exists,
                "opened_expected_view_type": is_valid,
            }
    finally:
        if opened.is_open:
            opened.close()

    final_validation = runtime.validate_ads_project(
        ads_wrk,
        native=True,
        src_path=ads_project_kit_src,
    )
    summary = {
        "schema_version": 1,
        "preflight": preflight,
        "ideal_report": ideal_report,
        "reopen_checks": reopen_checks,
        "final_validation": final_validation,
    }
    (run_dir / "acceptance-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--ads-project-kit", type=Path, default=None)
    args = parser.parse_args()
    summary = run_acceptance(
        workspace_dir=args.workspace.resolve(),
        run_dir=args.run.resolve(),
        ads_project_kit_src=args.ads_project_kit.resolve() if args.ads_project_kit else None,
    )
    print(json.dumps({"passed": summary["ideal_report"]["passed"], "final_validation": summary["final_validation"]["overall_status"]}, indent=2))
    return 0 if summary["ideal_report"]["passed"] and summary["final_validation"]["native_validated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
