# Execution record: al2o3-tf-msl-110g-em-r1

- Stage: `em-design`
- Task specification: [instruction.md](../../../tasks/al2o3-tf-msl-110g-em/instruction.md)
- Model plan: [model-plan.md](../../../tasks/al2o3-tf-msl-110g-em/model-plan.md)
- Verification plan: [verification-plan.md](../../../tasks/al2o3-tf-msl-110g-em/verification-plan.md)
- Execution run: `results/20261119T065241Z-msl-em-execution/` (gitignored)

## Retained runs

| Run ID | Purpose | Outcome | Notes |
| --- | --- | --- | --- |
| `20261119T065241Z-msl-em-execution` | W0-W5 single-line EM execution | **COMPLETE** | Frozen contract, amended ideal-ground model, width search, controls, reproduction |

## W0/G0 frozen contract (2026-11-19)

Gate state: **SATISFIED** by this record before any EM solve.

### Stack and provenance

| Layer / item | Frozen value | Source classification |
| --- | --- | --- |
| Substrate material | Al2O3 | user drawing |
| Substrate thickness | 127 um (dielectric thickness between the two Au layers) | user drawing |
| Substrate relative permittivity | 9.9 (real, frequency independent) | user drawing |
| Substrate loss tangent | 1e-4 | proposed typical value, approved by user |
| Top conductor | Au, 4.5 um thick | user drawing |
| Bottom conductor | Au, 4.5 um thick | user drawing |
| Conductor conductivity | 4.1e7 S/m | proposed typical value, approved by user |
| Conductor surface roughness | smooth (no roughness model) | proposed typical value, approved by user |
| Cover medium | air above and below, open boundaries | modeling choice |
| Coupon lengths | 3.0 mm and 6.0 mm | user drawing |
| Coupon transverse width | 2.0 mm nominal | proposed research assumption (G0 freeze item) |
| Design variable | uniform line width W | user decision |
| Acceptance frequency | 110 GHz | user decision (2026-11-19) |
| Band | 0.1-110 GHz | user decision |
| Solver | ADS 2027 Momentum microwave, thick metal | user decision |

The material stack is user-supplied and is not substituted. The loss values are
assumed typical values; every result is conditional on them and is not a
measured-material or foundry-qualified result.

### Geometry, ports, return and reference planes

- DUT: one straight, centered, uniform-width top Au line spanning the full coupon
  length. No launches, tapers, stubs, vias, airbridges or adjacent lines.
- Top coupon footprint and bottom Au footprint are both 2.0 mm (x) by L (y).
  The bottom Au is a finite conductor polygon, not an abstract ideal ground.
- Ordered microstrip ports: `rf_in` at `x=0` (port 1) and `rf_out` at `x=L`
  (port 2). Positive terminal on the top signal line; negative/reference terminal
  on the bottom Au directly beneath the port. Port width equals the line width W.
- Reference planes at the coupon edges. No port-discontinuity de-embedding and no
  reference-plane shift is applied. The physical length used in extraction is the
  distance between the declared reference planes (`L` = 3.0 mm or 6.0 mm).
- Raw S-parameters use real 50 ohm reference impedance, port order (1 = `rf_in`,
  2 = `rf_out`), and full complex entries.
- The port calibration mode and mesh settings are held identical across all
  widths and both lengths. Any alternative used as a sensitivity control is
  declared as a control only.

### Width search and budget

- Legal search range: W = 50-300 um inclusive (uniform, centered).
- Coarse grid: 25 um steps, 11 points (50, 75, ..., 300 um).
- Refinement: 5 um steps around the bracketing pair, at most 10 additional
  solves.
- Selection rule: choose an actually simulated width meeting H1
  (47.5 <= Z0(110 GHz) <= 52.5 ohm). Never interpolate an unsolved width.
- All failed and non-monotonic widths are retained.
- Control budget: at most 8 numerical or sensitivity controls plus one fresh
  reproduction.

