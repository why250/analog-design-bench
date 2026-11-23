# Task-owned engineering workspace layout

Use a stable task-owned directory for editable engineering work. Keep execution
identities below that directory, and keep machine configuration outside its
portable source. The same relative workspace path applies on the repository
host and the ADS host; each host's absolute root is a local setting.

## Ownership and identity

The task package under `tasks/<task-id>/` owns the specification, task identity,
revision and operator plans. An engineering workspace under
`workspaces/<task-id>/` owns editable native designs, reconstruction tools,
selected baseline inputs and ordinary simulation records. The workspace name
stays stable across runs. Record its complete task ID and revision in
`project.toml`; validate that identity against the task package.

An existing stable workspace, such as `workspaces/inp-lpf/` for the ideal LPF,
keeps its existing identity until an explicit migration is scoped. A new task
gets its own workspace instead of a stage directory inside an earlier task's
engineering source. A dated run is never the parent engineering project.

The nonideal LPF task uses this relative workspace root:

```text
workspaces/inp-passive-lpf-65g-nonideal-lc-feasibility/
```

Use the same suffix below the configured root on another host. Keep the
absolute roots, SSH aliases, tool installation paths, session IDs and migration
source locations in ignored repository `.local/` notes or configuration.

## Directory roles

```text
tasks/<task-id>/                  # Authoritative task package
  instruction.md
  task.toml
  *-plan.md
  DEVELOPMENT.md

workspaces/<task-id>/            # Stable engineering project
  README.md                     # Entry point, selected native case and commands
  project.toml                  # Identity and project-relative paths
  ads/
    <design-name>_wrk/           # Editable native source
  tools/                        # Reconstruction, simulation and analysis tools
  tests/                        # Regression and rejection checks
  inputs/
    baseline-r2/                # Pinned, selected baseline input snapshot
      manifest.json             # Provenance and exact-byte file hashes
    task-spec/                  # Task snapshot for an isolated host/handoff
  docs/
    execution-record.md          # Human entry point to retained runs
  results/                      # Ignored ordinary engineering records
    <run-id>/
      cases/                    # Frozen per-case inputs and raw evidence
      units/                    # Isolated-device evidence
      reproductions/            # Independent replay evidence and native snapshots
      handoff/original/         # Unchanged archives and transfer receipts
      work/                     # Ignored live rebuild/simulation scratch
      ...                       # The selected task's retained reports and exports

.local/                         # Ignored host mappings, session/probe notes
```

The selected task defines the contents of each run. The diagram describes
ownership rather than a mandate to rewrite an already completed record.
Existing `deep_dive/`, CSV, manifest and report paths inside a completed run
remain intact. New derived amendments use a fresh declared output location.

Use a UTC identifier for a new run, with a descriptive suffix when needed.
Task names and revisions belong in metadata; run IDs do not rename the stable
engineering project. Every output invocation uses a fresh directory. Record
the source/configuration hashes and selected native case with each invocation.

Keep live E9 rebuild workspaces under the run's `work/` directory. Keep their
released OA snapshots with the corresponding reproduction evidence. Only the
authored engineering workspace belongs directly under `ads/`; transient replay
workspaces must not accumulate beside it or inside another task's project.

## Portable source and inputs

`project.toml` contains project-relative paths. Resolve them from the manifest's
directory, validate their targets and pass them to tools. Tool entry points must
not infer the task from a host directory name, the current working directory,
an adjacent task workspace or a timestamp-named staging folder.

Keep the baseline input snapshot self-contained and record its upstream commit
and exact file hashes. It can include the minimal frozen helper source needed
to reproduce or independently compare the baseline. Reusable ADS workspace,
terminal and annotation operations belong in a small local support module.
The current task must run without importing another live workspace's tools.

Native ADS library definitions use relative project paths and installation
environment variables such as `HPEESOF_DIR`. Retain required hidden library
metadata, including `.oalib`. Exclude OA locks, session preferences, generated
simulation folders and Python bytecode from versioned source. Release native
workspace locks before recording a portable snapshot.

An isolated ADS host or handoff may use the frozen `inputs/task-spec/` snapshot
when the repository task package is unavailable. Record the snapshot identity
and hashes; keep the repository task package authoritative for development.

## Result boundaries

Ordinary circuit development and ADS engineering studies use the selected
workspace's ignored `results/` directory. Registered formal model evaluations
continue to use repository-root
`results/<taskVersionId>/<campaignId>/` under the
[evaluation result contract](evaluation-results.md). A directory reorganization
does not register an engineering study or create a benchmark score.

Archives belong in a run's `handoff/` directory with their byte hashes and
transfer receipts. Exclude `handoff/` and `work/` when packaging the evidence
being archived, so an archive cannot recursively include earlier archives or
live scratch. A selected handoff states which original evidence it omits and
identifies the complete archive that retains it.

A retained legacy staging project is a migration artifact. Keep its declared
archive location outside the current tool/input paths and exclude it from new
evidence packaging. Its timestamped historical name can be preserved inside
that migration archive; it is no longer the active engineering root.

## Migrating an existing engineering project

1. Inventory the source, active ADS workspace, unsaved designs, native locks,
   completed evidence, original ZIP files and every path-dependent entry point.
2. Prepare the stable task-owned destination. Copy source and selected inputs;
   update editable tools, configuration, imports and documentation there.
   Preserve the original source until the replacement is checked.
3. Relocate completed run trees with their internal paths and file bytes
   unchanged. Copy and verify across filesystems; a same-volume directory rename
   can be used after recording its complete inventory and retaining the original
   independent evidence archive. Verify the declared file set before and after.
   Retain original ZIP bytes in the destination run's `handoff/` area.
   Record the old-to-new roots, relative file mapping, byte sizes and SHA-256
   values in a migration receipt. Keep private absolute locations in `.local/`.
4. Validate every copied file and archive hash. Run relevant regressions, open
   the new native project and rebuild selected cases in a fresh validation run.
   Compare the generated circuit and numerical results under the original task
   contract. Keep these checks separate from the original completed study.
5. Switch entry points and local host mappings only after those checks pass.
   Retire the legacy staging root according to the explicit migration scope;
   retain its verified historical source/evidence or an archival mapping.

Do not change original internal report paths, regenerate an evidence ZIP or
rewrite a completed run's source/settings snapshots merely to adopt the new
layout. A migration records new locations; it does not claim a new electrical
experiment. See the [ADS workflow](ads-mcp-workflow.md) for native construction,
simulation, transfer and reproduction requirements.
