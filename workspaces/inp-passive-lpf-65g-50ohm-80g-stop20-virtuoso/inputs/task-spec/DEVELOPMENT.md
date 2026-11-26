# Virtuoso LPF task development — revision 1

## Status on 2026-11-25

**Task authored; ready for bounded WP0 preflight.**
The user requested a Virtuoso counterpart to the existing ADS ideal LPF task
and selected cross-tool reproduction before subsequent same-spec design.
This is engineering development with a disclosed baseline, not a blind
benchmark evaluation. No candidate has been built or simulated for this task.

| Layer | Observed or planned state |
| --- | --- |
| Lab planning and client binding | Configuration check passed for the calling client; an existing product connection was reused without configuration changes |
| MCP transport and live tools | Handshake/tool discovery passed; the actual agent could call product status and read the running Virtuoso library list |
| Native query channel | Library-list and version queries succeeded; this establishes a read path, not native editing or netlisting |
| Software discovery | Running Virtuoso reported IC25.1-64b.38; Spectre 25.1 executable responded to the status probe; installed Cadence documentation search succeeded |
| Actual Spectre license use and SP execution | Pending a retained functional run |
| Native source, netlisting and complex SP data round trip | Pending WP0 |
| Full filter reproduction and electrical outcome | Pending WP1 |
| Repository execution support | Version 0.1 implements Virtuoso local workspace/run preparation and the shared source/simulation evidence lifecycle; native acceptance remains pending WP0 |
| Isolated native workspace and writable session | A remote project root was selected by the user in the private binding; ownership, isolation and actual consumer-file checks remain pending |

Detailed host, process, deployment and transport observations belong in ignored
local preflight evidence. Configuration success does not establish a successful
Spectre invocation or a complete schematic-to-result flow. No Computer Use
inspection or GUI automation is part of the task-authoring evidence.

## Baseline source and retained inputs

The inherited electrical requirements come from
[`inp-passive-lpf-65g-50ohm-80g-stop20`, revision 2](../inp-passive-lpf-65g-50ohm-80g-stop20/instruction.md).
Its existing [workspace](../../workspaces/inp-lpf/README.md) records the ideal ADS
milestone dated 2026-10-27. That prior result belongs to ADS and remains unchanged.

This task includes selected text inputs so a frozen execution handoff does not
depend on another working directory's ignored results:

| Snapshot | Purpose |
| --- | --- |
| `inputs/baseline/schematic.net` and `synthesis.json` | Exact connectivity and full-precision component values |
| `inputs/baseline/ads_sparameters.csv` and `inp_lpf.s2p` | Same-grid complex ADS comparison data |
| `inputs/baseline/settings.json` and `summary.json` | Historical settings, coverage, engineering checks and machine-readable provenance |
| `inputs/baseline/source-inputs/analyze.py` | Historical fixed-topology synthesis/ABCD calculation; requires NumPy for calculations and Matplotlib for plotting, supplied separately |
| `inputs/source-task-r2/` | Original revision-2 instruction, metadata and measurement contract |

The snapshots retain their original bytes; they are reference inputs and not
newly generated Virtuoso deliverables. The selected input inventory must be
verified when freezing and receiving an execution package. No ADS project
binary, proprietary PDK or installed software is bundled. Do not modify the
baseline analyzer to make another topology appear to reproduce this reference.
The historical analyzer's report generator prints an integrity value in prose;
reuse its calculation separately or amend only new report presentation to follow
the current narrative policy. Preserve this historical input snapshot unchanged.

## Prerequisites and next work

1. Use the implemented [Virtuoso workflow](../../docs/virtuoso-mcp-workflow.md)
   and reviewed workspace/run preparation. Freeze its helpers and task-owned
   measurement tool. Actual native netlisting and SP export remain WP0 gates.
2. Verify the selected remote root's ownership and one isolated writable
   session/library; record actual consumer-visible paths and resource demand privately. Do not
   repurpose an active unrelated project.
3. Review the proposed bounded WP0/WP1 scope and freeze a new execution brief
   against this task and the implemented workflow. Complete actual environment
   checks and retain separate outcomes for every gate.
4. Run WP0, review its actual artifacts, then reproduce and independently check
   WP1. An MCP or solver failure stops the dependent package until resolved.
5. After WP1 review, a subsequent design run may freely select ideal LC topology,
   order and values for the same H criteria. Update the selected operator stage
   and kind before freezing that run; preserve executed revision-1 profiles and
   evidence and use a documented new revision if their contract changes.

The new task's `engineering.toml` resolves to Virtuoso workflow version 0.1.
Its offline lifecycle checks do not establish native readiness. The selected
helper dispatches to the Virtuoso workspace implementation; do not substitute
an ADS workspace. There is no runnable formal starter, independent
official verifier, runner registration or benchmark release change in this work.

## Decisions and verification scope

- Confirmed: ideal-only LC, inherited strict passband and exact single-point
  stopband criteria, external 50-ohm ports and initial ADS reproduction.
- Adopted engineering comparisons: absolute complex S tolerance `1e-6`,
  frequency pairing within 1 Hz and ideal-network checks within `1e-8`.
  These cross-tool comparisons are specified and remain unperformed.
- Authorized continuation: bounded WP0 with the single-job resource/attempt
  budget in the instruction; the execution brief records its exact boundary.
- Pending: isolated path/session ownership,
  actual license/SP run and native-source-to-export reproducibility.

Task metadata and declared input existence can be checked offline. Such checks
establish authoring consistency only. Electrical acceptance requires the exact
new candidate, native-derived input, actual Spectre data, coverage and original
comparison reports described in [verification-plan.md](verification-plan.md).