### Acceptance criteria (frozen)

| ID | Criterion |
| --- | --- |
| H1 | Z0(110 GHz) in 47.5-52.5 ohm inclusive |
| H2 | Last two mesh refinements: <=2% change in Z0 and epsilon_eff, <=5% change in alpha, at 65 and 110 GHz |
| H3 | Complete finite S2P; passivity `|S11|^2+|S21|^2 <= 1 + 1e-3`; reciprocity `|S21-S12| <= 1e-6`; no persistent nonphysical negative alpha |
| R2 | Report Z0(f) 10-110 GHz; screening window 45-55 ohm adopted |
| R4 | 3 mm and 6 mm give consistent Z0 and epsilon_eff; alpha*L scales with length |
| R5 | Conductor/dielectric loss split at 65 and 110 GHz |

Frequency checkpoints: 0.1, 1, 10, 40, 65, 80 and 110 GHz, plus the dense sweep.
110 GHz decides H1; 65 GHz is the in-band convergence checkpoint.

### Analytic seed and prediction recorded before EM

Zero-thickness Hammerstad-Jensen, er = 9.9, h = 127 um:

- 50 ohm quasi-static width: **W = 121.3 um**
- epsilon_eff at that width: **6.659**
- Predicted conductor loss at 110 GHz (`Rs/(Z0 W)`): **0.147 dB/mm**
- Predicted dielectric loss at 110 GHz: **0.0024 dB/mm**
- Skin depth in Au at 110 GHz: 0.237 um; 4.5 um is about 19 skin depths.
- Predicted 6 mm total line loss at 110 GHz: about 0.90 dB (excluding mismatch).

Prediction before EM: finite 4.5 um metal behaves like a slightly wider line, and
dispersion lowers Z0 toward 110 GHz, so the 110 GHz 50-ohm optimum is expected to
be **somewhat narrower than 121 um**. The EM search, not this estimate, decides H1.

## Preflight findings

- 2026-11-19: ADS MCP lists one UI session, PID 58724, host `<ADS_HOST>`, no
  workspace open. Attaching and running read-only Python succeeded.
- Remote repository root `<repository-root>` exists and contains
  `.local`, `docs` and `workspaces`; the remote `workspaces` root is writable.
- ADS installation is the configured ADS 2027 root. The native substrate
  API (`keysight.ads.subst`) and AEL EM-setup entry points are available.
- The task-owned MCP client connects over the configured SSH alias.
- Momentum license checkout is not yet proven; the first real solve is the
  license/feature preflight.

## Decisions and limitations

- 2026-11-19: Workspace initialized from the user's stack drawing and the four
  confirmed choices (50 ohm design at 110 GHz plus characterization, 0.1-110 GHz,
  width as design variable, typical loss assumptions).
- 2026-11-19: G0 frozen as above; no contract change requested.
- The 127 um value is treated as dielectric thickness between the Au layers.
- A converged EM result will support only the declared stack, geometry, ports and
  solver conditions. It will not establish fabrication accuracy, measured-material
  agreement, launch/connector performance, or filter acceptance.

## Execution log

### G1: native model and export

- ADS 2027 Momentum `MomEngine_64 2027.00.303`, host `<ADS_HOST>`, UI session 58724.
  Momentum license checkout and full-wave `Simulation Mode: uW` observed in the
  solver logs.
- Native workspace `ads/al2o3_msl_wrk`, library `MSL_R01_lib`, substrate
  `Al2O3_MSL` created. Exported deck confirms:
  `Al2O3_MSL PERMITTIVITY=9.9 LOSSTANGENT=1e-4`, `Au CONDUCTIVITY=4.1e7`,
  top metal `EXPAND=4.5e-06 UP`, bottom metal `EXPAND=4.5e-06 DOWN`,
  `TOP OPEN MATERIAL=AIR`, `BOTTOM OPEN MATERIAL=AIR`.
