# Stage 2 measurement, completion and reproducibility contract

**Draft operator protocol, not an implemented verifier. No Stage 2 results
exist by virtue of this document.** The numeric tolerances below are proposed
engineering research tolerances, distinct from the unchanged system limits.

## 1. Bench ownership and conditions

| Item | Owner / condition |
| --- | --- |
| DUT | Fixed series-L/shunt-C ladder with declared nonideal two-terminal models |
| Ordered native terminals | rfin, rfout, gnd; all inout |
| SP ports | Bench-owned Term1 at rfin and Term2 at rfout; real 50 ohm each |
| Ground / reference planes | Bench connects gnd to ideal common ground; planes at bare rfin/rfout |
| Bias / supply / loads | No DUT bias/supply; no internal termination or additional loading |
| Analysis | Linear small-signal two-port SP; all four complex S parameters |
| Temperature | Proposed 25 degC bookkeeping setting; no coefficient temperature dependence |
| Process / mismatch | Synthetic deterministic coefficient cases only; no PDK corners or probability model |
| Diagnostic band | 1 MHz-120 GHz, plus DC limit and device-resonance refinement |

Confirm units, model connections and coefficients against the schematic-generated
netlist for every case. A case manifest must distinguish a generator label such
as Q_L_ref from actual frozen Rs/Cp and terminal Q/SRF after perturbation.

## 2. System measurements

For the complete model's continuous response, including its DC limit:

```text
S11_worst = max over 0 <= f <= 65e9 of 20*log10(abs(S11(f)))
S22_worst = max over 0 <= f <= 65e9 of 20*log10(abs(S22(f)))
IL_worst  = max over 0 <= f <= 65e9 of -20*log10(abs(S21(f)))
S21_80    = 20*log10(abs(S21(80e9)))

S11_worst < -20 dB; S22_worst < -20 dB; IL_worst < 1 dB
S21_80 <= -20 dB
```

Implement comparisons in linear magnitude to handle exact zeros correctly:
passband abs(S11), abs(S22) < 0.1; passband abs(S21) > 10^(-1/20);
abs(S21(80e9)) <= 0.1. Finite complex S with zero magnitude is valid:
zero reflection passes matching; zero transmission fails passband insertion
loss and satisfies the stop checkpoint. Represent infinite dB limits with a
status plus the linear value, not JSON NaN/Infinity or a fabricated finite floor.
Missing/nonfinite complex samples are a different, invalid-data condition.

Report each worst metric and all tied extrema within the numerical resolution,
its frequency, signed margin, uncertainty and status. Include exact 65 GHz
S11/S22/S21 and exact 80 GHz S21. Preserve strict versus inclusive comparisons;
rounding a display value must not change a decision.

## 3. DC and full-band coverage

For the required leakage-free fixed-Rs model, compute DC from the sum of the
five series resistances as derived in [model-plan.md](model-plan.md). Cp opens
at DC and series capacitor branches open; capacitor ESR/ESL do not remove
that open circuit. Use the actual changed model if optional leakage is enabled.
DC failure alone establishes electrical FAIL, while RF characterization is
still required for completion of the research matrix.

The ideal Chebyshev continuous-band bound does not apply to lossy/parasitic
cases. Use this coverage procedure for each required full-filter case:

1. Retain the baseline broad grid (2401 points from 1 MHz to 120 GHz) and
   passband grid (1301 points from 1 MHz to 65 GHz, gap <=50 MHz). Add exact
   65/80 GHz points, within 1 Hz of their intended values. Merge only truly
   duplicate frequencies; retain all four complex S values.
2. Locate extrema of both reflections and transmission for the **actual**
   rational RLC network over 0-65 GHz, including endpoints. A scaled rational
   or state-space calculation may supply candidate stationary points; for a
   real-coefficient network, stationary roots of the squared-magnitude rational
   function can be sought in x=(f/65e9)^2. Retain root-isolation/count checks,
   derivative residuals and conditioning diagnostics. Cancelled poles and
   exactly degenerate lossless limits need explicit handling.
3. Use the independent calculation over 0-1 MHz as well; justify that no missed
   low-frequency extremum violates a limit. DC plus one positive sample alone
   is insufficient. The baseline's five ideal peak locations are search seeds,
   never sufficient coverage for a nonideal network.
