# Ideal ADS LPF simulation and metric verification plan (revision 2)

**Current scope:** ideal L/C schematic and S-parameter simulation only. This is a documented, manually repeatable measurement protocol, **not** an implemented independent formal verifier and **not** an ADS/PDK/EM validation claim.

## 1. Two-port setup

- Place two **ADS Term** ports at the LPF DUT boundaries; Port 1 = \`rfin\`, Port 2 = \`rfout\`, both referenced to the same ground and both \`Z = 50 Ohm\`. Terminations are owned by the testbench and are not part of the filter schematic.
- Use **ideal L and C** (positive, finite nominal values, no loss or parasitics) for the required design. A pure ideal TLIN stepped-impedance variant is an **optional comparison**, not a first-milestone requirement.
- Input and output reference planes are the bare DUT port terminals. Pads, PCB interconnect, EM extraction, de-embedding, temperature and process variation are **out of scope**.
- Confirm a continuous small-signal path through the filter at DC. S-parameters are obtained for frequencies **greater than zero**; use topology/low-frequency limit reasoning to represent DC.

## 2. Suggested ADS sweep and outputs

1. Create a new ADS workspace with a named LPF schematic and an SP controller (linear two-port S-parameter analysis).
2. Coarse sweep: e.g. **1 MHz–120 GHz**, including the 0–65 GHz passband and the 80 GHz stopband checkpoint. A broad sweep beyond 80 GHz is **for understanding only**, not an extra stopband requirement.
3. Passband metric sweep: e.g. **1 MHz–65 GHz with ≤0.1 GHz spacing**, then refine every suspected S11/S22 extremum and S21 minimum as needed. Coarse pointwise maxima alone do not certify the entire continuous band.
4. Add **separate exact frequency points at 65 GHz and 80 GHz**. Do not replace 80 GHz by the nearest point of a coarse frequency grid.
5. Plot \`dB(S(1,1))\`, \`dB(S(2,2))\`, \`dB(S(2,1))\`, optionally \`dB(S(1,2))\`; save the ADS schematic/workspace, sweep parameters, numerical results and a complex **.s2p Touchstone** export.

Do not confuse the stated **passband edge of 65 GHz** with a \`-3 dB\` cutoff. Report the actual \`-3 dB\` frequency separately only if useful for understanding the shape of S21.

## 3. Four mandatory acceptance checks

Let \`sij(f) = 20*log10(abs(Sij(f)))\`, in dB. The grid and interpolation/refinement method must be reported.

    S11_worst = max_{0 < f <= 65 GHz} s11(f)
    S22_worst = max_{0 < f <= 65 GHz} s22(f)
    IL_worst  = max_{0 < f <= 65 GHz} (-s21(f))   [dB]
    S21_80    = s21(80 GHz)

    PASS only if:
        S11_worst <  -20.0 dB           (strict)
        S22_worst <  -20.0 dB           (strict)
        IL_worst  <    1.0 dB           (strict)
        S21_80    <= -20.0 dB           (inclusive)

Always report the worst-case passband **frequency** for S11, S22 and IL. All four checks must be finite and available; failed simulation, missing frequencies, no converged data, or unknown numerical extrema must **not** be treated as passing. For an ideal lossless model, also check the low-frequency limit including the desired DC-through behavior.

Use \`IL(f) = -dB(S(2,1))\` for the positive insertion-loss metric. Note that in a lossless 50 Ω two-port, \`|S11|^2 + |S21|^2 = 1\`. Thus achieving **S11 < -20 dB** over the passband mathematically ensures \`IL < 0.04365 dB\`; the **<1 dB** limit is still a separate explicit criterion and useful for later finite-loss revisions.

## 4. First-milestone design workflow

| Step | Activity | Required evidence |
| --- | --- | --- |
| Define | Review all four limits and ordered ports | This document and approved specification |
| Synthesize | Start with a **simple ideal L-C ladder**; calculate element values using an appropriate 50 Ω normalized low-pass prototype | Topology sketch/ADS schematic, equations, component table |
| Evaluate | Simulate S11, S22, S21 over the specified passband and exact 80 GHz | Raw S-parameters, pass/fail table, frequencies of extrema |
| Refine | If a low-order ladder cannot meet the 65–80 GHz transition, increase order or introduce an **LC transmission zero** (Chebyshev / quasi-elliptic / elliptic as justified) | Updated topology rationale and before/after plots |
| Check | Compare simulated result to equations / a separate ABCD cascade calculation | Calculation method, discrepancies and explanation |
| Hand off | Freeze the ideal ADS source and relevant result data | Reproducible ADS workspace and a concise results summary |

The comparison to a stepped-impedance TLIN LPF is **optional** for this revision; physical feasibility, conductor Q, PDK passive models, SRF, dimensions, full-wave EM and DRC are deliberately deferred. There is **no continuous stopband acceptance range**.

## 5. Optional, non-scoring observations

Report to help understand or improve the ideal circuit, **not as pass/fail requirements**:

- S21 shape beyond 80 GHz and any other poles, resonances, transmission zeros, or spurious passbands. A notch exactly at 80 GHz by itself should not be called a demonstrated low-pass response without reviewing the overall shape.
- Passband group delay, ripple and return-loss margin.
- Ideal reciprocity \`S21 ≈ S12\`, lossless power conservation \`|S11|² + |S21|² ≈ 1\` and \`|S22|² + |S12|² ≈ 1\`, within numerical tolerance. No power gain is allowed in an ideal passive network.
- Sensitivity to ideal L/C values (for learning), without claiming process or manufacturing robustness.

## 6. Beyond this revision

A later **explicitly approved** task revision may add real InP PDK parts, finite Q/SRF, geometry, EM, PVT, layout sign-off, process corners and an implemented independent official verifier. Do not require these artifacts, invent device data, or describe this specification-only folder as a fully registered and runnable analog-design-bench benchmark.