- C01 build failed because ADS encodes uppercase cell names in the on-disk
  directory (`MSL_Line_C01` -> `%M%S%L_%Line_%C01`). The failed cell is retained.
  C02 is the same 120 um geometry rebuilt with the registered view path.
- A native emSetup must be registered with `Cell.create_view("emSetup",
  "eesof_em_setup")`; copying only the directory leaves the library unaware of
  the view. This is now in `tools/build_ads.py`.

### G1: port-model investigation (probe cells)

All probes use the frozen stack, a 120 um line, 3.0 mm length, 50 um mesh and
the 2.0 mm finite bottom Au unless stated otherwise.

| Port model | 65 GHz | 110 GHz | Observation |
| --- | --- | --- | --- |
| Direct, explicit P3/P4 | S11 -0.097-0.028j, S21 -0.193+0.932j, passivity 0.916 | S11 0.009-0.273j, S21 0.975+0.022j, passivity **1.0268** | Nonphysical at 110 GHz; ABCD gives Z0 3.1+53.0j. Large minus-pin warning from 5.86 GHz. |
| TML calibration, explicit P3/P4 | S11 0.075+0.009j, S22 -0.374+0.120j, passivity 0.969, Z0 43.2+4.1j | S11 0.056-0.030j, S22 -0.372+0.676j, passivity 0.689, Z0 45.9+23.9j | Port 2 asymmetric; TML de-embeds port 1 only. |
| Lumped (cal_type 2), explicit P3/P4 | passivity 0.883 | abs(S21) 1.048, passivity **1.159** | Gain; invalid. |
| TML, **ideal bottom ground plane** | S11=S22=-0.059-0.014j, abs(S21) 0.977, passivity 0.959, Z0 **46.91-0.03j** | S11=S22=-0.0039-0.0040j, abs(S21) 0.970, passivity 0.941, Z0 **51.07-3.27j**, A=D within 1.4e-5 | Clean, symmetric, passive control. |
| TML, 4.0 mm finite bottom Au | S11 -0.850-0.040j, S22 -0.052+0.981j, abs(S21) 0.258, passivity 0.791 | S11 1.020+0.033j, S22 0.974-0.054j, abs(S21) 0.048, passivity **1.043** | Worse than 2.0 mm; nonphysical. |
| TML, 2.0 mm finite bottom Au, 30 um mesh | abs(S11) 0.177, abs(S22) 0.133, abs(S21) 1.094, passivity **1.228** | abs(S11) 6.95, abs(S22) 5.83, abs(S21) 6.38, passivity **89.0** | Mesh refinement does not recover a physical result. |

### G1 decision point: finite-return representation

The frozen DUT (2.0 mm finite bottom Au) cannot be represented by the Momentum
microwave port models available in ADS 2027 (Direct, TML, Lumped) at 110 GHz:

- Direct with explicit P3/P4: passivity 1.027 at 110 GHz.
- TML with explicit P3/P4: port 2 asymmetric and Z0 complex.
- Lumped: gain (|S21| > 1).
- 4.0 mm finite ground: |S11| > 1 at 110 GHz.
- 30 um mesh: |S11| = 6.95 and passivity 89 at 110 GHz.

The only clean model is the **ideal bottom ground + TML** control:
S11 = S22, A = D, passivity 0.94, Z0(110 GHz) = **51.07 - 3.27j ohm** for
W = 120 um. That model uses the solver ground reference, which the frozen
contract explicitly classifies as a numerical control, not the DUT.

No width search or H1/H3 claim is made on the finite-ground DUT until the
contract decision below is recorded. The raw probe datasets, decks and logs are
retained under `results/20261119T065241Z-msl-em-execution/work/`.

**Decision required:** choose whether to (A) amend the contract to qualify the
ideal-ground model, (B) keep the frozen finite-ground DUT and report H1-H3
INDETERMINATE/INVALID with the control evidence, or (C) stop this task at the
blocker and open a separate port/launch-model task.

