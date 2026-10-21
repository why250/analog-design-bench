# Capturing trajectories, usage, and cost

Use this guide before a scored model attempt. It defines evidence the evaluation
producer must retain, independently of any website or viewer. Start with the
[evaluation workflow](model-evaluation.md) for task/protocol selection and
[environment guide](windows-official-environment.md) for simulation. These
instructions belong to the operator, not the blind circuit designer.

## Before launch

- Use a fresh solver history and an isolated workspace with permitted public
  materials. Keep references, hidden verification, operator instructions, and
  publishing credentials outside the solver's context and tool access.
- Check the actual initial messages recorded by the launcher, including injected
  runtime instructions. Files absent from a container can still be injected by
  the outer harness. Readable `AGENTS.md` is useful to the operator but is not
  automatically appropriate input for the solver.
- Stop and correct unrelated or protected-format input such as
  `%TSD-Header-###%` before a new scored attempt. A later display filter cannot
  undo historical input contamination or remove its token usage.
- Start capture at launch, not after the final circuit exists. Record the exact
  model/effort/harness, root session ID, prompt/source hashes, UTC timestamps,
  declared limits and output location. Keep setup/connection probes separate.
- Establish whether root usage covers only the root or also delegated work.
  If the harness permits children, plan explicit capture and attribution for
  those children. Do not scan unrelated sessions to fill an incomplete trace.

Inspect readiness before calling the model. If a launcher cannot retain required
input or accounting evidence, fix the capture path first or explicitly classify
the run as capture-incomplete. Do not claim full evidence from an incomplete run.

## What to retain

Keep original local records immutable, plus a reviewed export for consumers.

| Evidence | Required detail when available |
| --- | --- |
| Initial input | Actual task prompt and relevant system/runtime/tool instructions as sent, source/version and any injected context |
| Responses | Visible assistant messages, provider response IDs, reported model, completion status, request usage and timestamps |
| Tools | Exact call IDs, arguments, outputs, exit status, execution context, timing and any truncation |
| Delegation | Root/child relationship, each child's actual model/effort, explicit source files and accounting scope |
| Usage | Original provider fields, per-response versus cumulative semantics, thread/response identity, selected baselines and exclusions |
| Final submission | Frozen circuit bytes/hash, stop/freeze confirmation and independent verifier inputs/reports |

Preserve source order and agent context. A reused short tool ID in two sessions
does not identify the same call. Native events, streaming fragments, tool calls,
and inference requests are different units. Report model-request totals only
when the source establishes real request/response boundaries; keep an unknown
total unknown. Do not assign per-step duration or cost without supporting data.
Mark missing or truncated output instead of presenting it as a complete response.

## Native Codex capture

The evaluation launcher should retain its machine-readable stdout from the
start and explicitly identify the root thread. If a richer native transcript
is needed, retain only this attempt's exact, explicitly identified source files
and the files of its actual children. Do not read authentication files or search
all historical transcripts. Record the native harness version and actual initial
input; configuring a clean container alone does not establish a clean session.

When provided by the recorded version, attributed per-response usage records
identify a thread and provider response. Retain those fields and cumulative
snapshots so a consumer can deduplicate and cross-check them. Native formats are
version-dependent; do not promise that all Codex releases expose the same events.
Missing child transcripts and missing child accounting are different gaps.

Full native stdout/transcripts remain local. A public export may contain visible
messages, tools, and explicitly eligible public reasoning summaries. Private
reasoning bodies, encrypted reasoning, and unlabelled internal reasoning events
are not public summaries. Respect a recorded summary-disabled setting. Do not
decode encrypted content, reconstruct missing thinking, or publish complete raw
sessions merely because an adapter can read them. Consumers perform their own
versioned format conversion against explicitly selected records.

This is a capture contract, not a general native launcher implementation. An
existing website reader or offline adapter does not prove that a new native
attempt was started with clean input or that all its usage was captured.

## Local Chat Completions capture

Use the [NMOS SOP](nmos-evaluation.md) for the implemented campaign. Before its
first request, the launcher retains `record/initial-input.json` with the exact
initial messages, tool schema and request settings. Each actual request body is
also saved under private local `record/requests/`. Completed responses retain
provider usage, returned model, finish reason, request/start timestamps and tools.

The model receives bounded tool-output previews when needed; full output is
spooled into `record/tool-output/` with hashes and explicit truncation metadata.
Per-response streaming files remain local. A stream that fails before usage is
returned has unknown usage; do not treat captured fragments or request count as
a measured bill. Inspect `capture-report.json` and the usage warnings.

The runner preserves explicitly returned `reasoning_content`. That field does
not authorize exporting native private/encrypted reasoning or unrelated session
data. This harness does not delegate to child models. Native Codex capture above
remains a separate contract, not an implemented native execution backend.

Historical completed records may lack initial input or request-start timestamps.
The completed-evidence importer preserves existing files and explicitly marks
missing capture; it does not reconstruct a historical as-sent request or turn an
old result into a new attempt.

## Accounting and cost evidence

- Keep provider usage as received, including raw cache and reasoning fields.
  Distinguish independent per-response counters from cumulative snapshots;
  repeated snapshots and mirrored stdout/transcript records are not new usage.
- Identify accounting by thread and response when possible. Declare whether
  root totals already include children. Include delegated work once, record each
  child's actual settings, and mark unresolved attribution as unknown.
- Separate ordinary input, cache reads, cache writes and output only where the
  provider fields support the split. Thinking already included in output is a
  subcount, not an additional token charge. An unreported field is unknown,
  not a measured zero. Retain raw fields so consumers can check normalization.
- Preserve exact price evidence, date, currency, provider/model/service tier,
  applicable context tier and accounting scope for any estimate. Record
  assumptions and separate setup probes, failed preflight requests and other
  overhead from scored work. A rate without compatible usage is not a bill.
- Keep estimated API-equivalent cost separate from actual measured charges.
  Subscription execution has no known per-run bill unless independent billing
  evidence establishes it. Do not infer cost from elapsed time or request count.

The local NMOS runner writes normalized `usage.json`, preserving original
provider counters and unknown fields, and `cost.json` from explicitly supplied
dated rates. An absent price or insufficient accounting produces an unknown
estimate. It does not query provider billing or invent actual per-run charges.

## Prepare a consumer handoff

Select this experiment's evidence explicitly into an export directory/archive
independent of either repository checkout. Use relative paths within the export,
copy the frozen circuit and verifier bytes unchanged, retain checksums, and
document missing evidence, redactions, truncation and accounting assumptions.
The NMOS campaign automates an allowlisted evidence archive. An operator must
still review its content before publication; a file allowlist is not a universal
secret detector. See the [handoff SOP](nmos-evaluation.md#inspect-and-deliver-evidence).

Review command outputs, endpoint metadata, prompts and attachments for secrets
and unrelated private content. Retain originals locally; export only eligible
public material with a local source-to-export audit record. Keep authentication
files, cookies, API keys, full private sessions and encrypted/private reasoning
out of the handoff. If a trusted offline adapter needs an original native log,
keep that input local and explicitly selected; only its reviewed public outputs
may enter the public export.

The [evidence checklist](model-evaluation.md#deliver-completed-evidence) defines
the producer's deliverable. A website or other consumer owns its own input
adapter, bundle schema and publication procedure. Source capture, accounting
evidence, and independent verification remain this repository's responsibility;
future evaluations must not depend on another repository's documentation.
