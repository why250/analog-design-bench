# InP bonding wire / chip-on-board modeling feasibility

**Task ID:** `inp-bondwire-cob-modeling-feasibility`  
**Revision:** 1  
**Status:** Draft; no execution readiness is asserted.  
**Engineering kind and stage:** Feasibility; exploratory interconnect modeling.  
**EDA / workflow:** Keysight ADS; `ads-generic`, version 1.2 in the workflow
catalog used for this draft. Recheck and freeze the actual selected workflow
at execution. The [verification plan](verification-plan.md) defines the evidence
and decisions for this task.

## Objective and scope

Investigate the physics, available ADS modeling approaches, numerical validity
and bounded sensitivity of an InP bare-die to substrate bonding-wire RF
interconnect. Produce reproducible simplified and EM models and evidence for a
future engineering decision, subject to the stage gates below. The intended
decision is which modeling approaches and assumptions merit follow-up, including
their demonstrated limits; feasibility is conditional on those assumptions.
This is not a complete package design, manufacturing qualification, product
optimization, or a claim that a real InP process meets any performance target.

## Specification states

**Confirmed by the user**

- An exploratory feasibility study, with the initial research frequency range
  of 1–110 GHz, not a guaranteed broadband model validity range.
- Initial single-ended signal interconnect with an explicitly modeled complete
  return path, and a generic/idealized ceramic substrate for the first baseline.
- Compare lumped equivalent-circuit and suitable 3D EM representations;
  investigate wire, pad, substrate, return path, and S-parameter sensitivity.
- No arbitrary product S11 or S21 pass limits; distinguish research completion,
  model validity, electrical performance and formal benchmark acceptance.
- This request authorizes task definition only. It does not authorize starting
  an ADS process, simulation, workspace changes, benchmark registration or GUI
  operation. Learning Mode is optional and not active for task authoring.

**Proposed, not confirmed**

- Start with one signal bond, nearby explicit ground bond(s), die and substrate
  pads and a continuous ground return. A physically connected return and
  documented conductor geometry must be established before use as a baseline.
- Use equal real 50-ohm reference impedances as a comparison convention if
  suitable, subject to later confirmation. These values are not device specs.
- Use generic, fully disclosed idealized geometry and material constants with
  units and provenance. Avoid representing them as InP PDK or manufacturer data.
- Use a low-cost, staged frequency and mesh plan, followed by targeted refinement;
  the declared 1–110 GHz domain does not authorize a full-band dense EM sweep.
- Compare PCB and ceramic only after the baseline is credible, with separately
  justified material assumptions and an approved bounded experiment plan.

**Investigate before the affected work**

| Topic | Resolution and evidence | Disposition if unresolved |
| --- | --- | --- |
| Actual ADS release, documentation, supported wire/geometry/solver, license and Python/MCP capabilities | Inspect version-matched official documentation and the authorized environment; retain references and observed capabilities | Keep that operation pending; document a viable alternative without inventing an API or result |
| Pad dimensions, materials, die thickness/stack, wire material, diameter, length, loop and bond geometry | Obtain authorized process or packaging data, or explicitly choose generic study values with source, units and ranges | Restrict conclusions to idealized assumptions; do not claim manufacturing or InP qualification |
| Ceramic stack, dielectric and conductor parameters, return geometry and ground connections | Define complete geometry, material frequency dependence and sources in the model manifest | Invalid baseline if physical return is absent or materially undefined |
| Ordered ports, modes, impedance, excitation and reference planes; any fixture and de-embedding | Agree and diagram the port-to-return connections and matched comparison planes | No comparison or S-parameter conclusion until defined |
| Frequency points, refinement, numerical tolerances, solver budget and sensitivity cases | Propose a bounded plan, justify resolution and obtain scope authorization before costly computation | No solver run or full-band coverage claim |
| Multiple-wire coupling and manufacturing limits | Obtain application-specific constraints and decide whether a later extension is needed | Leave outside baseline; report not investigated |

## Model and interface requirements

The baseline DUT is the passive interconnect between die-side and substrate-side
signal reference planes, including explicitly defined pads, signal wire and
the physical conductors and dielectric needed to close its return. Its exact
3D boundary is an investigation item, not an assumed representation of the
whole chip or package. Record every excluded structure. No active die model,
bias supply, package enclosure, or process model is assumed. The bench owns
linear small-signal excitations, reference impedances, frequency sampling and
any explicitly documented fixtures; document their ground/return connections.
The ordered two-port interface is port 1 at the die side, port 2 at the
substrate side, with the associated return terminal(s), reference planes, port
polarity and modal definitions documented before simulation. Define how the
EM port and circuit model represent the same physical interface; do not infer
agreement from differently normalized or de-embedded data.