**Decision taken 2026-11-19: option A.** The user authorized amending the G0
physical-return definition to the solver ground reference for the selected-line
qualification. The amended DUT for H1-H3 is one uniform Au line on the frozen
127 um Al2O3 / 4.5 um Au stack with:

- ideal bottom PERFECT_CONDUCTOR at the Al2O3 bottom interface (solver ground),
- air above the line,
- 2.0 mm finite bottom Au and 4.0 mm finite bottom Au retained as declared
  numerical controls, not as the qualified DUT,
- TML-calibrated two ports at x=0 and x=L, 50 ohm reference,
- all other frozen values (width search range, 110 GHz acceptance, loss values)
  unchanged.

The task package `tasks/al2o3-tf-msl-110g-em/*` is not modified; this is a
recorded execution amendment in the workspace. The finite-ground results remain
as evidence of why the amendment was required.

### Amended model and candidate map

- Amended DUT: `Al2O3_MSL_GND` substrate, top Au line only, TML ports `rf_in`
  (P1) and `rf_out` (P2) with `::__GND__` reference, 50 ohm.
- Finite-ground controls: `Al2O3_MSL` substrate with the 2.0 mm and 4.0 mm
  bottom Au polygons.
- Candidate map:
  - C01: failed finite-ground build (cell-directory encoding); retained.
  - C02: finite-ground W = 120 um, 3.0 mm; used for the port-model controls.
  - C03-C13: finite-ground W = 50-300 um, 3.0 mm; retained controls, not used
    for H1.
  - C14-C24: **ideal-ground** W = 50, 75, 100, 125, 150, 175, 200, 225, 250,
    275, 300 um, 3.0 mm, 50 um mesh; coarse width search.
  - Refinement and 6.0 mm candidates are allocated after the coarse result.
- Native build/export verified for C14/C15: `proj.ltd` has
  `BOTTOM COVERED MATERIAL=PERFECT_CONDUCTOR`, `TOP OPEN MATERIAL=AIR`,
  `Al2O3_MSL PERMITTIVITY=9.9 LOSSTANGENT=1e-4`, `Au CONDUCTIVITY=4.1e7`,
  top metal `EXPAND=4.5e-06 UP`. `proj.prt` has two TML-calibrated ports with
  50 ohm references.

## Results (G2/G3)

> **Control note:** these are the PERFECT_CONDUCTOR-cover control results from
> the 2026-11-19 run. The corrected full-plane 4.5 um Au-cover DUT is documented
> in the 2026-11-20 correction section below; the finite-bottom-Au cases are
> retained failed/control evidence.

Selected line: **W = 120 um**, ideal solver ground, TML ports, 3.0 mm and
6.0 mm coupons. Primary extraction: ABCD, `Z0 = sqrt(B/C)`,
`gamma = acosh((A+D)/2)/L`. Sparse-checkpoint epsilon_eff uses a declared
2*pi*n branch inside the physical window 6.0-8.5; raw S2P is unchanged.

### H1-H3

| Criterion | Result | Evidence |
| --- | --- | --- |
| H1, 3.0 mm | **PASS**, Z0(110) = 51.102 - 3.335j ohm | exact 110 GHz solve, C28 |
| H1, 6.0 mm | **PASS**, Z0(110) = 49.365 - 2.269j ohm | exact 110 GHz solve, C30 |
| H2 | **PASS** | mesh 40 -> 30 um: dZ0 +0.18% (110), -0.10% (65); deps +0.11%/+0.10%; dalpha +1.05%/-1.07% |
| H3 | **PASS** | max passivity 0.996952 (3 mm), 0.993923 (6 mm); reciprocity <= 1e-15; no negative alpha; complete finite S2P |

### R1-R5

- **R1**: simulated H1 interval 110-125 um at 110 GHz; `dZ0/dW ~ -0.18 ohm/um`;
  W = 130 um is a retained non-monotonic extraction outlier (Z0 38.3 ohm with
  normal S-parameters). W = 120 um selected.
