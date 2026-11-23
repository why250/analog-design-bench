---
name: create-analog-design-task
description: Create or refine structured analog, RF, and mixed-signal circuit design, reproduction, or feasibility tasks. Read project conventions, progressively clarify requirements, define EDA and model prerequisites, and write a task package with explicit acceptance and evidence. Use for task authoring, not for executing an existing circuit task or registering a benchmark.
---

# Create Analog Design Task

Turn a circuit requirement into a task another engineer or LLM can execute
without the preceding conversation. Keep the workflow independent of any EDA
vendor. The output is a task package and its readiness assessment.

Default to engineering task authoring. Formal benchmark work is a separate mode
when explicitly requested or when maintaining an identified existing benchmark
contract. This skill supplies authoring guidance and measurement plans; it does
not itself provide an official runner/verifier or establish electrical results.

## Prerequisites and support

Authoring works on any host that can read and write the chosen task documents; no
particular repository, EDA installation, MCP connection or official verifier is required.
The user supplies the design goal and authorized technology/model references. Execution
uses separately available software and dependencies, whose supported versions and access
requirements must be recorded rather than bundled or presumed. Verify authored packages
with the destination's applicable checks and the handoff checks below.

## Discover the target project

- Use the user's target project and scope. Read applicable instructions and
  relevant task, workspace, environment, and verification conventions that
  actually exist. A repository, a particular guide filename, and an established
  task framework are not prerequisites. Inspect only relevant configuration.
- Select the intended engineering kind: new design, baseline reproduction or
  feasibility study, using formal benchmark mode only as described above.
  Record the design stage and intended
  decision. A completed study can conclude that no tested candidate meets its
  targets; define this separately from candidate acceptance.
- Reuse supported formats and entrypoints when the target project defines them.
  Otherwise use [the self-contained package guide](references/task-packages.md)
  to create a small standalone task. Do not require another project's docs,
  metadata schema, directory layout, runner, or verifier. Original requirements
  and implemented verifiers retain their authority; an index or template does
  not create a competing scoring contract.
- Prefer an explicitly identified task, workspace or run and its recorded workflow
  over choosing a new route from keywords. For a new task, record the selected EDA,
  engineering kind, stage, workflow/version and current deliverables using the
  destination's supported fields. Load only relevant software and domain procedures.
  A reserved software route supports a draft; it does not establish execution support.
- For a blind evaluation, inspect permitted interfaces and operator conventions
  without importing reference answers or hidden verifier material into the
  solver package. Record whether the starting design is disclosed.

## Build a draft and clarify consequential gaps

When a project separates a design into tasks, plan the task sequence before
writing the first executable package. Split at decisions that change scope,
design freedom, or acceptance evidence. Give each task its own contract and
state which reviewed upstream artifacts it consumes. Draft later tasks with
named prerequisites when an upstream choice is open. Keep routine execution
steps within their task and freeze each selected handoff before downstream work.

Produce a compact first draft once the goal, stage, principal inputs, and intended
deliverables are understood. Keep one evolving draft rather than independent
versions of the same requirements. For material statements distinguish:

| State | Treatment |
| --- | --- |
| Confirmed | Cite the user decision or authoritative project source. |
| Proposed | Explain the recommendation and its effect; do not label it confirmed. |
| Investigate | Assign a discovery action, completion evidence, and a disposition if unresolved. |

Ask only questions that change scope, success, implementation freedom, resource
use, or handoff. Usually group one to three key decisions per round and offer
reasoned choices. Follow a user who provides complete requirements without
forcing a questionnaire. Explain electrical ambiguities such as passband edge
versus cutoff, single-point versus band-wide targets, load ownership, and nominal
versus statistical coverage only when applicable.

Use routine project defaults for naming and formatting, or the bundled package
guide when none exist. Unknown model availability,
achievable loss, or environmental capability may be the subject of the study;
turn these into investigation work rather than requiring the answer in advance.
Resolve blocking ambiguity about the engineering goal or unauthorized changes
before labeling the task executable. Preserve a draft with explicit prerequisites
when the user cannot yet resolve them.

## Complete the execution contract

Use [the task brief](assets/task-brief.md) and
[the verification plan](assets/verification-plan.md) as adaptable authoring
templates. Keep applicable sections, replace drafting markers, and give omitted
requirements an explicit disposition when their absence matters. These Markdown
templates are not a runner schema. Link each requirement to its measurement,
conditions, evidence, and decision rule.

Pay particular attention to:

- Hard acceptance criteria, exploration outputs, and diagnostics as distinct
  categories; preserve units, strict boundaries, ranges, aggregation, numerical
  uncertainty, and invalid or missing-data behavior. Research targets without a
  numeric limit remain reportable rather than silently becoming pass criteria.
- Ordered DUT ports, returns, supplies, bias, stimuli, loads, feedback, and
  reference planes; identify what the DUT owns and what the bench owns.