The circuit model must state component topology, derivation, parameter units,
frequency dependence, reference geometry, parasitic attribution and intended
validity range. A series wire inductance alone does not describe its return or
pad parasitics. The EM model must state geometry, conductor and dielectric
models, boundary and radiation conditions, ports, meshing and convergence
controls. Record all assumptions and data provenance; no specific ADS feature
or API is asserted available until verified against the installed release.

## Ordered research stages and gates

1. **Theory and simplified model.** Review suitable sources; derive or cite
   applicable approximations for loop inductance, pad capacitance, conductor
   loss and mismatch. Describe parameter trends, underlying assumptions,
   expected frequency limits and a proposed equivalent circuit. A conceptual
   model may be completed without ADS. Gate: reviewed derivation, assumptions,
   return topology and a bounded proposal for the next stage.
2. **ADS method investigation.** Check actual-version official documentation
   and authorized capabilities for bondwire models, geometry, FEM and Momentum
   applicability, ports, reference planes, substrate, boundaries, meshing,
   convergence, S extraction and available automation. Distinguish documented
   capability from observed capability and inference; record unavailable
   features, reasons and alternatives. Gate: method choice and prerequisites
   supported by evidence; no presumption that either solver can represent the
   required wire or return adequately.
3. **Baseline model and verification.** After scope, environment and budget
   authorization, construct the simple equivalent circuit and an appropriate
   EM model with the same interface. Record S11, S21, S12, S22 and input
   impedance; extract equivalent parameters only with their fitting method and
   valid range. Perform physical, numerical and reproducibility checks in the
   verification plan. Record failure or indeterminate outcomes and the next
   diagnostic action; neither permits entry to Stage 4. The Stage 4 entry gate
   requires a credible baseline with its validated conditions and coverage stated.
4. **Bounded sensitivity study.** Only after the credible-baseline entry gate
   and a reviewed, authorized case budget, select a small subset of wire length, loop height,
   diameter, return arrangement, multiple wires and substrate changes. Define
   values, fixed variables, sample points and predictions before each case.
   Compare trends and limitations; do not claim unsampled global optimum or
   manufacturing feasibility. All extensions are optional until selected.

## Execution readiness, budget and stop rules

Draft status remains until the next work package has a confirmed scope,
acceptance, interface, inputs, evidence and bounded resource plan. The theory
work package can be separately authorized without committing to simulation.
Before native work, use the project environment planner and ADS workflow,
freeze the task and workflow, allocate a fresh run, prepare a delegation brief
and perform the relevant scaffold and actual readiness checks. Select the
existing environment rather than inventing one; verify configuration, transport,
documentation, session, workspace, models and licenses separately. Actual
version, tool access and all checks are pending. Keep private bindings private.

The profile declares the full eventual source, circuit simulation and EM
delivery scope; it is not a command to run all stages. Later engineering runs
must preserve the profile's required deliverables; a partial run does not close
as a complete full-scope delivery. Define a bounded authorized work package for
each later execution in accordance with the project workflow. No case count, runtime,
license use, mesh refinement or solver budget is approved here. Stop before
native work if authorization, return/interface, capability, model provenance,
resource ceiling or required inputs are missing. Stop and retain evidence if
the bound is exceeded, a check fails, or tool/model behavior is inconsistent;
review the next action before expanding scope. Do not turn a failed or missing
simulation into a performance conclusion.

## Future artifacts and handoff

Retain theory and source references, a parameter/assumption manifest, circuit
and EM native sources and settings, exact consumed source and input inventory,
logs, raw data, complex S-parameter exports, analysis, convergence/physical
checks, comparisons and a reproduction procedure for each authorized stage.
Preserve failures and coverage gaps. Upon later execution use the stable
`workspaces/inp-bondwire-cob-modeling-feasibility/` and its run-specific results
as required by the repository; no workspace or result is created by this task.
Record engineering, model, electrical and delivery conclusions independently.
Formal benchmark registration and independent benchmark verification are outside
the request and no benchmark acceptance is claimed.

After explicit user activation, the existing `engineering-learning` overlay may
explain decisions, cite documentation, record predictions before simulation,
compare observations and preserve learning notes under the task workspace. It
does not change this contract, its checks or the authorized scope.
