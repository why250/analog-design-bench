# ADS MCP schematic design and reproducible simulation

Use this workflow for native ADS schematic development, simulation and portable
engineering handoff. The selected task owns the electrical contract and permitted
models. Keep official benchmark execution under its existing runner contract.

First use the [engineering task workflow](engineering-task-workflow.md) to
resolve the task and route, freeze the delegation contract and select requested
deliverables. Retain the common run record and perform its preparation and
handoff checks alongside this software-specific procedure. Use one writer for
the primary native project and verify the actual ADS process host and files.

Use the [engineering workspace layout](engineering-workspace-layout.md) for
task ownership, stable cross-host paths, run storage and migration. New tasks
use `workspaces/<task-id>/`; a run timestamp belongs below `results/`.
For reusable InP logic cells and their receiver-load checks, use the
[ADS InP digital workflow](ads-inp-digital-workflow.md).
The [nonideal LPF workspace](../workspaces/inp-passive-lpf-65g-nonideal-lc-feasibility/README.md)
implements that layout with a portable `project.toml` and task-owned tools.

The first implemented example is the [ideal LPF workspace](../workspaces/inp-lpf/README.md).
It owns its synthesis, element values, commands and numerical results. The
[rebuild script](../workspaces/inp-lpf/tools/rebuild_ads.py) and
[independent analysis](../workspaces/inp-lpf/tools/analyze.py) are task-specific
implementations; adapt and verify them for a different circuit.

For a guided explanation of the electrical decisions and learner-visible
checkpoints, see the [LPF design learning notes](../workspaces/inp-lpf/design-learning-notes.md).
For a new low-pass filter, plan and author the design tasks using the
[task-first LPF workflow](ads-lpf-task-workflow.md). Execute the selected task
with the shared staged runner and retain the reviewed input for the next task.

## Client configuration and tool availability

The ADS MCP server must be loaded by the client that will call it. Codex,
Claude Code and Cursor use separate project configuration files; registering
the server in one client does not create tools in another, and a sub-session
inherits only its parent client's tool catalog.

- Codex reads `.codex/config.toml` (`[mcp_servers.ads2027]`). The repository
  keeps this machine file ignored.
