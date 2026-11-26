# Virtuoso/Spectre verification plan — revision 1

This plan defines engineering checks for the [task contract](instruction.md).
No check below has been executed for a new Virtuoso candidate. There is no
implemented official verifier or scoring entrypoint for this task.

The task-owned `tools/wp0_measure.py` checks measured CSV, explicit 50-ohm RI
Touchstone, or an identified SP PSF ASCII file against the fixed smoke circuit.
It validates all four complex entries and independently checks repeated data.
Its offline synthetic checks do not establish a native or solver result.

## WP0: native toolchain smoke gate

Use a dedicated ideal two-port with a 100 pH series inductor followed by a
100 fF capacitor from output to ground. Both 50-ohm ports remain bench-owned.
Use positive SP points at 1 MHz, 10 GHz, 65 GHz and 80 GHz. This deliberately
small circuit need not meet H1-H4; it tests known source-to-result behavior.

| Check | Required observation and evidence |
| --- | --- |
| Connection | The selected MCP is loaded in the actual client; a read-only native query reaches the intended Virtuoso process |
| Source | New task-owned schematic, explicit units, two DUT signal terminals and ground; connectivity and parameter inspection agree with the planned circuit |
| Save/check | Native check diagnostics reviewed; save, close and reopen preserve the source |
| Netlist | The actual native-derived Spectre input contains the same L/C values, terminals, external 50-ohm ports and SP points; retain it and its generation receipt |
| Solver | A single actual Spectre invocation completes with usable SP data and retained license/invocation log; version/status probes alone are insufficient |
| Readback | Read all four complex S entries with frequency, ordering and 50-ohm normalization; retain native raw data and CSV/Touchstone exports |
| Analytic comparison | Compare every complex entry against the series-Z/shunt-Y ABCD cascade at each actual frequency, using the tolerances below |
| Repeat | Reopen the saved native source, regenerate input and rerun; compare both consumed connectivity/parameters and repeated complex S data |

Use `Z = j*2*pi*f*L`, `Y = j*2*pi*f*C` and multiply
`[[1,Z],[0,1]] * [[1,0],[Y,1]]`. For ABCD entries A, B, C, D and real
`Z0 = 50 ohm`, let `q = A + B/Z0 + C*Z0 + D`. Then
`S11=(A+B/Z0-C*Z0-D)/q`, `S21=2/q`,
`S12=2*(A*D-B*C)/q`, `S22=(-A+B/Z0-C*Z0+D)/q`.

WP0 passes only with the entire source-to-repeated-result evidence chain.
If a documented tool cannot supply native netlisting or complex SP export,
retain that gap instead of substituting an unrelated handwritten deck.

## WP1: fixed ADS baseline reproduction

1. Freeze the selected inputs and inspect agreement between the full-precision
   parameter JSON and ADS netlist. Rebuild the identical series-L/shunt-C
   connectivity with no retuning, added loss or reference-plane changes.
2. Confirm the native source and generated Spectre input have exactly that
   topology and parameter set. Record any literal serialization difference and
   its numerical effect rather than silently changing the baseline.
3. Use the 3796 actual frequencies in the frozen ADS CSV for direct comparisons;
   retain any deduplication or native sweep segmentation settings. Additional
   local refinement is permitted and must remain distinguishable from the
   shared comparison samples. Do not compare interpolated traces as exact samples.
4. Compare all four Spectre complex S entries against both frozen ADS data and
   independent ABCD results at matched frequencies. Recompute the four electrical
   metrics from Spectre results, with the coverage and uncertainty rules below.
5. Save and reopen the native source, regenerate and repeat the selected run.
   Compare actual consumed parameter/connectivity sets and complex data; retain
   both attempts and review discrepancies before accepting reproduction.

## Numerical engineering tolerances

This task adopts the following engineering tolerances from the prior ideal
baseline analysis. Their application to ADS-versus-Spectre is a new, untested
cross-tool criterion; they are not an observed cross-tool result.

| Quantity | Criterion |
| --- | --- |
| Frequency pairing | Each requested comparison point and exact checkpoint must have an actual sample within 1 Hz; no nearest coarse-grid substitution |
| Complex S error | Maximum absolute difference across every frequency and all four S entries `<= 1e-6`, separately for Spectre-versus-ADS, Spectre-versus-ABCD and repeat-versus-original |
| Reciprocity | Maximum `abs(S21-S12) <= 1e-8` |
| Lossless unitarity | Maximum absolute entry of `S^H*S-I <= 1e-8`, using complex-conjugate transpose |
| Passive power excess | Maximum excess above unity of either column's sum of squared magnitudes `<= 1e-8` |

