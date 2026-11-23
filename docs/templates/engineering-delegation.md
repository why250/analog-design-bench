# Engineering execution brief

Fill this operator brief before delegating. Replace fields with actual values
or an explicit pending/not-applicable disposition. This brief accompanies the
frozen contract and is kept outside blind benchmark solver input.

## Identity and decision

- Task ID / revision / task version: `<task identity>`
- Kind (`design`, `reproduction`, `feasibility`) / stage: `<selected work>`
- EDA / workflow / workflow version: `<declared route>`
- Goal and decision this work must support: `<bounded objective>`
- Authoritative contract and verification plan: `<relative files>`
- Frozen contract and run record: `<run-relative files>`
- This populated brief (`run.json` -> `readiness.brief`): `<run-relative file>`
- Contract transfer inventory / consumer receipt: `<machine-readable files>`
- Starting checkpoint / reviewed upstream candidate: `<reference or none>`

## Scope and authorization

- Required work and deliverables: `<specific work packages and outputs>`
- Fixed topology/interface/model assumptions: `<constraints>`
- Allowed design variables and modifications: `<explicit freedom>`
- Out-of-scope work and protected source: `<boundaries>`
- Existing user authorization: `<authorized actions and applicable limits>`
- GUI consent: `<explicitly authorized for this task, pending, or not needed>`
- Candidate/run/license/time budget and stop rules: `<finite limits>`
- Mandatory review before another stage: `<checkpoint and decision owner>`

## Execution binding and ownership

- Stable workspace suffix: `workspaces/<task-id>/`
- Declared primary native source and views: `<relative path; library:cell:view>`
- Run output root: `results/<run-id>/`
- Private environment binding reference: `<local profile reference>`
- Frozen input and required tool files: `<relative paths and receipts>`
- PDK/model requirements and destination-supplied dependencies: `<requirements>`
- Primary native writer: `<executor role>`
- Other writers/copies: `<none, or separately owned copy and merge decision>`

Before editing, confirm the intended tool process, version, active workspace,
consumer-visible input paths and model binding. Return portable check outcomes
with private observations in the local receipt. Preserve unsaved source and
live locks. Do not infer the tool host from the agent or SSH shell host.

## Acceptance and return package

| Obligation | Required artifact/report | Decision rule and coverage |
| --- | --- | --- |
| Native source / selected candidate | `<relative path and view identity>` | `<reopen/connectivity/source check>` |
| Requested analysis or extraction | `<simulation netlist or EM solver input; settings/log/raw data>` | `<exact analyses and model domains, or not requested>` |
| Electrical measurements | `<task-owned check and report>` | `<limits, units, strictness, conditions and missing-data rule>` |
| Reproduction / transfer | `<receipt/comparison>` | `<scope and tolerances, or explicitly not requested>` |
| Workflow checks | `<scaffold/ready/handoff reports>` | `<actual checks and remaining gaps>` |

- Update `run.json` with evidence links and independent execution, electrical,
  model and delivery conclusions. Do not change frozen requirements to pass.
- Return actual check reports, failed attempts, warnings, budget consumed and
  unresolved limitations. Keep exact integrity values in machine receipts.
- Report the recommended candidate, its retained run and next action.
- The main agent must review the actual package before accepting a handoff or
  starting the next stage. A textual success summary is not the evidence.
- After review, close the run through the standard helper. Preserve sealed
  originals; later corrections are linked amendments.
