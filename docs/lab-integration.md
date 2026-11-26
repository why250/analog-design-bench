# External lab integration

## Shared MCP entrypoint

The lab exposes eight MCP tools: `list_capabilities`, `discover_environment`,
`list_software`, `get_launch_command`, `register_project`,
`ensure_product_tools`, `plan_environment` and `transfer_files`. It no longer
prepares, checks or closes engineering runs. Run preparation, workspace reuse,
verification and closeout stay in this repository and its `engineering_runs.py`
helper.

Start each design task with the read-only `plan_environment` gate, passing this
repository's absolute path, the route inferred from the task (`ads`, `em`, or `virtuoso`) and
the actual calling client (`claude` for Claude Code, or `codex`, `cursor`,
`antigravity`). The result selects one of these paths:

| Result | Action |
|---|---|
| `status=unregistered` | First connection: `register_project` with the actual client, then `ensure_product_tools`, then repeat the plan. |
| `status=blocked` with `setup_action` | Run the named action (`ensure_product_tools` or `register_project`) with the named client, then repeat the plan. |
| `status=blocked` without `setup_action` | Report the environment constraint; do not substitute a host. |
| `status=planned` and `project_binding.status=configured` | Call the product MCP named by `project_binding.mcp_name` under this project's workflows. |

A returning project starts at `plan_environment` and does not re-register or
rewrite MCP configuration. A visible product tool or an earlier conversation is
not evidence of the current binding. Registration adds the calling client's layer
without replacing another client's interface binding.

The portable `eda-lab` guidance and the MCP descriptions direct the agent through
environment planning and native execution. Product tools must be loaded in the
selected client. The CLI binding remains supported; `engineering_runs.py` uses
the lab's `lab.py plan` JSON interface behind the ignored `.local/eda-lab.json`
binding.

The legacy `plan_task` name is a Python/CLI compatibility alias for environment
planning only and is not one of the eight MCP tools. The former `prepare_run`,
`check_run`, `close_run` and handoff/relay interfaces no longer exist; use this
repository's `engineering_runs.py` commands instead.

## Responsibilities

This repository is the daily task entrypoint. It owns task requirements,
electrical checks, workflows, native projects and results. The external lab owns
host capabilities, selected software, connection launch definitions and resource
policy. Engineering workflow selection and execution-host selection are separate.

The agent calls the lab through its MCP tools or, for the helper commands below,
through a local subprocess and the lab's JSON interface; it does not require
another conversation. Keep the lab location, Python executable,
MCP alias mappings and remote roots in ignored `.local/eda-lab.json`. Never put
these machine-specific values in a portable skill or task contract.

The integration is a development-time dependency. Frozen task/evidence packages
and formal benchmark inputs keep their self-contained contracts. Runtime
credentials and private profiles are not part of portable result packages.

## First connection and returning projects

The MCP path above is the preferred onboarding: when `plan_environment` reports
`unregistered`, `register_project` and `ensure_product_tools` bind the calling
client. Registration writes only private metadata under `.local/` and an ignore
rule; it creates no task, workspace, run or remote directory.

The CLI binding remains available from the selected lab installation:

```powershell
python <lab-root>/scripts/lab.py bind-project --project <design-repository> --client claude --interface <lab-interface>=<client-mcp-name> --remote-root <host-key>=<existing-remote-project-root>
```

The command reuses a matching native MCP entry or appends a missing entry while
preserving unrelated settings. A conflicting or disabled launch is rejected.
Codex, Claude Code and Cursor have separate project configuration formats; bind
the intended client. Bindings are stored per client. When several clients are
registered, planning must name the calling client (`--client` on the helper
commands or the MCP `client` argument); an unnamed plan is blocked rather than
verifying or rewriting another client's connection. Each client must load its
project configuration and expose the mapped tools before execution. File
generation alone does not prove activation.

A remote root is a path proposal taken from existing authorized work or supplied
by the operator. Recording it does not grant new write scope. Preserve existing
task-specific roots and SSH bindings; conflicting constraints must be resolved,
not silently replaced. No binding/planning command creates remote directories.

## Starting a task

