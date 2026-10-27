# Ideal 65 GHz LC low-pass filter

Revision-2 engineering milestone for
`tasks/inp-passive-lpf-65g-50ohm-80g-stop20`: a nine-pole Chebyshev-I
ladder with five series inductors, four shunt capacitors and equal 50 ohm
reference impedances. The ideal ADS simulation passes all four electrical
requirements.

## Learn the design process

Read the [guided design learning notes](design-learning-notes.md) for the
matching-to-ripple derivation, order selection, component scaling, ADS inspection
checkpoints and curve interpretation. The notes distinguish the verified baseline
from planned learning experiments.

## Open the design

Open `ads/inp_lpf_wrk` as an ADS workspace.

- `inp_lpf_lib:inp_lpf:schematic` is the bare DUT.
- `inp_lpf_lib:inp_lpf:symbol` has ordered terminals
  `rfin, rfout, gnd`.
- `inp_lpf_lib:inp_lpf_sp:schematic` contains the DUT, external 50 ohm
  Term1/Term2, ideal ground and eight S-parameter controllers.

The library definitions use relative paths and ADS's `HPEESOF_DIR`.
The circuit uses only built-in ideal L/C models. The inductors have explicit
zero series resistance. There is no DUT termination resistor.

## Synthesis

The passband edge is 65 GHz. Let n = 9, R0 = 50 ohm,
omega_p = 2*pi*65e9 and rho = 10^(-21/20). Then:

    epsilon = rho / sqrt(1-rho^2)
    ripple_db = 10*log10(1+epsilon^2) = 0.03463497745546 dB
    gamma = sinh(asinh(1/epsilon)/n)
    a_k = sin((2*k-1)*pi/(2*n))
    b_k = gamma^2 + sin(k*pi/n)^2
    g_0 = g_10 = 1
    g_1 = 2*a_1/gamma
    g_k = 4*a_(k-1)*a_k / (b_(k-1)*g_(k-1))
    L_k = R0*g_k/omega_p       (odd ladder positions)
    C_k = g_k/(R0*omega_p)     (even ladder positions)

The ideal closed-form response is:

    |S21|^2 = 1 / (1 + epsilon^2*T_9(f/65e9)^2)
    |S11|^2 = |S22|^2 = 1 - |S21|^2

Since |T_9(x)| <= 1 for 0 <= x <= 1, this bounds the entire ideal
passband, including the interval below the first simulated positive frequency.
The order estimate for 20 dB attenuation at 80 GHz is 8.10334; nine poles
give equal terminations and margin at both acceptance boundaries.

| Elements, from input to output | Value |
| --- | ---: |
| L1, L5 | 120.674157213694 pH |
| L2, L4 | 238.891907001535 pH |
| L3 | 249.182172842647 pH |
| C1, C4 | 71.5588254888531 fF |
| C2, C3 | 82.6663847152029 fF |

Topology:

    rfin -- L1 --+-- L2 --+-- L3 --+-- L4 --+-- L5 -- rfout
                C1       C2       C3       C4
                |        |        |        |
    gnd --------+--------+--------+--------+

The displayed table is rounded. The native design, generated netlist and
`synthesize()` retain full floating-point precision. Small last-digit
differences in mirrored values are numerical rounding.

## Simulation and results

The retained baseline is `results/baseline-20261027/` (ignored by Git).

| Metric | ADS result | Worst-case frequency | Requirement |
| --- | ---: | ---: | --- |
| S11 | -21.000000 dB | 11.2871315484 GHz | < -20 dB |
| S22 | -21.000000 dB | 11.2871315484 GHz | < -20 dB |
| Maximum insertion loss | 0.0346349774555 dB | 61.0800203511 GHz | < 1 dB |
| S21 at 80 GHz | -25.1637752971 dB | exactly 80 GHz | <= -20 dB |

All five theoretical reflection maxima have the same -21 dB level; the
reported worst frequencies reflect floating-point tie breaking. Their frequencies
are 65*cos(k*pi/9) GHz, k = 0..4: 11.2871315484, 32.5, 49.7928888027,
61.0800203511 and 65 GHz.

The eight ADS controllers include:

- 2401 linear samples from 1 MHz to 120 GHz.
- 1301 linear samples from 1 MHz to 65 GHz, spacing below 50 MHz.
- A separate two-point sweep at exactly 65 GHz and 80 GHz.
- Five local sweeps around the analytic extrema, with 100 kHz spacing over
  +/-1 MHz, truncated at the 65 GHz passband boundary.

The merged export contains 3796 unique frequencies. The maximum absolute
complex difference from an independent ABCD cascade is 7.24e-13 (limit 1e-6).
The maximum unitarity residual is 2.23e-15; the reciprocity residual is
1.06e-15. At 1 MHz, S21 is approximately -6.67e-10 dB and S11/S22 are
-98.1388 dB. At DC the series inductors short and the shunt capacitors open,
so S21 approaches 1 and reflection approaches 0.

The baseline directory contains:

- `report.md`, `summary.json`, `settings.json` and `synthesis.json`.
- `inp_lpf_sp.ds`, simulator log, generated `schematic.net` and source snapshots.
- Complex `ads_sparameters.csv` and `inp_lpf.s2p` in Hz/RI/50-ohm format.
- Broadband and passband PNG plots, plus the native ADS schematic PDF.
- `reproduction.json`: a fresh-workspace rebuild produced identical
  frequencies, identical complex S data and an identical netlist hash.

The independent repetition is retained in `results/reproduction-20261027/`.
Transferred files are recorded with SHA-256 hashes in
`results/handoff-manifest.json`. Software versions and actual sweep parameters
are recorded with each run.

## Reproduce

Use an ADS 2027 Python environment with Design Environment and circuit
simulation licensing. From this directory:

    python tools/rebuild_ads.py --workspace ads/inp_lpf_wrk --output results/new-run --rebuild
    python tools/analyze.py verify results/new-run/ads_sparameters.csv --output-dir results/new-run --settings results/new-run/settings.json
    python -m unittest discover -s tools -p test_analyze.py -v

Use a new output directory for every run. `--rebuild` replaces the three
named project views. Omit it when creating a fresh workspace path.
Add `--schematic-pdf` to export the native ADS DUT drawing as well.

For ADS MCP, upload the tools directory to the ADS host and execute this
inside its Python session, substituting the project path:

    from pathlib import Path
    import sys
    project = Path("/path/to/inp-lpf")
    sys.path.insert(0, str(project / "tools"))
    import rebuild_ads, analyze
    tb, values, sweeps = rebuild_ads.build(project / "ads/inp_lpf_wrk", overwrite=True)
    out = project / "results/new-run"
    rebuild_ads.simulate(tb, out, design_values=values, sweeps=sweeps)
    csv_path = rebuild_ads.export_csv(out)
    assert analyze.main(["verify", str(csv_path), "--output-dir", str(out),
                         "--settings", str(out / "settings.json")]) == 0

The verifier checks finite data, exact checkpoints, passband spacing, local
extrema coverage, all four thresholds, complex ADS/ABCD agreement, unitarity,
reciprocity and absence of gain. Its tests also exercise invalid and incomplete
input rejection.

65 GHz is a passband edge. The 80 GHz threshold applies at that single
frequency; the broad sweep shows the low-pass response. This milestone is ideal
schematic verification. Physical InP implementation and official benchmark
registration remain future work.