- **R2**: Z0(f) 10-110 GHz stays within 46.9-51.1 ohm (45-55 screening window
  adopted). Worst point 65 GHz, 46.91 ohm. The 93.21 GHz adaptive point
  (Z0 = 39.57 ohm) is a flagged ABCD/TML phase ill-conditioning outlier; its
  S-parameters are normal and passive.
- **R3**: epsilon_eff 6.53 (10 GHz) -> 6.94 (65 GHz) -> 7.37 (110 GHz);
  quasi-static Hammerstad-Jensen 6.659; dispersion trend as expected; 3/6 mm
  agree to 0.05% at 110 GHz.
- **R4**: 3 vs 6 mm: Z0(110) 51.102 vs 49.365 (3.4% difference, both inside H1);
  epsilon_eff(110) 7.366 vs 7.362 (0.05%); alpha*L 0.267 vs 0.517 dB (ratio 1.94).
- **R5**: at 110 GHz alpha_total 0.08907, alpha_dielectric 0.01102,
  alpha_conductor 0.07805-0.08625 dB/mm; at 65 GHz 0.06056, ~0.0001, 0.05924-
  0.06045 dB/mm. Conductor loss dominates; simple `Rs/(Z0 W)` estimate 0.147 dB/mm
  is 1.7-1.9x the EM conductor-only value.

### Controls and reproduction

- Mesh 50/40/30 um: H2 PASS.
- Port TML vs Direct (ideal ground): 110 GHz 51.10-3.33j vs 31.32-26.63j;
  alpha 0.089 vs 1.014 dB/mm. TML is the frozen choice.
- Ground representation: finite 2.0 mm Direct passivity 1.0268; finite 2.0 mm
  TML asymmetric; finite 4.0 mm TML abs(S11) 1.020; all nonphysical at 110 GHz.
- Thickness 4.5 vs 9 um: Z0 51.10 vs 49.59; alpha 0.08907 vs 0.08437 dB/mm
  (5.3% lower at 9 um). The frozen value is 4.5 um.
- Adaptive vs discrete: 110 GHz Z0 identical; 65 GHz alpha 0.06117 vs 0.06056
  (1.0%). Exact 110/65 GHz values come from actual discrete solves.
- Fresh reproduction `MSL_Line_C31`: Delta Z0 +0.012% (65) / -0.059% (110);
  Delta epsilon_eff +0.025% / -0.010%; Delta alpha +0.363% / -0.045%; all within
  1%/1%/3%.

### Four conclusions

- **Study completion: COMPLETE.**
- **Selected-line result: PASS** (H1, H2 and H3) on the amended ideal-ground
  model. The finite-bottom-Au DUT is not qualified and remains a declared
  control; the G0 amendment is recorded above.
- **Model integration readiness: QUALIFIED over 0.1-110 GHz** for the 120 um
  line with the ideal solver ground, 3.0/6.0 mm, TML ports and assumed loss
  values. Gaps: finite-ground coupon, launch/connector, 4.5 um thickness
  sensitivity, 3/6 mm Z0 3.4% difference, isolated extraction outliers.
- **Full circuit/filter acceptance: NOT EVALUATED.**

### Retained evidence

- `results/20261119T065241Z-msl-em-execution/handoff/` — corrected AuGND S2P
  models (`model/MSL_R01_AuGND_W120um_L3mm.s2p`, `...L6mm.s2p`),
  `metrics_augnd.csv`, PERFECT_CONDUCTOR control S2P, `stack-port-manifest.json`,
  `extraction-report.md`, `plots/augnd_*.png`, `plots/ground_loss_vs_f.png`.
- `results/20261119T065241Z-msl-em-execution/cases/` — C32/C33 corrected Au-cover
  DUT (adaptive/discrete/mesh), C34/C35 fresh reproduction, C14-C29 PC width
  search, C28/C30 PC full-band, C31 PC reproduction, exports, decks,
  construction/prepare/launch/raw-model receipts and solver logs.
