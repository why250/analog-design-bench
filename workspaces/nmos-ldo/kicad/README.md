# Manual KiCad drawing workspace

Open `nmos-ldo.kicad_pro` in KiCad 10, then open its root schematic.
The project was loaded, natively serialized, and visually checked with KiCad
10.0.6. Devices and internal connections are left for manual placement.
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
existing Docker helper. Drawing-symbol fields alone do not configure a
simulator model, and saving a schematic does not regenerate that SPICE file.

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

These fields are drawing annotations, not configured KiCad simulator model
assignments. The library has no footprint assignments. Electrical equivalence
and KiCad simulator configuration can be checked after the circuit is drawn;
the incomplete scaffold is not expected to pass electrical ERC.

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
