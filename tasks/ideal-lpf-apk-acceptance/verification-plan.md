# Verification plan: ideal-lpf-apk-acceptance-r1

## Authority and readiness

- Engineering verification status: `Planned` (pending live ADS 2027 acceptance run).
- Formal benchmark status: unregistered integration acceptance task.

## Required checks

1. Select ADS environment via `ai-eda-lab` (`scripts/engineering_runs.py prepare`).
2. Run `preflight_ads_runtime()` in a real ADS 2027 runtime (`ads_project_kit` + `keysight.ads.de`).
3. Create native workspace `ads/design_wrk` with `LPF_R01_lib` and `LPF_R01_tb_lib` via `ads_project_kit.create_project()`.
4. Run `ads_project_kit.validate_project(..., native=True)` (both after creation and after closing/reopening).
5. Build `LPF_R01_lib:LPF_Ideal:schematic` + `symbol` and `LPF_R01_tb_lib:TB_LPF_Ideal_SP:schematic`, save, close, reopen, and verify `de.cellview_exists()` and `db_uu.open_design()`.
6. Execute real ADS S-parameter simulation, read complex dataset (`S11`, `S21`, `S12`, `S22`), and compare against analytical ABCD cascade and electrical acceptance limits.
7. Verify workspace and naming compliance with `scripts/ads_workspace.py validate`.