- `results/20261119T065241Z-msl-em-execution/work/` — finite-ground port-model
  probes, mesh/loss/thickness/port controls, sweep status JSON, and
  `augnd-analysis-summary.json` for the corrected DUT.
- `results/20261119T065241Z-msl-em-execution/remote-run/` — transferred copy of
  the remote run evidence.
- `results/20261119T065241Z-msl-em-execution/failed-builds/` — archived lowercase
  partial cells (`plain-dirs/`) and the local plain-dir archive
  (`local-plain-dirs/`), each with file hashes.
- `results/20261119T065241Z-msl-em-execution/delivery/` — PERFECT_CONDUCTOR and
  AuGND delivery-cell exports, 110 GHz verification cases, S2P and analysis.
- The local native source copy under `ads/al2o3_msl_wrk/` has
  `MomLayout/workspaceText` set to `.` for portability; the remote execution
  used the absolute workspace path. Construction/prepare/launch receipts are
  retained in the run evidence rather than in the tracked native source.

## Cleanup and delivery cells (2026-11-19)

### Library cleanup

The ADS API enumerated 38 registered cells in `MSL_R01_lib`: 31 canonical
candidates `MSL_Line_C01`-`C31`, 2 new delivery cells, and 5 probe cells. It
also registered 12 lowercase partial cells `msl_line_c01` and
`msl_line_c03`-`c13`, each with an `emSetup` view and no `layout`. They were the
failed first-pass plain-directory builds, displayed by ADS as lowercase names.

Actions, in order:

1. Copied the partial `msl_line_c01` `emSetup` XML into the canonical encoded
   cell `MSL_Line_C01` (`%M%S%L_%Line_%C01/em%Setup`), patched
   `MomLayout/cellText` to `MSL_Line_C01`, and verified the canonical view list
   is `layout, emSetup`. C03-C13 already had canonical `emSetup` views identical
   in substrate (`MSL_R01_lib:Al2O3_MSL`) and Direct P1/P3, P2/P4 ports, so no
   copy was needed.
2. Archived every lowercase partial cell to
   `results/<run>/failed-builds/plain-dirs/<name>/` with an
   `archive-manifest.json` containing source path, views, file sizes and SHA-256,
   and a verification flag; then deleted the registered partial cells with
   `Library.delete_cell`. `remaining_partials = []`.
3. Canonical `MSL_Line_C01`-`C31` and all run evidence were retained.

### Delivery cells

Created with `db.copy_design` (the ADS Python equivalent of saving the design
contents under a new cell) plus a copied and patched `emSetup` XML:

| Delivery cell | Source | W / L | Views | Substrate / ports |
| --- | --- | --- | --- | --- |
| `MSL_Line_Selected_W120um_L3mm` | `MSL_Line_C28` | 120 um / 3.0 mm | `layout, emSetup` | `Al2O3_MSL_GND`; TML P1/P2, `::__GND__` |
| `MSL_Line_Selected_W120um_L6mm` | `MSL_Line_C30` | 120 um / 6.0 mm | `layout, emSetup` | `Al2O3_MSL_GND`; TML P1/P2, `::__GND__` |

The copied `emStateFile.xml` has `cellText` and dataset names set to the
delivery cell, `MomSubstrate/libSubstName = MSL_R01_lib:Al2O3_MSL_GND`, and the
same 50 um mesh / 0.1-110 GHz AFS plan. Exported decks verified: TML calibration,
two 50 ohm ports, `BOTTOM COVERED MATERIAL=PERFECT_CONDUCTOR`,
`MATERIAL Al2O3_MSL PERMITTIVITY=9.9 LOSSTANGENT=1e-4`, `MAXCELLSIZE 50 UM`,
`SimulationMode 1`.

Exact 110 GHz verification solves:

