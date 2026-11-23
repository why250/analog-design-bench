# Stage 2 task development record

## Executed study: 2026-10-28

The untuned revision-1 research study is complete. The retained run
`stage2-20261027T113222Z` covers 225 filter request mappings, 219 unique physical
cases, 55 isolated-device validations and three fresh-workspace repetitions.
The 219 cases comprise 16 PASS and 203 FAIL results; none is numerically invalid
or indeterminate. All 64 E6 combined-coefficient requests and all 40 E8 slice
samples fail the unchanged specification. The documented primary stage decision
is **TOPOLOGY REVIEW REQUIRED**; partial loss-only passing samples remain visible.

See the [execution record](../../workspaces/inp-passive-lpf-65g-nonideal-lc-feasibility/docs/execution-record.md),
[implementation and reproduction entrypoint](../../workspaces/inp-passive-lpf-65g-nonideal-lc-feasibility/README.md),
and retained [report](../../workspaces/inp-passive-lpf-65g-nonideal-lc-feasibility/results/stage2-20261027T113222Z/report.md).
The completed [engineering layout migration](../../workspaces/inp-passive-lpf-65g-nonideal-lc-feasibility/docs/migration-record.md)
records the stable task-owned roots, original archive hashes and independent
layout validation. It preserves the completed study and its electrical decision.
All coefficients remain synthetic. No PDK capability, retuning result, SPICE
submission, official benchmark registration or score is claimed.

The material below records the specification preparation state on 2026-10-27.
The task instructions and model/experiment/measurement plans remain the frozen
research contract; their historical "not executed" statements are superseded
by this dated execution record for the retained study only.

## Specification preparation record

The engineering layout was subsequently normalized to the stable task-owned
`workspaces/inp-passive-lpf-65g-nonideal-lc-feasibility/` root. Its `project.toml`
owns portable relative paths, and the ADS host mirrors that same workspace
suffix. The Stage 1 project retains its existing root. The proposed nested
`workspaces/inp-lpf/stage2/` path below records the original preparation decision;
it is superseded by the [engineering layout contract](../../docs/engineering-workspace-layout.md).

**Revision 1 draft, prepared 2026-10-27. Planning only: no Stage 2 schematic,
simulation, optimizer, layout, PDK import or formal verification has run.**
Follow [task development](../../docs/task-development.md), the
[electrical contract guide](../../docs/electrical-design-contract.md) and
[ADS workflow](../../docs/ads-mcp-workflow.md).

## Engineering proposal and stage boundary

The ideal milestone resolved synthesis, order and matching/ripple interpretation:
a nine-pole Chebyshev-I ladder can meet the unchanged 65/80 GHz requirements
with equal 50-ohm references. It also established native ADS construction,
four-S export, independent ABCD analysis and fresh-workspace reproduction.
It did not establish realizable InP component values or losses.

Stage 2 should quantify how much loss, reactance distortion and parameter
variation this exact baseline tolerates, especially the roughly 239-249 pH
central inductors. Required experiments isolate mechanisms before combining
them. This makes later PDK model selection a comparison against a measured
requirement envelope instead of an unsubstantiated physical-feasibility claim.

| Stage | Ownership / exit |
| --- | --- |
| 1: Ideal LC | Completed r2 engineering milestone; preserve fixed source and historical evidence |
| 2: Nonideal modeling and sensitivity | This draft: ten work packages, reproducible envelope, physical explanations and explicit stage decision |
| 3: PDK-aware schematic | Acquire authorized data, compare device capability with the Stage 2 envelope, calibrate/migrate models |
| 4: Layout and EM co-simulation | Geometry, routing, return paths, mutual coupling and distributed extraction |
| 5: Corner / robustness verification | Validated process/temperature/tolerance models, statistical assumptions and sign-off conditions |

Required sensitivity/feasibility, optional same-topology retuning and synthetic
scans without PDK data were confirmed by the user on 2026-10-27. Numeric scan
axes, optional retuning bounds and numerical tolerances are proposed research
choices. They are neither system-spec changes nor foundry values.

## Organization decision

