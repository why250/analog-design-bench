# Shunt-first ideal low-pass filter verification

Revision 1 of the [ideal task](../../../tasks/inp-passive-lpf-65g-shunt-first-ideal/instruction.md) passed ADS circuit verification on 11 November 2026. The native workspace is [shunt_lpf_wrk](../ads/shunt_lpf_wrk). Its library is `ideal_lpf_lib`, with DUT cell `ideal_lpf` and two-port testbench cell `ideal_lpf_sp`.

## Selected ladder

The 50 Ω Chebyshev-I synthesis uses a 65 GHz passband edge and 21 dB design
return loss. The stop constraint gives an order bound of 8.10334. The lowest
supported odd order is nine. Transform the series-first prototype using
`Cdual = L / Z0²` and `Ldual = C × Z0²`. Its shunt capacitors connect to a
common return at the two port reference planes and at the three internal
nodes. Four series inductors connect consecutive signal nodes.

| Signal-path order | Ideal value |
| --- | ---: |
| C1, shunt at input | 48.26966 fF |
| L1, series | 178.89706 pH |
| C2, shunt | 95.55676 fF |
| L2, series | 206.66596 pH |
| C3, shunt | 99.67287 fF |
| L3, series | 206.66596 pH |
| C4, shunt | 95.55676 fF |
| L4, series | 178.89706 pH |
| C5, shunt at output | 48.26966 fF |

The [full-precision design](../results/20261111T071536Z-ads-ideal/design.json)
is the source for the geometry study. The testbench owns both real 50 Ω
terminations. At DC, the four series inductors are shorts and the five
capacitors are open, so the circuit has a continuous DC path.

## ADS results

| Check | Value | Frequency (GHz) | Requirement | Margin (dB) |
| --- | ---: | ---: | --- | ---: |
| Worst passband S11 | −21.00000 dB | 11.28713 | < −20 dB | 1.00000 |
| Worst passband S22 | −21.00000 dB | 65.00000 | < −20 dB | 1.00000 |
| Worst passband insertion loss | 0.03463 dB | 49.79289 | < 1 dB | 0.96537 |
| S21 at stop checkpoint | −25.16378 dB | 80.00000 | ≤ −20 dB | 5.16378 |

The 3,796 unique native samples span 1 MHz to 120 GHz and include exact 65 GHz,
exact 80 GHz, and refined samples at all five analytical passband extrema.
The maximum complex ADS-to-ABCD discrepancy across all four S-parameters
is 1.63e−15. Reciprocity and power-balance errors are below 2.67e−15. The
equal-ripple peaks agree to numerical precision, so the reported frequency
of a worst point may differ among metrics.

The [report](../results/20261111T071536Z-ads-ideal/report.md) contains the
[response curves](../results/20261111T071536Z-ads-ideal/sparameters.png).
The run retains the [complex Touchstone data](../results/20261111T071536Z-ads-ideal/sparameters.s2p),
[generated netlist](../results/20261111T071536Z-ads-ideal/ads-simulation/schematic.net),
[native dataset](../results/20261111T071536Z-ads-ideal/ads-simulation/ideal_lpf_sp.ds)
and [verification record](../results/20261111T071536Z-ads-ideal/ideal.json).
This stage uses ideal built-in ADS components. PCell losses require a
separate model-based run.

## Reproduction

The independent automation process reopened the saved native project and
generated the same netlist and complex samples byte for byte. See the
[replay receipt](../results/20261111T071536Z-ads-ideal/reproduction.json)
and [transfer receipt](../results/20261111T071536Z-ads-ideal/handoff/transfer-receipt.json).
The retained transfer was checked before and after extraction. The native
library definitions refer to the project library and the ADS installation.

Use an ADS 2027 Python automation environment with NumPy, Matplotlib,
`HPEESOF_DIR` set to the ADS installation, and the ADS binaries on the
process path. Run [run_ideal.py](../tools/run_ideal.py) with
`--run-id <new-UTC-run-id> --replay` from any working directory. Omit
`--replay` when reconstructing from the frozen inputs in a clean copy of
the task workspace. The runner uses the electrical [specification](../inputs/spec.toml),
the frozen task package and the reusable ideal workflow source listed in
the [source manifest](../inputs/source-manifest.json).
