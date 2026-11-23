---
name: rf-inductor-toolkit-design
description: Design and screen on-chip inductors with RFIC Inductor Toolkit and ADS Momentum, from parametric layout through full-wave EM, L/Q extraction and candidate selection. Use for Toolkit-based physical inductor design, not discrete-coil calculations.
---

# RF Inductor Toolkit Design

Deliver the requested editable inductor, complete EM network and candidate-selection
evidence. Use the destination's task contract, engineering layout and working automation
entrypoints. No particular repository, task name, script name or connection is required.

## Prerequisites and supported execution

- A licensed ADS installation with Momentum and a compatible RFIC Inductor Toolkit,
  on an operating system supported by those installed versions. Use an existing approved
  application/API route; headless and application export capabilities can differ.
- User-supplied, authorized technology and Toolkit dependencies, including physical
  layers, material properties, thicknesses and permitted geometry. This package contains
  no PDK, proprietary generator, simulator or technology-qualified reference design.
- A task contract defining ports/return, excitation, reference planes, frequency coverage,
  target/ranking and the intended screening or qualification decision.

If a dependency is unavailable, complete useful planning or analysis from retained data
and state what remains unperformed. Documentation work and a closed study do not launch
a solver. Execution requires authorization for the requested scope and resource budget.

## Resolve and freeze the task

1. Prefer an explicitly selected existing task/run and its checkpoint over creating a
   new project. Read applicable destination instructions and discover the selected
   profile, engineering root, model bindings and actual execution tools.
2. For a new design, establish target L and reference frequency, required band, stack
   classification, geometry limits, physical return and current deliverables. Distinguish
   a candidate screen from a qualified device model or parent-circuit acceptance.
3. Declare finite candidate, solver and diagnostic budgets, ranking and stop conditions.
   Count failed attempts. Preserve the first useful candidate before widening the search;
   a geometry budget does not authorize unlimited qualification diagnostics.
4. Freeze the task revision, selected workflow/version and required inputs with the run
   using the destination's snapshot and receipt mechanism. Keep private host paths and
   session identifiers in private settings. Check consumer-side input availability before
   native work. Changes to the contract start an amendment or new run, as appropriate.

## Execute the staged chain

Read [the screening and evidence guide](references/screening-evidence.md) for the native
construction, full-wave proof, network reduction and acceptance checks needed at each step.

1. **Build artwork.** Reuse or adapt the selected task's parameterized construction tool;
   otherwise implement against the installed Toolkit/ADS documentation. Retain complete
   geometry, native editable source, pins, EM setup and construction receipt. Use an owned
   dependency copy when edits are needed, preserving the installation and license.
2. **Export and solve.** Validate exported geometry, stack, ports and return before batching.
   Run each case in a fresh output directory and confirm actual full-wave execution from
   consumed solver inputs, logs and raw data. Cached or interpolated samples retain their
   actual status; a successful wrapper exit is not full-wave evidence.
3. **Extract metrics.** Retain the full complex network with ordered ports, reference
   impedance, frequency array and analysis settings. Apply the task's excitation and
   network reduction, preserving signed resistance and reactance. Derive L/Q only where
   the declared interpretation is valid; retain failures and invalid points.
4. **Select candidates.** Rank admissible observations within compatible model groups
   using the frozen target and tie-breaking rules. Write any prediction before a new
   solve; a predicted candidate requires fresh evidence. Do not relabel measurements at
   one frequency as another, relax thresholds or fit material values to hide discrepancies.

One executor owns writes to a native workspace at a time. Preserve other open/unsaved
designs; use independent work areas for concurrent construction. Discover current session
identity rather than reusing historical IDs. A remote tool host is an observed execution
property, not a consequence of where an agent runs.

## Verify, resume and hand off

- Use the destination's phase checks: a valid project skeleton is distinct from native
  readiness and from complete delivery. Independently inspect actual inputs, logs,
  complex data and measurements; structural checks do not establish electrical success.
- Keep each candidate's source-to-export-to-model-to-dataset relationship traceable.
  A selected native candidate must correspond to the network actually analyzed.
- Report execution completion, electrical outcome, model applicability and delivery
  completeness independently, including unperformed checks, limitations and valid
  negative research outcomes. Report reproduction separately when requested.
- Return native source, complete network, geometry/stack/ports, actual L/R/Q at requested
  frequencies, selection rationale and evidence index. Keep exact integrity values in
  machine-readable receipts; narrative reports use names, links and verification outcomes.
- Preserve original evidence and checkpoint the next authorized action. Stop at the
  requested deliverable or budget. Follow-on qualification or parent-circuit integration
  needs its own declared scope, conditions and acceptance evidence.

When delegating, provide the frozen contract/workflow, private binding reference, allowed
changes, target relative paths, budgets, required artifacts and next gate in a brief usable
without the preceding conversation. The receiving reviewer checks the returned artifacts.
