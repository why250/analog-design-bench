---
name: configure-ads-environment
description: Plan, select, configure, or preflight an ADS environment, including existing instances, engineering workspace organization, MCP connections, and model bindings. Use independently or when an analog task needs an ADS environment contract; circuit synthesis and optimization are outside this skill.
---

# Configure ADS Environment

Prepare a usable ADS environment or an honest plan for one. Preserve existing engineering
structure and working connections while separating requirements from observed readiness.
This skill runs independently; it does not require another task-authoring skill or repository.

## Prerequisites and support

Planning requires only the task and permitted environment information. Setup and preflight
require access to a user-supplied, licensed ADS installation on a platform supported by its
installed version, plus the selected automation route and separately supplied models/PDK.
No ADS binaries, proprietary technology or host-specific launcher are bundled. Discover
available capabilities before dependent operations; unavailable native checks remain pending.
Use the evidence levels below to verify the actual outcome of the requested mode.

## Choose the authorized mode

| Mode | When selected | Permitted outcome |
| --- | --- | --- |
| Plan | Default for task authoring, or when only an environment contract is requested | Inspect permitted configuration and documentation; return requirements, selected references, and pending checks. Do not modify MCP, create native projects, start ADS, or run simulation. |
| Setup | The user requests environment setup or configuration | Apply the confirmed instance/profile, merge necessary configuration, and create required engineering scaffolding within the authorized scope. Preserve unrelated settings and source. |
| Preflight | The user requests checks, or setup scope already includes them | Perform only authorized checks against the intended existing instance and report each check level independently. This does not implicitly authorize setup, a new ADS process, or simulation. |

Use the request's existing authorization without asking again for routine operations already
covered. Setup authorization is not permission to optimize a circuit or conduct a study.
Simulation, extraction, or circuit changes need their own explicit task scope. Starting a
headless instance consumes process and potentially license resources; keep it within the
selected setup scope rather than silently starting one when an existing session is absent.
Follow the destination's GUI-consent rules and keep any GUI inspection or operation within
current task authorization. Offer documented manual steps when appropriate; task authoring
alone does not authorize GUI work.

## Accept semantic inputs

Use the caller's or user's existing format; no cross-skill JSON schema is required.
Collect the following only as needed for the chosen mode:

- Scope and mode, requested readiness level, existing authorization, and deferred actions.
- Task identity/revision and next work package when an authoring workflow supplies them.
- Selected workflow/version, frozen contract/input references and destination phase checks,
  when supplied. Reuse the task's declared route rather than inferring a new one.
- ADS version constraints, required features, analysis types, and expected outputs.
- Existing environment profile, selected MCP binding or other route, and approved launcher.
- Existing workspace, library/cell/view identities, host roots, and model/PDK dependencies.
- Intended engineering layout and source ownership, including an existing project to retain.

Prefer an existing profile and launcher to a new connection pattern. Do not assume that a
connector label, local drive, installed version, license, or discovered session is the intended
one. Ask a few focused questions only when required choices cannot be inferred; keep other
unknowns pending and continue independent planning. Never fill gaps with invented observations.

## Read only the relevant bundled references

- [ADS environment fields, models, and evidence](references/ads.md): profile collection,
  portable/private/observed layers, parameterized model validity, and source-to-result evidence.
- [ADS engineering workspaces](references/ads-workspaces.md): stable engineering roots,
  native project structure, manifests, copies, frozen inputs, run isolation, and reproduction.
- [ADS MCP configuration and session selection](references/ads-mcp.md): existing bindings,
  concrete local/SSH configuration templates, encoding, discovery, attachment, and check levels.

These references are bundled and self-contained. Follow existing destination conventions when
they differ; do not require a particular repository guide, host, path, or external setup skill.
Use the MCP reference when MCP is selected; supporting other routes does not replace a working MCP.

## Apply or check the selected environment

1. Identify the intended instance, version, workspace, and route from existing evidence.
   Record discrepancies between the configured target and observed state before dependent work.
2. In plan mode, define prerequisites and stop at the environment contract. In setup mode,
   review the relevant reference and merge only required configuration or scaffold changes.
   Keep actual host roots, credentials, private model paths, and session bindings private.
3. For authorized checks, discover actual supported tools and installed-version documentation.
   Preserve the approved launcher and selected transport. Failed or absent APIs are evidence
   to diagnose, not justification for invented commands or claims of completed operations.
4. Preserve source workspaces and unsaved designs. Copies need consumer-side input checks;
   a transfer exit status or matching directory tree does not establish usable native source.
   Confirm the actual tool execution host independently of the agent's location. One executor
   owns writes to a native workspace at a time; use owned independent copies for parallel work.

Report the following layers separately, each with its actual evidence and unresolved limits:

| Check level | What its evidence establishes |
| --- | --- |
| Configuration | The intended client/profile is selected and required values are present. |
| Transport | The selected MCP or other route initializes and exposes its actual capabilities. |
| Documentation | Available documentation and schemas correspond to the selected tool/version. |
| Session | The intended existing ADS process is discovered and attached with matching identity. |
| Workspace | The actual selected library, views, and consumer-visible paths match the task. |
| Models | Actual bindings, samples, domains, includes, and warnings are known for the intended work. |

A configured server is not a connected session; a connected session is not verified models.
Leave unperformed checks pending. Use the destination's established status vocabulary, and
distinguish failure, missing evidence, model limitation, and a successful observation. Existing
datasets may support observations; generating a new simulation needs explicit simulation scope.

## Return an environment handoff

Return a concise record in the destination's preferred format, including:

- Selected instance and version constraints or actual observed version, with the evidence type.
- Preserved automation route and private profile/configuration reference.
- Portable engineering layout and native workspace/library/cell/view identities, if applicable.
- Check-level status, observation time, evidence references, and changes actually applied.
- Unresolved items, their owners or resolution steps, and the next authorized action.

Keep portable requirements, private execution details, and observed preflight results separate.
Do not report electrical acceptance, model qualification, or completed reproduction from setup
alone. The handoff may state readiness for a later stage while retaining pending prerequisites.

Use the destination's initialization, execution-readiness and delivery checks when present.
Passing a skeleton check with pending native/model observations is not execution readiness.
Return observation evidence and the next gate in a brief usable without prior conversation.
When incorporated into a later design result, keep execution completion, electrical outcome,
model applicability and delivery completeness independent; environment setup establishes
only its recorded checks. Preserve original evidence when making amendments.
