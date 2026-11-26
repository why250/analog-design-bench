# Engineering task routing, execution and closeout

Use this entrypoint for a new or resumed engineering design, reproduction or
feasibility study. The task package owns its electrical requirements; this guide
owns routing, delegation and evidence organization. A normal engineering task
does not require a benchmark registration, Docker image or official verifier.
Formal model evaluations continue through the [model evaluation workflow](model-evaluation.md).

## Select the task before selecting tools

1. If the user names an existing task, workspace or run, read its contract,
   revision and checkpoint first. Resume that identity; do not create another
   task because the conversation is new. Completed runs remain unchanged.
2. A changed requirement uses the task's revision rules. Distinguish a contract
   change from another candidate within the same revision.
3. For a new goal, use `create-analog-design-task` to define the kind, EDA,
   stage, ordered interface, model constraints, measurements, deliverables,
   budget and stop rules. Unresolved scope stays a draft. A bounded feasibility
   investigation may itself be executable while its answer remains unknown.
4. Select the EDA and workflow from the declared task and existing binding.
   Keywords help discover a likely workflow but cannot override a frozen task.
   Record the selected workflow and its version in the run record. If software
   is unspecified and not inferable, clarify that choice before native work.

The versioned [workflow catalog](../engineering/workflows.toml) is the common
index. The root `AGENTS.md` directs the agent to this guide; catalog lookup and
phase checks supply mechanical checks. Neither a catalog entry nor a skill
guarantees automatic execution or electrical correctness.

| Workflow | Use | Software branch |
| --- | --- | --- |
| `ads-generic` | ADS engineering without a more specific implemented workflow | ADS environment, native organization and task-owned electrical checks |
| `ads-lpf` | Passive LC low-pass filter staged design | Generic ADS requirements plus the [LPF task workflow](ads-lpf-task-workflow.md) |
| `ads-inductor` | RFIC Inductor Toolkit geometry and Momentum screening | Generic ADS requirements plus the available inductor skill; task-specific stack and checks remain required |
| `virtuoso` | Editable schematics and source-derived Spectre simulation | [Virtuoso workspace, native netlisting and evidence workflow](virtuoso-mcp-workflow.md); initial validation is ideal two-port work |

Only load skills and references needed for the selected work. The Virtuoso
branch uses the selected Bridge's actual native skills and installed Cadence
documentation. Its implementation does not establish PDK compatibility,
layout/extraction or ADE readiness; record those task-specific prerequisites
when requested. Unsupported routes remain drafts rather than guessed workflows.

### Record the task's route

The authoring agent creates `tasks/<task-id>/engineering.toml` for new
engineering tasks. This operator profile records selection, not electrical
criteria or benchmark runner configuration. A minimal example is:

```toml
schema_version = 1
eda = "ads"
workflow = "ads-generic"
kind = "design"
deliverables = ["source", "simulation"]
# Optional task-relative nested inputs used by this execution contract:
inputs = ["inputs/device-contract.json"]
```

`eda` selects the software; `workflow` names a catalog entry; `kind` is
`design`, `reproduction` or `feasibility`; `deliverables` selects only the
outputs required by the task. Use `source` alone for a native-source delivery
without analysis. The profile does not change the task revision or permit
another workflow to relax the contract. Keep it outside blind solver input.
Omit `inputs` when no extra nested input is needed. When present, each entry
names an actual file relative to the task directory; use it for required nested
model/bench/constraint inputs without copying restricted model installations.

```powershell
python scripts/engineering_runs.py route --task tasks/<task-id>
```

When a task profile exists, explicit options must agree with it; conflicting
options are errors, not overrides. Existing frozen runs keep their own selected
profile and baseline. For legacy tasks without a profile, read their contract
and record an explicit route for the next new run rather than rewriting prior
records. If a task requires a specialized workflow, do not silently fall back
to the generic ADS branch. Candidate iteration within one contract does not
increment the task revision.

Keep the route separate from readiness. Required scope or acceptance decisions
must be resolved before execution. Environment checks may remain pending until
the selected preflight work package; later-stage deliverables may be deferred
when they are explicitly outside the current stage. Record the responsible
work package and disposition for each such item. Deferred work is never a
successful result or a blanket exception from a required check.

