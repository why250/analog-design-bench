# al2o3-tf-msl-110g-em

Engineering workspace for `al2o3-tf-msl-110g-em-r1` (stage `em-design`).
Authoritative task contract: [tasks/al2o3-tf-msl-110g-em/instruction.md](../../tasks/al2o3-tf-msl-110g-em/instruction.md).
Model and acceptance plans: [model-plan.md](../../tasks/al2o3-tf-msl-110g-em/model-plan.md),
[verification-plan.md](../../tasks/al2o3-tf-msl-110g-em/verification-plan.md).

## Final design

- `MSL_Line_Selected_AuGND_W120um_L3mm` — uniform Au microstrip on Al2O3,
  **W = 120 um, L = 3.0 mm**, full-plane 4.5 um Au bottom ground cover
  (delivery copy of `MSL_Line_C32`).
- `MSL_Line_Selected_AuGND_W120um_L6mm` — **W = 120 um, L = 6.0 mm**, same
  stack (delivery copy of `MSL_Line_C33`).
- Delivered S2P:
  [3.0 mm](results/20261119T065241Z-msl-em-execution/handoff/model/MSL_R01_AuGND_W120um_L3mm.s2p),
  [6.0 mm](results/20261119T065241Z-msl-em-execution/handoff/model/MSL_R01_AuGND_W120um_L6mm.s2p).
- Model: top-only line, TML ports, 50 ohm, 0.1-110 GHz; full-plane 4.5 um Au
  bottom cover (`Al2O3_MSL_AuGND`, `groundplane=1`). H1 Z0(110 GHz) =
  **50.83 - 3.79j ohm** (3.0 mm) and **49.18 - 2.49j ohm** (6.0 mm); H2/H3 PASS.
- Controls, not the DUT: `MSL_Line_Selected_W120um_L3mm/L6mm` are the
  PERFECT_CONDUCTOR-cover copies (from C28/C30); the finite 2.0/4.0 mm bottom-Au
  cases are retained failed/control evidence.
- Details in [docs/execution-record.md](docs/execution-record.md) and the run's
  `handoff/extraction-report.md`.

## Design identity

- DUT: one uniform centered Au microstrip line on an Al2O3 thin film.
- Stack: Al2O3 127 um, er 9.9, tan(delta) 1e-4 (assumed); 4.5 um Au top line
  and a full-plane 4.5 um Au bottom cover, sigma 4.1e7 S/m, smooth (assumed).
- Coupon cases: 3.0 mm and 6.0 mm; 2.0 mm nominal dielectric/top layout width
  (assumed; the ground is a full-plane cover).
- Design variable: uniform line width `W`, target Z0 = 50 ohm at 110 GHz
  (confirmed acceptance frequency, 2026-11-19).
- Band: 0.1-110 GHz.
- Environment: ADS 2027 with Momentum microwave on the configured ADS host.

## Structure and design identity

- Manifest: [project.toml](project.toml) (`schema_version = 2`,
  `model_policy = "unrestricted-ideal"`)
- Primary ADS workspace: `ads/al2o3_msl_wrk`
- Task-owned libraries: `MSL_R01_lib` (DUT layout/emSetup/emModel/symbol);
  `MSL_R01_tb_lib` and `MSL_R01_em_lib` only if those roles are used
- Candidate cells: `MSL_Line_C01`, `MSL_Line_C02`, ...; the selected Au-cover
  candidates are `MSL_Line_C32` (W = 120 um, 3.0 mm) and `MSL_Line_C33`
  (W = 120 um, 6.0 mm), recorded in
  [docs/execution-record.md](docs/execution-record.md). The PERFECT_CONDUCTOR
  copies (C28/C30) are controls.
- ADS naming: [convention](../../docs/ads-naming-convention.md)
- Execution log: [docs/execution-record.md](docs/execution-record.md)
- Run artifacts: `results/<YYYYMMDDTHHMMSSZ>-<slug>/` (gitignored)

## Source policy

Native ADS source under `ads/` uses unrestricted/ideal material definitions and
may be tracked without transient caches/locks. Do not commit solver datasets,
Touchstone exports, logs, OA locks or private host bindings; those live under
`results/` or `.local/`.

## Entry points

```powershell
python scripts/ads_workspace.py validate --workspace workspaces/al2o3-tf-msl-110g-em
python scripts/ads_workspace.py new-run --workspace workspaces/al2o3-tf-msl-110g-em --slug width-search
python scripts/ads_workspace.py snapshot-spec --workspace workspaces/al2o3-tf-msl-110g-em
```

## ADS MCP client

Claude Code does not register the ADS MCP server directly. `tools/ads_mcp.py`
speaks newline-delimited JSON-RPC over the SSH alias in `ADS_MCP_SSH_ALIAS`
to `ads-mcp.exe` in the configured ADS installation. `ADS_MCP_SSH`,
`ADS_MCP_REMOTE` and `MSL_WORKSPACE_ROOT` override the corresponding defaults;
keep their values in the session environment or ignored `.local/` notes.

```powershell
python workspaces/al2o3-tf-msl-110g-em/tools/ads_mcp.py list-sessions
python workspaces/al2o3-tf-msl-110g-em/tools/ads_mcp.py --session <pid> summary
python workspaces/al2o3-tf-msl-110g-em/tools/ads_mcp.py --session <pid> exec --file <script.py>
python workspaces/al2o3-tf-msl-110g-em/tools/ads_mcp.py --local exec --code "print('hello')"
```

Each invocation starts a fresh MCP server process; scripts must be
self-contained. For long solver runs, launch a background process on the ADS
host and poll its log/status files from later `exec` calls. Prefer attaching to
an existing UI session; do not start a headless session or disturb unsaved
designs without recording the decision.

## Retained evidence per run

- `cases/<candidate>/`: frozen layout export/source snapshot, substrate and
  port settings, mesh settings, solver log, raw complex S2P.
- `units/`: lossless-metal and lossless-dielectric control runs.
- `reproductions/`: fresh rebuild of the selected candidate.
- `handoff/`: S2P, stack/port manifest, extraction report.
- Derived CSV/plots belong with the run and must name the raw dataset they
  come from.

## Status

Execution run `results/20261119T065241Z-msl-em-execution/` is **COMPLETE** on the
corrected full-plane 4.5 um Au-cover DUT: top-only line, W = 120 um, TML ports,
3.0/6.0 mm coupons, 0.1-110 GHz. Selected-line H1/H2/H3 **PASS**
(Z0(110) = 50.81 - 3.79j ohm on 3.0 mm, 49.18 - 2.49j ohm on 6.0 mm; mesh
convergence and passivity pass; fresh C34/C35 rebuild reproduces to <0.0003%).
The Au cover adds 0.011 dB/mm at 65 GHz and 0.018 dB/mm at 110 GHz versus the
PERFECT_CONDUCTOR control. The finite 2.0/4.0 mm bottom-Au cases are nonphysical
at 110 GHz and are retained as controls. Model integration is qualified over
0.1-110 GHz for the Au-cover model; full-filter acceptance is **NOT EVALUATED**.
See [docs/execution-record.md](docs/execution-record.md) and the run's
`handoff/extraction-report.md`.
