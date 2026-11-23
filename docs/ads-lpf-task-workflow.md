# Task-first ADS low-pass filter workflow

Use `$staged-lpf-design` as the entry point for a new passive LC low-pass
filter or an existing filter task. For a new filter, it reads and follows
`create-analog-design-task` to plan the task sequence and prepare the first
engineering task package. Record the port impedance, passband edge, reflection
limits, stopband coverage, insertion-loss policy, permitted topology, and
intended physical deliverable.
State which limits are strict, which frequencies are exact checkpoints, and
which metrics are observations. Resolve the decisions that determine acceptance
before executing the affected task. [Task authoring guide](task-development.md)
[Electrical design contract](electrical-design-contract.md)

## Default task boundaries

| Task | Approved inputs and work | Completion evidence and handoff |
| --- | --- | --- |
| Ideal LC synthesis and verification | Use the reviewed electrical specification and topology rules. Synthesize the ideal ladder, verify its port mapping and S-parameters in ADS, and cross-check the response independently. Report a loss or Q budget when it informs device selection. | Review the verified order, topology, nominal element values, response, margins, and limitations. Freeze the selected ideal design and evidence for the PCell task. |
| PCell feasibility and candidate selection | Use the selected ideal design and freeze its topology and order. Confirm model applicability and allowed dimensions, search within the approved budget, and rerun shortlisted exact geometries in the native circuit testbench. | Record the feasibility decision, bounds of the search, sampled match and rejection, insertion loss, and model warnings. Hand off a specifically selected native candidate and its exact model bindings when one is approved for layout. |
| Editable ADS layout and structural verification | Use the approved native candidate and its frozen device geometry. Create the editable hierarchical layout with the agreed signal and return connections, terminals, and reference planes. Reopen it in ADS and check it against the selected schematic. | Retain the native layout, instance and port map, geometry and connectivity checks, and verification record. Deliver the editable workspace at the declared structural milestone. |

The first review selects an ideal design before PCell optimization. The second
review selects a specific physical candidate before layout. Record the decision,
task revision, and selected run or candidate at each review. If the next task
depends on an unresolved choice or missing upstream evidence, leave it in
**Draft** with the exact prerequisite and evidence needed to make it executable.
Freeze that input when it becomes available. Revise the affected task contract
when requirements change and keep earlier attempts and decisions available.

The PCell feasibility task completes when the agreed search, observations, and
conclusion are documented. The conclusion may be that the tested geometries
missed the limits, or that model coverage left a result indeterminate. Candidate
acceptance uses the electrical criteria and model evidence in the approved
contract. Advance to layout only with an explicitly selected native candidate
and any scope exception recorded in the handoff. A bounded search supports a
conclusion about the tested space.

Define a separate coupled full-filter EM task when the requested milestone
requires electrical verification of the assembled layout. Its input is the
frozen editable layout. Its contract specifies physical ports and reference
planes, substrate, solver mode, sweep, mesh checks, and electrical criteria.
Include foundry rule checks, corners, packaging, or measurement where the
requested milestone requires them.

## Package and workspace for each task

Create a separate `tasks/<task-id>/` and `workspaces/<task-id>/` for each
approved task. Use a stable task ID and positive revision throughout. The task
package owns the specification and review decisions. The workspace owns editable
native designs, frozen inputs, and execution evidence.

| File | Record |
| --- | --- |
| `tasks/<task-id>/task.toml` | Task identity, revision, engineering scope, and implemented deliverable contract. |
| `tasks/<task-id>/instruction.md` | Intended decision, requirements, ordered DUT interface, permitted design changes, prerequisites, and deliverables. |
| `tasks/<task-id>/verification-plan.md` | Measurements, coverage, checks, evidence, stage-entry conditions, and decision rules for missing or inconclusive results. |
| `tasks/<task-id>/DEVELOPMENT.md` | Readiness, open items, selected environment binding, decisions, and evidence history. |
| `workspaces/<task-id>/project.toml` | Matching task identity and revision, with workspace-relative engineering paths. |

