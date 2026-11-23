# Single-device model and characterization plan

**Planning draft; no geometry, EM solve or achieved device performance is
claimed.** This independent task targets one complete 120 pH device for a
65 GHz LPF. Unit-device geometry and EM are authorized. Another on-chip process
or an explicitly assumed on-chip stack is allowed; execution must select and
freeze the stack, solver and numerical conditions before candidate-design and
acceptance EM work. Separately labeled preliminary solver calibration may use
scratch inputs but does not establish a candidate's acceptance.
The work is not restricted to the previously selected PDK. Assumed material
properties or a generic substrate do not establish an InP process capability.

Use [instruction.md](instruction.md) for the specification and
[verification-plan.md](verification-plan.md) for numerical acceptance. Report
frequency-dependent behavior through 80 GHz and any extended resonance search
within the qualified material/solver domain. No Q, SRF, footprint or geometry
value is asserted as available process capability by this document.

## 1. Physical device and input provenance

Define the device boundary at two signal terminals `p` and `n`. Retain a
physically specified ground/substrate/return environment and any independently
connected shield, backside or auxiliary conductor. These belong to the model;
an unexplained infinite ground plane is not a neutral reference choice.

Before EM record the source and status of conductor thickness/conductivity,
dielectric thickness/permittivity/loss, substrate properties, passivation,
vias, backside conditions and relevant frequency dependence. Separate supplier
data, published data and provisional assumptions. Keep restricted source and
host bindings private. Unverified stack assumptions imply conditional results,
not a fabrication-ready or qualified InP device.

Use finite conductor and dielectric/substrate loss in the engineering candidate
where physically applicable. Include skin/proximity effects and thickness using
an appropriate solver/material treatment. Perfect-conductor/lossless controls
may explain mechanisms but cannot establish achievable Q. Include every lead,
via and return segment inside the declared device boundary exactly once.

## 2. Raw network and return conditions

Prefer two signal ports referenced to the specified physical return, preserving
both signal-to-return and signal-to-signal behavior. Use additional ports when
independent substrate/shield connections are necessary. Preserve the complete
raw complex S matrix, original port order, reference impedances and reference
planes; a Touchstone filename alone does not define those physical connections.

A floating differential one-port alone can suppress common-mode/shunt behavior
needed when the device is inserted into an LPF. It is therefore an optional
diagnostic, not the sole handoff model. For a multiport device, declare all
auxiliary terminations before deriving a reduced two-signal-port response;
do not take an unexplained matrix sub-block as the terminated network.

Retain both raw and any calibrated/de-embedded network. Document feed removal
and its uncertainty, especially because access inductance may be comparable
with 120 pH. Moving a reference plane changes the reported device. Do not tune
the port location merely to recover the target number.

## 3. Primary end-to-end impedance definition

For the declared reduced two-port, let currents enter the signal terminals and
voltages reference the same physical return. Define the primary extraction by
zero net common-mode terminal current:

```text
[V1,V2]^T = Z * [I1,I2]^T
I1 = I; I2 = -I; Icm = I1 + I2 = 0
Vd = V1 - V2
Id = (I1 - I2)/2 = I
Zd = Vd/Id = Z11 + Z22 - Z12 - Z21
```

The whole device, from `p` to `n`, targets 120 pH under this definition.
It is not 120 pH per half. For a symmetric reciprocal network the expression
reduces to `2*(Z11-Z12)`; do not apply symmetry without checking the data.
There is no additional division by two in the definition above.

Some orthonormal modal conventions use different voltage/current scaling.
For two equal 50-ohm single-ended references, the usual physical differential
reference is 100 ohm. Record the actual convention and common-mode termination.
An Sdd value with the common mode matched is not generally the same experiment
as Icm=0 when differential/common-mode conversion is present.

Likewise, setting `Vcm=(V1+V2)/2=0` with a balanced voltage source does not
necessarily enforce Icm=0 in an asymmetric device. Preserve this distinction
when comparing direct excitations, mixed-mode conversions and impedance data.

Grounding terminal 2 is a different experiment. With V2=0:

```text
Zin_grounded = Z11 - Z12*Z21/Z22 = 1/Y11
```

Its extracted L/Q need not equal the end-to-end quantities. Z11 alone describes
I2=0, whereas a conventional S11 measurement has the other port matched;
neither is automatically the required Zd. State the condition beside every
reported inductance or Q curve.

