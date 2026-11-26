# Verification plan: inp-bondwire-cob-modeling-feasibility-r1

**Status:** Planned, not executed. This document describes an engineering
study and is not an implemented independent verifier. No simulated performance
or pass result exists from creating the task. The [task contract](instruction.md)
owns the scope and confirmed/proposed/investigate distinctions.

## Measurement conditions and mapping

Before a model is solved, retain an unambiguous two-port geometry and connectivity
diagram, actual materials and their frequency validity, port modes, reference
impedances, reference planes, return conductor, fixtures, de-embedding and
frequency list. Identify all exclusions and the geometry/parameters consumed by
each solver. Real 50 ohms is a proposed comparison convention, not a confirmed
device property. Use identical conditions for the circuit and EM comparison, or
document and justify a transformation to common planes and normalization.

| Obligation | Method and retained evidence | Decision |
| --- | --- | --- |
| Theory and model assumptions | Source-linked derivation and applicability for inductance, capacitance, loss, return and mismatch; equivalent circuit and expected trends | Complete when each effect and its limitations are explained; unsupported quantitative accuracy stays unknown |
| Tool methods | Version-matched official sources and, when separately authorized, observed tool capabilities for model, solver, geometry, setup and automation | Record documented/observed/inferred separately; unavailable capability and alternative remain explicit |
| Baseline observables | Complex S11, S21, S12, S22 and input impedance over the actual sampled frequencies; parameter extraction and fit uncertainty with defined method and range | Report data and coverage; no S11/S21 product PASS is defined |
| Physical model | Connectivity and return audit, materials/geometry/port review, passive-network full-matrix passivity and reciprocity tests using appropriate normalization | Missing return or invalid definitions invalidate the affected model; unexplained violations require investigation |
| Numerical credibility | Solver and mesh setup, convergence history, sampled frequency coverage, relevant boundary/port sensitivity and reproducible comparisons | A result is credible only within its demonstrated coverage and predeclared numerical criteria |
| Model comparison | Compare complex S on the same frequencies and physical reference planes; describe deviations, expected lumped-model limits and possible mechanisms | Agreement is evidence under stated conditions, not proof of real-device accuracy |
| Sensitivity, if authorized | Record pre-run predictions, baseline, one controlled change or a declared interaction matrix, case inputs, data, checks and limits | Report observed trends and sampled range; absent optional cases are uninvestigated |
| Reproduction and traceability | Fresh reconstruction or independent replay of the selected case with frozen inputs, tool version, settings, logs, raw data and comparison | Claim reproducible only if the predeclared comparison succeeds; otherwise retain the mismatch and limitation |

## Physical and numerical checks

Before a solver run, set and record numerical tolerances appropriate to the
solver, frequency, model precision and requested conclusion. They are numerical
credibility criteria, not product performance limits. Do not retroactively
relax them to force a pass. Keep the complete complex two-port matrix and check
finite values, expected frequency ordering, port orientation and reference
normalization. For passive power-wave S parameters with compatible real positive
reference impedances, evaluate the smallest eigenvalue of `I - S^H S` at each
sample and compare it against the predeclared numerical tolerance. Check
`S21 - S12` in complex form for a reciprocal structure under matched reference
conditions. Investigate nonphysical gain and any violation; checking only each
individual magnitude is not an adequate full-matrix passivity test.

Define mesh levels and convergence metrics before solving. Compare at least
successive refinements at representative low, middle and high frequencies and
near features that affect conclusions, including complex S and selected
extracted parameters. Record mesh sizes, solver stopping controls, residuals,
changes and frequencies. A single successful solve is not a convergence test.
If convergence is not established, mark the affected band/result indeterminate;
do not extrapolate a few frequencies to continuous 1–110 GHz coverage. Include
frequency refinement and boundary/port sensitivity where necessary to support
the claimed range, under the approved cost ceiling. Define comparison and
replay tolerances before running and report absolute as well as relevant
normalized differences with units. Separate solver convergence from physical
model validity and from independent experimental validation.

## Outcome semantics and completion

Record these conclusions independently, including reasons and evidence links:

- **Research completion:** COMPLETE only when Stages 1–3 have the specified
  documented outputs, an adequately verified and reproducible baseline, a
  comparison with limitations, and a reasoned next decision. Stage 4 completion
  requires only cases explicitly selected and authorized later. An incomplete
  or invalid required baseline leaves research INCOMPLETE; report useful failed
  findings without fabricating model validity or success.
- **Model validity:** PASS only for the specified idealized model, conditions and
  demonstrated frequency coverage with physical and numerical checks satisfied;
  FAIL for a demonstrated failed validity criterion; INDETERMINATE where
  evidence or convergence is insufficient; INVALID for a malformed model,
  absent return, incorrect setup or corrupt data. No PASS implies agreement
  with real InP hardware without independent measured/process evidence.
- **Electrical performance:** report S and impedance as observations. With no
  confirmed product threshold, product PASS/FAIL is not applicable; missing or
  insufficient data remains INDETERMINATE and an invalid model remains INVALID.
  A later product limit requires an explicit contract revision and appropriate
  uncertainty and coverage rules.
- **Benchmark acceptance:** outside current scope, not assessed; no formal
  benchmark or independent acceptance is established by this task.

For any future explicitly confirmed quantitative criterion, PASS means valid
evidence establishes the criterion within the stated numerical uncertainty;
FAIL means valid evidence establishes a violation; INDETERMINATE means coverage
or uncertainty cannot decide it; INVALID means defective inputs, model, setup,
simulation or data prevent a meaningful comparison. Keep other outcomes visible
and never interpret missing data as failure or success.

## Retention and review gate

In each later authorized run retain source and input snapshots, geometry and
material manifest, model boundaries, port definitions, solver deck/setup,
version and documentation references, frequency/mesh controls, logs, raw
results, complex S exports, measurements, check reports, comparison and
reproduction records. Relate each result to its actual consumed inputs and
keep failed attempts and explanations. Use machine-readable integrity receipts
where the project requires them; shared reports state verification outcomes in
plain language. Keep private model locations and environment bindings out of
the portable task. Review actual artifacts against this plan before closing a
run; static routing, a successful process exit, and the existence of files do
not establish electrical or model acceptance.
