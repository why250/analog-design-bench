# Stage 2 experiment matrix and engineering decisions

**Proposed plan; no experiment below has been executed.** All numeric axes are
synthetic, not InP capability, tolerance, corner or yield data. This document
defines ten work packages E0-E9. Retuning and richer device models are optional
extensions after the required study.

## Common controls

Use the pinned full-precision Stage 1 L/C values unless a row explicitly
perturbs them. In single-effect rows, all unspecified loss/parasitic parameters
are zero. In combined rows, explicitly assign every device coefficient. All
inductors share the selected Q_L_ref label but have individual
Rs_i = 2*pi*65e9*L_i/Q_L_ref. All inductors share the selected lossless
f_L0 label but have individual Cp_i = 1/((2*pi*f_L0)^2*L_i).
Both are labels for generating fixed coefficients, not constant measured Q
or independently assigned actual SRF. ESR and ESL axes are common absolute
per-capacitor values. See [model-plan.md](model-plan.md).

The ideal anchor is Rs=Cp=ESR=ESL=0. Encode its absent loss/resonance labels as
`"ideal"` / `null`, not nonstandard JSON Infinity. Optional G_leak and C_extra
are zero throughout the required matrix. No random sampling is required.

Freeze resolved physical coefficients before a value-perturbation row: varying
L or C alone does not regenerate Rs, Cp, ESR or ESL to keep Q or f_L0 constant.
Report the resulting changed Q and resonance. Deliberate co-variation is a
different experiment with a separate ID and explicit parameter rule.

## Required work packages

Case counts below refer to full-filter **parameter-setting requests**, not
frequency points, simulator invocations, isolated-device runs or unique cases
after deduplication. Adaptive sweeps may require multiple simulator invocations
per setting. Keep a map from every request to its actual retained case.

| ID | Question and controlled experiment | Full-filter requests | Required decision/evidence |
| --- | --- | ---: | --- |
| E0 | Recover the disclosed ideal baseline with all parasitics off in an isolated Stage 2 namespace | 1 | Baseline identity, four metrics, complex S agreement and preserved original inputs |
| E1 | Validate the device models before cascading them: three representative L values and two C values, with the coefficients used below | Separate unit-cell runs | Z(f), intrinsic and terminal Q, analytic/measured resonance and finite-Rs DC behavior; ideal and nonideal limiting checks |
| E2 | Inductor loss only: common Q_L_ref = 10, 20, 30, 40, 60, 100, 200; then only L2, only L3, only L4 at Q_L_ref=40 with all other inductors ideal | 7 + 3 = 10 | Loss/match/absorption tradeoff, analytic DC prerequisite, central-arm versus whole-ladder effect |
| E3 | Inductor Cp only: common f_L0 = 80, 100, 120, 160, 240, 480 GHz; then only L2, only L3, only L4 at f_L0=100 GHz | 6 + 3 = 9 | Shifted impedance/resonance, Cp budgets in fF, central-arm effect and failure modes near 65/80 GHz |
| E4 | Capacitor ESR only = 0.05, 0.1, 0.25, 0.5, 1, 2 ohm; ESL only = 1, 2, 5, 10, 20, 40 pH; one all-capacitor ESR=1 ohm + ESL=20 pH case; then each C1-C4 individually with ESR=0.5 ohm + ESL=10 pH | 6 + 6 + 1 + 4 = 17 | Separate dissipation from resonance shift; show which shunt branch dominates; do not predict all metrics to change monotonically |
| E5 | Ideal nominal-value sensitivity: each of nine elements independently at -10%, -5%, -1%, +1%, +5%, +10%; also Cartesian common L scale and common C scale in {0.95,1,1.05}, omitting (1,1) already in E0 | 54 + 8 = 62 | Rank local sensitivities; document large-perturbation nonlinear behavior, peak switching and S11/S22 asymmetry |
| E6 | Combined loss/parasitics: Q_L_ref in {20,40,80,160} x f_L0 in {100,160,320,640} GHz x ESR in {0.1,0.5} ohm x ESL in {2,10} pH | 64 | Four-metric feasibility maps, failed-metric attribution, finite-loss actual SRF and central-inductor effective response |
| E7 | Nonideal nominal-value sensitivity at anchor B, already scheduled in E6: Q_L_ref=80, f_L0=320 GHz, ESR=0.1 ohm, ESL=2 pH. Each L/C separately +/-1%; four common-scale combinations (L,C)=(0.95,0.95),(0.95,1.05),(1.05,0.95),(1.05,1.05) | 18 + 4 = 22 | Rank sensitivity with losses present; coefficients frozen, not Q/SRF labels; compare with E5 and identify harmful combined shifts |
| E8 | Four conditional boundary slices, defined below | 20 seeds + up to 20 adaptive requests | Sampled feasible/failing intervals and their controlling metrics, or explicit no-bracket / no-feasible-sample finding |
| E9 | Fresh-workspace rebuild of E0, B, and the E6 case Q_L_ref=40, f_L0=100 GHz, ESR=0.5 ohm, ESL=10 pH | 3 repetitions | Source/settings/netlist identity and complex-S reproduction; do not select only electrically favorable cases |

