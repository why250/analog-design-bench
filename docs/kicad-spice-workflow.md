# Manual KiCad drawing and task-compatible SPICE

Use this workflow to reconstruct a selected SPICE circuit manually in KiCad,
understand its topology, and simulate the schematic-derived netlist with the
task's existing benches. The schematic becomes an editable circuit source;
the task continues to own its interface, permitted devices, stimuli and scoring.
This is a learning and development workflow, not a model evaluation protocol.

Read the [Windows environment guide](windows-official-environment.md) for the
pinned simulator/PDK and container lifecycle, and the
[task development guide](task-development.md) for task contracts. Keep reference
circuits, operator instructions and hidden verifier material outside blind
solver input. Reference-guided reconstruction is not a blind model attempt.

When available, use the [structured electrical contract](electrical-design-contract.md)
to look up ordered ports, device constraints, metric criteria and bench coverage.
Its offline checks establish consistency of the declared inputs; validate the
actual schematic export and circuit separately as described below.

## Current implementation

The [NMOS LDO KiCad guide](../workspaces/nmos-ldo/kicad/README.md) owns its drawing
instructions, symbol settings, commands and export troubleshooting. Its native
XAMP export has retained nominal simulation evidence. The remaining LDO core
and testbench still come from source netlists in that workflow.

`scripts/kicad_xamp.py` and `scripts/Invoke-KiCadXampSimulation.ps1` are NMOS XAMP
tools: they select one sheet, six amplifier ports, two LVT MOS models and a
source-netlist LDO core. `scripts/Invoke-LocalSimulation.ps1` also selects the
NMOS task/image. Changing a workspace or bench argument does not establish
support for another task. Full-schematic export and other-task integration
require their own implementation and evidence; this guide does not claim them.

## Establish the task and source boundary

Select the exact task revision and read its `instruction.md`, `task.toml`,
starter, netlist guide and public development benches. Record:

| Contract item | What to establish before drawing |
| --- | --- |
| Submission | Artifact path, top-level subcircuit name and ordered ports |
| External circuitry | Supplies, grounds, bias direction, loads, feedback and injection sources owned by the bench |
| Devices | Allowed model names, terminal order, parameter meanings, units and passive restrictions |
| Simulation | Public diagnostic coverage and the separate formal condition matrix |
| Provenance | Task revision and the selected source circuit's identity and SHA-256 |

A source may be a saved candidate, a reference design, or a completed attempt's
frozen `record/submitted-circuit.spi`. Copy the selected bytes into a learning
workspace and record the source; preserve completed attempt directories and
evidence archives as described in the [result layout](evaluation-results.md).
Keep the original task fixtures unchanged.

These two existing interfaces illustrate why adaptation is task-specific:

| Task | Required DUT interface | Bench-owned details |
| --- | --- | --- |
| [NMOS LDO](../tasks/sky130-nmos-pass-ldo-0p4v-pvt-mc/instruction.md) | `nmos_pass_ldo vdd vout vss vref ibias loop_out pass_gate` | External reference, current sink at `ibias`, output load and loop injection between two separate ports |
| [Five-transistor OTA](../tasks/sky130-ota-5t-gain40-pm60-noise50uv-pvt/instruction.md) | `ota_5t vss ibias vdd vinn vinp vout` | Current injection into `ibias`, input common mode, load and feedback/injection network |

The OTA interface is an onboarding example, not evidence of a completed KiCad
integration. Determine each task's actual conditions from its own contract.

## Draw and configure the circuit

Keep the project, symbols, editable source circuit and public development
benches in a Windows workspace under `workspaces/`. Put generated exports and
simulation data in that workspace's `results/` directory and ensure it is
ignored by Git. Use a project-relative symbol-library table so that the project
is portable.

1. Choose meaningful functional sheets. Keep DUT and Testbench separate, with
   explicit hierarchical interfaces. The Testbench drawing can explain the
   experiment while the original task bench remains the simulation authority.
2. Maintain a device lookup with source instance, sheet, KiCad reference, model,
   terminal-to-net connections, parameters and units. Preserve hierarchy paths
   when matching devices and nets; equal local names on different sheets do
   not establish an electrical connection.
3. Place symbols and wire every terminal from the selected source. For SKY130
   MOS wrappers, expose D/G/S/B and connect Bulk explicitly. Keep a DUT supply
   return such as `vss` as a port; connect it to global node `0` only where the
   bench specifies. Grounding it inside the DUT can bypass supply perturbation
   and invalidate a negative-rail PSRR experiment.
4. Assign usable simulation models and pin mappings to every exported device.
   Drawing fields alone do not configure SPICE output. Bind editable fields to
   the native exporter, then inspect the generated device code. The NMOS guide
   contains a validated Raw SPICE Element configuration for its LVT MOS models.
