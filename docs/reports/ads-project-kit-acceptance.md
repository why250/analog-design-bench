# Real ADS 2027 Cross-Repo Integration Acceptance Report

This report records the end-to-end verification of `analog-design-bench`,
`ai-eda-lab`, and `ads-project-kit` in a live Keysight ADS 2027 runtime.

## Environment and Versions

- **Target task & workspace**: `ideal-lpf-apk-acceptance-r1` (`workspaces/ideal-lpf-apk-acceptance/`)
- **Run ID**: `20261126T074605Z-ads2027-acceptance`
- **analog-design-bench base commit**: `64dbe4e643f8fd9fa5958ebc38a822172043eabb` (`feat/ads-project-kit-integration`)
- **ads-project-kit target commit / version**: `0.1.0` (pinned commit `00ae027d578336c7b70f8d76ab553ecc257b3b67` on `feat/native-ads2027-integration`)
- **ai-eda-lab routing**: Host `win` (`platform = windows`, `transport = ssh`, `interface = ads2027-win`, `required_tools.ads = 2027`)
- **ADS version & runtime type**:
  - `de.version() = 650`
  - `de.product_version() = Design Environment (*) 650.shp Jul 29 2026 (64-bit)`
  - Runtime mode: headless local automation (`de.running_automation() == True`, `de.is_pde_app() == False`) via `HPEESOF_DIR/tools/python/python.exe` (Python `3.14.6`)
- **`ads_project_kit` load mode & path on ADS host**:
  - `load_mode = installed_environment` (editable/site-packages install present in the remote ADS Python environment)
  - `package_version = 0.1.0`
  - `deployed_commit = null` (see Known Limitations below)

## Verification Checklist

| Check | Outcome | Evidence / Observation |
| --- | --- | --- |
| Task & environment selection via `ai-eda-lab` | PASS | `scripts/engineering_runs.py prepare` resolved workflow `ads-lpf` (`1.3`) and selected host `win` / `ads2027-win` |
| Runtime preflight (`preflight_ads_runtime`) | PASS | Verified `keysight.ads.de`, `ads_project_kit`, writable ADS host parent directory, and `workspace_is_open == False` |
| Native workspace creation (`create_project()`) | PASS | Created `ads/design_wrk` with `LPF_R01_lib` and `LPF_R01_tb_lib`, `setup_schematic_tech=True`, and `ads-project-kit.json` |
| Post-create native validation (`validate_project()`) | PASS | All 6 `static` checks and all 5 `native` checks (`ads_workspace`, `ads_library:*`, `ads_library_tech:*`) returned `PASS` |
| LC LPF DUT schematic & symbol (`keysight.ads.de`) | PASS | Built 5th-order Chebyshev-I series-first ladder (`L1=932.15 pH`, `C1=435.57 fF`, `L2=1.5909 nH`, `C2=435.57 fF`, `L3=932.15 pH`) in `LPF_R01_lib:LPF_Ideal:{schematic,symbol}` with ordered ports `(rfin, rfout, gnd)` |
| S-parameter testbench (`keysight.ads.de`) | PASS | Built `LPF_R01_tb_lib:TB_LPF_Ideal_SP:schematic` with 50-ohm `Term1`/`Term2`, `GROUND`, and 6 `S_Param` controllers |
| Save, close, reopen & design checks | PASS | Closed and reopened `design_wrk`; `de.cellview_exists()` and `db_uu.open_design()` confirmed all 3 cellviews; post-reopen `validate_project()` returned `PASS` (`native_validated == True`) |
| Real ADS S-parameter simulation (`hpeesofsim`) | PASS | Executed 6 sweeps (`2401 + 1301 + 2 + 21 + 21 + 11` samples) producing `TB_LPF_Ideal_SP.ds` |
| Electrical acceptance & ABCD cross-check | PASS | Worst `S11 = -16.00 dB` (`< -15 dB`), `S22 = -16.00 dB` (`< -15 dB`), `IL = 0.1105 dB` (`< 1.0 dB`), `S21(20 GHz) = -35.29 dB` (`<= -20 dB`); max ABCD complex error `1.27e-15`, unitarity error `2.22e-15` |
| Convention & workspace audit (`ads_workspace.py validate`) | PASS | `status = ok`, `errors = []`, `warnings = []` with `ads_project_kit.naming` enabled |

## Known Limitations and Observations

1. **Pre-installed `ads_project_kit` precedence in ADS Python**: On the Windows ADS host, `ads-project-kit` (`0.1.0`) was already installed via `.egg-info` / `.pth` in the ADS Python environment. Passing a separate `src_path` triggered `load_ads_project_kit()`'s path-mismatch guard (`already loaded from ...`), confirming that the preflight guard catches shadowed installs. Calling with `src_path=None` loaded the installed environment cleanly, while `deployed_commit` reported `null` because the `.egg-info` install had no `.git` or commit marker file.
2. **Large directory `transfer_files` timeout**: Transferring an entire repository tree or full OA workspace in one `eda-lab` `transfer_files` call can exceed a 3-minute MCP tool timeout when many files are hashed over SSH. Scoping `source_path` to the minimal subdirectory (`src/ads_project_kit` or a single OA library) completed reliably with SHA-256 verification.
3. **Scope boundary**: This acceptance exercises schematic-only ideal technology (`setup_schematic_tech=True`) in ADS 2027 headless automation mode. External PDK attachment (`setup_schematic_tech=False`), layout geometry, Momentum EM, and attached GUI PDE sessions remain outside this acceptance scope.
