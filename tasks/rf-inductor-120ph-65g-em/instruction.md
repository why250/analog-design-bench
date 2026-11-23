# Design one 120 pH RF inductor for the 65 GHz LPF

**Revision 1 initial engineering task, prepared 2026-10-28. No geometry or EM
result has been produced by this task specification.**

## Objective and authorized scope

Design a physical on-chip passive inductor with target **0.12 nH = 120 pH**,
characterize it electromagnetically, and deliver a reproducible network model
that can be evaluated in the parent 65 GHz low-pass filter.

The user authorized single-device geometry and EM simulation, permits other
on-chip processes or explicitly labeled assumed stacks, and requested an
independent Codex chat to execute this subtask. No particular PDK is required.
This is not a PCB/discrete-inductor task and is not an active-inductor design.

The parent PDK-aware LPF task records a missing-inductor disposition.
This subtask may supply a newly designed model without asserting that an
existing PDK contains an inductor. Its local geometry/EM scope does not authorize
full-filter layout/EM, reopening Stage 2 or changing parent electrical limits.

## Target definition and research acceptance

Use the complete device's end-to-end effective series inductance under the
current-constrained excitation in [model-plan.md](model-plan.md), with
`I1=I, I2=-I` and common-mode current zero. The 120 pH target applies to the
whole device, not to each leg or half of a symmetric structure.

The reference frequency of 65 GHz and the numerical windows below are initial
engineering choices derived from the filter context; they are not foundry data
or additional user-specified system limits. Adopt or explicitly amend them at
G0 before acceptance runs. Preserve previous records when making an amendment.
The execution owner may adopt these initial engineering defaults at G0 within
the authorized scope; a separate permission round is not required. Record the
adopted contract before accepting candidate results, and ask only when a
material user-intent conflict or genuinely unavailable input prevents progress.

| Quantity | Initial research target / treatment |
| --- | --- |
| Effective inductance at 65 GHz | 120 pH +/-5%, inclusive: 114-126 pH |
| Inductance variation over 10-65 GHz | Suggested screening window 108-132 pH (+/-10% of target); report actual worst deviation |
| Behavior at 80 GHz | Remain inductive in the declared mode; characterize beyond it within the qualified simulation range to locate resonance |
| Q / loss | Report Q(f), Q at 65/80 GHz, real impedance and dissipation; optimize the loss/inductance tradeoff, with no invented minimum Q |
| Self-resonance | Report the first applicable crossing/mode and the tested range; no arbitrary SRF margin is a user requirement |
| Area / geometry | Report actual bounds, metal dimensions and legal/assumed rules; no unrequested area cap |
| DC / low-frequency path | Retain a conductive through-path and supported resistance/low-frequency evidence for model handoff |

The 10 GHz screening start does not remove the parent's DC-65 GHz requirement.
Below that point, separately characterize the device and document the network
model's valid low-frequency extension. Passing the scalar inductance target
does not establish sufficiently low loss for the complete filter.

## Stack, geometry and model inputs

Select and freeze one initial stack before geometry optimization. Every metal,
dielectric, substrate, conductivity, thickness, loss, roughness and return
assumption needs units, a source and a classification: supplier-backed,
published/open reference, or explicit research assumption. Do not invent a
foundry qualification. An assumed-stack EM result is valid only under that stack.

Prefer a simple straight/short-path, hairpin or single-turn loop candidate before
adding multi-turn structures. Choose based on 120 pH, loss, return path, area
and resonant behavior, not on a visually familiar spiral. A geometry generator
or analytic estimate supplies candidates; it is not the final EM result.

ADS Momentum is a preferred available workflow to verify, not a required PDK.
Check the actual solver/license, model setup and API support before use. Another
suitable solver may be selected with its environment and equivalent evidence
recorded. Use current supported tool documentation when implementing automation.

RFIC Inductor Toolkit may be used as an optional candidate generator after
checking installation, supported geometry and licensing. Existing demo geometry
generation does not establish a working EM optimization loop or 65 GHz validity.
Do not copy another project's whole source or depend on a live checkout for handoff.

## DUT, ports and reference planes

Use two signal terminals, provisionally `p` and `n`, with a documented physical
reference conductor/return and substrate environment. Native/EM port count is
determined by the actual structure; preserve additional shield/return ports
when they carry independent behavior. Freeze port numbering, current direction,
impedance convention and all external terminations before extraction.

Retain the complete N-port network. A scalar L/Q fit cannot replace substrate
or common-mode paths. Distinguish a floating-current extraction, a grounded
terminal test and the actual series-arm excitation in the filter. Reference
planes lie at declared device terminals; separately retain raw fixture data
and any justified de-embedding. No unrequested measurement pads are added.

## Work packages and learning sequence

| Work package | Required output |
| --- | --- |
| W0: freeze the research contract | Selected stack, solver, geometry limits, ports, target definition and adopted tolerances |
| W1: predict and seed | Physical reasoning, analytic estimates and up to three simple candidate geometry families |
| W2: establish the EM unit | Native geometry, real return, material/boundary/port settings and a verified runnable baseline |
| W3: bounded optimization | Legal geometry search, retained failed candidates and L/Q/resonance/area tradeoffs |
| W4: qualify and reproduce | Mesh/port/boundary checks, band/DC evidence, complete network and fresh rebuild |
| W5: hand off the model | Editable source, Touchstone, port/stack manifest, extraction report and parent-integration limitations |

Propose an initial budget of up to three families with three seed settings each,
then up to 30 additional geometry evaluations for the most promising families.
Mesh/port refinement and final independent repetitions are additional numerical
checks. Freeze the actual budget and stopping rule at W0; record any justified
extension rather than silently discarding failed attempts.

Use **Question -> Physical Model -> Prediction -> EM Simulation -> Observation
-> Explanation -> Design Decision**. Explain why geometry changes alter both
inductance and loss/parasitics. Retain predictions before their corresponding
simulations and distinguish optimizer cost from final acceptance.

## Deliverables and separate conclusions

Deliver editable geometry, the selected stack/material table, ports/returns and
reference planes, solver/settings/mesh history, raw results, full complex Snp,
extraction code/definitions, L/Q/impedance/resonance plots, DC evidence, retained
candidate comparisons and a fresh-workspace reproduction report. Retain enough
source and allowed dependencies to reproduce without another live workspace.

Report separately: engineering completion; adopted device-target results;
network-model readiness; and parent-filter acceptance. The latter remains
NOT EVALUATED until an explicit parent integration run. A non-InP or assumed
stack model may be used in a clearly labeled diagnostic comparison; it cannot
be relabeled as a validated InP device. Physical migration requires replacing
the stack/material/return assumptions and re-verifying the geometry/network.

Use the [verification plan](verification-plan.md) for acceptance and the
[development record](DEVELOPMENT.md) for scope/provenance. Exact integrity values
belong in machine-readable receipts, not narrative documents. Private paths,
licensed models and host/session configuration stay in ignored local records.
