# Verification plan: al2o3-tf-msl-110g-em-r1

**Revision 1 planning draft. No geometry, EM solve or line result is claimed.**
Use [instruction.md](instruction.md) and [model-plan.md](model-plan.md)
together. The authorized scope is one uniform line on the user-supplied stack;
this task does not evaluate a filter, a launch or a measured material.

## 1. Authority and readiness

- Verification scope: engineering EM milestone verification for the selected
  line candidate. Execution and evidence status: **planned, not performed**.
- Acceptance owner: the task contract and its retained evidence. No executable
  official verifier is implemented for this engineering task.
- Formal benchmark applicability: not registered. No official score, release
  membership or model-evaluation campaign is created.
- Frozen specification: this task package and the workspace
  `inputs/task-spec/` snapshot. Private host/session bindings stay in ignored
  local configuration.
- Pending preflight: ADS 2027/Momentum availability and license, the
  configured ADS-host session and the workspace path mapping. These are environment
  gates, not electrical results.

## 2. Coverage and decision mapping

| Criterion | Measurement method and units | Condition or domain | Raw evidence | Decision and coverage rule |
| --- | --- | --- | --- | --- |
| H1 | Z0 from ABCD, ohm | exact 110 GHz; frozen stack, ports and mesh; selected width | complex S2P, ABCD calculation, solver setup | PASS when 47.5 <= Z0 <= 52.5 ohm inclusive and the numerical-convergence evidence is valid |
| H2 | relative change of Z0, epsilon_eff, alpha between the final two mesh refinements, % | selected candidate at 110 GHz (acceptance point) and 65 GHz | mesh histories, settings, extracted metrics | PASS when changes are <=2%, <=2% and <=5% respectively; otherwise INDETERMINATE pending refinement |
| H3 | full-matrix passivity and reciprocity, finite complex entries | 0.1-110 GHz dense sweep | raw S2P, integrity checks | Invalid evidence when entries are missing/nonfinite, passivity or reciprocity fails outside tolerance, or attenuation is persistently negative |
| R1 | simulated width set and dZ0/dW, um and ohm/um | frozen search range | candidate table, retained failed runs, extraction | Report the feasible interval and the selected simulated width; a bounded miss completes the study without satisfying H1 |
| R2 | Z0(f), ohm; worst deviation from 50 ohm | 10-110 GHz dense sweep, internal extrema refined | S2P, extracted table and plot | Report; proposed screening window 45-55 ohm, adopted or amended at G0 |
| R3 | epsilon_eff(f) and model deviation, % | 1-110 GHz | extracted table, analytic model values | Report the deviation and trend; no pass threshold unless amended |
| R4 | Z0, epsilon_eff and alpha*L for 3 mm versus 6 mm | selected width | two S2P datasets and extraction | Report consistency; a large discrepancy indicates a port/reference-plane or numerical problem |
| R5 | alpha_conductor and alpha_dielectric, dB/mm | 65 and 110 GHz; lossy run and two controls | control runs, extraction, analytic estimates | Report both components and the comparison; no pass threshold |
| D1 | S11, S21, group delay, Z0, epsilon_eff, alpha curves | 0.1-110 GHz | plots and CSV derived from raw data | Report only |
| D2 | DC resistance and low-frequency limit | quasi-static/analytic | independent calculation and documented assumptions | Report only; the first EM point is not DC evidence |

H2 and H3 are evidence-qualification criteria. A candidate is not declared PASS
unless H1, H2 and H3 are all established. R2-R5 remain reportable research
observations.

## 3. Candidate-to-result evidence chain

1. Freeze the task revision, stack, coupon width, port definition, width range
   and acceptance frequency at G0.
2. Record the analytic width seed and predictions before their EM runs.
3. Retain the native layout, substrate definition, port setup, mesh settings
   and solver identity for every candidate.
4. Retain the exact generated simulation input or export, the solver log and
   the native dataset. Confirm that the solved layout matches the intended
   geometry and layer mapping.
5. Bind every extracted metric to a specific dataset and run. Reject stale or
   mismatched data.
6. Keep machine-readable integrity records (relative paths, byte sizes,
   SHA-256) with the evidence. Narrative reports use names, versions, dates and
   file links.
7. Keep the selected candidate's source and dataset unchanged when producing
   derived plots, fits or reports.

## 4. Numerical qualification details

Freeze the following proposed values at G0; record any amendment.

