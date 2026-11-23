# Proposed nonideal LC models and physical reasoning

Status: **DRAFT; no Stage 2 ADS experiments have been executed for this plan.**
Read with [the task specification](instruction.md) and
[the verification plan](verification-plan.md). The circuits below are synthetic,
parameterized research models. No Q, resistance, capacitance, inductance,
resonance frequency or scan range in this plan is an InP process claim.

Confirmed scope: sensitivity and feasibility research are required; same-topology
retuning is optional. No authorized InP data are currently available, so the
study uses synthetic scans. Numerical axes and model coefficients remain draft
research assumptions rather than confirmed process values.

## 1. Model boundaries and independent parameters

Keep the nine ladder positions, five series arms and four shunt arms of the
ideal baseline. Use positive L/C, nonnegative resistances and parasitics, and
the same ordered `rfin, rfout, gnd` interface. External 50 ohm terminations,
reference planes and ideal ground belong to the testbench.

The mandatory model uses fixed coefficients. Its independent physical circuit
parameters are each arm's L/Rs/Cp or C/ESR/ESL. Q and resonance labels are derived
coordinates, not additional independent components. Select a parameterization
before generating a case; do not independently prescribe L, Rs and Q, or L,
Cp and resonance frequency, without checking consistency.

When perturbing L or C for sensitivity, keep that arm's already generated
Rs/Cp/ESR/ESL fixed unless the case explicitly describes a different coupling.
Recomputing Rs to preserve Q, or Cp to preserve resonance, answers a different
question. Record both requested labels and actual component values for every
case; never label an automatically coupled sweep as an independent sensitivity.

## 2. Series-arm inductor model

Place an ideal inductor L in series with Rs and shunt that complete RL branch
with Cp across the **same two ladder terminals**:

```text
       +---- Rs ---- L ----+
  a ---+                  +--- b
       +------- Cp --------+
```

For `s = j*omega`, with omega in rad/s:

    ZL(s) = (Rs + s*L) / (1 + s*Cp*(Rs + s*L))
    fref = 65e9 Hz
    Q_L_ref = 2*pi*fref*L/Rs
    Rs = 2*pi*fref*L/Q_L_ref

`Q_L_ref` labels the loss of the internal RL branch at 65 GHz. Under fixed Rs,
its intrinsic loss ratio is `Q_L_loss(f) = 2*pi*f*L/Rs`, not a constant across
frequency. An infinite Q label means Rs=0. Cp does not change this internal
label, but it changes the complete terminal impedance.

For finite Rs>0, define signed terminal Q as:

    Q_L_terminal(f) = Im[ZL(j*omega)] / Re[ZL(j*omega)]
                    = (omega*L/Rs)
                      * (1 - Cp*Rs^2/L - omega^2*L*Cp)

Report terminal Q at 65 and 80 GHz together with Re(Z), Im(Z) and the sign of
the reactance. Negative terminal Q indicates capacitive terminal behavior.
Undefined ratios in ideal limits must be labeled explicitly, not replaced by
an arbitrary large finite Q. Cp is a two-terminal bypass capacitance here;
capacitance from either terminal to ground is a different model.

For Cp>0 define the **lossless tuning label**:

    fL0 = 1/(2*pi*sqrt(L*Cp))

For fixed Rs>0 the actual positive terminal reactance zero, when it exists, is:

    fL_SRF = sqrt(1/(L*Cp) - (Rs/L)^2)/(2*pi)

If the radicand is nonpositive, no positive inductive-to-capacitive crossing
exists. With Cp=0 there is no finite SRF in this model. With Rs=0 and Cp>0,
fL0 is an impedance pole with a reactance sign change; do not describe it as a
finite impedance zero crossing. Preserve these distinctions in plots and tables.

In the lossless case below fL0:

    Im(ZL)/omega = L_eff = L/(1 - (f/fL0)^2)

An inductive sign alone is a weak feasibility criterion: effective inductance
can already differ greatly from its low-frequency value while still positive.
For L3=249.182172842647 pH, algebraically derived Cp values are:

| Lossless tuning label fL0 | Cp giving that label |
| --- | ---: |
| 80 GHz | 15.8833944294 fF |
| 100 GHz | 10.1653724348 fF |
| 120 GHz | 7.05928641306 fF |
| 160 GHz | 3.97084860734 fF |

These are analytic illustrations, not simulations or available device values.
For a requirement `fL0 >= target`, the corresponding Cp is an upper bound at
fixed L. For illustration only, requiring the lossless effective inductance to
stay within +10% at frequency f implies `fL0 >= f*sqrt(11)`. At 80 GHz this
would require approximately 265.33 GHz and Cp<=1.44394 fF for L3. That 10%
example is not a new electrical acceptance condition.

## 3. Shunt-arm capacitor model

Connect this complete series branch from each ladder node to `gnd`:

```text
  node ---- ESR ---- ESL ---- C ---- gnd
```

    ZC(s) = ESR + s*ESL + 1/(s*C)
    YC(s) = 1/ZC(s)
    Q_C_loss(f) = 1/(2*pi*f*C*ESR)
    fC0 = 1/(2*pi*sqrt(ESL*C))       [ESL > 0]

Fixed ESR is the mandatory first-order loss model. `Q_C_loss` excludes ESL.
For ESR>0 use signed `Q_C_terminal = -Im(ZC)/Re(ZC)`: it is positive below
fC0, zero at fC0 and negative above fC0. The complete arm is inductive above
fC0. With ESL=0 there is no finite resonance; with ESR=0 the Q ratio is
undefined at resonance and infinite in ideal reactive regions.