4. Add ADS samples at predicted extrema and within their neighboring brackets.
   Independently discover additional extrema on the ADS grid. Halve local
   spacing until two successive refinements change each worst metric by
   <=0.005 dB and each tracked extremum frequency by <=1 MHz. Use linear
   magnitudes at exact zeros and retain tied peaks separately.
5. Allow up to eight local refinement rounds before diagnosing the cause.
   Extend/refactor the numerical method if needed; hitting the cap does not
   create a PASS. Check root coverage against a second dense independent grid.
   Local convergence by itself is not proof that all extrema were found.
6. Refine diagnostic 65-120 GHz resonances/zeros when necessary to explain the
   response, and sample isolated device resonances on both sides. Such device
   diagnostics may extend beyond 120 GHz to test synthetic f_L0 values, with
   no claim that a real device model is valid there.

Continuous-band electrical PASS requires justified extrema coverage and
numerical uncertainty smaller than the available margin. If only sampled
coverage is available, report its metrics and label the continuous-band result
INDETERMINATE. Retain a conservative uncertainty estimate from root isolation,
local refinement, conditioning and ADS/cross-check disagreement; the
0.005 dB convergence target alone is not a certified error bound. Do not use
it to weaken a strict electrical limit. Resolve threshold-overlapping
uncertainty before declaring PASS or FAIL for that metric.

## 4. Independent calculation and physical checks

Using the resolved per-case coefficients, cascade series-arm impedance and
shunt-branch admittance matrices:

```text
M_series = [[1, Z_L], [0, 1]]
M_shunt  = [[1, 0], [Y_C, 1]]
M_total  = M_L1 M_C1 M_L2 M_C2 M_L3 M_C3 M_L4 M_C4 M_L5
```

Convert the product to equal-real-50-ohm S parameters. Alternatively use
independent nodal/state-space equations. Use stable nodal/scattering limits at
an ideal branch resonance; an infinite intermediate Z is not evidence of
invalid finite S data. Independence means reconstructing the declared circuit
from its coefficients, not reading a second export of the same ADS dataset.

At every exported ADS frequency require these proposed numerical checks:

| Check | Proposed criterion |
| --- | --- |
| Complex circuit agreement | max over frequency and all entries abs(S_ADS - S_independent) <= 1e-6 |
| Reciprocity | max abs(S21-S12) <= 1e-8 |
| Full-matrix passivity | min eigenvalue of I-S^H*S >= -1e-8 |
| Ideal recovery only | max absolute entry of S^H*S-I <= 1e-8 |
| Duplicate export agreement | max complex difference <=1e-8 at duplicate frequencies |
| Fresh-workspace reproduction | Same frozen frequency list within 1 Hz, max complex S difference <=1e-6 |

A1=1-|S11|^2-|S21|^2 and A2=1-|S22|^2-|S12|^2 explain absorbed
power for one-port excitation. They need not be zero in lossy cases.
Column-power tests or checking abs(Sij)<=1 alone do not replace full-matrix
passivity for coherent excitation. S11=S22 is expected only for exactly
mirror-symmetric coefficients, not for every reciprocal network. Positive
primitive values also provide an analytical passivity argument; investigate
any disagreement rather than masking it with a larger tolerance.

E1 additionally compares isolated-device equations against ADS data. Use the
normalized impedance error max(abs(Z_ADS-Z_expected)/max(abs(Z_expected),
50 ohm)) <=1e-6. Near an impedance pole, use normalized admittance error
max(abs(Y_ADS-Y_expected)/max(abs(Y_expected),0.02 siemens)) <=1e-6 instead.
These are mixed absolute/relative criteria with explicit reference scales,
not equivalent pure relative errors. Select Z or Y based on declared numerical
conditioning, record the choice and raw absolute error in ohm/siemens, and
validate both in an overlap region. Validate ideal limits, finite loss,
near-resonance and beyond-resonance behavior. Record lossless poles separately
rather than dividing by an infinite impedance.

## 5. Result states and study acceptance

| Per-candidate state | Meaning |
| --- | --- |
| PASS | Valid data/model, all numerical and coverage prerequisites satisfied, all four system limits established |
| FAIL | Valid numerical evidence establishes at least one system violation; remaining metrics retain their own states |
| INDETERMINATE | Numerical/coverage uncertainty prevents deciding at least one otherwise unresolved metric |
| INVALID | Incorrect topology/model/units, missing or nonfinite data, conflicting exports, failed simulation or failed physical/circuit cross-check |

