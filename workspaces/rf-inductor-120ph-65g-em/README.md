# 120 pH on-chip inductor engineering workspace

This stable root belongs to `rf-inductor-120ph-65g-em-r1`. The
[task specification](../../tasks/rf-inductor-120ph-65g-em/instruction.md) is
authoritative and [project.toml](project.toml) declares portable relative roles.
Toolkit-generated native geometry and actual Momentum EM runs are now retained.
Execution was closed at the user's request on 2026-10-29. No further design
optimization or simulation is scheduled. A useful candidate and its raw EM
evidence exist; final qualification remains incomplete and no device PASS is
claimed. Start with the [closeout report](docs/closeout.md).
The initial EM run used an incorrect dielectric-loss sign and is retained as
invalid evidence for the passive design. Corrected passive-material runs use a
fresh result directory; the original targets and tolerances remain unchanged.

The user permits single-device geometry and EM, without restricting the PDK;
other on-chip platforms or explicit assumed stacks are allowed. W0 selects
one actual stack and solver before acceptance runs. The complete structure,
real return and declared current-mode extraction matter at 65/80 GHz.

Implementation roles:

```text
ads/inductor_120ph_wrk/  # Native geometry, unit benches and EM setup
tools/                 # Task-owned construction, extraction and search tools
tests/                 # Meaningful numerical/port/extraction checks
inputs/                # Selected allowed stack and dependency records
docs/                  # Execution, design decisions and adoption/amendment records
results/<UTC-run-id>/  # Fresh ignored geometry snapshots and raw EM evidence
```

Follow [the shared layout](../../docs/engineering-workspace-layout.md) and
[ADS workflow](../../docs/ads-mcp-workflow.md). Keep absolute host/install roots,
session details and toolkit references in ignored local settings. Recheck any
reported installation before use. No solver commands are fabricated here.

Retain full N-port data and its ports/reference/stack definitions; preserve raw
fixture evidence as well as any justified de-embedded model. Do not reduce the
handoff to one scalar inductance. Keep private inputs/results and unclassified
native exports out of public Git; publish permitted source only after its
dependency classification is established. Integrity values belong in receipts.

The parent PDK-aware LPF study
must decide whether this model is physically compatible with its stack and
whether the full filter passes. A generic/other-process unit is an explicitly
labeled comparison until that integration is qualified.

The current entrypoints are [the execution record](docs/execution-record.md),
[the frozen research contract](inputs/research-contract-r1.json),
[the actual expanded stack](inputs/effective-stack-r1.json), and
[the frequency-method amendment](docs/frequency-method-amendment.md).
The expanded-stack record explains ADS conductor expansion; the nominal
dielectric inputs alone do not describe the conductor elevations.

Task tools construct fresh native cells, check actual exported physical inputs,
prepare and run full-wave solves, preserve full complex networks, generate new
diameter predictions, evaluate constrained-current L/Q, and independently solve
the DC sheet conductor. They resolve this workspace through `project.toml` and
refuse to overwrite prior cases. Classic EM export needs an application session;
geometry construction and solver runs use an independent automation runtime.
The copied open dependency and simulator environment are required; consult the
ignored local binding for installation paths.

For reuse, start with the [automation-chain overview](docs/reproduce.md#reusable-automation-chain).
The repository skill
[`rf-inductor-toolkit-design`](../../.agents/skills/rf-inductor-toolkit-design/SKILL.md)
provides the callable workflow and routes to these task-owned tools.
It maps Toolkit generation, native export/full-wave solving, metric extraction
and candidate ranking to the existing tools, their artifacts and a minimal
screening continuation. It also identifies the application-session and
observation-manifest handoffs; no unattended end-to-end driver is claimed.

Raw actual EM points and native AFS-derived dense results remain distinct.
The model always includes the finite Metal1 return and both signal-to-return
paths. A scalar 120 pH value does not replace this network or establish full LPF
acceptance.
