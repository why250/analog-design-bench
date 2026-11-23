# Design a 50-ohm thin-film Al2O3 microstrip line and characterize it through 110 GHz

**Revision 1 initial engineering task, prepared 2026-11-19. No geometry or EM
result has been produced by this task specification.**

## Identity and readiness

- Task ID `al2o3-tf-msl-110g-em`, revision 1, stage `em-design`.
- Work type: engineering EM design and characterization. Engineering
  verification is planned; no simulation has been executed.
- Readiness: **Ready for preflight**. The stack, goal, band and ADS route are
  selected. ADS 2027/Momentum availability, the host binding and the
  G0 contract freeze remain pending.
- Formal evaluation: this is an engineering task. It is not registered as an
  official benchmark and has no independent official verifier.
- Solver-visible input is this task package. Private host, session and licensed
  bindings stay in ignored local configuration.

## Objective and authorized scope

Design one uniform gold microstrip line on a 127 um Al2O3 thin film that
presents **50 ohm at the nominal acceptance frequency**, and characterize the
line from 0.1 to 110 GHz. Deliver the selected geometry, its EM evidence and a
portable S-parameter model for later circuit work.

The authorized scope is the single uniform line on the stated coupon: width
selection, EM setup, Momentum simulation, metric extraction and model handoff.
It does not authorize a filter, matching network, taper, airbridge, via fence,
connector or launch redesign, measured-data correlation, or a change to the
user-supplied stack.

## Confirmed design inputs

| Item | Value | Status |
| --- | --- | --- |
| Substrate | Al2O3, 127 um thick, relative permittivity 9.9 | confirmed by user drawing |
| Conductors | Au, 4.5 um thick, top signal line and bottom ground | confirmed by user drawing |
| Ground representation | Full-plane 4.5 um Au cover (solver ground plane) | confirmed by user clarification (2026-11-20) |
| Coupon length | 3.0 mm and 6.0 mm cases | confirmed by user drawing |
| Design goal | Select line width for 50 ohm, then characterize the line | confirmed by user |
| Frequency range | 0.1-110 GHz | confirmed by user |
| Loss assumptions | tan(delta) = 1e-4; sigma(Au) = 4.1e7 S/m; smooth conductor | proposed typical values approved by user |
| Dielectric/top layout transverse width | 2.0 mm nominal | proposed research assumption; the ground is a full-plane cover |
| Nominal acceptance frequency | 110 GHz | confirmed by user (2026-11-19) |
| Environment | ADS 2027 with Momentum on the configured ADS host | confirmed by user |

The dielectric/top-layout transverse width and the provenance of the loss
values are **G0 freeze items**. The 110 GHz acceptance frequency and the
full-plane 4.5 um Au ground cover are user decisions. If the user supplies
measured material data or another acceptance frequency, amend the contract
before acceptance runs and preserve the earlier record.

## Target definition and acceptance

Characteristic impedance, effective permittivity and attenuation are extracted
from the line's two-port S-parameters at the declared reference planes, using
the definitions in [model-plan.md](model-plan.md). The 50 ohm target applies to
the selected uniform line at 110 GHz under the frozen stack and port setup.

| ID | Class | Quantity | Criterion | Conditions and aggregation |
| --- | --- | --- | --- | --- |
| H1 | hard | Z0 at 110 GHz | 47.5-52.5 ohm inclusive (50 ohm +/-5%) | frozen stack, ports and mesh; selected width |
| H2 | hard | Numerical convergence | Final two mesh refinements: <=2% change in Z0 and effective permittivity; <=5% change in attenuation | selected candidate; 110 GHz (acceptance point) and 65 GHz (in-band checkpoint) |
| H3 | hard | Evidence validity | Complete finite S2P; passivity and reciprocity within declared tolerance; no persistent nonphysical negative attenuation | full 0.1-110 GHz band |
| R1 | research | Width search | A documented bounded search selects an actually simulated width meeting H1; report the feasible interval, failed widths and dZ0/dW | width range and budget frozen at G0 |
| R2 | research | In-band impedance | Report Z0(f) over 10-110 GHz and the worst deviation from 50 ohm; proposed screening window 45-55 ohm, adopted or amended at G0 | full band, worst internal point |
| R3 | research | Effective permittivity | Report epsilon_eff(f) and compare with quasi-static and dispersion models; report the deviation and its trend | 1-110 GHz |
| R4 | research | Length scaling | 3 mm and 6 mm coupons give consistent Z0 and epsilon_eff; total attenuation scales with length | selected width |
| R5 | research | Loss decomposition | Report conductor and dielectric attenuation at 65 and 110 GHz; compare with analytic estimates | selected width |
| D1 | diagnostic | S11, S21, group delay, Z0(f), epsilon_eff(f), alpha(f) | Report; no acceptance threshold | full band |
| D2 | diagnostic | DC resistance and low-frequency limit | Report an independent DC/quasi-static estimate; the first EM point is not DC evidence | quasi-static |

