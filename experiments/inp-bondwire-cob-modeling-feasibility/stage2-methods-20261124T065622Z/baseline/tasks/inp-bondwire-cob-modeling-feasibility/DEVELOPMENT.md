# Development and readiness: inp-bondwire-cob-modeling-feasibility-r1

The [task contract](instruction.md) and [verification plan](verification-plan.md)
are draft plans. The confirmed initial research direction is 1–110 GHz,
single-ended, with an idealized ceramic baseline and complete physical return.
Specific dimensions, materials, interface details, cost limits and the actual
ADS environment remain unresolved as recorded in the contract.

The requested four stages remain inside one feasibility task: theory, method
investigation, baseline modeling/verification, then optional bounded
sensitivity. A stage handoff does not authorize the next stage. The selected
`ads-generic` route is an engineering route, not an official benchmark runner.
No native workspace, model, simulator result, or verification result is created
by this package. Environment checks, authorized work packages, frozen run
baseline, numerical criteria and required evidence remain pending.

Before native execution, follow the repository engineering task and workspace
workflows. Record the selected stage as `modeling-feasibility` to match
`task.toml`; select a block key and model policy from the actual plan, prepare
the stable workspace and fresh run, and complete scope and environment checks.
The project instructions own the actual lab selection and readiness steps.
The user may explicitly enable `engineering-learning` for a later work package.
