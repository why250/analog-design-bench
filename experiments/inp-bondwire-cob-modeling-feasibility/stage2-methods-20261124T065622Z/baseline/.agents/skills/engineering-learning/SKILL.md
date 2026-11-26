---
name: engineering-learning
description: >
  Optional execution-time overlay that adds engineering teaching behavior to any
  Analog/RF IC design task. When explicitly enabled by the user, the agent
  explains key physical principles, queries documentation, makes pre-simulation
  predictions, compares predictions against actual results, and records structured
  learning notes — without changing the task specification, acceptance criteria,
  EDA workflow, or verification protocol.
---

# Engineering Learning Skill

An optional, user-activated overlay that enriches task execution with
teaching behavior. It does **not** create a new task type, new workflow, or new
run state. Load this skill only when the user explicitly requests Learning Mode.

## Role and Responsibility

| Component | Owns |
| --- | --- |
| Task Specification | What to design and verify (unchanged) |
| Engineering Workflow | How to execute, freeze, and review (unchanged) |
| EDA Skill | How to perform EDA-specific operations (unchanged) |
| Verification / Verifier | Acceptance criteria and evidence rules (unchanged) |
| **engineering-learning** | How to explain and learn *during* execution |

This skill adds the "explain and learn" layer. It does not duplicate or override
any other layer.

## When to Load This Skill

Load only when the user issues a request such as:

- "Execute this task with Learning Mode enabled."
- "Use the `engineering-learning` skill for this task."
- "Open Learning Mode for the current step."
- "Explain the model selection and simulation method."

**Do not load this skill** for ordinary task execution. The user must opt in
explicitly. If in doubt, do not activate.

## Activation and Deactivation

**At task start:**

> "Execute task `<id>`, enable engineering-learning."

Agent activates Learning Mode for the entire task execution. The task
specification, workflow, and acceptance criteria are frozen and unchanged.

**Mid-task activation:**

> "For this ADS FEM port-definition step, open Learning Mode."

Agent activates Learning Mode for subsequent related steps in the current run.
No task re-creation or new run record is required.

**Mid-task deactivation:**

> "Close Learning Mode, resume normal execution."

Agent stops generating explanatory content immediately. Already-written learning
notes are preserved. The run and evidence record are unaffected.

**Re-activation:**

The user may toggle Learning Mode any number of times within a run. Each
activation/deactivation is instant; no state machine change is needed.

## Learning Method

Use the following six-stage method as a guide, not a mandatory checklist.
Apply the stages that are relevant to the current operation.

| Stage | Goal |
| --- | --- |
| **Problem** | State the specific engineering question being answered |
| **Analysis** | Explain the theory, model, governing equations, and applicability conditions |
| **Prediction** | Before executing: predict expected behavior and trends, with reasoning |
| **Simulation** | Execute the actual EDA operation through the established workflow |
| **Observation** | Read the real result; compare it quantitatively against the prediction |
| **Conclusion** | Summarize what the result means, its limits, and transferable experience |

For theoretical questions without simulation, use Problem → Analysis → Conclusion.

For already-completed operations being explained retrospectively, state clearly
that the observation is from a retained result, not a new run.

**Never fabricate an Observation.** If a simulation has not been run, leave that
stage explicitly pending rather than filling it with a synthesized result.

When a result contradicts the prediction, preserve both the original prediction
and the actual observation. Analyze the discrepancy; do not revise the
prediction after the fact.

## Teaching Depth

Prioritize explanation at genuine decision points and in proportion to their
engineering significance:

**Explain thoroughly:**
- Key physical principles and governing mathematics
- Why a particular topology, model, or solver was chosen over alternatives
- Trade-offs between design options
- How critical parameters influence results (sensitivity)
- Pre-simulation theoretical predictions
- Post-simulation interpretation of data
- Failure causes, diagnostic reasoning, and engineering lessons

**Explain briefly or skip:**
- Routine EDA GUI or API invocations with well-understood effect
- Repetitive parameter sweeps following an already-explained method
- Mechanical file or directory operations

Avoid generating an explanation for every MCP call or every tool parameter.
Engineering result quality and correctness come first; explanation is additive.

## Documentation-Driven Learning

When the engineer is unfamiliar with an EDA feature, model, or solver, query
reliable documentation before proceeding.

