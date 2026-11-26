# Virtuoso schematic and Spectre engineering workflow

This workflow covers editable Virtuoso schematics and source-derived Spectre
simulation with retained evidence. It uses the common engineering run lifecycle.
Its initial verification target is an ideal analogLib two-port. PDK qualification,
layout, extraction, EM and ADE Maestro need their own documented task procedures;
this workflow's implementation status does not establish those capabilities.
The current preparation branch accepts `source` and `simulation` deliverables;
it rejects layout and EM execution requests.

## Select the existing task and environment

Read the task, its `engineering.toml` and the
[engineering entrypoint](engineering-task-workflow.md). Use the AI EDA Lab
`plan_environment` gate with this repository's absolute path and actual calling
client. Follow its setup action only when required. Preserve the selected
independent product MCP and installation. Do not register a returning project
again or substitute a verification-only host.

Keep portable requirements in the task. Keep the selected versions, project
root, SSH alias, MCP name and session observations in ignored local bindings.
The task binding is `.local/virtuoso-projects/<task-id>.json`; its
`required_tools` identifies the selected Virtuoso and Spectre versions rather
than hardcoding deployment versions in this guide. The project-wide lab binding
remains `.local/eda-lab.json`.

The helper selects the environment and creates local records only:

```powershell
python scripts/engineering_runs.py environment --task tasks/<task-id> --client <client>
python scripts/engineering_runs.py prepare --task tasks/<task-id> --slug smoke --client <client> --block-key <BLOCK> --dut-cell <BLOCK>_Main --dut-ports rfin,rfout,gnd --model-policy unrestricted-ideal --cpus 1 --memory-gib 2
```

Use the returned workspace, run and private receipt. These commands do not
launch Virtuoso, create remote files or run a solver. Preparation freezes the
task, nested inputs, workflow and environment selection; it leaves readiness
in draft. Review and populate the returned delegation brief before execution.

## Stable native workspace and ownership

A new Virtuoso workspace uses schema version 2 and `eda = "virtuoso"` in
`project.toml`. Its static task/design identity is separate from dynamic runs:

```text
workspaces/<task-id>/
  project.toml
  README.md
  inputs/task-spec/
  virtuoso/                 # Editable native libraries and isolated definitions
  docs/
  tools/
  results/<run-id>/          # Frozen inputs, logs, data, reports and run.json
```

Use the same relative layout on the selected host. Resolve absolute roots from
the private receipt; matching directory names do not prove shared storage.
Name libraries and cells explicitly in the manifest. Preserve completed runs
and existing native views. Assign one native writer to the selected library.

Before a first remote write, verify the approved root, ownership, real path,
available space and consumer-visible files. Select the intended Virtuoso
process and version. A bridge server's working directory is separate from
the Virtuoso process directory and the Spectre execution directory.

Use task-owned library definitions and netlist directories. Establish how a
new library will be registered without changing an unrelated project's
`cds.lib` or `lib.defs`. Session-only registrations must be restored and their
effect verified. If isolation requires another session, establish that target
before editing. Do not switch an active project, dismiss unknown dialogs,
delete locks or repeat a timed-out mutation with an uncertain outcome.

## Actual preflight and source preparation

Use the selected Bridge's own current Virtuoso/Spectre skills and installed
Cadence documentation for version-specific APIs. Record the actual package
and target observations privately. Verify function signatures, ideal device
masters, terminal names, CDF properties and netlisting semantics before use.
Tool discovery and version queries alone do not establish a licensed run.

Retain separate observations for configuration, transport, current-agent tool
access, target identity, read-only SKILL, workspace, models and solver. Check
current aggregate demand against the lab's planning limits. One classic
Spectre job is the initial ideal smoke scope unless the task says otherwise.
Required mode licensing is established by the actual bounded simulation.

Populate the common preflight and readiness fields with evidence for the
authorized next package. An ideal-only model conclusion may be conditional
on the native-device and solver smoke check; state that bounded scope and
remaining checks explicitly. Run the common `ready` check before executing
the candidate. Static readiness does not grant permission beyond the brief.

Build only new task-owned views, or modify an explicitly selected owned view.
Read back connectivity and full-precision parameters. Review native check
diagnostics, save, close only views opened by this work, reopen and inspect.
Do not rely on a screenshot as connectivity or save evidence. Computer Use
and screenshots require explicit task-specific user consent.

## Native netlist, simulation and results

Generate the actual circuit input from the saved native schematic using a
documented Cadence netlister. Retain the generation settings, invocation,
diagnostics and resulting files. Batch `si` netlisting is a supported route
when confirmed for the selected installation and isolated library definitions.
Do not substitute a separately handwritten circuit and claim native export.

A generated circuit-only deck may be included unchanged by a retained analysis
wrapper. Inspect the consumed hierarchy, parameters, ground, bench-owned ports
and model includes against the native source. Document which analysis settings
were added outside the native view. Use unique per-attempt output directories.

Invoke the independent product MCP for the selected Spectre mode with the
brief's job and timeout limits. Inspect the actual simulator outcome and log;
an executable query, process exit or nonempty data alone is insufficient.
Preserve raw data even if parsing or export fails. Do not resubmit an uncertain
job until its original state has been resolved.

For two-port work, retain frequency and all four complex S entries with explicit
port ordering, reference planes and normalization. A transient-only waveform
reader cannot establish SP export support. Use a documented SP result file or
parser, and validate the exported values against the raw dataset. Keep the
native data, CSV and Touchstone tied to the exact consumed input and run.

The task owns electrical limits, exact checkpoints, continuum coverage and
numerical tolerances. Compare the ideal smoke against its independent ABCD
calculation, then repeat from the saved/reopened source. Smoke success is a
toolchain result; a full filter requires its separate electrical checks.

## Review and closeout

Use the common `run.json` schema and evidence roles. Simulation deliveries
require native source, consumed netlist, simulator log, raw data, measurements
and task-owned check reports. Include a reopenable native-source package,
library definitions and a machine-readable input/evidence inventory.

```powershell
python scripts/engineering_runs.py check --run <run-directory> --phase handoff
python scripts/engineering_runs.py close --run <run-directory>
```

The main agent reviews the actual source/result chain and measurements before
closeout. Keep execution, toolchain, reproduction, electrical, model and delivery
conclusions distinct. A failed or interrupted package retains its cause and
available artifacts with incomplete delivery; never label missing checks passed.
Closeout updates the workspace entrypoint. Preserve sealed runs and put later
corrections or interpretations in linked amendments. Exact integrity values
belong in machine receipts, not narrative reports.