R2-R5 inform the engineering conclusion and do not by themselves fail a
candidate unless a later revision makes them hard. A valid negative result
(e.g. no legal width reaches H1) completes the bounded study; it does not
satisfy H1.

## DUT, ports and reference planes

- DUT: one uniform, centered microstrip line on the top of a 127 um Al2O3
  slab, with a full-plane 4.5 um Au ground cover on the bottom. Coupon cases
  are 3.0 mm and 6.0 mm. The top line is the only patterned DUT metal; no
  bottom polygon, launches, connectors, vias, airbridges, tapers or adjacent
  lines belong to the DUT.
- Ordered ports: `rf_in` at the coupon edge `x=0` (port 1) and `rf_out` at
  `x=L` (port 2). Both are microstrip ports with the positive terminal on the
  signal line and the reference terminal on the bottom Au ground cover.
- The physical return is the full-plane 4.5 um Au ground cover (solver ground
  plane), not a finite bottom polygon and not an abstract ideal conductor. The
  2.0 mm width applies to the dielectric/top layout assumption; the ground is
  the solver cover. A finite 2.0/4.0 mm bottom-Au polygon and a
  PERFECT_CONDUCTOR cover are declared controls, not the DUT.
- Reference planes sit at the coupon edges. Any port-discontinuity calibration
  or de-embedding must be declared and identical across candidates and lengths.
  Moving a reference plane changes the reported device.
- Raw S-parameters use 50 ohm reference impedance and port order
  (1 = `rf_in`, 2 = `rf_out`), and retain every complex entry. A scalar Z0 fit
  cannot replace the full two-port.

## Design freedom

| Property or parameter | Policy | Value, range or source | Constraints |
| --- | --- | --- | --- |
| Line width `W` | variable | search 50-300 um; freeze a narrower legal range at G0 | uniform width, centered, minimum-feature check |
| Line length `L` | fixed cases | 3.0 mm and 6.0 mm | spans the full coupon |
| Substrate | fixed | Al2O3, 127 um, er = 9.9, tan(delta) = 1e-4 | user-supplied; no substitution |
| Conductors | fixed | Au, 4.5 um, sigma = 4.1e7 S/m, smooth | top and bottom |
| Topology | fixed | one straight uniform line | no tapers, stubs, matching, airbridges or ground stitching |
| Dielectric/top layout width | fixed assumption | 2.0 mm nominal | sensitivity check on the selected candidate; the ground is a full-plane cover |
| Solver | fixed | ADS 2027 Momentum microwave with thick metal | another solver requires a task amendment |

The executor may choose mesh, port calibration, sweep sampling and extraction
implementation inside this contract. Changing the stack, topology, band, port
definition or acceptance frequency requires a visible contract decision.

## Work packages and learning sequence

| Work package | Required output |
| --- | --- |
| W0: freeze the contract | Confirmed stack and loss provenance, coupon width, port definition, solver, width range, acceptance frequency and budget |
| W1: predict and seed | Hammerstad-Jensen estimate of the 50 ohm width, predicted epsilon_eff and loss, recorded before any EM run |
| W2: establish the EM unit | Native layout/emSetup, substrate and port definition, mesh/boundary checks and a verified runnable baseline |
| W3: bounded width search | Coarse then refined width sweep; selected candidate meeting H1; retained failed widths and dZ0/dW |
| W4: qualify and reproduce | Mesh/port/length/loss controls, band characterization, passivity/reciprocity checks and a fresh rebuild |
| W5: hand off the model | Editable source, complex S2P, stack/port manifest, extraction report and the qualified band with limitations |

Propose an initial budget of at most 11 coarse width points (25 um steps), at
most 10 refinement solves, at most 8 numerical or sensitivity controls, and one
fresh reproduction. Freeze the actual budget and stop rule at G0. A finite
unsuccessful search does not prove that no legal width exists.

## Deliverables and separate conclusions

Deliver editable ADS source (`MSL_R01_lib` under the task workspace), the
substrate and port definition, the selected geometry, solver settings and logs,
raw complex S2P for every retained case, the Z0/epsilon_eff/alpha extraction,
band and loss plots, mesh/port/length controls, a DC/low-frequency estimate and
a reproduction report. Include a stack and port manifest with exact reference
planes and units.

Report separately:

- engineering completion: COMPLETE / INCOMPLETE;
- selected-line result against H1-H3: PASS / FAIL / INDETERMINATE / INVALID
  after the contract freeze;
- model integration readiness, with its qualified band and limitations;
- full-circuit or filter acceptance: **NOT EVALUATED** by this task.

A converged EM result supports the declared geometry, stack, ports and solver
conditions only. It does not establish fabrication accuracy, connector or
launch performance, or agreement with a measured material.

Use [verification-plan.md](verification-plan.md) for acceptance and
[DEVELOPMENT.md](DEVELOPMENT.md) for scope, provenance and environment status.
Exact integrity values belong in machine-readable receipts, not narrative
documents. Private paths and host/session configuration stay in ignored local
records.
