# External lab integration

## Shared MCP entrypoint

When the EDA Lab MCP is connected, use `register_project(profile="auto")`,
`plan_task` and `prepare_run` with this repository's absolute path. The shared
service detects the existing engineering profile and delegates preparation,
checks and closeout to the helper documented below. Author the task contract
first and pass its selected workflow/block-key options when needed. Existing
task and workspace identities remain authoritative. Generic new repositories
can use the shared service without copying this repository's scripts.

The portable `eda-lab` guidance and the MCP descriptions direct the agent through
environment planning, native execution and retained evidence review. Product
tools must be loaded in the selected client. The CLI binding remains compatible.

## Responsibilities

This repository is the daily task entrypoint. It owns task requirements,
electrical checks, workflows, native projects and results. The external lab owns
host capabilities, selected software, connection launch definitions and resource
policy. Engineering workflow selection and execution-host selection are separate.

The agent calls the lab through a local subprocess and its JSON interface; it
does not require another conversation. Keep the lab location, Python executable,
MCP alias mappings and remote roots in ignored `.local/eda-lab.json`. Never put
these machine-specific values in a portable skill or task contract.

The integration is a development-time dependency. Frozen task/evidence packages
and formal benchmark inputs keep their self-contained contracts. Runtime
credentials and private profiles are not part of portable result packages.

## One-time project binding

From the selected lab installation, run its binding command with discovered
paths and an interface from its host inventory:

```powershell
python <lab-root>/scripts/lab.py bind-project --project <design-repository> --client codex --interface <lab-interface>=<client-mcp-name> --remote-root <host-key>=<existing-remote-project-root>
```

The command reuses a matching native MCP entry or appends a missing entry while
preserving unrelated settings. A conflicting or disabled launch is rejected.
Codex, Claude Code and Cursor have separate project configuration formats; bind
the intended client. The current preferred binding identifies which native
configuration is checked during planning. Each client must load its project
configuration and expose the mapped tools before execution. File generation
alone does not prove activation.

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
python scripts/engineering_runs.py environment --task tasks/<task-id>
python scripts/engineering_runs.py prepare --task tasks/<task-id> --slug nominal --block-key <BLOCK> --dut-cell <BLOCK>_Main --dut-ports <ordered,ports>
```

`environment` reads the task/workflow and existing private task binding, calls
the external lab planner, and returns its actual JSON plan. It creates no run.
ADS simulation/source/layout work requests the lab's `ads` route; requested EM
deliverables request `em`. Specialized electrical workflows remain authoritative.
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
until the actual ADS process and filesystem are checked. Live solver scratch
may be produced in vendor-owned locations; collect retained evidence into the
selected run. Do not synchronize an open workspace continuously in both directions.

Preparation freezes the selection but leaves task readiness in draft. Review
and populate `delegation.md` from the frozen delegation template using the
user's existing authorization, budget and stop rules. Verify the actual tool
process, workspace and PDK; record real preflight observations. Set readiness
only for the agreed work. GUI work follows the user's explicit consent rule.
No preparation command launches ADS, simulates, transfers files or starts a
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