| Item | Proposed requirement |
| --- | --- |
| Frequency sweep | adaptive 0.1-110 GHz plus a discrete checkpoint sweep at 0.1, 1, 10, 40, 65, 80 and 110 GHz on the selected candidate |
| Mesh convergence | final two refinements agree within 2% in Z0 and epsilon_eff and 5% in alpha at 65 and 110 GHz |
| Port sensitivity | report Delta Z0 and Delta alpha at 65/110 GHz for the port calibration/reference-plane alternative; keep the frozen setup for acceptance |
| Layout-width sensitivity | report Delta Z0 and Delta alpha for the 2.0 mm versus 4.0 mm dielectric/top layout |
| Ground representation | report Delta Z0 and Delta alpha for the PERFECT_CONDUCTOR cover and the finite bottom-Au polygon relative to the 4.5 um Au cover |
| Thickness treatment | confirm convergence with the 4.5 um conductor represented by multiple mesh layers or the solver's thick-metal model |
| Adaptive versus discrete | the 110 GHz acceptance value and the 65 GHz checkpoint must come from actual solves or a demonstrated interpolation check |

Do not use a mesh that fails convergence to declare PASS. Unresolved numerical
uncertainty makes the affected criterion INDETERMINATE.

## 5. Data integrity and physical checks

- Retain all complex S entries, frequency units, port order and reference
  impedance.
- For power-normalized real references, check `|S11|^2 + |S21|^2 <= 1` within a
  predeclared numerical tolerance. A lossy line should be strictly below 1.
- Check `S21 = S12` within a predeclared tolerance for the reciprocal
  structure.
- Check that the phase of `S21` is smooth and that the unwrapped phase is
  monotonic over the qualified band except at an explained resonance.
- Check that extracted attenuation is non-negative away from numerical noise.
  Near zero, use an absolute tolerance rather than a relative comparison.
- Missing, nonfinite or inconsistent data is INVALID evidence. A valid S-matrix
  that makes a derived conversion singular is represented by a typed status and
  the underlying values, not by an arbitrary number.
- Any passivity repair, fitting or extrapolation is a separate derived artifact
  with residuals and a declared domain; it cannot silently replace raw EM data.

## 6. Gates

| Gate | Required evidence |
| --- | --- |
| G0: frozen contract | Confirmed stack and loss provenance, coupon width, port/return definition, solver, width range, acceptance frequency, criteria and budget |
| G1: numerical model | Native layout/emSetup, connectivity and dimensional checks, mesh/port/boundary/thickness evidence, runnable baseline |
| G2: design selection | Bounded width search, selected simulated width, H1 result at 110 GHz, band characterization, retained misses |
| G3: qualification and handoff | H2/H3 evidence, port/width/ground/length controls, loss decomposition, fresh reproduction, S2P and stack/port manifest |

Use NOT STARTED / BLOCKED / SATISFIED gate states with an evidence reference.
An unresolved environment or material definition is an input gap, not an
electrical FAIL.

## 7. Result states

| Evidence state | Decision treatment |
| --- | --- |
| Valid, converged, within the frozen contract | Evaluate H1-H3 against the declared limits |
| Missing checkpoint, condition or raw data | INCOMPLETE; never infer PASS from absent data |
| Invalid input, failed solve or corrupt dataset | INVALID; retain the cause and affected checks |
| Unresolved mesh/port/coverage uncertainty | INDETERMINATE; identify the refinement needed |
| Valid result outside H1 | FAIL; preserve the measured value and condition |
| Bounded search with no width meeting H1 | Study may be COMPLETE; the selected-line result is FAIL for the tested range |

Report each criterion's value, frequency, signed margin, uncertainty and state
without display rounding changing the decision. Before the contract freeze,
report results against proposals only.

## 8. Reproduction and retained deliverables

Repeat the selected width in a fresh ADS project or clean rebuild using the
frozen geometry, stack, ports and settings. Compare connectivity, mesh/solver
configuration, complex S2P and extracted metrics under predeclared tolerances.
Proposed reproduction tolerances: Delta Z0 <= 1%, Delta epsilon_eff <= 1%,
Delta alpha <= 3%. Explain generated metadata differences; retain unsuccessful
attempts.

Retain editable source, material/stack definitions with source classification,
port/reference-plane diagrams, solver setup and logs, convergence history, raw
and processed S2P, loss-control runs, extraction code/settings, metric tables
and plots. Store ordinary evidence below the task workspace's ignored
`results/`; use a fresh UTC-named run for each execution and the
[shared layout](../../docs/engineering-workspace-layout.md).

Keep private host paths and restricted material data out of public documents.
Exact file-integrity values belong in machine-readable receipts; narrative
provenance uses names, versions, dates and permitted links.

## 9. Four independent conclusions

Report **study completion** as COMPLETE / INCOMPLETE, **selected-line result**
as PASS / FAIL / INDETERMINATE / INVALID after the contract freeze, **model
integration readiness** with explicit qualified band and gaps, and **full
circuit/filter acceptance** as NOT EVALUATED by this task.

A converged EM result does not establish fabrication accuracy, a connector or
launch model, or measured-material agreement. A model from this assumed stack
is not automatically a qualified process device.