Failure takes precedence when a valid definitive violating metric exists;
record other unresolved metrics explicitly. INVALID evidence cannot establish
electrical FAIL or PASS. Failed simulation, timeouts and missing files cannot
be scored as low performance. Rerun/repair mandatory cases or leave the study
INCOMPLETE. A scientifically explained specification failure is useful evidence.

The **study is COMPLETE** only when all of the following are demonstrated:

- E0-E9 have retained case mappings and evidence; all mandatory numerical and
  coverage problems are resolved. Boundary resolution is reported to its
  sampled intervals without an unsupported global threshold claim.
- Every required case has valid measured metrics and an established electrical
  result. The four deep-dive selections include device response, rational transfer
  poles, moved extrema, predictions and physical explanations.
- Independent circuit/physical checks pass. E9 reproductions pass the frozen
  comparison policy. Source/evidence manifests are complete and portable.
- Dominant devices, sensitivity ranks, feasible/failing regions, limitations
  and the next design decision are documented. No electrical PASS is required
  merely to complete a reproducible infeasibility study.

Study completion does not grant official benchmark acceptance. No reward.json,
reference acceptance, model score or runner readiness is generated here.

## 6. Evidence and workflow implementation required later

Reuse [the ADS workflow](../../docs/ads-mcp-workflow.md) for discovery,
native views, generated-netlist inspection, fresh outputs and cross-host transfer.
Extend the current automation through a small separately named Stage 2 path;
do not copy a complete runner or run the ideal `verify` command on nonideal data.
Before research execution, implement meaningful rejection checks for missing
65/80 GHz points, invalid coefficients, corrupt/duplicate data, passivity
violations, shifted/missed peaks and unresolved numerical thresholds. Preserve
the ideal regression checks. These checks are future work, not passed tests.

For each run retain UTC creation time, task version, baseline commit, experiment
and case IDs, full coefficient manifest, tool versions, sweeps/refinement history,
native source and script snapshots, generated netlist and exact-byte SHA-256,
simulator log, raw .ds, complex CSV, .s2p, metric/coverage/physical-check report,
plots and learning notes. JSON reports must be finite and machine-readable;
diagnostic infinity has a separate typed status. Keep failed attempts intact.

Store ordinary results in
`workspaces/inp-lpf/results/stage2-<UTC-run-id>/<case-id>/` with fresh,
non-overwriting directories. E9 reproductions use separate directories and
separate workspaces; freeze the original resolved sweep lists for comparison.
Compare netlist hashes; explain any generated header/path difference using a
retained exact diff, never silently normalize away circuit differences.

Before handoff, include the selected baseline inputs, Stage 2 source, settings,
analysis entrypoints and selected raw evidence in a self-contained bundle.
Preserve original evidence and distinguish derived plots/reports. Private PDK
material and machine/session configuration stay in authorized ignored local
storage. A future formal campaign must instead follow the repository's
registered-runner/result contracts after real verifier implementation.

## 7. Stage 3 entry decision

Select one primary stage decision in this precedence order:

1. **NOT READY:** the study or reproducibility evidence is incomplete.
2. **TOPOLOGY REVIEW REQUIRED:** the study is complete but no nonideal sample
   meets all four limits in the explored range, or a documented engineering
   judgment finds its feasible combinations unsuitable for further mapping.
   State the evidence and the fixed-value/optional-retuning boundary. PDK data
   acquisition may still proceed to test whether the synthetic range was
   relevant. A separate lower-order, elliptic or stepped-impedance comparison
   needs its own task scope; this decision does not authorize redesign here.
3. **READY FOR DATA MAPPING:** the study is complete, at least one nonideal
   sample meets all four limits, the envelope/limiting mechanisms are
   reproducible, and a concrete PDK-data request exists. This does not require
   the PDK to be available already or mean that physical devices meet the
   envelope. Conditional feasibility and process capability remain separate.

Actual PDK-aware schematic design requires authorized device data/models,
validated frequency/reference-plane definitions and an explicit mapping of
L/C, loss, parasitics and coupling. Layout/EM and corner sign-off remain later
stages regardless of the Stage 2 label.
