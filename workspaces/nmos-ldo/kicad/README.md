# Manual KiCad drawing workspace

Use the [shared KiCad workflow](../../../docs/kicad-spice-workflow.md) for the
cross-task drawing, export and validation contract. This page owns the NMOS LDO
project's specific drawing instructions and current XAMP hybrid simulation.

Open `nmos-ldo.kicad_pro` in KiCad 10, then open its root schematic.
The XAMP sheet contains a saved amplifier drawing. The remaining DUT-core and
Testbench devices and internal connections are left for manual placement.
SPICE simulation continues through the Docker workflow in the parent directory.

## Required environment

Install the stable KiCad 10 Windows package from the
[official download page](https://www.kicad.org/download/windows/), including
its standard symbol libraries. At first startup, select **Start with the
built-in KiCad libraries**. Open the project file before opening the schematic
so that KiCad resolves the project library and sheet hierarchy correctly.

The project already registers `AnalogBench` in its `sym-lib-table` using
`${KIPRJMOD}`. No global registration or separate SKY130 symbol download is
needed. Use the built-in `Simulation_SPICE`, `Device`, and `power` libraries
for testbench sources, ordinary capacitors, and ground symbols. Leave the
four-terminal project MOS symbols available for the DUT.

For this manual drawing workflow, no Windows PDK installation or KiCad
simulator setup is required. Continue running `../circuit.spi` through the
existing Docker helper. The LVT MOS symbols now bind their drawing fields to
native SPICE export as described below. Saving a schematic does not regenerate
the workspace's original `circuit.spi`.

The version-specific global settings and library tables are in
`%APPDATA%/kicad/10.0`; project-specific libraries stay beside this project.
See the [KiCad configuration guide](https://docs.kicad.org/10.0/en/kicad/kicad.html)
for the first-run library options. Machine-specific installation and
validation records belong in the repository's ignored `.local/` notes.

```text
nmos-ldo.kicad_pro
nmos-ldo.kicad_sch             Overview: DUT/testbench interfaces
sheets/
  testbench.kicad_sch         External sources, load, and loop injection
  ldo-core.kicad_sch          XPASS, XCCOMP, XGATECAP, and XAMP sheet block
  error-amplifier.kicad_sch   XPM0..XPM5 and XNM0..XNM5
AnalogBench.kicad_sym         Project drawing-symbol library
sym-lib-table                Portable project-library registration
device-map.csv               Pin/model/parameter lookup for 15 leaf devices
```

The hierarchy is `Overview -> Testbench` and `Overview -> DUT -> XAMP`.
On the overview, seven matching ports connect the two child sheets. Each child
has matching hierarchical labels; wire their short stubs to the components you
place. In the DUT sheet, connect `XAMP.vfb` to `vout` and the remaining XAMP pins
as described by [the source circuit](../circuit.spi).

## First-time walkthrough

### 1. Open the project and find the drawing sheet

1. If available, double-click the **NMOS LDO - KiCad** desktop shortcut.
   Otherwise, start KiCad, choose **File -> Open Project**, and select
   `nmos-ldo.kicad_pro` in this folder.
2. In the KiCad project manager, double-click `nmos-ldo.kicad_sch` in the
   project file tree. This opens the **Schematic Editor**. Use this editor
   for drawing; the **Symbol Editor** edits reusable library symbols.
3. The first page is an overview. Its **Testbench** and **DUT** rectangles
   represent child sheets, not transistor symbols. Their internal circuits
   contain the existing amplifier drawing and the remaining manual drawing pages.
4. In the editor's hierarchy navigator on the left, expand **DUT** and click
   **XAMP**. You are now on the error-amplifier page. If the navigator is
   hidden, enable **View -> Panels -> Hierarchy Navigator**. Alternatively,
   double-click the **DUT** rectangle, then the **XAMP** rectangle inside it.
5. Keep [circuit.spi](../circuit.spi) and [device-map.csv](device-map.csv)
   open beside KiCad in a text editor or CSV viewer. The `sheet` column tells
   you where each device belongs; `DUT/XAMP` contains six PMOS and six NMOS
   devices. Use the netlist as the source of truth if the design has changed.

Menu names below are the English KiCad names; a localized installation may
translate them. The listed keys are default shortcuts. **Help -> List
Hotkeys** shows your current assignments.

### 2. Place your first transistor

1. Move the pointer into an empty part of the **XAMP** drawing canvas and
   press `A` (**Add Symbol**). Do not type shortcuts while a text field has
   focus. The first symbol search may take a moment to load the libraries.
2. In the symbol chooser, search for `AnalogBench`. For the first example,
   select `AnalogBench:SKY130_NMOS_LVT_4T` and click **OK**.
3. A preview follows the pointer. Move it to the drawing area and left-click
   once to place it. Press `Esc` until the selection arrow is active again
   so that you do not accidentally place extra copies.
4. Keep the drawing grid at **50 mil** for symbol placement and wiring. Zoom
   with the mouse wheel; pan with the middle mouse button. Use `R` to rotate
   a selected symbol before wiring it if needed.

### 3. Fill in the device parameters

Click the symbol's body, then press `E` (**Properties**), or right-click it
and choose **Properties**. Selecting the text beside a symbol can select
only that text field, so use the transistor body when editing the device.

Find the `XNM0` row in `device-map.csv`. Fill in its properties as follows:

| KiCad property | Value for this example | Meaning |
| --- | --- | --- |
| `Reference` | A unique reference, for example `Q1` | KiCad's device identifier |
| `NetlistInstance` | `XNM0` | Original instance name in the SPICE source |
| `Model` | `sky130_fd_pr__nfet_01v8_lvt` | Already supplied by the chosen symbol; verify it |
| `W` | `4` | Copy from CSV `W_um`; micrometres |
| `L` | `1` | Copy from CSV `L_um`; micrometres |
| `m` | `20` | Copy from CSV `m` |
| `mult` | `20` | Copy from CSV `mult` separately |

Keep `Value` as the symbol name if you do not need a different display value.
Enable the field visibility checkbox for `NetlistInstance`, `W`, `L`, `m`,
or `mult` when you want those annotations to appear beside the transistor.
Click **OK** to apply the properties. For the configured LVT MOS symbols,
these fields also supply the native SPICE export described below. Continue
editing these fields rather than duplicating their values in `Sim.Params`.

### 4. Connect the pins from the netlist

For this project's four-terminal MOS symbols, pin numbers are **1 = D**,
**2 = G**, **3 = S**, and **4 = B**. Read the pin names or numbers after
rotating a symbol; do not infer connections from its position on the page.
The CSV columns `D`, `G`, `S`, and `B` contain the required net names, not
values to enter into the symbol's properties.

For `XNM0`, the source line is:

```spice
XNM0 nleft nleft vss vss sky130_fd_pr__nfet_01v8_lvt w=4 l=1 m=20 mult=20
```

This means connect **D and G to `nleft`**, and **S and B to `vss`**:

1. Point at a pin's connection endpoint and press `W` (**Add a Wire**).
   Click to add bends, then click the destination pin or existing wire to
   finish the connection. Press `Esc` to stop wiring.
2. Connect pins **D (1)** and **G (2)** with a wire. Press `L` (**Place Net
   Labels**), enter `nleft`, and place the label's attachment point directly
   on that wire. Press `Esc` to leave label placement.
3. Connect pins **S (3)** and **B (4)**, then wire that connection to the
   existing `vss` hierarchical label's short wire stub on this page. The bulk
   pin is separate; connecting Source alone does not connect Bulk.
4. Zoom in and check the endpoints. Unconnected pin circles should disappear
   when connected. Inspect junction dots where wires join; crossing lines
   alone do not establish a connection.

Matching local labels connect wires **within the same sheet**. For the six
existing amplifier interfaces, wire into the existing hierarchical label
stubs so the connections reach the parent sheet. Plain text annotations do
not create electrical connections.

### 5. Save and continue

Save with `Ctrl+S` or **File -> Save**. Repeat the placement, parameter, and
wiring steps for the remaining amplifier devices, giving each one a unique
KiCad `Reference` and the correct `NetlistInstance`. Then follow the
[suggested drawing order](#suggested-drawing-order) below for **DUT** and
**Testbench**. Saving the schematic does not update `circuit.spi`.

| Default shortcut | Action |
| --- | --- |
| `A` | Add a symbol; search for `AnalogBench` |
| `W` | Draw an electrical wire |
| `E` | Edit the selected symbol's properties |
| `L` | Place a local net label |
| `R` | Rotate a selected symbol |
| `M` | Move a selected symbol; attached wires stay behind |
| `G` | Drag a selected symbol while keeping attached wires connected |
| `Esc` | Cancel the current action; press again to leave the tool if needed |
| `Ctrl+S` | Save the schematic |
| `Ctrl+Z` | Undo an accidental edit |

If `AnalogBench` is missing from the chooser, make sure you opened the
project file first. In **Preferences -> Manage Symbol Libraries**, check
the project-specific table for `AnalogBench` pointing to
`${KIPRJMOD}/AnalogBench.kicad_sym`. If standard symbols are missing, check
that the standard KiCad symbol libraries are installed and listed in the
global symbol library table.

For the general editor controls, see the
[official KiCad 10 schematic tutorial](https://docs.kicad.org/10.0/en/getting_started_in_kicad/getting_started_in_kicad.html).

## Place symbols and record parameters

Use **Add Symbol** (`A`) and search for `AnalogBench`. The library provides:

| Symbol | Use |
| --- | --- |
| `SKY130_NMOS_LVT_4T` | XPASS and XNM0..XNM5 |
| `SKY130_PMOS_LVT_4T` | XPM0..XPM5 |
| `SKY130_NMOS_1V8_4T` | XGATECAP, wired as a MOS capacitor |
| `SKY130_MIM_2T` | XCCOMP |

MOS pin numbers are `1=D, 2=G, 3=S, 4=B`; MIM pins are `1=c0, 2=c1`.
Bulk is exposed and is not internally connected to Source. Symbols have a
model-name field and blank `NetlistInstance`, `W`, `L`, `m`, and `mult` fields.
Edit properties (`E`) to populate them from [device-map.csv](device-map.csv)
and enable visibility for the fields you want beside each symbol. KiCad can
use references such as `Q1`; `NetlistInstance` preserves names such as `XPM0`.
Retain `m` and `mult` separately. W/L values are in micrometres; the source PDK
netlist uses numeric geometry with `scale=1u`.

The LVT NMOS and PMOS symbols have hidden native simulation settings bound to
these fields. The other two symbols remain drawing symbols in this workflow.
The library has no footprint assignments. Uncompleted pages are not expected
to pass full-project electrical ERC.

## Native SPICE export and Docker simulation

This workflow uses **KiCad's native SPICE Model exporter** for the completed
XAMP page. It combines that exported amplifier with the existing source-netlist
LDO core, then runs the public nominal diagnostic in the persistent development
container. The transistor lines come directly from KiCad; XML is exported only
for independent connection and parameter checks.

Save your schematic in KiCad first. From PowerShell in the repository root:

```powershell
.\scripts\Invoke-KiCadXampSimulation.ps1
```

To export and check the netlist without starting Docker:

```powershell
.\scripts\Invoke-KiCadXampSimulation.ps1 -Mode Export
```

The entrypoint finds KiCad 10 and Python automatically in common Windows
installations. Override `-KiCadCliPath`, `-PythonPath`, `-WorkspaceDirectory`,
or `-ContainerName` when needed. Docker Desktop must be running for a simulation.
The shared local helper validates the existing image and writable workspace
mount and starts the development container if it is stopped.

### Edit parameters in one place

Continue using `E` on each transistor to edit `Model`, `W`, `L`, `m`, and
`mult`. Numeric W/L values remain in micrometres under the existing SKY130
model convention; enter `4` for 4 micrometres. Keep `m` and `mult` separate.
The hidden simulation settings are:

```text
Sim.Device = SPICE
Sim.Pins   = 1=1 2=2 3=3 4=4
Sim.Params = type="X" model="${Model} w=${W} l=${L} m=${m} mult=${mult}"
```

This is KiCad's **Raw SPICE Element** model. It generates a four-terminal
subcircuit call in D/G/S/B order. The actual SKY130 model definitions and
process-corner selection remain in the Docker testbench; no Windows PDK copy
is needed. Do not replace the expressions with duplicated numeric values.

KiCad uses references such as `XQ7` in the native SPICE output for schematic
reference `Q7`. `NetlistInstance=XNM0` remains the original-source identifier
used for traceability; it does not rename KiCad's native SPICE instance.

The configured library defaults apply to newly placed LVT MOS symbols. If
reapplying the settings to existing instances is needed, first save and close
the schematic editor, then run:

```powershell
.\scripts\Invoke-KiCadXampSimulation.ps1 -Mode Configure
```

This adds or updates only the hidden `Sim.*` settings in the LVT library
definitions and XAMP instances. It retains a backup under `../results/`.
Reopen the schematic afterward. The `Run` and `Export` modes do not modify
the saved drawing.

### Inspect the exported files and results

Each export creates a fresh `../results/kicad-xamp-<UTC-run-id>/` directory:

| File | Contents |
| --- | --- |
| `inputs/` | Saved schematic, symbol library, source circuit, and source bench snapshots |
| `xamp-native.spi` | Unmodified native KiCad SPICE Model export |
| `connectivity.xml` | Native connectivity export used to check all four pins and parameter values |
| `manifest.json` | Input hashes, export commands, and the Q/XQ/original-instance mapping |
| `circuit.spi` | Simulation copy containing native XAMP, an interface adapter, and the source LDO core |
| `simulation/nominal.log` | Simulator diagnostics and measured nominal values, when Run mode is used |
| `simulation/dc.txt`, `loop.txt`, `psrr.txt` | Windows-readable numerical exports |
| `simulation/*.raw` | ASCII waveform exports |

A named standalone project is created only inside the input snapshot so the
CLI can name the exported subcircuit. The native exporter orders interface
ports itself; the adapter reads that order and connects them to the original
amplifier interface. The native transistor lines are preserved verbatim.

This is a **hybrid nominal simulation**: schematic-derived XAMP plus the
source-netlist LDO core. DUT and Testbench drawing pages are not used by this
entrypoint. It does not overwrite the original workspace `circuit.spi`, prove
full-schematic equivalence, or run the official PVT/Monte Carlo verifier. The
existing `Invoke-LocalSimulation.ps1 -Mode Verify` continues to verify the
workspace `circuit.spi`, not this newly exported simulation copy.

For direct manual export in the Schematic Editor, choose **File -> Export ->
Netlist -> Spice Model**, enable **use current sheet as root** on the XAMP
page, and export. The helper above additionally preserves snapshots, validates
connections/parameters, adapts the port order, and runs the Docker bench.

### Troubleshooting native export

| Symptom | Cause to check | Verified remedy |
| --- | --- | --- |
| Export contains placeholder lines such as `Q7 __Q7` | The placed symbol has no usable simulation settings. Filling `NetlistInstance` alone does not configure a model. | Save and close the schematic editor, run `-Mode Configure`, and reopen the schematic. This updates existing XAMP instances and embedded LVT definitions as well as library defaults. |
| A standalone sheet export starts with an unnamed `.subckt` | The CLI's loaded project has no name; the subcircuit name comes from the project. | Use the helper's named standalone project in the input snapshot. Keep the native device lines unchanged. |
| An exported amplifier behaves incorrectly after being connected to the source LDO | The native exporter may order its ports differently from the original subcircuit. | Read the exported header and adapt the call by port name. The helper does this; do not assume the original positional order. |
| A changed W/L value is absent from the export | The drawing was not saved, or `Sim.Params` contains a separate literal value. | Save first, retain the field expressions under **Edit parameters in one place**, and check the new export's `manifest.json`. The helper rejects exported values that differ from the saved fields. |

`XQ7` and `XNM0` can identify the same device in different artifacts: KiCad
uses the first name natively, while the custom `NetlistInstance` field records
the original-source name. Use the manifest mapping when comparing files.
An ERC pass alone does not establish equivalence to the source netlist; inspect
native pin/model/parameter checks and simulation evidence as separate checks.

### Regression checks

From the repository root, run:

```powershell
python -m unittest discover -s scripts -p test_kicad_xamp.py -v
```

The tests include an integration check that calls the installed KiCad CLI on a
temporary copy of the XAMP sheet. It verifies a named native subcircuit, checks
all exported pins and parameters against native XML, doubles one transistor's
W field, and verifies that only that native instance's width changes. The
source drawing and symbol library remain unchanged. No Docker or PDK is
required for these export checks; they do not run an electrical simulation.

The integration check discovers `kicad-cli` on PATH or in common Windows
KiCad 10 installation locations. To select another executable, set
`KICAD_CLI` to its full path before running the tests. An invalid explicit
path fails the tests; an absent auto-discovered CLI skips only the integration
check, leaving the unit tests active. A skipped integration check is not
evidence that native export was validated on that machine.

## Suggested drawing order

1. Open **DUT / XAMP** from the hierarchy navigator. Draw the 12-transistor
   amplifier using its six existing interface labels.
2. Return to **DUT**. Place its three remaining leaf devices and wire the XAMP
   ports. Keep `loop_out` and `pass_gate` separate.
3. Open **Testbench**. Draw sources and load from
   [the public bench](../testbench/tb_nominal.spi). Connect `vss` to ground and
   place VLOOP between `loop_out` and `pass_gate`. The overview already supplies
   the DUT connection; do not add another DUT instance on this sheet.
4. Compare every connection and parameter against the SPICE source. Update the
   lookup if the source design changes; it captures the current reference.

Double-click a child sheet or use the hierarchy navigator to enter it. Return
to its parent through the navigator. Save your drawing normally. These files
are in the Windows workspace mounted into Docker, but schematic edits do not
automatically update `circuit.spi`.

Native previews and hierarchy validation exports are stored outside this
source folder in `../results/kicad-scaffold-validation/`.
