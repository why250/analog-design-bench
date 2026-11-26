# Stage 1: theory and simplified model proposal

**Task:** `inp-bondwire-cob-modeling-feasibility`, revision 1.  
**Record:** 2026-11-24, theory-only work package. The task contract and workflow
baseline are retained in `baseline/` alongside this report. This directory is a
theoretical study record, not an ADS engineering run. No ADS application, circuit
simulation, EM solve, or physical measurement was performed. The user has
separately authorized this Stage 1 theory work; the frozen task's original
task-definition-only authorization is not itself an authorization to simulate.

**Evidence labels:** `[Doc]` identifies cited research or technical literature;
`[Interp]` identifies an analysis or prediction derived from stated assumptions.
Simulation observations are **pending**. The confirmed research domain is
1–110 GHz, with a single-ended signal and a generic idealized ceramic substrate
for the first baseline. This domain is not a claim that any lumped model remains
valid up to 110 GHz. No product S-parameter limit or real InP process property is
assumed.

## 1. Problem, physical boundary, and choice of model

**Problem.** What limits a single signal bond between a die-side pad and a
substrate-side pad, and what must a useful first model include? The signal current
must leave one terminal and return to its source through conductors, grounds, and
potentially displacement-current paths. The magnetic energy of that whole loop,
not a signal wire in isolation, determines the loop inductance. The electric
field between the signal conductors, pads, return metal, die, and substrate stores
energy represented approximately by capacitances. At higher frequency the return
current distribution and the fields can change, and delay, radiation, and
resonances can make a small lumped network inadequate. `[Interp]`

**Choice.** Start with a proposed physically closed signal/return two-conductor
structure and a corresponding coupled lumped circuit. It exposes the missing
return path and permits analytical reasoning before a geometry is specified. It
is not a validated geometry or a claim about an ADS component. A later, separately
authorized EM model is intended to test the same physical reference planes,
return arrangement, materials, and frequency points. `[Interp]`

```text
                  proposed signal bond and associated metal
  P1 signal  o----[ Rs(f) ]----[ Ls ]-------------------o  P2 signal
             |                    || M                  |
            C1                 magnetic                C2
             |                 coupling                 |
  P1 return  o----[ Rg(f) ]----[ Lg ]-------------------o  P2 return
             ^          proposed physical return         ^
             |                                           |
        local die return                         local substrate return
```

The two return nodes are distinct. Do not short them together ideally in the
model and then count `Lg` again: that bypasses the physical return impedance.
Each `C1`/`C2` is a **proposed lumped approximation** from a local signal node
to its local return, including only the declared part of pad-to-return electric
field. The actual structure may require signal-to-return distributed capacitance,
cross-couplings, dielectric conductance, ground-plane spreading, multiple return
branches, and surrounding metal. `Rs` and `Rg` represent conductor and contact
loss only to the extent explicitly assigned. The mutual inductance `M` requires
a consistent reference direction and dot convention. The diagram does not
establish the actual ground-bond number, pad dimensions, ground-stack geometry,
bond contacts, or a complete three-dimensional physical layout. `[Interp]`

P1 is the die-side pair `(signal, local return)` and P2 the substrate-side pair
`(signal, local return)`, ordered and with voltages taken from signal to its
local return. The analysis bench owns excitations and terminations. Use equal
real 50-ohm reference impedances only as a **proposed comparison convention**;
the target device impedance, port modes, de-embedding, fixture ownership, and
actual planes remain to be agreed before solving. A future port definition must
identify how its current closes through the physical return, and both circuit
and EM representations must use equivalent port reference planes and wave
normalization. A local return is not a magical ideal ground in the DUT. A fixture
may contain return conductors outside the DUT only if its connectivity and
de-embedding are documented. `[Interp]`

## 2. Inductance and the return path

### Loop, mutual coupling, and limits

Take the positive reference directions of two coupled conductors to be aligned
along the same geometric direction, with a positive mutual inductance `M` for
that reference convention. For a single isolated two-conductor loop, the actual
signal and return currents are equal and opposite: `i_s = I`, `i_g = -I`. With
magnetic energy `W = (Ls i_s^2 + Lg i_g^2 + 2 M i_s i_g)/2`, the loop energy is

