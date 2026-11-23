# Stage 2: nonideal LC modeling and sensitivity for the 65 GHz LPF

**Status: draft engineering specification, revision 1; study not executed;
unregistered; no official benchmark verifier or score.**

## Design objective

Determine how loss, self-resonance and component perturbations limit the
completed nine-pole Chebyshev-I ladder, and produce a reproducible conditional
feasibility envelope for later InP PDK selection. Preserve its five series
inductor arms and four shunt capacitor arms. Additional reactive elements inside
device models can introduce additional modes; "nine-pole" identifies the ideal
prototype, not the order of every nonideal transfer function.

The fixed source is task `inp-passive-lpf-65g-50ohm-80g-stop20-r2`. Its pinned
source identity is retained in the [project manifest](../../workspaces/inp-passive-lpf-65g-nonideal-lc-feasibility/project.toml). See the
[baseline workspace](../../workspaces/inp-lpf/README.md) and
[learning notes](../../workspaces/inp-lpf/design-learning-notes.md). This is a
disclosed-baseline engineering study, not a blind solver evaluation.

User-confirmed scope: sensitivity and feasibility are required; same-topology
retuning is optional. No authorized InP device data is currently available;
all Stage 2 scan coordinates are synthetic research assumptions. Their values
and the proposed numerical research tolerances remain reviewable draft choices.

## Electrical specification

These system requirements are unchanged. Evaluate each complete candidate
separately; a completed study does not imply that any candidate passes.

| Quantity | Requirement | Measurement boundary |
| --- | --- | --- |
| Reference impedance | Real 50 ohm at both ports | Bare DUT terminals, common reference ground |
| Input match | dB(S11) < -20 dB | Entire DC through 65 GHz band, inclusive endpoints |
| Output match | dB(S22) < -20 dB | Entire DC through 65 GHz band, inclusive endpoints |
| Insertion loss | IL = -dB(S21) < 1 dB | Entire DC through 65 GHz band, inclusive endpoints |
| Stop checkpoint | dB(S21) <= -20 dB | Exactly 80 GHz |

Here dB(Sij) = 20 log10(abs(Sij)). The 65 GHz value is a passband
edge, not a -3 dB cutoff. There is no continuous stopband threshold.
The 80-120 GHz response is diagnostic. DC is evaluated by the actual model's
zero-frequency limit, not by claiming a zero-Hz ADS S-parameter simulation.
The [measurement plan](verification-plan.md) owns the detailed expressions,
coverage, numerical uncertainty and result states.

## Fixed topology and DUT interface

```text
rfin -- L1 -- n1 -- L2 -- n2 -- L3 -- n3 -- L4 -- n4 -- L5 -- rfout
             |           |           |           |
             C1          C2          C3          C4
             |           |           |           |
gnd ---------+-----------+-----------+-----------+
```

Each label above denotes a two-terminal device model, not necessarily one ideal
element. In particular, an inductor's Cp spans that series arm's two terminals.

| Element group | Baseline value, rounded for display |
| --- | ---: |
| L1, L5 | 120.674157213694 pH |
| L2, L4 | 238.891907001535 pH |
| L3 | 249.182172842647 pH |
| C1, C4 | 71.5588254888531 fF |
| C2, C3 | 82.6663847152029 fF |

Use full-precision values from the pinned baseline synthesis/input snapshot.
Record actual per-element values, including mirrored rounding, in each case.

The native DUT has ordered terminals **rfin, rfout, gnd**, all inout; ports 1
and 2 are the RF signal terminals and terminal 3 is their return. Preserve the
logical future SPICE signature `.subckt inp_lpf rfin rfout gnd`; no verified
ADS-to-SPICE export or runnable SPICE submission is claimed. Use a separate
Stage 2 workspace/library namespace, proposed `inp_lpf_stage2_lib` with DUT
cell `inp_lpf` and bench cell `inp_lpf_sp`. The symbol has three terminals;
the S-parameter testbench has two RF ports.

## Allowed components and models

- Mandatory: positive finite ideal L/C primitives with explicit nonnegative
  resistive loss and nonnegative parasitics, following [model-plan.md](model-plan.md).
  Recover the ideal anchor by removing/bypassing zero-valued parasitic branches.
- Inductor: series Rs + L, in parallel with terminal-to-terminal Cp. Fixed Rs
  is parameterized by an RL-branch Q at **65 GHz**, not constant terminal Q.
- Capacitor: series ESR + ESL + C from the ladder node to gnd. ESR/ESL are
  separate variables. Optional leakage/additional shunts require the declared
  connections and separate evidence in the model plan.
- Frequency-dependent loss is an optional, explicitly bounded diagnostic model;
  it must not replace the required fixed-coefficient RLC study or imply a PDK fit.
- No internal 50-ohm loads, absorptive matching pads, active devices, negative
  resistance, gain, added cross-coupling, new filter arms or dedicated
  zero-generating branches. Resonances and transmission zeros arising naturally
  from the declared device parasitics are allowed and must be analyzed.
  Elliptic and stepped-impedance alternatives are possible future decisions,
  not required implementations in this task.

## Testbench and simulation conditions

Use an ADS small-signal linear two-port SP bench with external Term1/Term2,
each 50 ohm, and ideal testbench ground tied to the DUT's gnd terminal. Place
reference planes at rfin/rfout without pads or de-embedding. Retain the native
DUT, symbol, bench and schematic-generated netlist separately.

