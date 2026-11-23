# Standalone analog task packages

Use this guide when a target project has no task-authoring conventions, or use
it to fill gaps without replacing conventions that do exist. Every essential
template and reference is bundled with this skill. Task creation requires no
particular repository, project document, runner, or EDA connector.

## Discover conventions without assuming a framework

Read applicable host/project instructions and any task conventions identified by
the user or visible in the selected project. Inspect relevant existing examples
when available. Treat their naming, metadata, and verification interfaces as
local choices, not universal requirements. Avoid copying an unrelated task's
thresholds, source circuits, model assumptions, or reserved submission interface.

When there is no established format, adopt the small default below as an ordinary
authoring choice. Explain it briefly; do not ask the user to invent a framework
before their task can be written. Use the user's requested destination instead
if specified.

```text
tasks/<task-id>/
  instruction.md          # Identity, requirements, inputs and deliverables
  verification-plan.md    # Measurements, evidence and decision rules
```

Start from [the task brief](../assets/task-brief.md) and
[the verification plan](../assets/verification-plan.md). For a small task, their
content can share a single document when that improves usability. A separate
decision record is useful only when decisions or amendments actually need one.
Do not create empty circuit files, fake benches, reference results, or unused
directories merely to make a package look complete.

## Minimum contract and authority

Keep one authoritative location for each requirement. In the standalone default,
the brief owns identity, scope, criteria and current artifact obligations; the
verification plan owns how those criteria will be measured and evidenced. Resolve
contradictions before the affected work starts. Record the task ID, positive
revision, task kind and readiness explicitly in the brief. Revision 1 is a
reasonable initial default for a genuinely new task without another convention.

Use stable IDs to connect hard criteria, research obligations, diagnostic outputs,
condition sets, measurements, evidence and conclusions. Distinguish confirmed
decisions, proposed defaults and unknowns assigned to investigation. Make design
freedom, budgets, stage gates and the treatment of unresolved items explicit.

A structured Markdown package is sufficient when no metadata consumer exists.
Do not manufacture a TOML/JSON schema or imply compatibility with an absent
runner. If the project provides a machine-readable format, use its supported
fields and validation. Keep current native-source obligations separate from
future submission or export interfaces.

## Native work and results

Declare where future editable source, analysis inputs and evidence will live.
When there is no existing layout, a task-relative `source/` and ignored `results/`
are reasonable defaults. They describe future execution output; creating the
task does not mean a candidate or its results already exist. A separate stable
engineering workspace is optional unless selected assets or project rules need it.

Use task-relative paths for portable assets and resolve them from a documented
package root, independently of the caller's working directory. Keep repeated
runs in fresh named result directories. State how selected parameters or a native
source snapshot relate to the actual consumed simulation input and raw data.
Only introduce a manifest when an existing consumer or reproducibility need
justifies it; do not assume a particular manifest filename or native EDA layout.

## Environment with or without an existing profile

Use [the EDA environment contract](eda-environments.md) and
[the EDA companion handoff](eda-companions.md). Discover a companion only for
the selected software; its product-specific work is owned by that companion
when available. Existing connection profiles can be referenced after inspection.
If no profile or companion exists, document needed capabilities and missing
binding fields, assign setup/preflight work, and leave readiness pending.
Environment setup and task authoring are distinct operations.

Keep actual hosts, installation roots, credentials and restricted model paths in
a suitable private settings location. Use an existing local mechanism when one
exists; otherwise agree on a local, excluded settings file only if it is needed.
Do not force a particular hidden directory or include private bindings in the
portable task to make it appear self-contained. A documented user-performed
workflow is valid when automation is unavailable.

## Handoff without a runner or verifier

Check internal references, identity, units, predicates, coverage, stage gates,
current outputs and unresolved items directly against the authored documents.
State which checks were performed. A written measurement plan is not an
implemented verifier, and a task can be ready for preflight without a simulator
being accessible to its author.

Engineering tasks do not need benchmark registration or an independent official
verifier to be well-defined. State their verification scope and evidence status
explicitly: task creation plans engineering milestone verification; later results
may establish it only for the recorded candidate, models, conditions and coverage.
Retain conditional conclusions when model or numerical limits remain unresolved.
When checked for that task/version, state that it is not registered as an official
benchmark and no independent official verifier is implemented. If formal status
was not assessed or is outside scope, say so. Do not infer the status of a task
from the repository name, this skill's contents, or another task's verifier.

For a blind evaluation, separate executor-visible material from reference
answers and private checks. For formal benchmark authoring, identify the actual
starter, execution, verification and reference-evidence work still required.
Never claim registration, independent acceptance, reference feasibility or
electrical results on the basis of a completed task document.