```text
W = (1/2) L_loop I^2,       L_loop = Ls + Lg - 2 M.
```

This expression assumes a two-path loop, consistent dot convention, and a
frequency region where the selected current distribution and lumped description
are meaningful. A different current reference reverses the sign convention for
`M` without changing physics. With several return bonds, return-plane spreading,
unequal currents, displacement-current paths, or additional coupled metal,
retain the full coupled-inductance/impedance matrix; substituting `Lg/N` or a
single `M` without solving current sharing is not justified. `[Interp]`

`[Interp]` The idealized parallel-wire relationship in the next section predicts
that bringing the signal and return conductors closer reduces loop inductance
per unit length under its stated assumptions. It is not a universal numerical
prediction for an arched bond or a multilayer substrate.

### Analytic limiting example: parallel wires

For two long, straight, parallel circular conductors with the same radius `a`,
center-to-center separation `d` much greater than `a`, uniform surrounding
medium with permeability `mu` and permittivity `epsilon`, and a quasi-static
two-conductor TEM approximation, a useful per-unit-length external approximation
is `[Doc]` [Hirano, 2022](https://globals.ieice.org/en_transactions/electronics/10.1587/transele.2021ESS0002/_pdf):

```text
L_loop' ≈ (mu / pi) ln(d/a)      [H/m]
C_pair' ≈ (pi epsilon) / ln(d/a) [F/m]
```

The relation assumes an idealized uniform medium, idealized long parallel
conductors, and does not include end effects, dielectric stratification,
ground planes, wire curvature, bond balls, conductor internal inductance,
proximity redistribution, radiation, or cavity modes. It is a sanity-check
limit, not a formula for this COB geometry. In this restricted limit, reducing
`d/a` decreases loop inductance per length and increases pair capacitance;
these changes are linked, so lower inductance alone does not guarantee better
wideband matching. `[Interp]`

`[Doc]` Hirano's specific simulated GSG structure gave a low-frequency scale
near 1 nH/mm and showed a chip–substrate resonance around 22 GHz for one
particular geometry. Those numbers describe that paper's structure, not the
present die, ceramic, fabrication process, or allowable operating frequency.
The same paper shows that a simple transmission-line representation can miss
chip–substrate resonance. The Stuttgart review discusses a 1 nH/mm rule of
thumb and single-wire inductance approximations, which similarly do not define
this task's loop inductance: [Bond-Wire Impedance Compensation for
Millimeter-Wave Chip Interconnects](https://www.ilh.uni-stuttgart.de/dokumente/proceedings_2020.pdf).

## 3. Pad capacitance and frequency-dependent conductor loss

### Capacitance

For a uniform dielectric between large parallel conducting plates of overlap
area `A`, separation `h`, and permittivity `epsilon`, the electrostatic limit
is `C ≈ epsilon A/h`. It predicts more capacitance with greater area or
permittivity, and less with greater spacing, **only while the assumed geometry
is held fixed**. `[Doc]` [OpenStax, Capacitors and
Dielectrics](https://openstax.org/books/physics/pages/18-5-capacitors-and-dielectrics).

An actual bond pad is not generally a large parallel plate. Edge fringing,
die thickness, dielectric stack, nearby grounds and traces, finite thickness,
bond shape, conductive substrate and frequency-dependent dielectric loss can
change both capacitance and coupling paths. `C1` and `C2` need not be equal.
A larger shunt capacitance may partially compensate inductive reactance over
some band, move a resonance, or worsen mismatch elsewhere; it cannot be called
universally beneficial. No actual InP PDK capacitance is supplied here. `[Interp]`

### Resistance and skin effect

For a homogeneous good conductor of conductivity `sigma` and permeability
`mu`, at angular frequency `omega = 2 pi f`, skin depth is `[Doc]`
[MIT electromagnetic-field text, Section 7.4](https://ocw.mit.edu/courses/res-6-002-electromagnetic-field-theory-a-problem-solving-approach-spring-2008/a351c693a668be056fefd2ffff0dc068_MITRES_6_002S08_chp07_text.pdf):

```text
delta = sqrt(2/(omega mu sigma)) [m].
```

For an isolated round wire of radius `a` and length `ell`, when `delta << a`,
the ideal smooth-surface approximation is

```text
R_ac ≈ ell / (2 pi a sigma delta) [ohm],      R_ac ∝ sqrt(f).
```

`[Doc]` [MIT thesis, wire internal impedance approximation](https://cba.mit.edu/docs/theses/02.09.fletcher.pdf).
When skin depth is comparable to the radius, use an appropriate full internal
impedance model instead. This approximation does not include nearby-return
proximity effects, nonuniform current in the bond, ground-plane and pad loss,
contact resistance, surface roughness, temperature dependence, or dielectric
loss; actual signal and return losses must each be included as applicable.
Using frequency-dependent resistance without its associated reactive dispersion
may also compromise a causal broadband model. `[Interp]`

## 4. Reflection and a purely analytic illustrative example

To isolate the effect of loop inductance, temporarily replace the **entire closed
loop** by a single series impedance `Z = j omega L` between two ports with the
same real reference impedance `Z0`; omit both pad capacitors and all loss. This
is a mathematical reduction of the closed loop, not a one-wire DUT without a
return. For a series element, `A=D=1`, `B=Z`, `C=0`. Standard two-port conversion
then gives `[Interp]`:

```text
S11 = Z / (2 Z0 + Z)
S21 = 2 Z0 / (2 Z0 + Z)
|S11|^2 + |S21|^2 = 1  for Z = j omega L and real Z0.
```

The lost transmitted power in this lossless example is reflected power, not
conductor heating. With `x = omega L/Z0`, `|S11| = x/sqrt(4+x^2)` and
`|S21| = 2/sqrt(4+x^2)`. `S11_dB = 20 log10 |S11|` and insertion loss
`IL_dB = -20 log10 |S21|`. The following hand-calculation values use **only**
the hypothetical `L=100 pH` and `Z0=50 ohm`; they are not process values,
measured data, ADS output, performance limits, or an established model valid
at every row frequency. `[Interp]`

| Frequency | Series reactance | S11 | Insertion loss |
| --- | ---: | ---: | ---: |
| 1 GHz | 0.628 ohm | -44.04 dB | 0.00017 dB |
| 10 GHz | 6.283 ohm | -24.05 dB | 0.0171 dB |
| 110 GHz | 69.12 ohm | -4.90 dB | 1.696 dB |

The last row deliberately extrapolates the *formula* to show its mathematical
sensitivity to frequency; it is not evidence that a physical bond wire is a
100 pH constant inductor at 110 GHz. Pads, losses, delay, parasitic coupling and
resonances can all change the response. An eventual calculation should compare
complex S-parameters on common reference planes and must not label the analytic
numbers an observation. `[Interp]`

## 5. Predictions recorded before any simulation

The following are conditional hypotheses, not results. For any later controlled
comparison, state which end positions, arc length, surrounding geometry,
frequency, reference planes and material properties are kept fixed. `[Interp]`

| Change | Prediction for a controlled low-frequency case | Important exceptions |
| --- | --- | --- |
| Increase wire length | Series resistance and loop inductance generally increase when the return topology and comparable cross-section remain fixed; inductive mismatch tends to increase | Changing length may also change pad separation, wire shape, mutual coupling, distributed phase, and resonances; measured S response need not be monotonic |
| Bring a properly connected return bond closer | Mutual coupling can reduce loop inductance for opposite signal and return currents | Capacitance, current crowding, pad geometry, additional return paths, and resonances also change; no universal spacing optimum |
| Increase wire diameter at fixed path and material | DC resistance decreases; isolated-wire high-frequency resistance generally decreases; inductance changes more weakly in the parallel-wire limit | Proximity effect, actual contact geometry, finite thickness and nonuniform current may dominate; S-parameters need not improve at every frequency |
| Increase loop height | A higher arch may increase enclosed loop area and arc length, increasing inductance if the return remains fixed | No monotonic law is established for arbitrary endpoint, arch shape, ground spacing, or fixed arc length; capacitance and radiation also change |
| Add parallel signal or ground bonds | Equivalent impedance may decrease and coupling/current distribution changes | Strong mutual inductance means neither inductance nor AC resistance is automatically divided by the wire count; interactions can cause new modes |
| Change ceramic to PCB | Permittivity, loss, thickness and ground layout can alter capacitance, return current, phase and loss | No general ordering is possible without specified material stacks and geometry; comparison is a later optional study |

**Pending observation:** no candidate structure, ADS output, measured S-parameter,
mesh convergence or experiment exists in this work package. Predictions are to
be retained unchanged and compared against actual authorized observations later.

## 6. Frequency range, resonance, and model validity

An electrically short geometry, often screened using `ell/lambda << 1`, can be
a reason to try a lumped model; it is not proof of validity. The relevant
wavelength depends on fields and propagation environment, not necessarily free
space alone. Even a short wire may be coupled to a larger die/board structure
with a resonance. Verify the complete geometry and frequency coverage against a
more appropriate model and, where available, independent physical data. A
constant low-frequency RLC fit must not be extended to 110 GHz without evidence.
The agreement band must be reported from actual comparisons; do not invent an
upper validity frequency. `[Interp]`

`[Doc]` The [Hirano paper](https://globals.ieice.org/en_transactions/electronics/10.1587/transele.2021ESS0002/_pdf)
explicitly reports that, for its chosen GSG setup, even the simple distributed
line equivalent misses a resonance involving the substrate, bond and chip.
That paper's result motivates a physical-boundary investigation; its resonance
frequency is not transferable to this study.

For any future passive reciprocal baseline, record the full complex S-matrix,
real positive reference impedances and reference planes. The task verification
plan calls for a full-matrix passivity test, reciprocity check, numerical
convergence and reproducibility under predeclared tolerances. Mesh convergence
alone does not establish an accurate physical model or measured-hardware
agreement. The analytic example above is not a verification result. `[Interp]`

## 7. Next investigation, decisions, and open questions

**Stage 1 handoff:** this record supplies a theoretical model proposal, formulas,
assumptions, limitations and predictions for engineering review. It does not
approve Stage 2 execution or resolve readiness for a native ADS study.

**Proposed bounded Stage 2, pending authorization:** inspect the actual selected
ADS version's official documentation and available authorized capabilities for
bond-wire representations, parameterized geometry, FEM versus Momentum suitability,
port/return construction, materials, boundaries, meshing, S-parameter extraction,
and any supported automation. Retain exact references, version, what was actually
observed versus inferred, unavailable features and alternatives. Do not assume
any particular API exists, start ADS, or create a solver model merely by adopting
this proposal. Before a future solve, agree on a resource ceiling, frequency
sampling, convergence criteria, and scope. `[Interp]`

**Open questions, pending:**

1. What actual RF application, priority sub-band, port modes, real or complex
   reference impedances, de-embedding and reference planes are intended?
2. What die thickness, pad shape and stack, ceramic dielectric/conductor stack,
   ground-plane extent, and connections form the physical boundary?
3. What are the wire material, diameter, arc length, loop profile, contact
   structure, manufacturing constraints, and permissible ground bonds? If unknown,
   which generic values and sources are acceptable for a limited study?
4. How many physical return paths carry current, and what environment or fixture
   completes each loop? Are neighboring signal wires relevant to coupling?
5. Which documented tool and solver capabilities are actually available, and
   what frequency sampling, cost budget and predeclared numerical tolerances will
   support the next decision?
6. What independent data, if any, could later test physical accuracy beyond
   passivity, reciprocity, reproducibility and numerical convergence?

The engineering workspace is not yet initialized. When it is created under the
approved workflow, the learning record is intended for
`workspaces/inp-bondwire-cob-modeling-feasibility/learning-notes.md`; preserve
this report as the source and append rather than overwrite existing notes. This
record is supplementary and does not change the task contract, workflow, or
verification criteria.