| Delivery cell | Z0 (ohm) | Source Z0 (ohm) | Difference |
| --- | --- | --- | --- |
| `MSL_Line_Selected_W120um_L3mm` | 51.068 - 3.271j | 51.102 - 3.335j | -0.067% real |
| `MSL_Line_Selected_W120um_L6mm` | 49.355 - 2.240j | 49.365 - 2.269j | -0.020% real |

Both pass H1. C28 and C30 were not modified. The delivery evidence is under
`results/<run>/delivery/<cell>/`.

### Local source sync

- Copied the two delivery cell directories and the canonical C01 `emSetup` view
  from the remote library into `ads/al2o3_msl_wrk/MSL_R01_lib/`; refreshed
  `libRefs.json`, `.oalib`, `tech.db`, `materials.matdb` and the two `.subst`
  files.
- Moved the local uppercase plain partial dirs `MSL_Line_C01` and
  `MSL_Line_C03`-`C13` to
  `results/<run>/failed-builds/local-plain-dirs/` (contents preserved).
- Re-patched every local `emStateFile.xml` `workspaceText` to `.`; the local
  `ads/` tree now has zero local absolute-path occurrences.
- `python scripts/ads_workspace.py validate --workspace
  workspaces/al2o3-tf-msl-110g-em` -> `status: ok`, no errors or warnings.

## Correction 2026-11-20: full-plane 4.5 um Au ground cover

The updated task package clarifies that the intended return is a **full-plane
4.5 um Au cover (solver ground plane)**, not a finite bottom-Au polygon. The
2.0 mm width applies to the dielectric/top layout assumption; the ground is
laterally the solver cover. The finite 2.0/4.0 mm bottom Au and the
PERFECT_CONDUCTOR cover are controls, not the DUT.

### Substrate verification

- Created `Al2O3_MSL_AuGND` from `Al2O3_MSL_GND` with the bottom cover material
  changed from `PERFECT_CONDUCTOR` to `Au`, thickness 4.5 um.
- `.subst` stack:
  `AIR | interface groundplane=1 materialname="Au" thick="4.5" micron |
  Al2O3_MSL 127 um | interface | AIR`; top Au layer 4.5 um on the Al2O3 top
  interface.
- Exported `proj.ltd`:
  `TOP OPEN MATERIAL=AIR`,
  `INTERFACE Name=__Interface1 MASK={cond}`,
  `LAYER Name=__SubstrateLayer1 HEIGHT=0.000127 MATERIAL=Al2O3_MSL`,
  `BOTTOM COVERED THICKNESS=4.5e-06 MATERIAL=Au`,
  `MATERIAL Au CONDUCTIVITY=4.1e7`, `MATERIAL Al2O3_MSL PERMITTIVITY=9.9
  LOSSTANGENT=1e-4`.
- Port deck: two TML ports, plus P1/P2, reference `::__GND__`, 50 ohm; no P3/P4.

### Corrected DUT

- New candidates `MSL_Line_C32` (W=120 um, L=3.0 mm) and `MSL_Line_C33`
  (W=120 um, L=6.0 mm), top-only line, TML ports, `Al2O3_MSL_AuGND`.
- H1 at 110 GHz: `C32` Z0 = **50.809 - 3.706j ohm**, `C33` Z0 =
  **49.178 - 2.448j ohm**; both inside 47.5-52.5 ohm, so W=120 um remains the
  selected width and the bounded width search does not need to be rerun.
- Ground-loss contribution at 110 GHz: `C32` alpha = 0.10705 dB/mm versus
  PERFECT_CONDUCTOR control `C28` 0.08907 dB/mm, delta **+0.01798 dB/mm**;
  `C33` alpha = 0.10411 versus `C30` 0.08618, delta **+0.01793 dB/mm**. The
  ground loss is consistent across lengths and accounts for about 20% of the
  total attenuation at 110 GHz.