| Option | Benefits | Cost / fit |
| --- | --- | --- |
| Existing task ID, revision 3 | Valid versioning route for changed models; common task history | Replaces an ideal-only brief with different model allowances and a different definition of completion; less clear independent stage closure |
| Separate Stage 2 task, revision 1 | Preserves ideal r2 as a fixed reproducible milestone; gives feasibility research its own lifecycle | Requires explicit baseline identity and portable selected-input handoff |

**Selected: separate task `inp-passive-lpf-65g-nonideal-lc-feasibility-r1`.**
The task development guide requires versioning changed allowed environments,
interfaces or scoring contracts; it permits a distinct development task.
Here research completion can coexist with electrical failure, unlike the ideal
design milestone. An independent ID makes that distinction explicit. Do not
relabel prior r2 runs as Stage 2 results. Later changes to the Stage 2 contract
follow its own positive revision sequence.

Retain the existing specification-stage package pattern: task metadata,
instruction, model/experiment/measurement plans and this development record.
No duplicated runner or pretend executable benchmark assets are needed.

## Baseline and local evidence audit

The starting checkout was clean on `main`, using the disclosed ideal revision-2
baseline recorded in the [project manifest](../../project.toml). Changes were
prepared on `codex/inp-lpf-stage2-task`. The ideal task has explicit revision 2 and only
four specification/development files. Its completed engineering sources live
under `workspaces/inp-lpf/`. The frozen release is
`analog-design-bench-v2`; it does not include this InP task.

Read-only inspection on 2026-10-27 found the ignored directories
`workspaces/inp-lpf/results/baseline-20261027/` and
`workspaces/inp-lpf/results/reproduction-20261027/`, including raw ADS .ds,
logs, netlists, settings, complex CSV, summaries and reports. Both CSVs contain
3796 samples and their byte hashes match their recorded input hashes.
The stored summaries report engineering PASS and null official score:

| Historical metric | Recorded result |
| --- | ---: |
| Worst passband S11 | -21.000000 dB |
| Worst passband S22 | -21.000000 dB |
| Maximum passband IL | 0.0346349774555 dB |
| S21 at exactly 80 GHz | -25.1637752971 dB |
| Maximum complex ADS/ABCD error | 7.24065e-13 |

The historical reproduction record reports identical S data/frequencies and
netlist identity. This planning audit read the records and checked file/hash
consistency; it did not rerun ADS, retest all old acceptance logic or establish
official benchmark acceptance. A fresh checkout may lack ignored evidence;
record its actual availability and reproduce in an isolated namespace when
starting execution. Never infer local raw-data availability from the README.

One provenance detail matters: both retained netlist files are CRLF. Their
saved-file bytes match the handoff manifest, while the settings identify the
UTF-8 text normalized to LF. The builder checksums its in-memory netlist text
before writing, so these records identify different representations. Preserve
both historical records unchanged. Stage 2 must record actual saved-file
integrity metadata and label any additional canonical-text identity separately;
text normalization is not an exact-byte integrity check.

## Reuse existing automation with explicit extensions

These are future implementation requirements, not changes made by this draft.

| Existing asset | Reuse | Necessary Stage 2 extension |
| --- | --- | --- |
| `tools/analyze.py:synthesize()` | Pinned full-precision ideal values and prototype provenance | Resolve per-device nonideal coefficients into deterministic case manifests |
| `tools/rebuild_ads.py` | Native DUT/symbol/bench construction pattern, external ports, netlist/dataset/settings capture | Separate Stage 2 workspace/library; explicit models, per-case parameters and adaptive sweeps; saved-byte hashing |
| `tools/rebuild_ads.py:export_csv()` | Complete complex S11/S21/S12/S22 export and duplicate consistency convention | Parameter-sweep dimension selection, case identity and dataset-name handling |
| `tools/analyze.py` CSV/Touchstone helpers | Hz, real/imaginary, 50-ohm conventions | Stage-aware labels, robust exact-zero representation and plots suitable for finite loss |
| Ideal verification | Ideal E0 regression only | Separate nonideal analysis: actual DC, shifted extrema, model-aware ABCD/nodal calculation, full-matrix passivity and split study/electrical status |
| General ADS MCP workflow | Session discovery, unsaved-view checks, host-path validation, export/transfer and fresh-workspace reproduction | No new task-specific orchestration loop; parameterized selected models and settings |

