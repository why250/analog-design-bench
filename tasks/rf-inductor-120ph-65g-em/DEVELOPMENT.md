# 120 pH inductor subtask development

**Execution closeout, 2026-10-29:** The user requested an end to further
iteration. Toolkit-driven native geometry generation, six corrected candidate
screens, full-wave EM networks and multiple numerical controls were completed.
The selected candidate gives 121.3788 pH and Q 35.9132 at 65 GHz on an assumed
research stack. Final qualification is incomplete; the device result remains
INDETERMINATE and the parent LPF is NOT EVALUATED. See the workspace
[closeout report](../../workspaces/rf-inductor-120ph-65g-em/docs/closeout.md).
No further optimization, simulation, publication or parent integration is
scheduled by this task. The original planning record below is retained.

**Prepared 2026-10-28; independent revision-1 engineering task.** This package
defines future single-device geometry and EM work. No component result is
claimed by creating its task/workspace files.

## Scope and relationship to the LPF

The user requested a new 0.12 nH inductor subtask without a fixed PDK, then
confirmed single-device geometry/EM, other on-chip platforms or explicit
assumed stacks, and a separate Codex chat for execution. The neutral task ID
`rf-inductor-120ph-65g-em` avoids claiming a particular process implementation.

The parent InP passive-LPF Stage 3 task records that its selected kit has no
catalog inductor. This subtask explores
a custom physical device/model. Parent Stage 1/2 source/evidence and the
Stage 3 no-full-filter-layout/EM boundary remain unchanged. Return a model
for explicit parent evaluation; do not run the full filter implicitly here.

The requested value is exactly 120 pH as the design target, rather than silently
copying the slightly different ideal baseline value. The 65 GHz extraction
reference, +/-5% value window, suggested 10-65 GHz flatness screen and 80 GHz
inductive behavior are initial engineering choices. Freeze/amend them before
acceptance data; no minimum Q or extra SRF margin has been supplied by the user.

## Execution prerequisites and available resources

W0/G0 must select a complete stack, source/assumption classification, reference
conductor, geometry/rules, solver, numerical protocol and target definitions.
PDK independence permits an assumed research stack; it does not make metal or
substrate properties irrelevant. An existing toolkit/demo can accelerate
geometry creation but cannot establish the final device's loss or resonance.

Related installation records report an RFIC Inductor Toolkit geometry demo in
an ADS environment. Treat that as a resource to recheck: the reported geometry
generation is distinct from a verified Momentum loop. Keep machine locations
and connection details in ignored local configuration. Do not alter its demo
or an open parent workspace to create this task's source.

Use [the task-owned workspace](../../workspaces/rf-inductor-120ph-65g-em/README.md)
and [shared layout contract](../../docs/engineering-workspace-layout.md). Reuse
reviewed general helpers without copying an unrelated runner or importing
another live task's tools. Native source belongs in this task's own ads role;
scratch/replay source and evidence belong below fresh results directories.

## Contract and result boundaries

[instruction.md](instruction.md) owns the objective, initial targets and W0-W5;
[model-plan.md](model-plan.md) owns extraction and physical modeling;
[verification-plan.md](verification-plan.md) owns numerical/device/model checks.
The engineering [project manifest](../../workspaces/rf-inductor-120ph-65g-em/project.toml)
owns portable identity and relative paths. Record adopted execution inputs and
later amendments with the run instead of rewriting earlier evidence.

This EM task has no registered shared-runner submission interface. Consequently
task metadata declares no runner artifact rather than pretending a SPICE export
exists. Required engineering deliverables remain explicit in the instruction.
No environment/test/solution placeholder, official score, design-contract hash
instance, frozen-release membership or model-evaluation campaign is created.

A converged EM result supports the declared geometry/material/model conditions.
It does not prove foundry manufacturability or physical measurement accuracy.
A model from another platform can help evaluate a method or circuit diagnostic,
but it is not automatically a replacement for the restricted InP PDK devices. Full LPF acceptance
requires a later authorized integration using compatible physical assumptions.

## Handoff to the execution chat

The new chat should first inspect dirty workspace state and these task sources,
then carry W0-W5 through a bounded design and EM loop. Preserve existing work;
ask only for genuinely missing inputs that cannot be resolved within the
authorized open-platform/assumed-stack scope. Report model gaps and solver
failures transparently. Do not infer a result from a toolkit's numeric estimate.

Source changes are prepared on `codex/rf-inductor-120ph-task`. Existing
uncommitted parent/shared-guide changes are retained. Private integrity receipts
support preservation checks; narrative provenance uses names, versions, dates
and links rather than literal digests.