**Priority order:**
1. The installed EDA tool's built-in documentation for the actual version in use
2. API documentation and examples available through the configured MCP interface
3. PDK / technology documentation and authorized technical references
4. Published technical papers and textbooks

If the project has an ADS Documentation MCP configured, use it. Do not invent
documentation citations or assume a capability is available without verifying it.

Distinguish:
- **Documented and confirmed**: the reference explicitly covers this operation
- **Theoretically inferred**: derived from first principles or related documentation
- **Unverified**: the behavior has not been confirmed in this tool version

When actual tool behavior differs from documentation, preserve the discrepancy
and investigate rather than resolving it in favor of either source.

## Learning Notes

### When to Write Notes

Write a learning note when:
- A non-trivial engineering decision was made and explained
- A prediction was compared against an actual simulation result
- A simulation failure was diagnosed and analyzed
- A key concept was introduced with a theoretical derivation

Do not write a note for routine EDA housekeeping steps.

### Location

Learning notes belong to the specific engineering workspace for the task being
executed. Place them at the workspace root alongside `README.md`:

```
workspaces/<task-id>/
  README.md              ← Retained baseline, reproduction commands (unchanged)
  learning-notes.md      ← NEW: learning record for this workspace
  ads/                   ← Native ADS project (unchanged)
  results/               ← Simulation run outputs (unchanged)
```

Before writing, check whether a `learning-notes.md` (or a pre-existing
`design-learning-notes.md` from earlier sessions) already exists in the workspace
and append to it rather than overwriting it. If the workspace is not yet
initialized, note the intended path and create the file when the workspace is
ready. For new workspaces, prefer the name `learning-notes.md`; do not rename
an existing file.

> [!NOTE]
> The workspace `README.md` owns the component table, retained baseline, and
> reproduction commands. `learning-notes.md` explains the engineering reasoning
> and observable predictions. Do not merge them or duplicate their content.

### Template and Format

Each learning note entry uses the following structure. Omit sections that are
genuinely not applicable; do not leave placeholder text in the final record.

```markdown
## <N>. <Short title of the engineering question>

**Problem.** <State the specific engineering question or decision point.>

**Background / Theory.**
<Key physics, governing equations, applicable conditions. Include derivations
when they aid understanding. Distinguish confirmed from inferred knowledge.>

**Method Selection.**
<Why this model, solver, or approach was chosen. Alternatives considered and
their trade-offs. Documentation source when available.>

**Prediction.** *(before execution)*
<Quantitative expectation and the reasoning behind it. This section must be
written before the simulation is run; label it clearly when written
retrospectively from a retained result.>

**Simulation.**
<The actual EDA operation performed, referencing the existing workflow and run.
Do not repeat the full run record here; link or reference it.>

**Observation.**
<Actual result from the simulation. If not yet run, write "Pending — awaiting
execution of run <run-id>." Never fill with synthetic data.>

**Explanation.**
<Compare Observation to Prediction. If they agree, explain why. If they
disagree, preserve both and analyze the cause.>

**Key Takeaways.**
<Concise, transferable conclusions: design rules, model limits, sensitivity
insights, failure modes.>

**Open Questions.**
<Unresolved questions, follow-on experiments, or areas needing further
investigation. Explicitly mark these as pending.>

**Evidence References.**
- Documentation: <citation and type: documented / inferred / unverified>
- Simulation: <run-relative path to relevant results, logs, or reports>
- Interpretation: <label AI-derived inferences as "Engineering interpretation">
```

### Evidence Classification

Every piece of evidence in the learning notes must be classified:

| Type | Label | Meaning |
| --- | --- | --- |
| Documentation Evidence | `[Doc]` | Sourced from official documentation, PDK references, or peer-reviewed literature |
| Simulation Evidence | `[Sim]` | From actual EDA execution: logs, raw data, measurement reports from the current run |
| Engineering Interpretation | `[Interp]` | Reasoning derived by the agent or engineer from theory and evidence |

Do not use `[Sim]` for data from a run that was not actually executed in this
context. Do not use `[Doc]` for content recalled from training without a
traceable reference.

### What Learning Notes Do Not Replace

