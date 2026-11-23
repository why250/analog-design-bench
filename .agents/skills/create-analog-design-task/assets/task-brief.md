# {{task_title}}

Use the target project's terminology and file contracts when present. Otherwise this
template can serve as the standalone task contract without a metadata schema or runner.
Fill relevant sections, remove inapplicable rows, and leave unsupported facts unresolved.

## Identity and readiness

- Task ID and explicit revision: {{task_id_and_revision}}
- Work type, evaluation mode, and current stage: {{type_mode_stage}}
- Selected EDA, workflow and version, or unresolved route: {{eda_and_workflow}}
- Objective and intended engineering decision: {{objective}}
- Readiness for the next named stage: {{readiness_and_remaining_gates}}
- Engineering verification scope and actual execution/evidence status: {{engineering_verification_scope_and_status}}
- Formal evaluation applicability, task-version registration, and independent official verifier status: {{formal_evaluation_status_and_basis}}
- Authoritative specification, existing metadata, and amendment references: {{references}}
- Solver-visible inputs and operator-only material: identify the boundary when relevant.

At task creation, engineering verification is planned or not yet performed unless
specific retained evidence is identified. A measurement plan or engineering analysis
script does not imply an independent official verifier. When established for this
task/version, explicitly state that it is an engineering task, is not registered as
an official benchmark, and has no independent official verifier. Otherwise record
formal evaluation as not applicable or not assessed rather than inventing a status.

## Facts, assumptions, and authority

Classify each consequential statement; a confirmed requirement is not a verified model fact.

| ID | Statement | Status | Source or decision authority | Consequence if unresolved |
| --- | --- | --- | --- | --- |
| F1 | {{statement}} | confirmed / proposed / investigate | {{source}} | {{consequence}} |

Record the version or date of supporting material. Identify which source wins if documents
conflict; resolve conflicts before dependent execution rather than silently choosing a value.

## Scope and interfaces

- Required work and completion boundary: {{scope}}
- Explicitly deferred work and prohibited substitutions: {{boundaries}}
- Input dependencies and authorized reuse: identify source versions and access restrictions.
- DUT identity, ordered terminals, directions, units, and electrical meanings: {{dut_interface}}
- DUT-owned devices, returns, bias networks, and connections: {{dut_owned}}
- Bench-owned supplies, loads, clocks, stimuli, feedback, and references: {{bench_owned}}
- Measurement boundary, reference planes, and included or omitted interconnect: {{boundary}}

## Criteria and observations

Assign stable IDs. Hard criteria decide acceptance; research objectives decide study
completion; diagnostics inform interpretation without introducing new pass thresholds.

| ID | Class | Quantity or question | Predicate or required outcome | Conditions and aggregation |
| --- | --- | --- | --- | --- |
| H1 | hard | {{quantity_and_unit}} | {{expression_comparator_limit}} | {{domain_endpoints_conditions_worst_case}} |
| R1 | research | {{research_question}} | {{evidence_needed_to_answer}} | {{declared_scope}} |
| D1 | diagnostic | {{observation}} | Report; no acceptance threshold | {{observation_conditions}} |

Reference the verification plan for measurement definitions, coverage, uncertainty, and
failure handling. Distinguish design margin from the actual acceptance threshold.

## Design freedom

| Property or parameter | Policy | Value, range, units, or source | Coupling and validity rules |
| --- | --- | --- | --- |
| {{topology_device_geometry_or_parameter}} | fixed / variable / optional | {{definition}} | {{constraints}} |

Include geometry, models, returns, coupling, and which changes require amendment or revision.

## Environment and models

- Required EDA capabilities, analysis types, and supported versions: {{requirements}}
- Existing environment profile or workflow reference: {{profile_reference_or_not_yet_defined}}
- Selected native project layout/manifest and automation route: {{layout_and_selected_interface}}
- Private host, installation, licensing, and session bindings: keep in local configuration.
- Pending environment observations and preflight owner: {{pending_checks}}
- Model provenance, parameter domain, conditions, and required samples: {{model_requirements_and_gaps}}
- Supported frequency or time domain, interpolation or extrapolation policy, and warnings:
  {{validity_limits}}
- DC, zero-frequency, initial-state, or steady-state reasoning needed beyond sampled data:
  {{required_evidence_or_not_applicable}}

A documented configuration is not evidence that the intended models or session were loaded.
An unperformed preflight remains pending; model-limited results retain their qualification.

## Execution stages and stopping rules

Before execution, freeze this contract, the selected workflow instructions and the required
input inventory using the destination's supported mechanism. Record the consumer's receipt
without placing private host bindings or restricted dependencies in the portable package.

| Stage | Entry evidence | Allowed work | Budget and stopping rule | Exit evidence or next gate |
| --- | --- | --- | --- | --- |
| {{stage}} | {{prerequisites}} | {{permitted_changes}} | {{budget_and_stop}} | {{exit_or_branch}} |

For searches, declare ranges, candidate selection, iteration or extraction budget, and the
condition for widening freedom. A finite unsuccessful search does not prove infeasibility.

## Deliverables and decision states

| Artifact | Current obligation | Acceptance evidence or authority | Future or reserved status |
| --- | --- | --- | --- |
| {{artifact_and_project_relative_location}} | {{required_now_or_optional}} | {{check_or_evidence}} | {{implemented_or_deferred}} |

Include editable source, actual simulator inputs, raw data, settings, decisions, and
reproduction instructions as applicable. Reserved metadata does not imply a working exporter,
runner, checker, or verifier. Keep task completion, candidate performance, evidence validity,
and next-stage readiness as separate conclusions; retain valid negative study outcomes.

When results are produced, report execution completion, electrical outcome, model
applicability and delivery completeness independently. State the selected candidate/run,
remaining checks and next action. An initialized directory is not completed delivery.

For delegation, include the frozen contract/workflow, next work package, relative target
paths, private profile reference, allowed changes, carried-forward authorization, budget,
stop conditions, evidence checklist and next review gate in a self-contained brief.

## Unknowns and change control

| Gap ID | Unknown and affected work | Owner | Allowed resolution and budget | Unresolved disposition |
| --- | --- | --- | --- | --- |
| G1 | {{gap_and_dependency}} | {{owner}} | {{investigate_or_request_decision}} | {{stop_dependent_work_or_qualify}} |

Freeze the handed-off specification and inputs. Record later changes with their reason,
authority, affected criteria, and revision decision; preserve earlier evidence and conclusions.
