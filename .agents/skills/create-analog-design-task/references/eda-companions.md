# EDA companion selection and handoff

The task-authoring skill owns requirements, interfaces, measurements, execution
boundaries, deliverables and readiness. A software-specific companion owns its
product's instance selection, engineering layout, connection configuration and
preflight procedure. This is a workflow relationship between independent skills,
not automatic inheritance or an additional host configuration schema.

## Select one relevant companion

Use the user's selected software and existing environment binding. Discover a
matching skill through the host's available-skills catalog or the destination's
declared skill locations. Read its actual `SKILL.md` from the discovered path.
Do not assume the original project's checkout, a fixed sibling path, a global
installation, or a particular MCP server name.

An existing task/run's declared software and workflow take precedence over keyword
inference. If the destination declares a route reserved or unimplemented, preserve a
useful draft and its missing prerequisites; do not silently redirect it to another EDA.

| Selected software | Known companion | When to use it |
| --- | --- | --- |
| ADS | `configure-ads-environment` | ADS engineering structure, existing instance/profile, MCP or other selected connection, setup planning or authorized preflight |

For other EDA software, choose a genuinely available matching skill by its
description; do not invent a skill name or load every installed EDA skill.
If none is available, continue the generic task contract and record unresolved
software-specific work. An absent companion does not prevent a draft or a
task ready for preflight. Explain that no companion was used; do not claim a
native workspace, connection, verification result or live capability exists.

## Pass the minimum relevant context

Give the selected companion:

- Task identity, revision, engineering stage and selected software/version or
  required compatibility. Include the next planned work package.
- Selected workflow/version and frozen contract/input references for the execution
  boundary. Verify receipt at the intended consumer before dependent native work.
- Required analyses, models/PDK, outputs, electrical interface and data needed
  to judge environment suitability.
- Existing native project and selected views, the environment-profile reference,
  chosen instance, established layout and connection/launcher, if any.
- The target project scope and its actual instructions or formats relevant to
  the environment; no source-project documentation is required.
- The mode and existing authorization: task-authoring plan, environment setup,
  or specific preflight checks. Separate access restrictions and private data.

Default to the companion's planning/authoring mode when called during task
creation. Reading or delegating to a companion does not authorize installing
software, rewriting a working profile, starting an EDA process,
consuming new licenses, operating a GUI or executing circuit simulations.
Carry forward separately granted authorization instead of asking for it again.

## Incorporate its result without changing authority

Request these semantics, adapting to the destination's existing formats rather
than imposing an inter-skill JSON schema:

| Result | Treatment in the task |
| --- | --- |
| Portable environment requirements | Record software compatibility, analyses, required features/models and exports. |
| Selected native organization | Record a relative layout or manifest reference and actual source identifiers when known. |
| Private binding reference | Keep host roots, launcher/connection settings and restricted model locations private; preserve the selected route. |
| Completed checks and evidence | Distinguish declarations, generated config, observed process/workspace facts and verified capabilities. |
| Gaps, prerequisites and next action | Assign investigation/setup/preflight work, budget, owner and unresolved disposition. |
| Readiness | State which next work package can start; never convert a configuration draft into verified environment availability. |

The companion does not redefine electrical targets, design freedoms or acceptance
authority. If it discovers a conflict requiring a material task change, return
the decision to the task-authoring flow with the affected requirements identified.
An environment smoke check is not circuit acceptance or model qualification.

## Extend to another EDA product

Create an independently discoverable software-specific skill when there is real
reusable setup knowledge to maintain. Keep product procedures, examples and
version boundaries in that skill. Implement the same handoff semantics and
distinguish planning from authorized setup/preflight. Add an explicit routing
row only after that companion actually exists. Do not duplicate the task-authoring
flow, require a reverse dependency on it, or add empty skills for future products.