- Z0 shift versus the PERFECT_CONDUCTOR control: -0.57% (3.0 mm) and -0.38%
  (6.0 mm); epsilon_eff is unchanged within the extraction noise.
- Delivery cells: `MSL_Line_Selected_AuGND_W120um_L3mm` and
  `MSL_Line_Selected_AuGND_W120um_L6mm` copied from C32/C33, with
  `Al2O3_MSL_AuGND`, TML ports and the same patched emSetup/dataset names.
  The earlier PERFECT_CONDUCTOR delivery cells
  `MSL_Line_Selected_W120um_L3mm/L6mm` remain as declared controls.

### Corrected-DUT qualification

- **H2 (mesh 40 -> 30 um, C32 3.0 mm)**: 65 GHz dZ0 -0.098%, deps +0.096%,
  dalpha -0.887%; 110 GHz dZ0 -0.248%, deps +0.096%, dalpha +0.786%; **PASS**.
- **H3**: max passivity 0.996738 (3 mm), 0.993498 (6 mm); reciprocity
  2.3e-16 / 7.8e-16; no negative alpha; **PASS**.
- **R2**: Z0(f) 10-110 GHz within 46.1-50.8 ohm excluding the flagged
  93.21 GHz extraction outlier (40.78 ohm; S-parameters normal and passive).
  Worst non-outlier: 46.403 ohm at 58.713 GHz (3 mm), 46.125 ohm at 57.667 GHz
  (6 mm); inside the 45-55 ohm screening window.
- **R3**: epsilon_eff 6.535 (10 GHz) -> 6.944 (65 GHz) -> 7.371 (110 GHz) on
  3 mm; 6 mm 6.535/6.943/7.367; Hammerstad-Jensen 6.659.
- **R4**: 3 vs 6 mm: Z0(110) 50.831 vs 49.178 (3.25%); epsilon_eff(110) 7.371 vs
  7.367 (0.05%); alpha(110)*L 0.321 vs 0.625 dB (ratio 1.95); Z0(65) 46.922 vs
  47.221 (0.64%).
- **R5 / ground loss**: Au cover adds +0.01108 dB/mm at 65 GHz and
  +0.01801 dB/mm at 110 GHz (3 mm); +0.01106 / +0.01797 (6 mm). That is about
  15-17% of the total attenuation; the PERFECT_CONDUCTOR control provides the
  top-conductor + dielectric split.
- **Reproduction**: fresh C34/C35 versus C32/C33: dZ0 <= 0.00029%,
  deps ~0%, dalpha <= 0.00011%; **PASS**.
- **Delivery cells**: `MSL_Line_Selected_AuGND_W120um_L3mm` and
  `MSL_Line_Selected_AuGND_W120um_L6mm`; 110 GHz delivery Z0 =
  50.810 - 3.706j and 49.178 - 2.448j ohm.
- **Updated handoff**: `model/MSL_R01_AuGND_W120um_L3mm.s2p`,
  `model/MSL_R01_AuGND_W120um_L6mm.s2p`, `metrics_augnd.csv`,
  `stack-port-manifest.json`, `extraction-report.md`,
  `plots/augnd_*.png` and `plots/ground_loss_vs_f.png`.
- `results/<run>/work/augnd-analysis-summary.json` retains the complete
  per-case H1/H2/H3/ground-loss records.

### Corrected-DUT conclusions

- **Study completion: COMPLETE.**
- **Selected-line result: PASS** (H1, H2 and H3) on the corrected full-plane
  4.5 um Au-cover DUT, W = 120 um, 3.0/6.0 mm.
- **Model integration readiness: QUALIFIED over 0.1-110 GHz** for the corrected
  Au-cover model with assumed loss values. Gaps: launch/connector and coupon
  edge, finite bottom-Au control, 3.25% Z0 difference between 3 and 6 mm,
  ~5% thickness sensitivity, the 93.21 GHz extraction outlier, and no measured
  material.
- **Full circuit/filter acceptance: NOT EVALUATED.**