The current builder hard-codes `inp_lpf_lib`, its three native views and
ideal synthesis. `--rebuild` replaces those views: **never point a Stage 2
build at the retained ideal workspace**. The current analyzer hard-codes ideal
ABCD, unitarity, ideal peak locations, ideal DC and small ideal-loss plot axes.
Its `verify` command cannot accept nonideal evidence correctly. Preserve the
baseline commands; implement a small separately named Stage 2 builder/analyzer
path with shared utilities where useful, rather than copying the whole runner.
Confirm current ADS MCP/API documentation when implementing, before relying on
component parameter names or dataset behavior.

Future Stage 2 source may live in `workspaces/inp-lpf/stage2/`, with the
workspace root passed explicitly and fresh outputs under the existing ignored
`workspaces/inp-lpf/results/`. No empty workspace or fictitious script commands
are added now. Consult ignored local environment notes for host-specific
authorization/paths; keep shared instructions portable. The existing Windows
Docker helper targets another task and is not an ADS or generic InP runner.

## Acceptance, handoff and readiness

[instruction.md](instruction.md) owns the system/stage specification;
[model-plan.md](model-plan.md) owns the physical assumptions;
[experiment-plan.md](experiment-plan.md) owns E0-E9;
[verification-plan.md](verification-plan.md) owns numerical/electrical evidence
and completion. All remain draft until the research protocol is reviewed for
execution. No Stage 2 evidence is claimed in the package.

To enter Stage 3 data mapping, complete E0-E9 and retain:

- A conditional feasible/failing envelope, limiting metric/element ranking and
  quantified boundary intervals, including the fixed-Rs model's DC limitation.
- Four deep-dive selections, independent physical/circuit checks and
  three fresh-workspace repetitions.
- A separate conclusion for study completion, each candidate's four electrical
  limits and PDK readiness; explicitly scope any no-feasible-point result to
  the scanned range and fixed/retuned values.
- A PDK request covering available inductors/capacitors and value range,
  de-embedded multi-frequency impedance/S data, DCR and Q(f), actual SRF,
  model reference planes/validity, MIM loss/density, metal/substrate/return-path
  rules, coupling, coefficient correlation and later corner models.

No favorable synthetic sample establishes manufacturability. If none passes,
the completed study can still hand off a topology-review or data-acquisition
decision. A real implementation go/no-go requires comparison with authorized
PDK data, followed by later layout/EM and robustness stages.

This package is **not registered** under `evaluation/tasks/`. Do not add a
`schemaVersion: 1` design-contract JSON yet: its required hashed starter,
device guide, original entrypoint and verifier do not exist. The guide's input,
port, bench, metric, condition and output concepts are covered here in prose;
that is not a successful static-contract validation. The metadata's
`/app/circuit.spi` and R/L/C checker allowance reserve a future interface only.
Current required deliverables are the engineering source and evidence in the
instruction, not a validated single-SPICE submission.

Do not create placeholder environment/tests/solution, reward.json, verifier
scores, runner profiles or frozen-release membership. A later benchmark
promotion needs real assets, independent negative-case and reference validation,
isolated runtime and an explicit release decision. Selected handoffs must be
self-contained; include the pinned baseline inputs rather than depending on
another live checkout. Keep formal campaigns and publication receipts separate
under the existing repository contracts if that later work is authorized.

## Remaining protocol review items

No unanswered scope question blocks this draft. Before execution, review the
proposed scan sizes (208-228 filter requests before deduplication, plus unit
cells and frequency refinement), extrema/root-conditioning method, numerical
tolerances and evidence retention budget. Continuous-band extrema isolation
for the nonideal rational network is a substantive new analysis deliverable;
the existing ideal analyzer does not implement it. Validate its conditioning
before a large campaign, and retain INDETERMINATE when coverage is unproven.
An optional optimizer needs its own
search budget and coefficient co-variation policy. Any later private data must
have an authorized storage/use boundary before calibration; it must not enter
the public task or blind-solver material.

This change only adds the Stage 2 specification package. Original ideal task,
native ADS workspace, scripts, ignored evidence and frozen release are retained.
