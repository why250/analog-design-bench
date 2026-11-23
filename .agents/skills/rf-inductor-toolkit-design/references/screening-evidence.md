# Inductor screening and evidence

This guide supplies reusable checks for Toolkit-generated structures and Momentum
networks. The destination task supplies numerical targets, technology, filenames,
entrypoints and acceptance authority. No technology-qualified example is bundled.

## Native construction and exported inputs

Retain complete generator inputs: all dimensions and units, layer mapping, conductor
and substrate parameters, dielectric/loss assumptions, generator/version, ports and
reference planes. An assumed stack remains an assumed stack even after a valid solve.
Check actual generated polygons and connectivity rather than only requested dimensions.

Export through the application context required by the installed tooling. Record the
consumed geometry, vertical elevations, passive material signs, mesh/solver settings,
frequency plan and port excitation. Identify a finite physical return; document ideal
grounds or omitted conductors and their effect. Copying an EM setup can retain paths to
the original project: rebind the owned copy and verify it cannot write the original.

Before a batch, verify one useful case end to end. Distinguish geometry generation,
application export, full-wave solving, interpolation and cached-model lookup. Keep logs
showing the actual solver path and complete raw dataset, including nonconvergence and
warnings. Do not infer an extraction from a configuration flag or wrapper exit status.

## Complex network and metric definitions

Record ordered ports, reference impedance, normalization and common reference. Preserve
the complete complex S network and actual frequency samples in a standard network file
or an equally explicit format; retain the native dataset and conversion settings.

For a two-port structure with a common physical reference and constrained differential
excitation `I1 = I`, `I2 = -I`, the measured differential voltage gives:

```text
Zd = Z11 + Z22 - Z12 - Z21
R = Re(Zd)
L = Im(Zd) / (2*pi*f)
Q = Im(Zd) / Re(Zd)
```

These expressions do not include a factor of two. They describe this particular
voltage/current convention. A grounded one-port, another normalization, extra ports,
finite common-mode excitation or an auxiliary return needs its own explicitly derived
constraint. Do not drop ports from a network before defining their boundary conditions.

Only interpret Q as inductive quality factor in the declared inductive, passive region
with positive R and positive reactance. Preserve negative or zero values as diagnostics;
do not apply absolute values to manufacture acceptable L/Q. Record singular conversions,
nonfinite data, resonance and unsupported samples as invalid or qualified observations.

Apply the task's endpoint, checkpoint and band-wide rules. Refine extrema where required;
sparse samples alone do not establish a continuous-band bound. Keep interpolation and
extrapolation policy explicit. Do not invent a DC endpoint for a sampled RF network.

## Ranking and applicability

Separate observations with incompatible stacks, ports/returns, reference planes,
topologies or model methods. Rank only admissible candidates within compatible groups.
Use the task's reference frequency, target tolerance, objective and tie-breaker; no
particular target inductance or frequency is implicit in this skill.

Record every evaluated geometry, observation validity, failure reason, raw-data link and
budget consumption. A bounded unsuccessful search establishes only what was tested.
Predictions guide new cases; they are not observations or acceptance evidence.

## Delivery verification

For the selected candidate, verify that native geometry, solver input, raw network and
reported metrics describe the same source and conditions. Reopen or independently rebuild
when requested and authorized, in a fresh work area; report the comparison and tolerances.

Provide the editable source and required metadata, complete network, settings, model
limitations, logs, measurements and a small index of the selected evidence. Keep private
technology bindings and licensed dependencies in their authorized store; list what the
consumer must supply. A byte-verified transfer establishes integrity, not model validity,
electrical acceptance or successful native reopening.
