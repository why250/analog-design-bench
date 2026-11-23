# EDA environment contract

Use this reference when defining an analog task that needs an EDA environment.
Describe the required capabilities without assuming one vendor, connector, host,
or file layout. Task authoring records the contract and execution prerequisites;
it does not start simulation, extraction, optimization, or remote application work.

## Three layers

| Layer | Contents | Location |
| --- | --- | --- |
| Requirements | Portable capabilities and compatibility constraints needed by the task | Task specification or its existing environment contract |
| Binding | The selected installation, host mapping, local roots, connection profile, and external model locations | Existing local configuration, excluded from the shared skill and portable task |
| Observations | What an authorized inspection or execution actually established, its time, scope, and evidence | Local preflight or run records |

Keep these layers distinct. A configured installation is a declared binding;
an observed version establishes only the inspected installation's identity.
Neither establishes usable licensing, model coverage, a successful run, or
electrical acceptance. Retain the relevant evidence for each separate conclusion.

## Portable requirements

Record only the capabilities that affect this task's execution or interpretation.
Use existing project fields and documents when present. When absent, record the
following semantics directly in the task; no external schema or guide is required.

| Requirement | Definition to capture |
| --- | --- |
| Software | Required capability, compatible version or format constraints, and any user-selected product |
| Analyses | Required analyses, operating conditions, frequency/time ranges, exact checkpoints, and outputs |
| Technology | Required PDK or technology family, allowed models, external dependencies, and permitted source access |
| Model interface | DUT ports, reference planes, ground/return, parameter names and units, model includes, and required exports |
| Licensing | Features or solver licenses needed, with availability left to preflight |
| Tool entrypoints | How the executor can discover the configured installation and supported automation or manual workflow |

Do not invent a version pin, installation path, model range, or license state.
An exact product/version is a requirement only when specified by the user or
needed by the selected assets. Otherwise record the compatibility question and
its planned check. Keep proprietary model payloads and credentials external.

## Access and discovery

Prefer applicable APIs or connectors, then supported CLI or scripting interfaces.
MCP is one possible interface, not a prerequisite for creating or executing an
analog task. A documented manual workflow is valid when automation is unavailable;
state the required user handoff and evidence instead of fabricating a tool path.
Follow the target project's consent rules before any later GUI inspection.

When the user or a selected working profile specifies MCP, retain that route and
its launcher/settings in the task binding. Supporting multiple interfaces does
not authorize dropping the selected one. Preserve concrete native-project
organization as well, while keeping absolute host roots and instance values local.

During authoring, inspect existing manifests, available tool metadata, and
accessible documentation as needed, without assuming any exist. When no
environment is configured, capture required capabilities and unresolved binding
fields rather than demanding a project workflow document. Include useful read-only checks within the
existing authorization and describe remaining live checks. Creating a task does
not itself authorize changes to a live EDA session or design, or solver execution.
Creating the agreed task documents and workspace scaffold remains in scope.

At execution preflight, establish which process will consume the files, which
filesystem it sees, and which configured tool entrypoint reaches that process.
Matching drive letters or directory names across hosts do not prove shared storage.
Preserve stable project-relative paths and resolve absolute roots through bindings.

## Select and retain the task binding

Identify the intended environment for each execution role. Record design and
formal verification separately when they use different runtimes. A versioned
runtime already specified by the task can serve as the selection for that role.

For a selected local or remote installation, save a task-level binding or a
reference to an existing authorized profile using the project's local convention.
Several tasks may share the same profile. Retain any task-specific workspace and
model mappings. Recording the selection leaves the launcher and live environment
configuration under their existing authorization.

Before handoff, resolve each selection and check that it matches the task revision,
intended tool, execution route, and applicable workspace and model bindings. If
a selection is missing, ambiguous, or incompatible, record it as `pending-binding`
and identify the decision or input needed to proceed. Preflight checks the selected
environment before dependent work starts. Resolve discrepancies before switching
hosts, simulators or entrypoints.

## Readiness without false certainty

A task with a resolved selection can be created with `pending-preflight`
environment readiness when its goal, scope, acceptance, and deliverables are clear.
List each execution blocker, the check that resolves it, and the permitted
response if the check fails.
An unresolved environment item does not require endless requirements questions.
Use existing readiness vocabulary if the repository defines one.

Separate unknown access or licensing from unknown scientific feasibility.
A research task may deliberately investigate model availability or achievable
performance; define its evidence and completion rule accordingly. Preserve a
blocking prerequisite when execution genuinely requires an unavailable asset.

## Model applicability and result boundaries

Record geometry, frequency, temperature, bias, return/substrate, and extraction
coverage where relevant. Distinguish existing samples, interpolation, extrapolation,
and newly generated models. Identify model warnings and how they will be resolved
or carried into a conditional conclusion. A model file's existence is insufficient.

Keep study completion, candidate electrical status, model applicability, and
physical qualification distinct. Failed simulation, unsupported model conditions,
and unmet electrical limits have different causes. Require actual candidate
source, model bindings, generated simulation input, and result evidence to agree.
Apply the same discipline to any EDA product or execution interface.