Retain the selected upstream artifacts and a provenance manifest under the
downstream workspace's `inputs/`. Identify the source task, revision, selected
run, candidate where applicable, and the files carried forward. Verify that the
consumer can open the snapshot and use the referenced models. Preserve exact
integrity data in the machine-readable manifest. Keep the active editable ADS
workspace under `ads/` and new run evidence under `results/`. Put installation
paths, account-specific connections, and licensed PDK bindings in ignored local
configuration. [Engineering workspace layout](engineering-workspace-layout.md)

An ideal handoff carries the specification and port map, verified schematic or
rebuild inputs, nominal element values, and complex response evidence. A PCell
handoff adds the selected candidate's full per-instance geometry, exact model
identity and applicability, native schematic and testbench, and corresponding
response evidence. A layout handoff carries the editable layout and schematic,
the reference-plane definition, and reopened structural verification. Retain
licensed native inputs on the authorized ADS host and transfer only permitted
files or compact evidence.

## Restricted InP PDK implementation

When a task uses the restricted InP PDK, reuse the validated device profile when
its device families match the task's process and layout scope. Bind the
inductor and capacitor PCells with explicit signal and ground ports, allowed
variables, fixed geometry, and routing layers. Use the exact native EM sample
for each selected geometry and preserve model warnings with the results. A
missing geometry calls for extraction in the run-owned ADS copy and a check of
the resulting native sample before use. Record the saved fixture and resume
route when extraction requires application mode.

The real profile carries licensed device identities and geometry, so it lives in
ignored local configuration (`.local/profiles/`). The committed
[example profile](../scripts/lpf/profiles/example-inp.toml) shows the schema with
neutral names; pass the private profile with `--profile` for a real search.

Derive the execution TOML from the approved task contract and use the shared
staged commands for the supported equal-termination Chebyshev-I ladder and
exact stop checkpoints. A continuous stopband mask needs a corresponding
verification method in the task package. Keep reusable skills independent of
project IDs, host paths, and licensed files. The project guide and device
profile carry the repository-specific conventions. [Staged ADS commands](../scripts/lpf/workflow.py)
[ADS environment workflow](ads-mcp-workflow.md)

## Execute and hand off approved tasks

For an authored task that uses the shared runner, set `project.stage` in its
workspace `project.toml` to `lpf-ideal`, `lpf-pcell`, or `lpf-layout`. Match
the task ID and revision to the task package. Retain the task package in
`inputs/task-spec/` when the runner is on an isolated ADS host. Keep the
workspace `inputs` and `results` paths relative to the project.
Keep generated `results/` and `inputs/upstream/` ignored in the workspace.
The latter may contain licensed native model data from the reviewed candidate.

Start Task 1 with the approved electrical TOML and its own workspace. After
reviewing the result, freeze it into Task 2 and run the search from the new
run directory returned by the handoff command.

```powershell
python -m scripts.lpf.workflow ideal --project <ideal-workspace> --spec <approved-spec> --ads
python -m scripts.lpf.workflow handoff --run <ideal-run> --project <pcell-workspace> --approve-ideal
python -m scripts.lpf.workflow search --run <pcell-run> --ads-source <pcell-source-wrk>
```

After selecting a reviewed native PCell candidate, hand it off to Task 3 and
use the new layout run directory. The layout command consumes that selection.
To select from an earlier PCell attempt, add `--search-attempt <attempt-id>`
at handoff. Record an explicitly accepted electrical near miss with
`--accept-near-miss` at handoff.

```powershell
python -m scripts.lpf.workflow handoff --run <pcell-run> --project <layout-workspace> --candidate <candidate-id>
python -m scripts.lpf.workflow layout --run <layout-run>
```

The handoff preserves the shared electrical TOML, reviewed result and supporting
files under the receiving task's `inputs/upstream/`. The receiving task gets
its own checkpoint and attempts. Use `status --run <run>` to resume within one
task. If the electrical requirements change, use the task authoring and revision
workflow to establish the new contract and identify the affected evidence.