E0-E7 schedule **185** filter requests. E9 adds three repeats. E8 adds
20-40 requests before duplicate removal: **208-228 scheduled filter evaluations**
in total, excluding unit cells and additional frequency refinement. Reuse an
identical resolved parameter manifest rather than rerunning duplicates, while
preserving its experiment mappings. This is a planning budget, not completed
coverage or a promise of a fixed ADS job count.

## E8: conditional boundary search

Use reference coefficients generated from Q_L_ref=200, f_L0=640 GHz,
ESR=0.1 ohm and ESL=2 pH. Change only one generator coordinate per slice;
the remaining coordinates stay at these reference values. Resolve coefficients
once per case and retain the full manifest.

| Slice | Five initial nodes | Refinement coordinate |
| --- | --- | --- |
| Common Q_L_ref | 10, 20, 40, 80, 200 | Geometric midpoint |
| Common f_L0 | 80, 120, 200, 360, 640 GHz | Geometric midpoint |
| Common capacitor ESR | 0, 0.1, 0.5, 1, 2 ohm | Arithmetic midpoint |
| Common capacitor ESL | 0, 2, 10, 20, 40 pH | Arithmetic midpoint |

Evaluate every node under the full system specification. Insert up to five
additional parameter settings per slice, prioritizing adjacent valid PASS/FAIL
intervals, then intervals with the smallest signed electrical margin. Retain
all observed windows; do not assume monotonicity or apply bisection across a
known nonmonotonic interval. Refinement narrows a sampled local boundary; it
does not prove a unique global minimum Q or maximum Cp/ESR/ESL.

Report the two endpoint manifests, width, limiting metric and its numerical
uncertainty for every bracket. If all samples fail, report "no feasible sample
in this slice"; if all pass, report the explored range without inventing an
outer limit. Budget-limited unsearched intervals remain explicit. Additional
parameter sampling is optional; unresolved frequency coverage or invalid data
at a required sample must be resolved under the verification plan.

Translate f_L0 intervals into individual Cp intervals, and report terminal
Q for L2/L3/L4 at 65 and 80 GHz, plus each device's actual SRF. Inductive sign through 80 GHz
is a diagnostic screen; the actual filter's four metric checks determine
conditional electrical feasibility.

## Measurements for every filter case

Retain all four system metrics with worst-case frequencies, exact 65 GHz
S11/S22/S21 and exact 80 GHz S21. Record signed margins relative to the limits,
DC-limit metrics, coverage, passivity, reciprocity and independent complex-S
error. Store failures as well as passes. Plots must expose the full response
and use insertion-loss axes suitable for lossy cases.

Calculate A1=1-|S11|^2-|S21|^2 and A2=1-|S22|^2-|S12|^2 to explain
absorption. Compare the E2/E4 loss-only cases with E3 and E4 ESL-only cases:
an apparently improved return loss may reflect absorbed power or damping.
An isolated 80 GHz notch cannot establish satisfactory passband behavior.

For E5 and E7, calculate the central secant
`[m(p*1.01)-m(p*0.99)]/0.02` for each finite metric m, reporting units as
dB per unit fractional parameter change (divide by 100 for dB per 1%). Report
the peak frequencies on both sides; a maximum over frequency can switch
peaks and be nonsmooth. Add linear-magnitude or complex-S sensitivity when
dB is undefined at an exact zero. Never derive a process probability from
these deterministic perturbations.

## Required deep-dive cases and learning records

Analyze E0, anchor B, the E9 near-resonance E6 case, and at least one E8
limiting bracket in detail. If E8 finds no valid PASS/FAIL bracket, use the
valid E8 sample/window closest to a system threshold and explain the no-bracket
outcome; absence of a bracket does not itself prevent study completion.
These are four deep-dive selections; a bracket selection includes both endpoint
cases. For each selection:

1. Overlay transmission, both reflections and absorbed power with the ideal
   baseline; annotate moved extrema and explain their physical origin.
2. Plot L2/L3/L4 terminal impedance, signed Q, effective reactance and actual
   resonance. Compare the large inductors with L1/L5.
3. Extract or independently calculate poles of the declared rational RLC
   transfer function, using a scaled state-space/nodal formulation. Retain
   residual checks and stable denominator construction. Distinguish complex
   poles, impedance resonances, reflection maxima and transmission zeros;
   do not infer poles by counting plot peaks. Treat lossless marginal cases
   and pole-zero cancellation explicitly.
4. Write the prediction before ADS; then cite observed data, explain
   agreement/disagreement, and record the next design decision. The four
   checkpoints in [model-plan.md](model-plan.md) provide starting questions.

## Optional same-topology retuning

Freeze E0-E9 conclusions first. A proposed exploratory bound is +/-10% on the
five symmetry groups (L1/L5, L2/L4, L3, C1/C4, C2/C3), retaining the ladder and
fixed anchor-B Rs/Cp/ESR/ESL. This bound is not a fabrication tolerance.
Record starting and final values, search budget/algorithm and stopping rule.
Evaluate with the same independent bench and dense frequency checks; retain
untuned and tuned cases separately. Changing L alters derived Q and SRF under
the frozen-coefficient policy. A future geometry-aware search needs PDK data
to specify how all coefficients co-vary.

No optional retuning success, lower-order synthesis, elliptic design, TLIN,
layout, EM, Monte Carlo or PDK calibration is required to close Stage 2.
