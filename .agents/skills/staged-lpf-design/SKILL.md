---
name: staged-lpf-design
description: Plan a new passive LC low-pass filter as staged design tasks, or execute and resume an approved task for ideal verification, PCell optimization, or editable ADS layout.
---

# Staged low-pass filter design

## Prerequisites and support

Task planning is independent of a particular repository or host. Native ADS execution
requires a licensed supported installation, an authorized automation route, and the
task's separately supplied PDK/PCell data when nonideal devices are requested. These
dependencies are not bundled. Discover destination entrypoints and installed-version
capabilities; analytical checks can proceed within scope when native execution is
unavailable, with native acceptance left pending.

## Select the next step

- **New filter.** Discover `create-analog-design-task` by name in the available
  skills and read its `SKILL.md` in the same request. Follow it to clarify the
  electrical specification, plan the task boundaries and handoffs, and author
  the first task package. Apply the active project's conventions. For the
  typical sequence, plan ideal synthesis, PCell feasibility and candidate
  selection, then editable layout. Keep dependent tasks in Draft while their
  required upstream decisions are open. If the companion is unavailable,
  apply the project's task-authoring guidance and record any unresolved inputs.
  Start execution when the request authorizes it and the task is ready.
- **Changed requirements.** Identify the affected task and follow the project's
  revision rules. Use the task-authoring companion when revising the contract.
  Preserve the previous run and its evidence.
- **Existing task or run.** Read the task and checkpoint, then resume at the
  recorded review or execution stage. Use an approved upstream handoff when
  starting the next task.

## Execute the selected task

Read the approved task, its verification plan, and the accepted upstream
inputs. Run only the work owned by that task. Use the project's engineering
workflow and device profile to execute or resume it. Discover the ADS
installation, workspace, and model bindings for the selected task. If native
verification is unavailable, report the remaining evidence and perform any
analytical work within the task's scope.

Freeze the selected workflow/version and required inputs alongside the task revision
using the destination's receipt mechanism. Use its common run/checkpoint record and
phase checks when available; initialization, native readiness and complete delivery are
different states. Keep candidate selection and dynamic state outside static identity
metadata. A selected existing task/run takes precedence over creating another project.

1. Record equal real port impedance, passband edge, strict input and output
   match limits, exact stop checkpoints, and an explicit insertion-loss limit
   or report-only choice from the frozen task contract. Save the execution
   input and identify the run. Resume from its checkpoint when the user
   returns to the same task.
2. For a series-first odd-order Chebyshev-I ladder, derive the ripple from the
   stricter match or lossless insertion-loss requirement and the design margin.
   For each stop point, compute the order bound `acosh(sqrt(10^(A/10)-1)/epsilon)
   / acosh(fs/fp)` with the `acosh` argument bounded below by one. Choose the
   lowest allowed odd order meeting every bound. Check the resulting ADS
   response against independently cascaded ideal series-Z and shunt-Y ABCD
   matrices at both edges, all checkpoints, and passband extrema.
3. **Pause after ideal verification.** Show order, L/C values, curves, margins,
   and evidence status. Continue to geometry search after the user confirms the
   selected response. Freeze the order and topology for that search.
4. Load the allowed PCells, explicit pin roles, mutable and fixed geometry,
   exact model samples, and applicability information from the device profile.
   Rank likely sizes using effective reactance and loss, then score full complex
   model responses. Search paired sizes first and expand within the approved
   budget. Verify shortlisted candidates using their native schematic and
   exact checkpoints. Retain gaps and model warnings alongside metrics.
5. **Pause before creating the complete layout.** Show the native candidates,
   dimensions, worst loss, match and stop margins, and any model limitations.
   Let the user choose a candidate or revise the search. Resume using the saved
   candidate and its model and specification records.
6. Build the editable hierarchical layout with verified signal and return pin
   roles. Reopen it and verify geometry, connectivity, and reference planes.
   Deliver the layout and its source evidence. Treat coupled full-wave results
   as a later validation stage when requested.

Apply the task's review and stop rules at each handoff. When the next stage
belongs to a separate task, use the project's handoff entrypoint or deliver
the selected artifacts and evidence for its input snapshot. Start the next
task from that frozen input and its own workspace. Project profiles supply
ADS/PDK dependencies and device settings. Retain original evidence with its
engineering project.

When delegating, supply the frozen task/workflow, accepted upstream inputs, allowed
changes, target relative paths, private binding reference, budget/stop rules, evidence
checklist and next review gate in a self-contained brief. One executor owns native
workspace writes at a time. Review actual returned artifacts. Report execution,
electrical outcome, model applicability and delivery completeness independently;
structural checks do not establish electrical success. Preserve interrupted runs and
record the exact checkpoint without bypassing the review gates above.