- Fixed topology and parameters, legal variables, stage-entry gates, search
  budget, and stop rules. Let the executor choose a method when that freedom is
  intended, requiring a bounded plan before costly runs. Finding a feasible
  candidate does not demonstrate global optimality or infeasibility elsewhere.
- Required EDA capabilities and model applicability. Read
  [EDA environment authoring](references/eda-environments.md) for environment and
  model fields. Use [EDA companion selection and handoff](references/eda-companions.md)
  to load only the selected software's available skill. Product-specific
  engineering and connection details belong to that companion. Preserve an
  already selected layout, launcher and automation route in the task's binding.
  Apply the [binding selection and handoff check](references/eda-environments.md#select-and-retain-the-task-binding)
  for each environment the task uses.
- Current deliverables versus future reserved interfaces. Never invent a native
  exporter, starter, reference result, official verifier, or executable benchmark.

## Decide readiness and create the task

Stop clarification when the goal, acceptance semantics, design permissions, and
handoff are clear and remaining unknowns have bounded discovery work. Use the
project's status vocabulary; where it has none, explain these proposed labels:

| Readiness | Meaning |
| --- | --- |
| Draft | A task exists; a named decision still prevents an executable plan. |
| Ready for preflight | The contract is coherent and the environment is selected; environment or input checks remain. |
| Ready for execution | Recorded prerequisites allow the next planned work package to start. |

Readiness does not claim electrical success, validated physical models, or formal
benchmark acceptance. A research task may begin with model qualification as its
first work package. Configuration alone is not evidence that a tool is available.

When the user requested task creation, write the package within the agreed scope
once material decisions are settled; do not repeatedly request permission for
ordinary new files. A draft-only request remains a draft-only request. Resolve
conflicting existing assets without overwriting unrelated work.

Task creation does not itself authorize circuit execution, paid runs, GUI
automation, connector reconfiguration, PDK changes, benchmark registration, or
publication. Honor any separately authorized scope and the project's permission
rules. Record preflight as pending when it was not performed.

## Check and hand off

- Verify task identity and revision across the package. Freeze the exact task
  input used for execution; distinguish later amendments from the frozen record.
  Do not replace completed evidence to make it match an updated specification.
- Freeze the selected workflow instructions and required input inventory as well
  as the task contract before delegated execution. Use the destination's receipt
  and distribution mechanism; a version label alone does not prove that a remote
  consumer received those bytes. Keep restricted dependencies and private bindings
  in their authorized store, with portable references and explicit prerequisites.
- Check requirement-to-measurement mappings, stage gates, model conditions, path
  resolution, required files, and unresolved drafting markers. Run applicable
  existing metadata or static checks; distinguish them from electrical validation.
- Define evidence that relates candidate native source or a reproducible parameter
  set to the actual netlist, model bindings, raw data, measurements, and decision.
  Netlist screening and a selected native-source delivery are separate states.
  Requirement acceptance must allow every design the task permits; reproduction
  checks may additionally compare a specifically disclosed reference design.
- Report execution completion, candidate electrical outcome, model applicability,
  and delivery completeness independently when results are later produced.
- State the task/version's verification scope and actual evidence status. An
  engineering milestone can be planned, unperformed, partial, conditional,
  passed under stated coverage, or failed. Record formal benchmark applicability,
  registration and independent verifier status separately from engineering checks;
  claim absence or official acceptance only when established for that task/version.
- Deliver file links, readiness, confirmed choices, remaining prerequisites with
  their owners or work packages, and the next action. Keep precise integrity data
  in machine-readable receipts and describe verification outcomes in prose.

For delegated execution, provide a brief usable without the preceding conversation:
task/revision and frozen contract/workflow, next work package, relative target paths,
private environment-profile reference, permissions already granted, permitted changes,
budget and stop rules, required evidence and next review gate. One executor owns writes
to a native engineering workspace at a time. The receiving reviewer inspects actual
returned artifacts rather than treating the executor's summary as acceptance evidence.

Use existing phase checks when supplied: initialization validates the project skeleton,
execution readiness validates required inputs/environment, and handoff validates the
task's current delivery obligations. These checks do not substitute for electrical
verification. Preserve original runs, including failed/interrupted work and negative
research outcomes; keep dynamic state in the destination's run/checkpoint record.

## Keep the skills independent and shareable

Keep essential software-neutral authoring guidance and templates inside this
folder. Product-specific environment skills own their own instructions and
references and can also be invoked independently. Discover companions by name
and capability rather than a source-project path; never invent a platform
dependency setting to represent this workflow relationship. If a companion is
unavailable, keep task authoring usable and record its environment work as
pending rather than claiming that setup or checks occurred.

Existing project instructions may override bundled defaults, but their absence
must not block task creation. Share this skill for general authoring and selected
companions for their software-specific capabilities. Host aliases, installation
roots, instance IDs, proprietary models, credentials and private results remain
in destination-local configuration or an authorized evidence store. The
containing project is an installation location, not an execution dependency.