The user describes the goal in ordinary language. The authoring agent resolves
an existing task first or writes a new task and `engineering.toml`, including
its EDA, workflow and requested deliverables. It populates the actual electrical
contract; the user does not need to fill configuration files.

```powershell
python scripts/engineering_runs.py environment --task tasks/<task-id> --client claude
python scripts/engineering_runs.py prepare --task tasks/<task-id> --slug nominal --client claude --block-key <BLOCK> --dut-cell <BLOCK>_Main --dut-ports <ordered,ports>
```

`--client` is optional when exactly one client is bound to the project; with
several registered clients it is required, otherwise the lab returns a blocked
plan naming the registered clients.

`environment` reads the task/workflow and existing private task binding, calls
the external lab planner, and returns its actual JSON plan. It creates no run.
ADS simulation/source/layout work requests the lab's `ads` route; requested EM
deliverables request `em`. Virtuoso source/simulation work requests `virtuoso`
and carries the selected Virtuoso and Spectre requirements from its private
task binding. Specialized electrical workflows remain authoritative.
Optional `--host`, `--platform`, `--cpus` and `--memory-gib` constrain selection.
An existing task SSH binding is also a constraint. Missing project binding,
unavailable interfaces, configuration drift and incompatible requests do not
produce a guessed execution environment.

`prepare` performs that selection, reuses the matching workspace, or initializes
a schema-v2 workspace for an authored task. A new workspace requires a block key
for standard naming; `--model-policy unrestricted-ideal` selects open ideal-only
source, while the default preserves restricted PDK material. Existing workspace
identity, names and model policy are retained. Multiple matching workspaces need
an explicit `--workspace`. It then allocates a fresh run and writes:

| Location | Contents |
|---|---|
| `results/<run-id>/run.json` | Common run identity, evidence index and outcomes |
| `results/<run-id>/environment-plan.json` | Portable selected environment, relative paths and pending checks |
| `results/<run-id>/delegation.md` | Prepared execution brief; scope and budget still require review |
| `results/<run-id>/contract/` | Frozen task, workflow and environment selection |
| `.local/engineering-runs/<task-id>/<run-id>/environment.json` | Private lab response, actual MCP alias and local/remote paths |

The returned run path is authoritative. The private receipt gives the executor
the exact remote native project and run-output locations, derived from the
workspace manifest and selected root. All remote locations remain proposals
until the actual native EDA process and filesystem are checked. Live solver scratch
may be produced in vendor-owned locations; collect retained evidence into the
selected run. Do not synchronize an open workspace continuously in both directions.

Preparation freezes the selection but leaves task readiness in draft. Review
and populate `delegation.md` from the frozen delegation template using the
user's existing authorization, budget and stop rules. Verify the actual tool
process, workspace and PDK; record real preflight observations. Set readiness
only for the agreed work. GUI work follows the user's explicit consent rule.
No preparation command launches an EDA application, simulates, transfers files or starts a
subagent. The parent agent delegates the self-contained work package within the
task's authorized scope and maintains one native writer.

Resume a frozen run from its retained plan and private receipt; do not overwrite
its selection with today's defaults. A new invocation gets a fresh run. Legacy
runs without an environment plan retain their existing schema and evidence;
this integration does not bulk-migrate them.

## Returning results

Use the existing `scaffold`, `ready` and `handoff` checks in the engineering
workflow. An environment plan is checked for identity and integrity and pinned
by the frozen contract. It is not live solver readiness or an electrical result.

The executor returns the selected native-source snapshot and every evidence
group requested by the task, including actual logs, raw results, measurements
and acceptance comparisons when analysis is requested. The parent agent reads
the files and independently reviews the comparisons before closeout.

```powershell
python scripts/engineering_runs.py check --run <run-directory> --phase handoff
python scripts/engineering_runs.py close --run <run-directory>
```

For prepared runs, closeout updates a managed section in the stable workspace
README with the retained run, native design, evidence links and separate
execution/electrical/model/delivery outcomes. Existing README prose is preserved.
Failed or interrupted runs retain that status; an entrypoint link does not imply
electrical acceptance. Sealed run contents remain unchanged by indexing.

Detailed sz16 delivery and old-version compatibility are deferred. The external
lab must not use sz16 as a development-compute fallback.
