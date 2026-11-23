# Verification plan: {{task_id_and_revision}}

Adapt to an existing checker, benches, result layout, and terminology when available.
Otherwise define the measurement protocol here using the task's own requirement IDs.
This plan describes required evidence; it does not create an executable verifier or score.

## Authority and readiness

- Verification scope and engineering execution/evidence status: {{verification_scope_and_execution_status}}
- Acceptance owner and implemented measurement/check entrypoint, if any: {{authority_and_entrypoint_status}}
- Actual covered candidate, models, conditions, and retained evidence, if already executed: {{actual_coverage_or_not_performed}}
- Formal benchmark applicability, task-version registration, and independent official verifier implementation/execution status: {{formal_status_and_basis}}
- Specification and input snapshot: {{frozen_source_reference}}
- Public diagnostics, independent verification, and reference access boundaries:
  {{verification_mode_and_visibility}}
- Pending environment or model preflights and their owners: {{pending_checks}}

Do not record an unperformed check as passed. A reference reproduction and a successful
diagnostic run do not establish independent acceptance or a blind benchmark result.
For engineering tasks, describe the result as engineering milestone verification with
its actual coverage and limitations. Pending verification remains pending. Formal
registration, verifier implementation, and a successful official verifier run are
separate facts; confirm each for the selected task version before claiming it.

## Coverage and decision mapping

Create one row per criterion or research obligation. Link condition sets rather than
silently substituting a nominal case for the required operating matrix.

| Criterion ID | Measurement method and units | Condition or domain | Raw evidence | Decision and coverage rule |
| --- | --- | --- | --- | --- |
| {{H_or_R_or_D_ID}} | {{expression_and_extraction_method}} | {{conditions_endpoints_sampling}} | {{raw_artifact_and_run_reference}} | {{predicate_aggregation_uncertainty}} |

Define stimulus, analysis, measurement windows, initialization, loading, reference quantities,
and process/voltage/temperature or statistical sampling only as relevant to the task.
For extrema or integrated metrics, state coverage, refinement, numerical uncertainty,
and treatment of unsampled intervals. Exact checkpoints follow declared sampling rules.
Document DC, zero-frequency limits, or steady-state evidence separately where required.
Diagnostics have no acceptance thresholds unless the specification explicitly assigns them.

## Candidate-to-result evidence chain

1. Freeze the actual candidate and bench source, parameter values, and input dependency list.
2. Inspect the generated netlist or equivalent simulator input for interface, connectivity,
   units, device policy, and required model includes; retain that exact input.
3. Resolve the actual model files, selected sections, samples, geometry, interpolation policy,
   supported domains, return structure, and warnings used by the simulator.
4. Retain simulator identity, settings, command or invocation receipt, log, and native dataset.
5. Bind each measurement and export to that run and dataset; reject stale or mismatched data.
6. Keep machine-readable integrity records with the evidence; narrative reports use names,
   versions, dates, and file links. Keep private bindings and restricted models outside public output.

## Validity and failure handling

| Evidence state | Decision treatment |
| --- | --- |
| Valid, covered, within model domain | Evaluate the declared predicate or research outcome. |
| Missing checkpoint, condition, or raw evidence | Incomplete; never infer a pass from absent data. |
| Invalid input, failed simulation, or corrupt dataset | Invalid; retain the cause and affected checks. |
| Unresolved numerical or coverage uncertainty | Indeterminate; identify the refinement needed. |
| Extrapolation or unresolved model applicability | Conditional or indeterminate; state the exact limitation. |
| Valid result outside a hard limit | Electrical failure; preserve the measured value and condition. |

Use the project's established status vocabulary when present. Keep work completion, per-candidate
electrical result, evidence validity, and readiness separate. A supported negative finding may
complete a research study without satisfying its candidate's electrical targets.

## Cross-checks, reproduction, and verifier readiness

- Acceptance checks evaluate the allowed design space, not agreement with one reference answer.
- Reference reproduction checks identify the selected baseline, reconstruction method, compared
  quantities, and tolerances separately; baseline-specific extrema are not universal requirements.
- Where justified, compare measured results with an independent calculation or physical invariant
  under its stated assumptions; choose checks appropriate to the analysis and model.
- If implementing a verifier, exercise genuine electrical failures and missing or invalid evidence
  as well as a feasible reference. Static contract consistency is not electrical verification.
- Reproduce the selected candidate in a fresh run with resolved dependencies; retain discrepancies
  and acceptance tolerances. State explicitly when reproduction has not been performed.

## Freeze and handoff

Retain the selected source, actual simulator input, model bindings, raw dataset, logs, settings,
measurement report, unresolved gaps, and reproducible entrypoints in the project's result layout.
Record search stages, ranges, failed candidates, and stopping decisions when a search was required.
An amendment identifies changed inputs or criteria, authority, reason, and revision impact; preserve
earlier runs and evidence. Metadata-only edits cannot convert missing assets into an executable task.
