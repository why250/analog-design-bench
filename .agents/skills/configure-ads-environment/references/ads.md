# ADS environment fields, models, and evidence

Use this self-contained reference to describe or check an ADS environment. Apply the
plan, setup, or preflight boundary selected by this skill's entrypoint. Listing prerequisites
does not perform them, and environment setup alone does not authorize circuit simulation,
model extraction, source changes, or GUI use beyond the current task's explicit scope.

## Retain concrete engineering and connection methods

Preserve the selected native project structure, manifest, launcher and MCP binding
when they already exist. Portability parameterizes machine-specific values; it does
not replace a working configuration with an unspecified interface.

- Use [ADS engineering workspaces](ads-workspaces.md) when the task creates, copies,
  extends or hands off an ADS project. It supplies a concrete portable layout and
  manifest example even when the destination has no engineering guide.
- Use [ADS MCP configuration and session selection](ads-mcp.md) when the chosen
  instance is reached through MCP or MCP setup is requested. It retains local and
  SSH stdio patterns, encoding requirements, session discovery and check levels.
  Other interfaces remain available when the task actually selects them.

Carry the selected workspace/manifest and environment-profile references into the
environment handoff or calling task. If MCP is required or configured, preserve
its approved launcher; an alternative route is a separate choice, not an implicit
effect of describing other supported routes.

## Reuse or collect environment information

Inspect an existing user-approved configuration first. Preserve its instance selection,
working paths, model bindings, and supported automation route unless the task requires a
change. Record obsolete or conflicting information instead of silently replacing it.
When no configuration exists, collect the fields below and leave unknown values pending.
Do not assume a connector, installation, version, host, license, or currently open view.

Keep three layers distinct:

- Portable requirements: ADS version constraints, required analyses and features, native
  source organization, model capabilities, expected exports, and measurement conditions.
- Private execution profile: selected instance, connection binding, host filesystems,
  workspace roots, license access, installed PDK/library paths, and selected design views.
- Observed preflight: actual loaded version, workspace, resolved model files, available
  features, warnings, observation time, and evidence. Configuration alone proves none of these.

The JSON below is an illustrative record shape, not an ADS SDK, MCP product contract,
or required project schema. Adapt an existing format rather than introducing a competing one.
Unknown values stay `null`; empty lists remain unconfirmed inventories until checked.

```json
{
  "portable_requirements": {
    "tool_family": "ADS",
    "version_constraint": null,
    "analysis_types": [],
    "required_exports": []
  },
  "private_profile": {
    "instance_selector": null,
    "automation_route": null,
    "connection_binding": null,
    "execution_host": null,
    "workspace_root": null,
    "execution_root": null,
    "host_filesystem_mapping": null,
    "required_license_features": [],
    "pdk_model_bindings": [],
    "selected_design": {
      "workspace": null,
      "library": null,
      "dut_cell_view": null,
      "bench_cell_view": null
    }
  },
  "observed_preflight": {
    "status": "pending",
    "observed_at": null,
    "actual_version": null,
    "actual_workspace": null,
    "evidence": []
  }
}
```

Choose an automation route supported by the selected instance: MCP, documented API,
CLI, or user-performed manual steps. Preserve an existing route and launcher. In plan mode,
describe missing setup without performing it; in setup or preflight mode, apply only the
configuration or checks covered by the current authorization. No other skill is required.

## Execution prerequisites to record, in order

In plan mode, retain these checks as pending. In other modes, perform only checks covered
by current authorization and record what was actually observed.

1. Identify the intended instance and version, discover its actual capabilities, and name
   the chosen automation route. Keep unobserved license and feature availability pending.
2. Resolve the source and output locations in the ADS process host's filesystem. Identify
   transfer or mounting boundaries; a local shell path may not exist for the ADS consumer.
3. Identify the active workspace, library, DUT cell/view, symbol, and bench cell/view.
   Distinguish alternatives and historical views; preserve unsaved or shared source work.
4. Inspect library resolution and generated top-level model includes before proposing
   model renaming or edits to supplied PDKs. Record the files the simulator actually uses.
5. Inventory model provenance, supported geometry and conditions, interpolation policy,
   extracted samples, frequency domain, return structure, and unresolved warnings.
6. Define analysis settings, exact measurement checkpoints, candidate-specific coverage,
   DC or low-frequency reasoning, required raw outputs, and fresh task-owned run locations.

If a call fails or an API is unavailable, consult the selected instance's supported tools
and current documentation. Record the failure; do not invent fallback commands or report
an operation as completed. A different execution route needs its own verified prerequisites.

## Parameterized and EM-backed models

Identify the complete parameter assignment, generator/model family, ground and return
connections, margins, vias, and extraction settings. Equal nominal sizes need not mean
equal geometry or equivalent extracted samples. With interpolation disabled, require a
matching sample or leave extraction pending; do not substitute an ideal or assumed model.
Distinguish reused data, requested extraction, and successfully retained new extraction.
Geometry acceptance is not foundry qualification. Keep model-band and accuracy warnings
attached to candidate conclusions; sampled circuit agreement does not qualify full-filter EM.

## Source-to-result evidence

Preserve the selected editable candidate and bench, full parameter values, generated
netlist, resolved models and samples, settings, simulator log, native dataset, and exports.
Bind the source to that netlist and the netlist/model assignment to that dataset; reject
stale or mixed-run evidence. A successful transfer needs consumer-side input verification.
When screening uses netlist variants, separately reconstruct the required native source
and re-export it before claiming native-source delivery. Keep reproduction, electrical
acceptance, and model validity separate. Private profiles and restricted dependencies stay
outside shareable task content; retain portable requirements and unresolved prerequisites.