Use 1 MHz-120 GHz diagnostics plus a <=50 MHz passband grid, exact 65/80 GHz
points, model-specific low-frequency bounds and adaptive extrema searches as
defined in [verification-plan.md](verification-plan.md). Ideal peak locations
are seeds only for the nonideal cases. One nominal bookkeeping temperature of
25 degC, no bias, no process/corner/mismatch sweep, no noise or large-signal
analysis is proposed. Fixed model coefficients have no temperature law; this
does not establish physical operation at 25 degC or any temperature range.

## Design procedure

Follow **Question -> Physical Model -> Prediction -> ADS Simulation ->
Observation -> Explanation -> Design Decision** for each experiment family.

1. Audit baseline provenance and evidence; recover it in an isolated Stage 2
   namespace before adding nonidealities. Preserve original files and outputs.
2. Validate isolated device models and predict their impedance/Q/SRF and DC limits.
3. Run the required single-effect and targeted-device experiments with baseline
   nominal values fixed. Explain the dominant physical changes before combining them.
4. Perturb each L/C separately, then evaluate deterministic combined conditions.
   Never label a synthetic perturbation as a manufacturing tolerance or yield.
5. Map conditional boundaries, dominant devices, shifted reflection extrema,
   actual rational-network poles and parasitic resonances. Resolve numerical
   ambiguity before drawing feasibility conclusions.
6. Rebuild selected cases independently and retain evidence. Optionally retune
   within the same topology, after freezing the untuned study and documenting
   parameter bounds and the loss/parasitic co-variation policy.
7. Recommend a PDK-data request and either map this topology to PDK models or
   start a separately scoped topology comparison, supported by the measured envelope.

The [experiment plan](experiment-plan.md) defines ten required work packages,
explicit axes and evidence. Optional optimization cannot replace them.

## Measurement and acceptance

Report three separate conclusions:

1. **Study completion:** COMPLETE / INCOMPLETE, based on the evidence and
   reproducibility checklist. A well-supported infeasibility result can complete
   the study; unresolved mandatory numerical failures cannot.
2. **Per-candidate electrical status:** PASS / FAIL / INDETERMINATE / INVALID,
   under the unchanged system specification and declared model. A positive
   result is conditional circuit feasibility under synthetic coefficients.
3. **PDK readiness:** READY FOR DATA MAPPING / TOPOLOGY REVIEW REQUIRED /
   NOT READY, with the missing evidence/data and next action.

There is no weighted score, partial-credit reward or official acceptance claim.
Keep individual metric failures visible even when the study completes.

## Required deliverables

| Deliverable | Required content |
| --- | --- |
| Model specification | Equivalent circuits, units, independent/derived variables, Q reference frequency, validity limits and physical predictions |
| Parameter manifest | Deterministic case IDs, parent experiment, full per-element SI values, synthetic provenance, frozen-coefficient policy and source hashes |
| Editable engineering source | Separate ADS DUT/symbol/bench, reconstruction and nonideal analysis entrypoints; no modification of baseline views |
| Per-case evidence | Raw ADS dataset/log, generated netlist, source/settings snapshots, complex four-S CSV, 50-ohm Touchstone, metrics and coverage/cross-check status |
| Analysis | Baseline overlays, loss/absorption curves, sensitivity ranks, combined feasibility maps, boundary intervals, central-inductor impedance/Q/SRF, poles versus response peaks |
| Learning record | Prediction recorded before simulation, observations with run references, physical explanation, decision and unresolved questions for each family |
| Reproduction and handoff | Fresh-workspace repetitions, frequency/S/netlist comparisons and hash manifest; selected portable source/evidence bundle |
| Stage decision | Separate study/electrical/PDK-readiness conclusions and prioritized PDK data requirements |

Ordinary Stage 2 outputs belong under the existing ignored
`workspaces/inp-lpf/results/stage2-<UTC-run-id>/`. Future editable Stage 2
sources belong in a separate subtree such as `workspaces/inp-lpf/stage2/`;
these sources and commands are not implemented by this draft. Keep private
models, machine paths, authorizations and tool-session details out of Git.

## Assumptions, limitations and open questions

| Class | Current position |
| --- | --- |
| Confirmed system specification | Four unchanged electrical limits, 50-ohm ports, fixed Stage 1 baseline |
| Confirmed stage boundary | Required sensitivity/feasibility; optional same-topology retuning; synthetic scans without PDK data |
| Proposed research choices | Numeric scan axes, refinement tolerances, bookkeeping temperature, optional retuning bounds and case budget |
| Temporary model assumptions | Lumped uncoupled RLC, constant coefficients, ideal return, independent parameter control; no geometry or broadband accuracy claim |
| PDK-dependent unknowns | Achievable L/C, Q(f), DCR/R(f), terminal SRF, substrate/metal loss, MIM density/ESR/ESL, return-path inductance, coupling, corners and model validity |

Stage 3 must resolve component availability and calibrated frequency behavior
before claiming InP feasibility. Layout/EM is Stage 4; corner/robustness
verification is Stage 5. Stage 2 perturbations do not substitute for either.
See [DEVELOPMENT.md](DEVELOPMENT.md) for the organization decision, audit,
workflow reuse and outstanding review items.