## 4. Frequency-dependent metrics and resonance

At positive frequency f define:

```text
L_eff(f) = Im[Zd(f)]/(2*pi*f)
R_eff(f) = Re[Zd(f)]
Q_imp(f) = Im[Zd(f)]/Re[Zd(f)]   [Re(Zd)>0]
```

Evaluate the 120 pH target at 65 GHz under the specified conditions. Report
L_eff, R_eff and signed Q_imp at 65 and 80 GHz with full curves. The impedance
ratio Q_imp is a declared diagnostic; it is not every possible stored-energy
or resonator-bandwidth definition of Q. A negative value denotes capacitive
reactance, not negative dissipation. Ideal zero-loss limits need typed statuses,
not fabricated finite Q values. Numeric tolerance and flatness targets belong
to the reviewed task specification; they are not process facts.

Define the first terminal SRF operationally as the first positive-frequency
inductive-to-capacitive reactance crossing under the same return/excitation
conditions, where a finite crossing exists. An impedance-magnitude peak can
occur elsewhere; retain both quantities separately. A lossless impedance pole
may reverse the reactance sign without a finite zero. Distributed structures
can have multiple resonances, so retain all observed crossings/modes and their
search intervals. If none is found, report no crossing observed in the qualified
interval. Claim an SRF lower bound only when adequate lower-frequency and
interval coverage supports it; do not invent an infinite or extrapolated value.

## 5. Candidate families and EM checks

Start with a small inventory-driven comparison of straight conductors/high-Z
sections, hairpin/U-shaped conductors and single-turn/open-loop structures.
Change legal length, width, spacing and return configuration with a recorded
physical prediction. Add a multi-turn spiral only when the initial candidates'
reactance, footprint or losses justify its additional coupling and capacitance.
No dimensions can be selected credibly before the stack and geometry limits.

An available RFIC Inductor Toolkit may generate initial artwork. Review its
layer mapping, dimensions, underpass/vias, terminals and source assumptions
against the frozen stack. Generated or demo-validated geometry does not prove
that the selected 65 GHz device has achieved its target or passed EM convergence.

A high-Z section is a distributed network, not automatically a pure inductor.
It may meet L_eff at one frequency while retaining consequential shunt loading.
Use the full response and declared flatness criterion before calling any family
a usable 120 pH replacement. Inspect current density and return currents to
explain metal loss, nearby-conductor coupling and unexpected resonances.

Separate mesh refinement, frequency-interpolation checks, boundary-distance
checks and port/calibration sensitivity. Refine conductor edges, gaps, vias
and thickness treatment as required by the selected solver. Check the actual
65/80 GHz solves, not only an interpolated display. A DC/low-frequency solver
or supported limit must establish DCR; the first RF point is not DC evidence.
Compare DCR against a geometry/material estimate where applicable.

Check passivity and reciprocity with the appropriate normalization and retain
conditioning diagnostics. S-to-Z conversion can be ill-conditioned near an
open common mode or a resonance. Use a stable constrained-current/nodal or
appropriate network calculation; do not add arbitrary regularization and then
claim precise L/Q. Preserve the original S data when a derived quantity fails.

## 6. Model returned to the LPF

Return the full qualified two-/multiport model with physical returns, frequency
domain, raw evidence and declared device boundary. A compact explanatory fit
must retain its residuals and validity and cannot silently replace EM data.
Zd alone cannot reproduce arbitrary common-mode loading of a series LPF arm.
Record nearby-metal/return assumptions and any keepout sensitivity; one isolated
device does not characterize coupling among all filter elements. This task
qualifies one 120 pH candidate, not the larger central inductors or the complete
LPF. Filter integration still requires all original electrical checks.

## Primary references

- [Muehlhaus: RFIC Inductor Measured vs. Simulated](https://muehlhaus.com/wp-content/uploads/2011/12/RFIC-Inductor-Measured-vs-Simulated.pdf): end-to-end versus grounded Q definitions and physical-boundary comparisons.
- [Muehlhaus: global-ground or differential ports](https://muehlhaus.com/support/ads-application-notes/momentum-port-global-ground-or-differential): port definitions must preserve required shunt-current paths.
- [Keysight Momentum overview](https://www.keysight.com/il/en/lib/resources/training-materials/momentum-key-features-1936424.html): planar geometry, coupling, current/mesh and broadband modeling capabilities; not validation of an unspecified stack.