- Claude Code reads the project `.mcp.json` (`mcpServers.ads2027`). Use the same
  SSH launch command and remote `ads-mcp.exe` as the Codex entry; the file is
  ignored by the root `.gitignore` because it carries the host alias and ADS
  installation path. See the client template in the
  [ADS environment companion](../.agents/skills/configure-ads-environment/references/ads-mcp.md#claude-code-project-mcpjson-template).
- After creating or changing the project config, restart or reload the client
  session and approve the project MCP server. A configured file, a successful
  SSH exit, or a connected session is not proof that the tools are exposed;
  verify `list_sessions` and a read-only `execute_python` before design work.

When native registration is unavailable, a local JSON-RPC client over the same
SSH launch can bridge the ADS MCP (the task-owned `tools/ads_mcp.py` or the
ignored `.local/ads_mcp_client.py`). That fallback adds PowerShell, SSH and
process-management layers: every invocation starts a new `ads-mcp.exe`, so the
Python REPL does not persist across calls; scripts must be self-contained and
long solves use a detached driver plus log/status polling. Prefer the native
client tools when they are available, and keep the bridge only as a fallback.

The actual host alias, installation path and selected sessions stay in ignored
local notes; the portable workflow names capabilities, not machine bindings.

## Establish the task and execution boundary

1. Read the selected task revision, ordered DUT ports, testbench-owned circuitry,
   permitted devices, frequency boundaries and exact acceptance comparisons.
   Identify the engineering deliverables and the separate official verification
   status from the task documentation.
2. Discover ADS sessions with the MCP session tools. After connecting, inspect the
   active workspace and make a small read-only Python call to establish the ADS
   process host, working directory and accessible project paths. Session IDs and
   machine configuration belong in ignored local notes.
3. Check repository access from the ADS process before creating directories. The
   shell host and ADS host may differ; the same drive letter does not establish a
   shared filesystem. Confirm an existing parent on each host and parameterize the
   project and output paths.
4. Read the ADS MCP documentation for execution modes, AEL bridging and schematic
   construction before significant design work. Prefer supported Python APIs,
   then documented AEL operations. Select classic or Nexus simulation according
   to the requested workflow and the available tools.

## Build an editable, portable source

- Complete [Start another ADS task](engineering-workspace-layout.md#start-another-ads-task)
  before the first native build. When creating a new native ADS workspace and
  local libraries, follow [ADS Project Kit integration](ads-project-kit-integration.md):
  preflight the ADS runtime (`preflight_ads_runtime()`), create the workspace and
  role libraries with `create_ads_project()` (wrapping `ads_project_kit.create_project()`),
  and verify native readiness with `validate_ads_project()`. Do not duplicate
  `de.create_workspace()` / `de.create_new_library()` setup or fall back
  silently when `ads_project_kit` is missing.
- Create the editable ADS project under its
  declared `workspaces/<task-id>/ads/` path and resolve paths from `project.toml`.
  Check for unsaved designs before switching the ADS session's active workspace;
  never close an already-open workspace to create or validate a project.
- For tasks that attach an external PDK technology (`attached_tech_lib_name`) or
  layout/EM technology, pass `setup_schematic_tech=False` to `create_ads_project()`.
- Keep the DUT, its symbol and its simulation testbench as separate views. Give
  the DUT explicit ordered terminals; place sources, reference terminations and
  global ground connections in the testbench according to the task contract.
- Build using connectivity-aware placement where available, commit connectivity,
  save the native views and inspect the generated netlist. Verify component
  models, units, terminal order, node connections and controller sweeps against
  the intended circuit.
- Retain a parameterized reconstruction script with the native OpenAccess
  library. Use project-relative library definitions and installation environment
  variables. Include required hidden library metadata such as `.oalib`.
- Release OA locks before taking a portable snapshot. Exclude lock files and
  session preferences from versioned engineering source.

## Simulate and verify the selected contract

- Use a fresh run directory. Retain the schematic-generated netlist, its SHA-256,
  source snapshots, simulator log, raw dataset and simulation settings. Record
  actual software versions with the run evidence.
- Simulate exact acceptance frequencies and include task-appropriate coverage
  between them. Refine suspected extrema. When a synthesis formula supplies
  extrema or a continuous-band bound, use it with the simulator samples to
  justify the reported worst case.
- Export sampled complex S parameters with their reference impedance and ordered
  ports. Preserve complex values for independent checks and Touchstone export.
- Apply strict and inclusive thresholds as specified. Require finite, complete
  results and adequate frequency coverage before declaring success.
- Cross-check the simulated network using an independent calculation appropriate
  to the circuit. For ideal passive reciprocal networks, also check reciprocity,
  power conservation and the low-frequency limit.

The LPF workspace documents the implemented sweep and cross-check method.
Its verification results establish that circuit and task revision only.

## Screen cached-model circuit variants by netlist

When a fixed testbench and extracted PCell EM samples already exist, screen many
device sizes without editing the DUT:

- Generate the top-level testbench netlist once, then replace only the intended
  per-instance parameter literals. Keep topology, ground pins, model bindings and
  the kit include unchanged. Use a fresh output directory per case and retain the
  netlist actually simulated.
- Run `hpeesofsim` per netlist. From the ADS application's Python, a subprocess
  needs `stdin=subprocess.DEVNULL`, stdout and stderr redirected to files, and
  `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP`; otherwise Windows can raise
  `WinError 6` (invalid handle). Parallelism is license- and host-dependent; start
  with a small worker count and require a valid dataset from every case.
- Read the dataset with `keysight.ads.dataset`. Combine passband and refinement
  blocks only after sorting by frequency, and read exact checkpoint frequencies
  from their own block. Record the sample count and refinement method.
- A standalone ADS Python can fail to import `keysight.ads.dataset` with a DLL
  load error. Before the import, add the ADS installation's `bin` and
  `lib/win32_x86_64` directories with `os.add_dll_directory`, set `HPEESOF_DIR`
  to the intended installation, or run inside the ADS MCP session. Do not infer
  success from an exit code alone.
- Netlist continuation lines must end with exactly one backslash. Do not build
  them by nested string escaping; keep a validated controller block in a template
  file and insert that block into generated netlists.
- A size without a cached sample is not a circuit result. It attempts an
  on-demand extraction and a direct simulator may fail with a Gemx error. Use the
  open-application extraction path documented in the Windows EDA project's
  `ads2027-pcell` skill, `references/parameterized-em.md`, and verify the sample
  index before screening.

This is a screening aid. A selected candidate still needs a fresh run with its
netlist, simulator log, native dataset, model bindings, source hashes and a
model-validity review.

## Toolkit geometry and Momentum candidate screening

Use the repository skill
[`rf-inductor-toolkit-design`](../.agents/skills/rf-inductor-toolkit-design/SKILL.md)
to apply this staged design workflow to a requested task.

For Toolkit-generated on-chip inductors, start with the task-owned
[automation-chain overview](../workspaces/rf-inductor-120ph-65g-em/docs/reproduce.md#reusable-automation-chain).
It connects parameterized artwork/native construction, validated application
export, Momentum full-wave solving, full-network L/Q extraction and recorded
candidate ranking. The same guide owns the detailed commands and handoff
formats; keep that implementation documentation in one place.

This is a staged implementation for an assumed-stack 120 pH research task.
Application export and observation-manifest assembly remain explicit handoffs.
Reuse for another task requires its own stack, physical return, port/excitation
contract and adapted tool checks. A completed candidate screen is separate from
qualified continuous-band device acceptance and parent-circuit integration.
The original study is closed; these instructions do not restart it.

## Transfer and reproduce

When the ADS host cannot access the repository, use the available authorized
tools to relay the required source and return the native project plus evidence.
The verified LPF handoff used ZIP bytes encoded as base64 through ADS MCP,
followed by local decoding and extraction.

1. Create an archive with paths relative to the project root. Include the native
   design, required library metadata and selected run evidence.
2. Record relative file paths, byte sizes and SHA-256 values in a manifest. Verify
   the archive hash after transfer, then verify every extracted file against the
   manifest. Keep extraction targets within the intended project directory.
   These checks establish transfer integrity; electrical acceptance comes from
   the retained simulation and independent analysis.
3. Keep generated datasets, exports, logs and transfer staging in the workspace's
   ignored `results/` directory. Preserve editable source and reconstruction
   tools in the development workspace. Keep hostnames, absolute machine paths,
   installed versions and probes in applicable ignored `.local/` notes.
4. Rebuild into a fresh ADS workspace and rerun the simulation. Compare frequency
   arrays, complex results and the generated netlist identity. Record the actual
   differences or tolerances achieved; bit-identical output is an observed result
   of the LPF reproduction, not a guarantee for other circuits or installations.
5. Recheck transferred data locally using the retained analysis script. Preserve
   the original run evidence when producing derived checks or presentation files.

## Inspect the engineering handoff

Complete the [layout handoff checks](engineering-workspace-layout.md#check-the-layout-before-handoff)
alongside the electrical checks below.

Open the native design and render exported schematic pages and plots. Check
terminal labels, annotations, units, margins and the full response shape. A native
print can need explicit bounds and smaller annotation text to keep long numeric
values legible; the LPF script's optional PDF export includes those settings.

The workspace README remains the circuit-specific entrypoint. Link its evidence
and reproduction instructions from the task's development record, preserving the
distinction between engineering verification and official benchmark acceptance.
