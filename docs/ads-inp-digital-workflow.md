# ADS workflow for InP digital circuits

Use this workflow for digital units implemented with an InP process in ADS.
Start from the task's logic function, electrical contract, and model scope.
Keep native source and run evidence in the task workspace. Use the shared ADS
workflow for tool access, setup, and replay. [Task development](task-development.md)
· [Engineering workspace layout](engineering-workspace-layout.md)
· [ADS MCP workflow](ads-mcp-workflow.md)

## Design and verify in stages

1. **Define the interface.** Write the truth table, or the state and transition
   table for a sequential unit. Specify pin order, polarity, signal reference,
   supplies, static bias, drive impedance, and output loads. Separate nominal
   logic levels from allowed input ranges and output windows. Identify the
   applicable timing, power, and operating conditions, and state which are
   acceptance limits or characterization results.
2. **Bind and check the technology.** Resolve the authorized PDK and models in
   the selected ADS runtime. Record the supported device types, legal
   geometries and passive parameters, terminal order, model sections, and
   available corners. Check that intended bias and switching states fall
   within the documented model and device operating ranges. Use targeted
   device benches to check current density, terminal voltages, dissipation,
   reverse junction bias, and any off-state or saturation assumptions that
   affect the topology.
3. **Build the primitive cells.** Reduce the Boolean expression to the gates
   needed by the topology. Give each reusable gate a native ADS schematic,
   ordered symbol pins, and a small standalone bench. Identify the supply and
   bias pins on the symbol. Compare generated instance terminals and model
   bindings with the intended circuit before connecting gates in a top level.
4. **Characterize each interface under load.** Test the full gate truth table
   with the intended upstream drive and downstream receiver or a justified
   load model. Check input current, output levels, fanout, and drive margin.
   Measure rise and fall times and each relevant input-to-output arc with
   the stated input slew and output load. Track static and switching power
   under declared conditions. Where the PDK supports them and the task needs
   them, sweep process, voltage, and temperature over the intended domain.
   Record missing corners and other model limits in the qualification scope.
5. **Compose and verify the hierarchy.** Instantiate the native cell symbols
   and wire the actual interstage loads. Audit the saved top-level symbol,
   generated netlist hierarchy, terminals, rails, and model bindings. Check
   the complete reachable logic contract at the DUT pins with simultaneous
   loads. Exercise transitions that cover the required timing paths and any
   relevant hazards or startup states. Compare measured internal levels and
   currents with the standalone evidence. Record transient diagnostics and
   acceptance criteria separately.
6. **Freeze and replay.** Keep the selected native schematic and symbols,
   benches, generated netlists, model binding record, simulation settings,
   logs, raw datasets, and extracted measurements together. Open a fresh
   copy of the native project, regenerate its netlists, rerun the required
   checks, and compare results under the declared tolerances. Record the
   verified operating conditions and the remaining qualification scope.

## Reuse by technology and by task

Keep qualified primitive cells and their characterization methods in the
technology layer. A reusable cell record identifies its model family, permitted
parameters, pin map, supply range, input slew and receiver load envelope,
and the evidence for the conditions it covers. Install the authorized PDK
separately and resolve its paths from local configuration. Recheck cell
qualification when the model revision or an interface condition changes.

Keep the top-level logic, pin mapping, rail values, target loads, timing
patterns, and acceptance bench in the consuming task. Exercise the top-level
interface against its own contract even when each primitive has passed its
cell bench. Start with a task-owned cell and promote it to wider reuse when
its interfaces and characterization support the intended uses.

## Characterization and release checklist

- **DC interface and noise margin.** Sweep each input with the other inputs
  at relevant fixed states. Derive the allowable input ranges from the
  required output windows under the declared load. For each qualified
  driver and receiver pair, check both `VIL,max − VOL,max` and
  `VOH,min − VIH,min` against the required margins.
- **Real fanout.** Use the intended receiver cells or a validated equivalent
  load. Record input current versus voltage and the receiver's switching
  load. State whether fanout is measured in receiver pins or equivalent
  input branches. Check internal cascade levels separately from output levels
  under an external load.
- **Timing and hazards.** Sensitize each input-to-output timing arc with the
  other inputs held at the required logic values. Record the crossing
  thresholds, input slew, output load, delay, and output transition time for
  both directions. Sweep the supported slew and load ranges. Check held
  outputs and reconvergent paths for extra crossings and settling, including
  relevant changes on multiple inputs with declared skew.
- **Power and model coverage.** Record current drawn from every rail and
  bias feed for each stable code. Report input drive current separately.
  For switching energy, state the transition, integration window, and how
  the steady-state contribution is handled. Check device stress during
  cutoff, conduction, saturation, and switching. Qualify only the modeled
  process, supply, and temperature conditions that were verified. Record
  gaps in corner coverage and saturation recovery calibration.