Learning notes are supplementary. They do **not** replace:
- The Task Specification (`tasks/<task-id>/instruction.md`)
- The Engineering Profile (`tasks/<task-id>/engineering.toml`)
- The Run Record (`run.json`) and its evidence inventory
- The Simulation Results (raw data, logs, measurement files)
- The Verification Report
- The Engineering Review and delegation brief
- Native ADS project files

Reference those artifacts rather than duplicating their content.

## Engineering Correctness Boundaries

Learning Mode must not compromise any of the following:

- **Task integrity**: Do not modify a frozen task specification for teaching purposes.
- **Acceptance criteria**: Do not relax or reinterpret electrical acceptance thresholds.
- **Ideal vs. real**: Do not present ideal-model simulation conclusions as physical device validation.
- **Convergence ≠ correctness**: Simulation convergence is not proof that the model is accurate.
- **Prediction ≠ result**: A theoretical prediction is not a simulation result.
- **AI inference ≠ engineering truth**: Label inferences explicitly; do not assert them as verified conclusions.
- **EDA authorization**: Learning Mode does not grant new EDA operation permissions beyond the current run scope.
- **Existing evidence**: Do not alter completed run evidence, sealed records, or retained baselines.

If the learning process reveals a potential error in the original design
requirements, document it in the Open Questions section and route it through
the existing Task Revision and Engineering Review mechanisms. Do not resolve
it unilaterally inside the learning notes.

## Interaction with Simulation Failures

When a simulation fails during Learning Mode:

1. Preserve the failure evidence exactly (logs, partial data, error messages).
2. Explain the most probable causes based on the available evidence.
3. Distinguish confirmed failure causes from hypotheses.
4. Propose diagnostic steps within the authorized run scope.
5. Record the failure, its evidence, and the diagnostic plan in the learning notes.
6. Do not declare the step complete, invent a successful result, or skip the gap.

The run record must reflect `state: failed` or `state: interrupted` as
appropriate. Learning notes record what can be learned from the failure;
they do not convert a failed run into an acceptable one.

## EDA Tool and Domain Scope

This skill is EDA-agnostic and circuit-type-agnostic. It applies equally to:

- **ADS**: RF/MMWave circuit simulation, EM (Momentum / FEM), packaging, bonding wire, filters, amplifiers
- **Virtuoso**: OTA, LDO, Bandgap, PLL, ADC, DAC (reserved; execution support pending)
- **SPICE/Docker**: Netlist-level circuit analysis and numerical verification
- **Python / MATLAB**: Behavioral models, theoretical calculations, data analysis

Do not embed tool-specific or circuit-specific procedures in this skill. Those
belong in the EDA companion skill (e.g., `configure-ads-environment`,
`rf-inductor-toolkit-design`, `staged-lpf-design`).

## Relationship to Existing Skills and Guides

This skill adds the teaching layer only. For all engineering operations, follow
the existing entrypoints:

| Need | Go to |
| --- | --- |
| New or changed task | `create-analog-design-task` |
| ADS environment setup and preflight | `configure-ads-environment` |
| Task routing, execution, evidence, closeout | `docs/engineering-task-workflow.md` |
| ADS MCP operations and handoff | `docs/ads-mcp-workflow.md` |
| ADS workspace layout | `docs/engineering-workspace-layout.md` |
| LPF staged design | `staged-lpf-design` |
| RF inductor EM screening | `rf-inductor-toolkit-design` |
| Lab environment planning | `AGENTS.md` → `plan_environment` |

Do not duplicate those guides here. When in doubt, follow the established guide
and add the learning layer on top.

## Verification Checklist (Static)

Before closing a Learning Mode session, confirm:

- [ ] No task specification file was modified
- [ ] No acceptance threshold was relaxed
- [ ] All Observations in the learning notes are from actual executed runs (or explicitly marked Pending)
- [ ] All Predictions predate their corresponding Observations (or are labeled retrospective)
- [ ] Discrepancies between Prediction and Observation are preserved, not silently corrected
- [ ] Evidence is correctly classified as `[Doc]`, `[Sim]`, or `[Interp]`
- [ ] The run record (`run.json`) reflects the actual execution state
- [ ] Existing retained runs and baselines are unaltered
- [ ] Open Questions route unresolved issues to the appropriate mechanism

---

*This skill is an optional overlay. The engineering workflow, task specification,
and acceptance evidence remain authoritative. Learning notes are supplementary
records that make reasoning observable and transferable.*