Optional exploratory extensions, disabled in the core matrix, may add
`G_leak >= 0` and `C_extra >= 0` in parallel with the **complete branch**:

    YC_extended(s) = 1/ZC(s) + G_leak + s*C_extra

This declares an alternate node-to-ground model without assigning a physical
InP origin. Leakage across the ideal C inside the series branch instead gives
`ZC = ESR + s*ESL + 1/(G_leak+s*C)` and is a different circuit. Label and retain
its placement explicitly if studied. Do not silently absorb C_extra into C.

## 4. DC prediction and model limitations

With optional leakage disabled, capacitor branches open at DC, Cp opens, and
each inductor becomes Rs. For equal 50 ohm references and `Rsum = sum(Rs)`:

    S21(0) = S12(0) = 100/(100 + Rsum)
    S11(0) = S22(0) = Rsum/(100 + Rsum)
    IL(0) = 20*log10(1 + Rsum/100)

Therefore strict DC matching requires `Rsum < 100/9 = 11.111111... ohm`;
strict IL<1 dB requires `Rsum < 100*(10^0.05-1) = 12.201845... ohm`.
For the full-precision baseline, `sum(L) = 968.314301273105 pH`. A common
Q_L_ref gives `Rsum = 395.466382381918/Q_L_ref ohm`, hence necessary bounds:

- Matching: Q_L_ref > 35.5919744144.
- Insertion loss: Q_L_ref > 32.4103746965.

These are analytic necessary conditions for this fixed-Rs model, not sufficient
RF feasibility conditions, ADS results or InP performance estimates. With
leakage enabled, solve the changed DC resistor network instead. Record an
analytic zero-frequency limit separately from positive-frequency SP samples.

Fixed Rs/ESR isolate mechanisms but do not claim actual broadband conductor
or dielectric behavior. A constant-Q prescription `Rs(f)=2*pi*f*L/Q` changes
the DC limit by driving resistance to zero; it cannot replace the mandatory
fixed-Rs experiment. Frequency-dependent variants need a declared frequency
range and low-frequency extension. Arbitrary sampled loss laws support only
frequency-domain diagnostics unless a causal passive realization is established;
do not infer rational poles or time-domain responses from them.

The models omit mutual coupling, distributed interconnect, ground-return
impedance, substrate networks, radiation and geometry. A favorable synthetic
case establishes conditional circuit behavior. PDK-aware design still needs
authorized device models, metal/substrate information, validity ranges and
extraction/reference-plane definitions.

## 5. Required learning checkpoints

Use the full sequence below before drawing a design conclusion. All ADS actions
and observations in this draft are planned or pending.

| Question | Physical model | Prediction | ADS simulation: planned | Observation | Explanation and design decision |
| --- | --- | --- | --- | --- | --- |
| Why does Rs increase insertion loss? | Fixed series Rs, Cp=ESR=ESL=0 | DC transmission falls by the formula above; RF dissipation follows internal currents | Compare ideal, finite-Q labels and DC prediction with complete S data | Pending | Partition reflected, transmitted and absorbed power; decide which Rs/Q range merits combined study |
| What does Cp do before self-resonance? | RL branch shunted terminal-to-terminal by Cp | Effective inductance changes below fL0; near-resonance behavior can move reflection peaks and alter 80 GHz rejection | Scan Cp with fixed L/Rs; inspect isolated L2/L3/L4 impedance and full-filter response | Pending | Compare actual reactance crossing and terminal Q with tuning labels; decide required Cp/SRF envelope |
| Why can matching improve while transmission worsens? | Passive lossy ladder | Smaller reflection need not imply better transmission because power may be absorbed | Overlay S11/S22/S21 and A1=1-|S11|^2-|S21|^2 for selected cases | Pending | Explain the power balance before declaring any improvement; retain all original electrical checks |
| When does capacitor ESL undermine the ladder? | Series ESR/ESL/C shunt branch | Near fC0 the arm becomes strongly resonant; above it the arm is inductive | Scan ESL independently and with ESR; inspect branch impedance, shifted extrema and selected rational-network poles | Pending | Distinguish device resonance, response peaks and transfer poles; decide whether the feasible envelope supports PDK mapping |

For every checkpoint retain the pre-run prediction, exact circuit coefficients,
simulation evidence, discrepancy explanation and next decision. Use independent
ABCD or nodal equations with these same declared models. Lossy passivity replaces
lossless unitarity as the general physical check; preserve the ideal recovery
case as the check where unitarity is expected.

## 6. Primary references and attribution

- [Keysight Impedance Measurement Handbook](https://www.keysight.com/us/en/assets/7018-06840/application-notes/5950-3000.pdf): background on ESR/ESL, parasitic capacitance and frequency-dependent applicability of equivalent circuits.
- [Coilcraft: Testing Inductors at Application Frequencies](https://www.coilcraft.com/en-us/resources/application-notes/testing-inductors-at-application-frequencies/): terminal Q and inductance depend on frequency and measurement conditions.
- [Coilcraft: Measuring Self Resonant Frequency](https://www.coilcraft.com/en-us/resources/application-notes/measuring-self-resonant-frequency/): first-resonance modeling and fixture influence on measured SRF.

These primary references support model interpretation only. The exact equations,
DC bounds and Cp illustrations above are derived for the declared synthetic
circuits; the references supply no InP process parameters for this task.
