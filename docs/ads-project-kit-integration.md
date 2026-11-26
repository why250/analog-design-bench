# ADS Project Kit integration

`ads-project-kit` (<https://github.com/why250/ads-project-kit>) is the single
authoritative source for generic ADS project structure, generic naming checks,
and native ADS workspace/library creation and validation.

## Three-repository boundary

| Project | Owns | Does not own |
| --- | --- | --- |
| `analog-design-bench` | Task specs (`tasks/<task-id>/`), workflows, run records, task/revision naming extensions (`<BLOCK>_R<NN>_lib`), circuit synthesis, simulation plans, electrical acceptance | Host/MCP routing, generic ADS project-creation code |
| `ai-eda-lab` | Host/software discovery, `plan_environment`, `ensure_product_tools`, client MCP bindings, verified `transfer_files` | Task contracts, circuit design, ADS naming or validation rules |
| `ads-project-kit` | Generic ADS `<name>_wrk` / library / cell / view rules (`ads_project_kit.naming`), `create_project()`, `validate_project()` via `keysight.ads.de` | Task lifecycle, simulation, electrical checks, host/SSH selection |

Ordinary non-ADS tasks (`virtuoso`, KiCad/SPICE, Docker Sky130 benchmarks) do
not import or require `ads-project-kit`.

## Pinned dependency and runtime deployment

- Repository: `https://github.com/why250/ads-project-kit`
- Minimum version: `0.1.0`
- Pinned commit (ADS 2027 native integration): `00ae027d578336c7b70f8d76ab553ecc257b3b67`

The ADS Python Runtime (`HPEESOF_DIR/tools/python` or an attached/local ADS MCP
session) may run on a different host and use a different Python environment than
the orchestrator agent. Installing `ads-project-kit` in the agent's local
Python does not make it importable inside ADS.

Deploy `ads-project-kit` on the ADS host using either supported mechanism:

1. **Install into the ADS Python environment** (`python -m pip install ...`
   against the target ADS Python interpreter, subject to host policy), or
2. **Deploy the pinned source tree to the ADS host** (for example with
   `ai-eda-lab` `transfer_files` into an ignored host-owned dependency directory)
   and load it via `ADS_PROJECT_KIT_PATH` or `src_path` in
   [the runtime helper](../scripts/ads_project_kit_runtime.py).

Do not modify Keysight's installation directory and do not hardcode personal
usernames, SSH aliases, drive letters, or host-specific paths in committed
files.

## Runtime preflight and creation workflow

For any ADS task that creates a new native ADS workspace:

1. Resolve the task and route (`engineering/workflows.toml`).
2. Select the ADS environment via `ai-eda-lab` (`plan_environment` /
   `scripts/engineering_runs.py prepare`).
3. Confirm the ADS MCP session (`list_sessions`, `start_local_session` or
   authorized `connect_session`).
4. Run `preflight_ads_runtime(...)` from `scripts/ads_project_kit_runtime.py`
   inside the ADS Python Runtime to verify:
   - `keysight.ads.de` imports and exposes the ADS runtime mode/version.
   - `ads_project_kit` imports cleanly, recording its actual `package_path`,
     `package_version`, and `deployed_commit` (when available).
   - The target `<name>_wrk` path belongs to the ADS host, its parent is
     writable, and no existing workspace will be overwritten.
   - No other ADS workspace is currently open (`de.workspace_is_open()`).
   If `ads_project_kit` is missing or invalid, stop with the raised
   `AdsProjectKitError`; never fall back to manual `de.create_workspace()` calls.
5. Call `create_ads_project(workspace_path, name, libraries, setup_schematic_tech=...)`
   which runs `ads_project_kit.create_project()` and immediately verifies the
   result with `ads_project_kit.validate_project(..., native=True)`.
6. Open the created workspace using `keysight.ads.de`, build the task-owned
   DUT schematics/symbols and testbenches, save, close, reopen, simulate, and
   re-run `validate_ads_project(..., native=True)` before closing out the run.

## Interpreting PASS, FAIL, and NOT RUN

- `static_passed == True` with `native` status `NOT RUN` reports
  `overall_status = "NOT RUN"` and `native_validated = False`. Static checks
  never substitute for native ADS validation.
- If another ADS workspace is already open in the session, `create_ads_project()`
  refuses to close or replace it, and `validate_ads_project()` leaves it
  untouched and reports `NOT RUN`.
- Existing legacy workspaces are preserved and are not forced to migrate.

## External PDK, layout, and EM boundaries

`ads_project_kit.create_project()` defaults to `setup_schematic_tech=True`,
which calls `Library.setup_schematic_tech()` (schematic-only `tech.db` +
`schematic.prf`). When a task attaches an external PDK technology via
`attached_tech_lib_name` or configures layout/EM technology (`create_layout_tech_*`),
pass `setup_schematic_tech=False` so no local schematic `tech.db` blocks
attaching the PDK technology.