## Establish stable ownership

For this project's configured host integration, follow
[External lab integration](lab-integration.md). After task selection, use
`engineering_runs.py environment --task tasks/<task-id> --client <lab-client>`
to obtain the lab's host/MCP plan; the client is required when several clients
are registered. Use `prepare --task tasks/<task-id> --slug <purpose> --client
<lab-client>` for a new execution; it reuses or initializes the stable
workspace, allocates a run, prepares delegation and freezes the baseline. These
commands replace manual allocation/freezing for that prepared run. Continue the
actual readiness and closeout steps below; do not allocate another run for the
same invocation.

Keep `tasks/<task-id>/` authoritative and `workspaces/<task-id>/` stable. Apply
the [engineering workspace layout](engineering-workspace-layout.md) before
building an ADS project and the [naming convention](ads-naming-convention.md)
before creating its libraries or cells. For Virtuoso, use the
[native workspace and ownership rules](virtuoso-mcp-workflow.md#stable-native-workspace-and-ownership).
Keep task, workflow and software versions
distinct. A new run or candidate is not a new task revision.

`project.toml` is static identity and path configuration. Dynamic selection and
outcomes belong in the run's `run.json`. Keep host roots, SSH aliases, installed
paths, session identifiers and restricted model locations in ignored `.local/`
bindings. Shared requirements and reports refer to those bindings without
copying their private contents.

Preserve legacy workspace identities and original evidence. `ads_workspace.py
audit` inventories them; compatibility or a successful `--all-v2` check does
not mean that old tasks have been migrated or electrically verified. Migrate
an old workspace only as a separately scoped change.

## Freeze before delegating execution

Allocate a fresh run and select its deliverables before native execution. The
initial `run.json` is a draft record, not evidence of readiness. For example:

```powershell
python scripts/engineering_runs.py route --workflow ads-generic --eda ads
python scripts/ads_workspace.py new-run --workspace workspaces/<task-id> --slug nominal --workflow ads-generic --kind design --deliverables source,simulation
python scripts/engineering_runs.py freeze --run workspaces/<task-id>/results/<run-id>
python scripts/engineering_runs.py check --run workspaces/<task-id>/results/<run-id> --phase scaffold
```

Use the returned run directory. The freeze captures all top-level task `.md`
and `.toml` files, the task profile's explicitly declared nested `inputs`, the
workflow catalog and declared normative files, including the workflow helpers.
The frozen execution plan also pins EDA, kind and deliverables; editing the run
record cannot remove an agreed evidence group. The workspace task-spec
snapshot likewise includes `engineering.toml` and its declared nested inputs.
Do not silently regenerate it after execution starts. A contract change starts
a new run with the appropriate task revision. Complete unfinished requirements
before calling a draft executable; freezing bytes does not resolve ambiguity.
The authoring agent supplies the task profile and populated contract; the user
can continue expressing the goal in normal language rather than filling these
records manually. Use `ads_workspace.py init --create-task` only as a scaffold,
then replace its draft requirements before execution.

For a remote executor, transfer the selected frozen contract, required scripts,
task-owned tools and permitted inputs with their original relative layout.
Also include any supporting resources that a selected skill or task tool
actually needs. Restricted PDK material is supplied through the destination's
authorized model binding, not bundled into shared guidance. A version label is
insufficient: retain a machine-readable inventory and verify the received file
bytes. The executor returns a consumer receipt identifying the actual baseline
and input snapshot used. Keep exact integrity values in receipts; human reports
state the version, observation time and verification outcome without printing
digest or commit values.

Use the [delegation brief](templates/engineering-delegation.md). It must be
understandable without the preceding conversation and include scope, paths,
existing authorization, model dependencies, bounded work and return artifacts.
Carry forward authorization already given; creating a task alone does not
authorize simulations, new licenses or GUI work. Apply the user's explicit
Computer Use consent rule when UI inspection or operation is needed.

## Check the actual execution environment

Before modifying native source, the executor must establish the intended tool
process, software version, workspace and consumer-visible files. Distinguish
the agent's environment, SSH shell host and native EDA process host. Matching drive
letters or an MCP server label do not establish a shared filesystem.

For ADS, follow the [ADS MCP workflow](ads-mcp-workflow.md) and record separately
the configuration, transport, documentation, session, workspace and model
checks actually performed. Link a portable preflight report from `run.json`;
keep exact host/session/path observations in the private binding receipt.
Unavailable or unperformed checks remain pending. A recorded preflight status
is an assertion with evidence references; the static checker does not discover
the remote session or test a license itself. For Virtuoso, apply the corresponding
[preflight and native-source checks](virtuoso-mcp-workflow.md#actual-preflight-and-source-preparation),
including isolated library definitions and source-derived netlisting.

Assign one writer to the primary editable native workspace. Parallel analysis
may read frozen inputs. Parallel native edits require separate owned copies
and an explicit selected result. Do not switch another operator's active
workspace, delete live locks or discard unsaved changes to force execution.

Run the `ready` phase before circuit execution:

```powershell
python scripts/engineering_runs.py check --run workspaces/<task-id>/results/<run-id> --phase ready
```

## Record evidence and close out

Keep each invocation's logs, frozen candidate inputs and raw results below its
run directory. Task-specific formats and subdirectories may differ; `run.json`
is their common index. Declare only deliverable groups required by this task.
A source-only delivery does not imply simulation; an EM delivery requires its
own stack, ports, solver and measurement evidence.

### Populate the generated run record

The executor updates the generated JSON as observations become available;
there is no separate status-update command. All evidence references are
normalized paths relative to the run root and must identify nonempty files,
not directories, links or absolute host paths. For multi-file native source,
link its released snapshot files or archive and retain the corresponding
inventory. The stable editable project remains in the manifest's native
directory (`ads/` or `virtuoso/`).

| Field | Use |
| --- | --- |
| `task`, `run_id`, `eda`, `workflow`, `kind`, `deliverables` | Frozen run identity and requested scope; preserve the generated values |
| `selection.candidate`, `selection.native_design` | Selected candidate and exact `library:cell:view`; native design may initially name the planned build target |
| `readiness` | Set `status` to `confirmed` only with a nonempty authorized `scope`, `confirmed_by` role, actual `confirmed_utc`, and a run-relative `brief` file |
| `preflight` | Run-relative JSON report path with actual retained workspace/model observations |
| `state`, `started_utc`, `ended_utc` | Record `planned`, `running`, `completed`, `failed` or `interrupted` and UTC times ending in `Z`; conclude explicitly before closeout |
| `evidence` | File lists grouped by role, as required below |
| `outcomes` | Independent facet objects containing `status`, evidence paths and a `reason` for a not-applicable conclusion |
| `gaps`, `notes` | Missing obligations, failure causes, coverage limits, decisions and next action |
| `contract` | Generated frozen-contract reference; never repair it by hand to hide drift |

The preflight report has `schema_version = 1`, `status = "ready"`, actual
`observed_utc`, `eda`, `task_version_id` and the same `native_design` as the run.
It includes `workspace` with `status = "verified"` and an `evidence` file list,
plus `models` with `status = "verified"`, `"conditional"` or `"not-applicable"`
and an `evidence` file list. Conditional and not-applicable model conclusions
also require a nonempty `reason`. Use real tool observations, not this example
as a substitute for evidence. A conditional model conclusion limits the next
authorized work package and does not establish model qualification.

| Deliverable group | Required evidence role lists at completed handoff |
| --- | --- |
| Every delivery | `native_source` |
| `source` | Native source evidence only; no simulation is implied |
| `simulation` | `netlist`, `simulator_log`, `raw_data`, `measurements`, `check_report` |
| `layout` | `layout`, in addition to native source |
| `em` | `solver_input`, `simulator_log`, `raw_data`, `measurements`, `check_report`, `em_setup`; a circuit netlist is not required unless simulation is also requested |

Additional task obligations still apply. A source/layout-only run may give
electrical analysis a reasoned `not-applicable` status; simulation and EM runs
must give a reportable electrical conclusion. Outcome status values are:
execution (`completed`, `failed`, `interrupted`), electrical (`passed`,
`failed`, `conditional`, `not-applicable`), models (`verified`, `failed`,
`conditional`, `not-applicable`), and delivery (`complete`, `incomplete`).
Non-applicable outcomes require a reason; other concluded outcomes require
evidence. `pending` and `running` describe unfinished work, not completed
handoffs. Consult the [run helper](../scripts/engineering_runs.py) for the
machine schema and rejection rules.

`readiness.brief` links the populated delegation brief retained inside this
run. The checker requires a nonempty file; the main agent still reviews its
authorization, scope, budget and stop rules. It does not mechanically parse
those decisions. For EM, `solver_input` identifies the actual solver deck or
its released package with the corresponding setup and input inventory.

Keep four conclusions independent: work execution, candidate electrical
outcome, model applicability and delivery completeness. A completed bounded
study may find no passing candidate. Missing data cannot imply a pass, and a
simulator's zero exit code is not electrical acceptance. Link task-owned checks
and their actual reports rather than replacing them with a self-reported flag.

| Phase | What the common checker establishes | What it does not establish |
| --- | --- | --- |
| `scaffold` | Run identity and record structure; use `route` separately for catalog selection | Native project readiness or resolved electrical requirements |
| `ready` | Frozen input integrity and required preparation/evidence declarations | A live remote process, a valid model domain or permission beyond the recorded scope |
| `handoff` | Required evidence references and closeout consistency for the requested deliverables | Electrical pass, native reopenability or independent reproduction without their actual task checks |

Before closing, the main agent reads the returned files and original check
reports, independently verifies the transferred inventory and reviews the
task's actual acceptance comparisons. It records gaps and decides whether the
next stage may start. A subagent's summary alone is insufficient.

```powershell
python scripts/engineering_runs.py check --run workspaces/<task-id>/results/<run-id> --phase handoff
python scripts/engineering_runs.py close --run workspaces/<task-id>/results/<run-id>
```

Closeout records the original evidence inventory for append-only retention
and later integrity verification. This is an engineering convention, not
immutable storage or protection against malicious rewriting of both evidence
and receipts. Preserve sealed bytes and put later interpretations or corrected
reports in a new amendment run referencing
the original. Failed or interrupted work retains its cause, available evidence,
budget consumed and next action; archiving it must not label missing delivery
or electrical checks successful.

The helper takes the terminal state from `run.json`; there is no `--state`
option. Failed or interrupted closeout requires recorded gaps, the matching
execution outcome and incomplete delivery, and preserves frozen-contract
integrity when a contract exists. It is an archive action, not a successful
`handoff` result. Remove disposable scratch before closing; adding files,
changing evidence or storing a new check output inside a closed run invalidates
its sealed inventory. Store later check receipts outside the closed run.

Prepared runs also link their retained source/reports from a managed workspace
README section at closeout. The index preserves existing prose and reports each
outcome separately; it does not select a passing design from a failed study.

The workspace README is the human entrypoint: link the currently recommended
native design, its exact retained run, outcome scope and reproduction command.
`docs/execution-record.md` explains decisions and chronology. Keep current
machine state in the selected run record; do not maintain competing status
claims in several documents. Updating an entrypoint must not overwrite older
runs or rename their native candidates.

## Maintain the distributed standard

When normative behavior changes, update the affected workflow version and
checks together. Record the change in the task/development record when it
affects task interpretation. Before requiring remote adoption, inspect the
actual bundle contents and consumer receipt; local untracked files are not
evidence that another checkout received the standard. Committing or publishing
a baseline is separate from preparing and validating its frozen handoff.

Verify updates using temporary tasks and runs: route an existing task, create a
new ADS and Virtuoso run, reject reserved workflow execution, reject missing or changed
evidence, and close a complete source-only or simulated delivery. Do not use
historical evidence as disposable test fixtures or claim electrical validation
from these workflow tests.
