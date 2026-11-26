# Ideal 65 GHz LPF in Virtuoso and Spectre

Task `inp-passive-lpf-65g-50ohm-80g-stop20-virtuoso`, revision 1.
Current kind: reproduction. Current stage: ideal cross-tool reproduction.
Readiness: **ready for WP0 preflight; isolated workspace and native toolchain execution remain unverified**.

Use Cadence Virtuoso and Spectre through the product MCP selected by AI EDA Lab
to reproduce the disclosed ideal ADS filter, then retain the freedom to design
another ideal LC filter with the same electrical requirements. The user selected
this order on 2026-11-25. The original task and retained ADS evidence remain unchanged.

## Electrical contract

The DUT is a single-ended, passive, reciprocal, ideal LC low-pass filter.
Its ordered terminals are `rfin`, `rfout`, `gnd`. Port 1 is `rfin` and port 2
is `rfout`, both referenced to the common `gnd`. The testbench owns both real
50-ohm ports; internal termination resistors, matching attenuators and active
devices are prohibited. Reference planes are at the bare DUT terminals.

| ID | Criterion | Domain and decision |
| --- | --- | --- |
| H1 | Input match | `20 log10(abs(S11)) < -20 dB` at every frequency in `(0, 65 GHz]` |
| H2 | Output match | `20 log10(abs(S22)) < -20 dB` over the same complete passband |
| H3 | Insertion loss | `-20 log10(abs(S21)) < 1 dB` over the same complete passband |
| H4 | Stopband checkpoint | `20 log10(abs(S21(80 GHz))) <= -20 dB`, at exactly 80 GHz |
| H5 | DC-through | Verify the signal-through topology and analytic positive-frequency limit at DC |
| H6 | Model and interface | Positive finite ideal lossless L/C values, ordered DUT terminals and external real 50-ohm ports |

65 GHz is the inclusive passband edge. Simulate exact 65 and 80 GHz points.
There is no continuous stopband limit. Show a broad response through 120 GHz
to document low-pass behavior; that plot adds no stopband threshold. Do not
describe a zero-Hz S-parameter as simulated. InP is a future implementation
target; this task has no PDK, finite Q, parasitics, layout, EM, PVT or physical
feasibility acceptance. H3 remains explicit even though ideal losslessness and
H1 imply a tighter insertion-loss bound.

## Work packages and gates

| Package | Scope | Exit gate |
| --- | --- | --- |
| WP0: toolchain smoke | In an isolated task-owned library, create a small series-L/shunt-C two-port, save and check it, obtain native-derived Spectre input, run SP, export/read complex data, reopen and repeat | All toolchain checks in the verification plan pass with retained evidence |
| WP1: ADS reproduction | Rebuild the frozen nine-pole baseline with its exact connectivity and full-precision values in Virtuoso; simulate in Spectre | Source/netlist correspondence, cross-tool and ABCD comparisons, all H criteria and fresh reopen/repeat evidence reviewed |
| WP2: same-spec design | After WP1 review, choose topology, order and values freely within ideal LC scope; retaining the reproduced candidate is also permitted | A separately frozen design run satisfies the same H criteria with a method appropriate to its actual topology |

WP0 isolates automation failures from the difficult LPF synthesis problem. A
successful standalone handwritten Spectre deck verifies only the solver portion;
it does not pass the native schematic-to-result gate. WP1 is disclosed reference
reproduction, with fixed topology and values. It is not a blind evaluation.

The current `engineering.toml` selects WP0/WP1 as reproduction. Before WP2,
record its reviewed stage selection and change the operator profile to `kind =
"design"` before freezing a new run. Preserve earlier frozen profiles and runs;
if this changes an already executed revision's contract, make a documented new
revision. A new task identity is not required merely for another candidate.
WP2 does not require a different topology, an improved score or global optimality.

## Frozen reproduction inputs

The selected ADS baseline is dated 2026-10-27 and belongs to source task revision 2.
Its selected text inputs are included under `inputs/baseline/`; the inherited
electrical contract is included under `inputs/source-task-r2/`. Use the actual
connectivity and element literals in `schematic.net`, cross-checked against
`synthesis.json`; do not transcribe rounded display values. The five series
inductors and four shunt capacitors form the disclosed nine-pole Chebyshev-I ladder.

The existing CSV has 3796 unique samples, including exact 65 and 80 GHz and
refined analytic passband reflection maxima. It and the Touchstone file are
**ADS reference data**, never Spectre evidence. `summary.json` describes the
prior ADS result only. The retained `source-inputs/analyze.py` documents the
baseline synthesis and ABCD calculation; it is fixed to this ladder and is not
a checker for arbitrary WP2 candidates. No ADS binaries or proprietary model
files are needed for this ideal reproduction.

## Environment and execution prerequisites

AI EDA Lab selects the installation and independent product MCP. Preserve the
selected route and keep absolute host roots, session identity and configuration
in ignored local bindings. Current discovery selected Virtuoso IC251 and Spectre
251; these are observations, not portable version pins. Execution must confirm
actual versions, SP support, license checkout, library ownership, consumer-visible
paths, available resources and analogLib ideal-device semantics.

The repository's `virtuoso` workflow version 0.1 implements local workspace/run
preparation and the source/simulation evidence lifecycle. Its native procedure
is documented in `docs/virtuoso-mcp-workflow.md`. Complete the actual isolated
workspace, native netlisting and SP result/export checks before claiming the
toolchain passed; implementation and offline tests alone are insufficient.
The user selected a remote project root through the private binding. Verify its
ownership, actual filesystem and one isolated writable session/library.
Freeze this task, selected inputs and implemented workflow before delegation.
Do not change another user's active design, remove live locks or replace views.

This package creates the task and measurement plan. It contains no Virtuoso
candidate or Spectre result. Configuration checks and task authoring do not
authorize a full synthesis search. GUI inspection and screenshots require the
user's explicit Computer Use consent for this task; prefer supported APIs.

## Initial verification budget and stop rules

The user's continuation authorizes the bounded WP0 verification package:
one solver job at a time, one CPU and at most 2 GiB requested memory; up to
three WP0 attempts and three WP1 attempts, with a 120-second simulator timeout
per attempt. A repeat counts as an attempt. Retain every failed attempt and
stop after the first unresolved connectivity, ownership, license, unsupported
netlisting/export or source/data mismatch. Resume after its cause is resolved
in a fresh recorded attempt. WP2 needs a bounded candidate/search plan before
execution. Do not silently expand resources, change solver, retune the fixed
baseline or bypass a failed gate.

## Deliverables and conclusions

For each executed package, retain an editable Virtuoso library and bench plus
a portable native-source archive with necessary library definitions and replay
instructions. Keep native source, source-derived Spectre netlist, invocation
receipt and simulator log, native raw data, complex CSV and 50-ohm Touchstone,
parameter/connectivity table, settings, plots, measurement and check reports,
and reopened repeated-run evidence together. Delivery names in `task.toml` are
relative to the selected retained run. Full artifact obligations and comparison
rules are in [verification-plan.md](verification-plan.md).

Report toolchain status, reproduction status, candidate electrical outcome,
ideal-model applicability and delivery completeness independently. A working
bridge does not establish a successful SP run; matching ADS does not replace
H1-H6 checks. No formal benchmark registration, score or independent official
verifier is created. See [DEVELOPMENT.md](DEVELOPMENT.md) for current readiness.
