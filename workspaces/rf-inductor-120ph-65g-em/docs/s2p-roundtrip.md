# Standalone ADS S2P consumer control

[validate_s2p_roundtrip.py](../tools/validate_s2p_roundtrip.py) checks that ADS
consumes the complete two-port handoff with the declared interpolation and
terminal convention. Run it only in a new headless ADS Python process. It
creates a fresh owned workspace and does not open or modify the parent LPF.
Completion of this control is separate from device, material, continuous-band
or parent-filter qualification.

The implementation follows ADS 2027 Python API documentation for `Library`,
`Design`, `Instance`, `InstTerm`, `Param`, `simulation/run` and
`simulation/results`. `design.generate_netlist()` produces the native deck;
`keysight.edatoolbox.ads.CircuitSimulator().run_netlist(...)` executes it.
The installed S2P component guide is
`ccsim/S2P_(2-Port_S-parameter_File).html`. The installed component definitions
and retained native probes establish the following configuration:

| Item | Required setting |
| --- | --- |
| S2P master | `ads_datacmps:S2P:symbol` |
| S2P terminals 1 / 2 / 3 | p / n / common reference |
| File type | Touchstone, native `Type="touchstone"` |
| Interpolation mode | Mode0 / Linear, native `InterpMode="linear"` |
| Interpolation domain | ID1 / Rectangular, native `InterpDom="ri"` |
| Temperature | 25 degrees C for S2P and both stimulus terms |
| Passivity enforcement | Disabled |
| Stimulus terms | `ads_simulation:Term:symbol`, 50 ohms, Num 1 and 2 |
| Term terminals 1 / 2 | Positive signal / common reference |

The S2P guide's default DataBased domain uses polar interpolation for S data,
including a Touchstone file whose stored representation is RI. Explicitly
setting both mode and domain is therefore necessary for the intended complex
rectangular linear consumer. File representation alone is insufficient.

The common reference is the P4 finite-return reference already represented
inside the complete source network. A schematic ground marker fixes that
abstract reference potential for the unit test. It does not remove the return
network or add an infinite physical ground plane to the EM model. No new lead,
pad or de-embedding operation is introduced.

## Run after final model assembly

Replace the portable placeholders and adopt numerical consumer-control limits
before execution. The helper requires explicit absolute tolerances for complex
S and for the same full-network differential impedance Zd. It does not choose
new electrical design limits.

```powershell
& "<ADS_PYTHON_EXECUTABLE>" tools/validate_s2p_roundtrip.py `
  --model "<FINAL_COMPLETE_MODEL.s2p>" `
  --assembly-receipt "<FINAL_MODEL_ASSEMBLY.json>" `
  --require-dc-anchor --output-dir "<FRESH_STANDALONE_CONTROL_DIRECTORY>" `
  --max-absolute-s-error "<ADOPTED_ABSOLUTE_S_LIMIT>" `
  --max-absolute-zd-error-ohm "<ADOPTED_ABSOLUTE_ZD_LIMIT_OHM>"
```

Use `--require-dc-anchor` only for a handoff explicitly including the derived
DC endpoint. In that mode the verified assembly receipt must declare the DC
anchor and the source's first two samples must be exactly 0 and 10 MHz. The
unit test executes an actual ADS circuit sweep from 0 to 10 MHz in 1 MHz
steps, plus independent exact 10/65/80 GHz circuit controls. Every test frequency
must lie inside the source file's domain. A source without a zero-frequency
sample can be checked without this flag, but that run provides no 0--10 MHz
consumer evidence. No extrapolation is permitted.

Before simulation, the helper validates the actual native netlist topology:
`S2P(p,n,0)`, `T1(p,0)` and `T2(n,0)`, the explicit file/type/interpolation
settings, temperature, 50-ohm references and disabled passivity enforcement.
It also verifies that returned dataset frequencies match each requested group
and that the dataset contains exactly the complete two-port matrix.

For every actual ADS consumer sample, Python computes each expected S entry by
linear interpolation of its real and imaginary parts between source samples.
No interpolation is applied to the source file or presented as new EM data.
The comparison uses all four complex entries and the existing full-network
`Zd=Z11+Z22-Z12-Z21` observable under Icm=0, with no factor of one half or
arbitrary matrix regularization. At exactly DC, L is undefined; finite S and
Zd/R can still be compared. Singular common-mode full Z is reported through
the analyzer's observable/conditioning fields.

## Retain and interpret the evidence

The fresh control directory retains the unchanged input model copy, editable
native workspace, each generated netlist and native configuration receipt,
simulator output and datasets, complete `consumed.s2p`, `comparison.json` and
`roundtrip-receipt.json`. A refused or failed attempt remains on disk; retry
in a new directory. The source model must remain byte-identical throughout.

Read the control result and every per-frequency S/Zd error against the declared
limits. A successful circuit process, an imported file or a visually similar
curve alone does not establish the consumer control. This control also does
not establish that interpolation between DC and the first RF sample is
physically accurate: the separate DC/contact/LF evidence and supported-limit
justification remain required. The parent filter remains NOT EVALUATED.