Use absolute complex error rather than relative or dB error near reflection
zeros. Check frequency arrays are finite, positive, complete and consistently
ordered; all complex values must be finite. S-parameter export order must be
documented; do not confuse `S12` with `S21`. Keep internal full precision.
Report discrepancies and investigate failures before proposing a tolerance
change. A numerical tolerance does not relax an electrical boundary.

## Electrical coverage and requirement mapping

Define `sij(f) = 20*log10(abs(Sij(f)))`. Valid exact zeros may have a negative
infinite dB limit; evaluate those with their finite complex values. Invalid or
missing complex data never become a passing dB value.

| ID | Measurement | Required evidence and decision |
| --- | --- | --- |
| H1 | `max(s11)` on `(0,65 GHz]` | Strictly `< -20 dB`; retain maximum and frequency, full-band coverage and uncertainty |
| H2 | `max(s22)` on the same band | Strictly `< -20 dB`; same evidence |
| H3 | `max(-s21)` on the same band | Strictly `< 1 dB`; same evidence |
| H4 | `s21(80 GHz)` | `<= -20 dB` at an actual exact checkpoint |
| H5 | DC path and positive-frequency low-frequency limit | Series L short/shunt C open limit gives `S21=S12=1`, `S11=S22=0` for the fixed ladder; record the 1 MHz sample separately |
| H6 | Source and consumed-netlist inspection | Only positive finite ideal L/C in DUT; correct ordered terminals, common ground and external real 50-ohm ports |

For WP1, retain the complete 1 MHz–120 GHz shared grid and all five positive
reflection maxima `65 GHz*cos(k*pi/9)`, `k=0..4`, including exact 65 GHz.
Include each maximum and local points within 1 MHz on both available passband
sides. The frozen grid has at most about 50 MHz spacing in the passband. Use
the Chebyshev analytic bound together with the native-derived network and
independent calculation to cover the continuous passband, including below
the first positive sample. A sampled maximum alone cannot certify the band.

For a later WP2 candidate, derive extrema and a low-frequency limit for its
actual topology. Use a passband grid with spacing at most 0.1 GHz, exact 65 and
80 GHz, local refinement of every suspected maximum, and an analytic or
otherwise justified coverage argument. Refine until numerical uncertainty is
smaller than the available specification margin. If the continuous-band bound
or a strict threshold remains uncertain, report conditional/indeterminate
coverage and do not claim pass. The baseline's nine-pole extrema and analyzer
are not generic acceptance rules for another topology.

## Retained evidence and validity

The future stable workspace is `workspaces/inp-passive-lpf-65g-50ohm-80g-stop20-virtuoso/`.
Its actual manifest and run layout must be defined by the implemented Virtuoso
workflow before native writes. Use fresh run directories for smoke, baseline,
repeat and later design work. Keep edited native source apart from frozen
retained run inputs; absolute remote paths are resolved through private bindings.

Each completed simulation delivery needs: native schematic/bench source archive
and library definitions, source/netlist correspondence report, generated Spectre
input, generation and invocation settings, simulator log, native raw data, full
complex CSV, Touchstone, plots, metric/coverage/comparison reports, repeated-run
references and a machine-readable evidence inventory. `native-source.zip`,
`spectre-input.scs`, `sparameters.s2p` and `measurements.json` name primary delivery
files under the selected run; they are planned artifacts, absent at authoring.
Preserve all other required evidence alongside them and link it in the run index.

Maintain the chain from the saved source and fixed parameters to the consumed
netlist, simulator identity/settings, native raw dataset and every exported
measurement. Exact integrity data belong in machine-readable manifests and
receipts; narrative reports state provenance and verification outcomes plainly.
The input snapshot's historical settings/summary retain their original evidence;
their ADS pass status must not be copied into the new run's conclusions.

Missing samples, unavailable exports, nonconvergence, timeout, stale data,
uncertain extrema or incomplete repeated-run evidence are incomplete/invalid,
never inferred passes. Retain failure cause and available artifacts. A valid
result outside H1-H4 is an electrical failure even if tools worked. A toolchain
failure does not establish that the filter requirements are infeasible.

Conclude separately: execution, native toolchain, baseline reproduction,
candidate electrical result, ideal-model applicability and delivery completeness.
Formal scoring and physical model qualification remain outside this task.