- **Physical release.** Verify native layouts and matching pin and device
  mappings. Retain results from the applicable technology DRC and LVS on
  the delivered geometry and source. If extraction is in scope, retain the
  extracted netlist and rerun electrical checks on it. Validate any timing,
  power, and physical abstracts in the downstream tools that will consume
  them. An automated digital flow typically consumes Boolean functions and
  Liberty timing and power tables, placement and pin abstracts such as LEF,
  and the signoff geometry. Record schematic, layout, and extracted
  qualification separately.
  [Cadence characterization reference](https://login.cadence.com/content/dam/cadence-www/global/en_US/documents/tools/custom-ic-analog-rf-design/liberate-characterization-portfolio.pdf)

## Sequential cell verification

1. **Define the state transitions.** Declare which clock edge samples
   data, the startup condition, reset polarity and priority, and the
   expected state during clock and data transitions. For asynchronous
   reset, test assertion with the clock held at each level and verify
   reset priority across a clock edge. For an edge-triggered cell, check
   that release away from an active edge preserves the reset state until
   the next valid capture.
2. **Probe the storage path.** For a master–slave implementation, observe
   both phases and the actual latch enable or inhibit nodes. Measure
   overlap at a declared threshold on both handoffs and check the
   resulting output behavior while D changes during each clock phase.
   Count any storage feedback on an output node toward its load. When
   using separate output buffers, qualify fanout at the public pins and
   replay the functional bench with the intended upstream drivers.
   Record real-driver functional coverage separately from timing measured
   with prescribed source slews.
3. **Measure timing with known initial state.** Precondition each trial to
   a known state and arrange an observable output transition. Establish
   clock-to-output delays for both directions at comfortably separated
   D and clock edges. Sweep setup and hold independently for both data
   transitions, using signed offsets and declared voltage thresholds.
   Retain the sweep grid, settling criteria and any permitted increase
   in clock-to-output delay from the baseline. A signed sampled boundary
   applies to its fixed test conditions. Joint setup/hold aperture,
   reset recovery and removal, minimum pulse width, and metastability
   need distinct tests.
4. **Sweep clock periods under a declared stimulus.** Record the duty
   cycle, data placement, slew, load and number of scored captures.
   Compare every output after each capture and check for extra crossings.
   Publish the passing and failing sampled periods with those conditions.
5. **Deliver a native functional bench and reproducible sweeps.** Put
   the openable transient schematic and named probe signals in the
   handoff. Run batch sweeps from its generated device hierarchy and
   model bindings. Keep native bench replay, functional checks and
   sampled timing evidence together.

A resettable D flip-flop example belongs in the task-owned cell library with its native bench.

## Reusable physical row interfaces

For an abutted digital row, use the actual PDK artwork and pin positions to
choose a common height. Keep the cell width flexible on a declared pitch.
Give the sites a shared coordinate grid, orientation policy, rail layer,
rail centers and widths, and signal access convention. Use the qualified
schematic dimensions when trying the first layout. If a device dimension
changes, rerun the electrical checks before updating its cell qualification.

Build and verify a mixed-cell row before laying out the circuit hierarchy.
Check native bounds, continuity across rail seams, signal clearance,
numbered port access, and placement against the consuming schematic.
Track placement, routing, geometry checks, foundry DRC, LVS and extraction
as distinct evidence. An unqualified rule, model, or extraction setup
remains visible in the handoff. Keep the row-pilot evidence in the task-owned workspace.

## Example: 3-to-8 InP NPN decoder

For output `Y_c`, compare each input bit `Ai` with the corresponding fixed
address bit `ci`. The mismatch term `Ai XOR ci` reduces to `Ai` when `ci = 0`
and to `NOT Ai` when `ci = 1`. An active-high output is the NOR of its three
mismatch terms. The resistor-transistor logic (RTL) topology therefore uses
three shared inverters and eight NOR3 branches, with each branch connected to
the appropriate input polarities. the task specification

The INV and NOR3 schematics and symbols are in a separate ADS gate library.
The standalone characterization covers nominal DC transfer through a NOR3
and an inverter driving four actual NOR3 receivers. The assembled decoder
has its own output-load and transition tests. Use the recorded conditions
when reusing the cells and qualify wider load and cascade cases separately.
the task-owned cell-library record

The same workspace also holds a separate 12-gate library with nominal
truth tables, sampled transfer bounds, real receiver loads, switching
measurements and an eight-stage cascade. Its ADS build and bench scripts
can be replayed independently of the decoder's acceptance tests.
the task-owned standard-cell record
