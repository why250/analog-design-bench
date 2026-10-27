# ADS and EM verification plan (operator guidance)

This plan defines how to **measure and report** the requested electrical behavior. It is not an executable independent verifier, a statement of PDK availability or a substitute for the task-development guide.

## 1. Bench boundary and conditions

Use a linear small-signal two-port simulation with **real 50 Ω source and load references**. Set the ports at the LPF DUT terminals; connect each port signal to the common on-chip return and exclude the bench 50 Ω terminations from the DUT. Use the identical reference planes for all candidate topologies.

- Nominal process and temperature: **TBD by the actual InP PDK**. Never label unspecified corners as verified.
- Frequency resolution: combine a low-frequency logarithmic sweep to establish the DC limit (for example, 1 MHz–1 GHz), a broad 1–200 GHz sweep, and a refined 60–90 GHz sweep; use explicit 65 and 80 GHz samples. Start with ≤0.1 GHz step near the passband edge and refine any return-loss peak or S21 notch adaptively. These are proposed bench settings, not evidence of accuracy by themselves.
- Positive-frequency S-parameter values are evaluated through **65 GHz inclusive**. Inspect DC conduction/transfer separately; a conventional S-matrix at exactly 0 Hz is not defined by this task.
- Retain complex S-parameter data (Touchstone preferred), not only screenshots. Annotate frequency units, port orientation, de-embedding and all extracted-pad reference-plane changes.

## 2. Confirmed acceptance metrics

For each declared, actually simulated condition, calculate:

```text
RL_in_worst_dB  = max_{0<f<=65GHz} [20*log10(abs(S11(f)))]
RL_out_worst_dB = max_{0<f<=65GHz} [20*log10(abs(S22(f)))]
STOP_80_dB      = 20*log10(abs(S21(80GHz)))

PASS only if:
  RL_in_worst_dB  < -20.0 dB
  RL_out_worst_dB < -20.0 dB
  STOP_80_dB     <= -20.0 dB
```

Implement robust interpolation and passband peak search, record the frequency at each extremum, and distinguish no data/nonconvergence from a passing case. S-parameter magnitudes should also be reported using `dB(S(1,1))`, `dB(S(2,2))` and `dB(S(2,1))` in ADS Data Display.

**Do not mark a physical filter as fully accepted on these checks alone.** The passband insertion-loss bound is still unspecified, and a matched dissipative network can pass return-loss criteria while failing the intended signal-transmission function.

## 3. Report-only measurements pending sign-off thresholds

- `IL_passband_max_dB = max_{0<f<=65GHz}[-20*log10(abs(S21(f)))]` (positive insertion-loss convention).
- Worst S21 over representative 80–120 GHz and 80–200 GHz stopband intervals; report any transmission peak, extra notch or spurious passband.
- Passband ripple, group delay, filter area, layout dimensions and component-count tradeoffs.
- Port power balance for a passive two-port. Verify `SᴴS ≼ I` within numerical tolerance for a passive EM/circuit model, noting that small round-off errors can occur; a reciprocity check compares S12 and S21 at the same planes.
- Optional thermal/process/geometry corners and parameter perturbations, only after the real PDK and legal layout rules are available.

## 4. Staged candidate comparison

| Candidate | Synthesis / initial check | Physical verification risk |
| --- | --- | --- |
| LC ladder / quasi-elliptic | Ideal 50 Ω L/C prototype, possible resonant transmission zeros; compute full 2-port response | Finite inductor Q, self-resonance, capacitor ESL, metal coupling, zero-frequency shifts |
| Stepped-impedance | Alternating high-/low-impedance ideal TLINs, optimized full ABCD chain with 50 Ω *external* ports | Actual microstrip/CPW stack, conductor and substrate loss, step discontinuities, phase velocity, long total line length |
| Hybrid (optional) | Co-optimized LC and line elements, with justified added complexity | Unmodeled coupling and parasitic resonances |

Do **not** reuse theoretical component values or claimed ideal S-parameter numbers from informal discussions as verified results. Recompute the prototypes, save the ADS project, and reproduce every plot from frozen inputs.

## 5. Physical/EM verification sequence

1. **Ideal topology** — analytical ABCD/S-matrix or ADS ideal elements; document normalized prototype, 50 Ω frequency scaling, match extrema and stopband response.
2. **PDK substitution** — frequency-dependent L/C and line models, Q and SRF; check their documented frequency range. Perform loss and parasitic sensitivity sweeps, including series resistance, stray shunt capacitance and resonator coupling.
3. **Layout + EM** — include signal metal, real return path, grounding vias, MIM connections, bends, junctions and neighboring structures. Confirm substrate, conductor, via and metal-layer definitions match the authorized process.
4. **Combined EM/circuit** — simulate at consistent calibrated/de-embedded reference planes, compare with schematic results, and investigate reflection peaks and shifted transmission zeros.
5. **Reproducibility / robustness** — save exact candidate geometry, PDK identifier (without distributing proprietary files), ADS/Momentum settings, extracted S-parameters, run logs, condition values and metric extrema. If available, test PVT/geometry sensitivity rather than silently assuming nominal behavior holds across corners.

## 6. Promotion gates

Only after the environment, testbenches and reference design are available should this plan be converted into complete public/hidden test files, executable structural/electrical verification, reward/report outputs and a versioned runner profile. This plan's metric definitions are subject to review against those original benches. No current part of this folder establishes official or silicon-validated compliance.