5. Follow the selected task's device guide. Its SKY130 MOS wrappers use `X`
   calls in D/G/S/B order and numeric W/L in micrometres under `scale=1u`.
   Preserve supported parameters separately: `nf`, `m`, `mult` and passive
   wrapper parameters such as `mf` are not interchangeable. Configure physical
   PDK passives where required; a bench's ideal load does not permit the same
   ideal primitive inside the DUT.

Add support for each needed device family before claiming export readiness.
The existing XAMP validator's fixed MOS parameter set is not a generic model
schema for every task.

## Export native SPICE and match the interface

Save the schematic before export. Use KiCad's **File -> Export -> Netlist ->
Spice Model** to export a DUT as a subcircuit for a separate simulation. Select
the DUT as the export root, and inspect which sheets and devices are included.
Keep the native output unchanged in a fresh result directory.

Read the native `.subckt` header rather than assuming its name or port order
matches the task. If necessary, add a small wrapper that exposes the task's
exact ordered interface and calls the native subcircuit in its exported order.
Reject missing, extra or ambiguous interface ports before simulation. Preserve
the native device lines; the wrapper only adapts the interface.

The resulting candidate `circuit.spi` must contain all user-defined DUT
subcircuits. PDK dependencies come from the selected pinned environment; avoid
dependencies on another workspace or a live source checkout. Keep task-owned
supplies, loads, injection sources and simulation controls in the bench. Follow
the task's model-loading convention so the original bench can select its PDK
corner; do not introduce machine-specific Windows model paths or a fixed DUT
corner. Internal instance names may differ when the task permits it, but keep
a mapping back to the source for review.

Use an independent native connectivity export, such as KiCad XML, to check
pins and saved parameter fields against the native SPICE output. Compare those
connections and parameters with the selected source as a separate check.
Agreement between two exports alone does not establish source equivalence.
XML is diagnostic evidence, not a replacement circuit generator.

KiCad documents [Spice Model export and hierarchical interface labels](https://docs.kicad.org/10.0/en/eeschema/eeschema.html#netlist-formats)
and the [CLI netlist formats](https://docs.kicad.org/10.0/en/cli/cli.html#schematic-export-netlist).

## Validate and retain the exact exported candidate

Keep these validation claims separate:

| Stage | Required evidence |
| --- | --- |
| Drawing/export | Every intended device, terminal, model, parameter and interface is present; exported values match saved fields |
| Source reproduction | Connections/parameters match the selected source, or intentional differences are recorded |
| Nominal diagnostic | The exact exported candidate runs with the selected public bench; measurements and simulation logs are retained |
| Formal verification | The selected task's original checker and complete electrical verifier ran on the exact candidate; reward and available per-check reports were inspected |

On a temporary copy, change one device parameter and confirm that the next
native export changes that device's value. This checks that editing the drawing
affects the actual simulation input. For a reproduction, also compare exported
and source-netlist simulations under the same bench, model set and conditions,
with declared comparison tolerances. An ERC pass or a successful export is not
electrical verification.

Retain saved schematic/project/library inputs, the selected source and bench,
unmodified native SPICE, connectivity export, interface wrapper, final candidate,
export commands, source-to-native instance mapping, input hashes and simulation
logs. Record task revision, image identity, actual conditions and whether any
part of the circuit still came from a source netlist. Use fresh result paths
and report missing evidence explicitly.

For local formal verification, pass the exported candidate explicitly to
`scripts/Invoke-OfficialTask.ps1` using `-Task`, `-Circuit` and a fresh
`-OutputDirectory` inside the learning workspace's `results/`. See the
[verification entrypoint](windows-official-environment.md#verify-a-circuit).
Omitting `-Circuit` selects the published reference, so it would not verify the
new schematic export. The NMOS local helper's `Verify` mode also continues to
read its workspace `circuit.spi`; do not confuse it with a later export.

Read `verifier/reward.json` and the available reports. A zero process exit code
or one successful nominal point does not establish formal acceptance. Local
schematic verification does not create a scored model campaign; formal model
attempts follow the [evaluation workflow](model-evaluation.md).

## Onboard another task

Apply the same stages while supplying that task's interface, device rules,
source mapping, public bench and original verifier. Keep reusable export and
validation behavior shared; isolate task-specific mappings instead of copying
an entire export/simulation runner per circuit. Model-evaluation registration
remains in the [shared runner profiles](shared-evaluation-runner.md), with
scoring in the original task.

Before marking a task ready, demonstrate its required device families, complete
DUT export, port-order adaptation, source comparison, parameter-edit propagation
and simulation of the frozen export. Label partial drawing support, hybrid
simulation, full-schematic simulation and formal verification separately. Do
not generalize one task's result to the rest of the benchmark.
