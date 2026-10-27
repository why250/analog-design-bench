# ADS MCP schematic design and reproducible simulation

Use this workflow for native ADS schematic development, simulation and portable
engineering handoff. The selected task owns the electrical contract and permitted
models. Keep official benchmark execution under its existing runner contract.

The first implemented example is the [ideal LPF workspace](../workspaces/inp-lpf/README.md).
It owns its synthesis, element values, commands and numerical results. The
[rebuild script](../workspaces/inp-lpf/tools/rebuild_ads.py) and
[independent analysis](../workspaces/inp-lpf/tools/analyze.py) are task-specific
implementations; adapt and verify them for a different circuit.

For a guided explanation of the electrical decisions and learner-visible
checkpoints, see the [LPF design learning notes](../workspaces/inp-lpf/design-learning-notes.md).

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

- Create a task-owned workspace under the relevant development workspace. Check
  for unsaved designs before switching the ADS session's active workspace.
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

Open the native design and render exported schematic pages and plots. Check
terminal labels, annotations, units, margins and the full response shape. A native
print can need explicit bounds and smaller annotation text to keep long numeric
values legible; the LPF script's optional PDF export includes those settings.

The workspace README remains the circuit-specific entrypoint. Link its evidence
and reproduction instructions from the task's development record, preserving the
distinction between engineering verification and official benchmark acceptance.
