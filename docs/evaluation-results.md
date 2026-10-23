# Retaining and finding evaluation results

Keep formal model evaluations under this repository's ignored
`results/<taskVersionId>/<campaignId>/` directory. This applies to newly executed
campaigns and explicitly imported completed experiments. The repository owns
the original evidence; a publishing consumer owns its website-specific bundles.
Read the [evaluation workflow](model-evaluation.md) and the selected task's SOP
before executing or importing an experiment.

## Directory contract

Use a campaign ID containing a UTC timestamp and the model configuration ID,
for example `<yyyyMMddTHHmmssZ>-<modelConfigId>`. Add a safe suffix when needed
for uniqueness. The directory name helps discovery; it does not replace the
complete identity and provenance recorded in metadata. Use filesystem-safe path
components and retain exact identifiers in metadata.
The current campaign runner's default includes UTC time, a safe model
configuration slug and a random suffix. An explicit output path remains
supported; select the canonical layout for retained formal evaluations.

```text
results/
  migration-index.json               # Historical archive lookup, when present
  <taskVersionId>/
    <campaignId>/
      campaign.json
      evaluation-summary.md          # Derived human-readable campaign summary
      migration.json                 # Present for a copied historical record
      attempt-1/
        solver/                      # Original solver workspace, when retained
        record/                      # Capture, accounting, frozen circuit and provenance
        verifier/                    # Original independent-verifier output
      attempt-1.evidence.zip          # Original neutral evidence archive
      exports/
        attempt-1/
          <revision>/                # Derived amendments or reviewed public evidence
      publication/
        attempt-1/                   # Receipts, public verification or consumer index
```

Later attempts use `attempt-2` and `attempt-3` in the same form. The
[NMOS SOP](nmos-evaluation.md#inspect-and-deliver-evidence) lists the retained
files within each attempt. Imported evidence may have no original `solver/`
workspace or initial-input capture; record the gap rather than creating a
fictional execution history.

The campaign runner writes `evaluation-summary.md` at completion, including
failures. It derives identity, protocol, requested scope, partial/complete
coverage, per-attempt status/verdict and relative evidence paths from campaign
metadata for convenient reading. Use the original attempt `result.json`,
`reward.json` and verifier reports to assess the evidence.

Keep the following records separate:

| Record | Location and purpose |
| --- | --- |
| Formal model attempts | Repository-root `results/<taskVersionId>/<campaignId>/` |
| Ordinary circuit development and simulation | The selected workspace's ignored `results/` directory |
| Local configuration, build checks, input previews and connection probes | Ignored `.local/`; these are setup records, not scored attempts |
| Task fixtures and reference designs | Original task directories; these are inputs and reference materials, not model results |
| Website-specific import packages | The consumer's own workspace; the producer may retain a consumer index or receipt |

The root `results/` directory is ignored by Git. It can contain private raw
capture and is not automatically a public export or a backup. Preserve a
separate backup according to the operator's retention needs.

## Identity and immutable evidence

Record the task revision, exact model and configuration, harness/source version,
protocol, attempt numbers, blind/guided/reference mode, limits, actual timestamps,
status and source hashes in `campaign.json` and the per-attempt metadata. Keep
requested settings, observed settings and later operator classifications
distinct. Do not infer identity or coverage from a folder name alone.

Once an attempt is complete, preserve its original directory and
`attempt-N.evidence.zip` bytes. Put accounting amendments, redactions and public
reviews in a fresh `exports/attempt-N/<revision>/` directory. Record the parent
archive SHA-256 and the declared changes, as described in the
[amendment procedure](nmos-evaluation.md#amend-a-completed-record). A derived
revision remains the same attempt and score.

Use `publication/attempt-N/` only for publication receipts, anonymous public
verification and an index identifying the consumer's package or public record.
Do not use it as another producer evidence store or generate a website bundle
there. Consumer IDs and publication status do not rewrite the original identity.

## Import and migrate completed records

The [completed-evidence importer](nmos-evaluation.md#import-an-already-completed-experiment)
accepts selected existing files without model execution. Place its output at
`attempt-N/` and its neutral archive at the campaign root. The importer creates
the attempt evidence, not a campaign summary; retain a `campaign.json` describing
the imported identity, source, attempt scope and available evidence. Preserve
historical execution timestamps rather than reporting the import as a new run.

For historical records outside the new layout:

1. Identify the original task, model configuration, protocol and attempt from
   retained metadata. Keep unknown identity or missing evidence explicit.
2. Copy the selected original attempt and archive to a fresh canonical campaign
   directory. Keep the source originals in place; do not rerun, edit or repack
   them merely to adopt the directory layout.
3. Compare every copied file's relative path, byte length and SHA-256 with its
   source. Check the frozen circuit and original archive explicitly. If any
   comparison fails, preserve both sides and resolve it before treating the
   migration as verified.
4. Retain `migration.json` with `schemaVersion`,
   `recordType: "archive-migration"`, `createdAtUtc`, `sourceRoots`,
   `mappings` entries containing `source`, `target`, `size` and `sha256`, and
   `generatedFiles` listing any new archival summaries. Include exclusions or
   unavailable source evidence in the archival notes. A migration is a local
   archival operation, not another experiment or a public-content review.
5. Update `results/migration-index.json` after verification. This is a lookup of
   archived historical batches and known externally located active runs, not an
   automatically maintained index of every evaluation. Keep private source
   locations in ignored local records, outside public exports.

The migration record and lookup supplement the original metadata. They must not
silently replace an original run record, claim missing hashes were verified, or
change the selected attempt scope.

If a historical layout lacks a campaign summary, label the new `campaign.json`
as a derived historical index. Preserve the original protocol, including custom
short protocols, and disclose missing capture. Place historical amendments or
public revisions under `exports/attempt-N/<revision>/` without changing the base
attempt or archive. Keep migrated setup/preflight records in `.local/`.
When an existing summary is replaced by a derived archival summary at the
campaign root, preserve the original summary bytes at
`provenance/original-evaluation-summary.md` and label the new summary as derived.

Do not copy or move an active run while its process can still write results.
Register its current external location in the migration lookup and wait until
it finishes before archiving it.

## Find an existing result

Use `results/migration-index.json` to locate a migrated historical batch or a
known external active run. Inspect the campaign and per-attempt records for
identity and status. To list canonical retained campaign summaries from the
repository root:

```powershell
Get-ChildItem -LiteralPath .\results -Filter campaign.json -File -Recurse
```

Use the recorded task/model/protocol identity and frozen-circuit hash to select
evidence. Check `exports/attempt-N/` for reviewed revisions and
`publication/attempt-N/` for receipts. A missing receipt does not establish that
the experiment was never published; confirm with the named consumer when needed.
