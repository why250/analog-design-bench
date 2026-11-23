# Task-owned engineering workspace layout

Start with the [engineering task workflow](engineering-task-workflow.md) for
task routing, frozen delegation inputs and phased run checks. This document
owns the ADS directory and static manifest contract; `validate` alone is not a
readiness or completion check.

Use a stable task-owned directory for editable engineering work. Keep execution
identities below that directory, and keep machine configuration outside its
portable source. The same relative workspace path applies on the repository
host and the ADS host; each host's absolute root is a local setting.

ADS library, cell and view names follow the
[ADS naming convention](ads-naming-convention.md) for new tasks and new task
revisions. Completed workspaces keep their existing names.

This is the required layout for new task-owned ADS engineering work in this
repository. Initialize it before the first native build or simulation. Existing
workspaces retain their identities until a separate migration is scoped.

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
    <baseline-id>/              # Pinned baseline inputs, when the task uses one
      manifest.json             # Provenance and exact-byte file hashes
    task-spec/                  # Task snapshot for an isolated host/handoff
  docs/
    execution-record.md          # Human entry point to retained runs
  results/                      # Ignored ordinary engineering records
    <run-id>/
      run.json                  # Common run identity, evidence links and outcomes
      contract/                 # Frozen task and workflow baseline
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
Include only the input and evidence categories the selected task actually uses;
the nonideal LPF's `baseline-r2`, E0-E9 experiment IDs and analysis tools are
task-specific examples, not a template for another circuit's experiment plan.

Use a UTC identifier for a new run, with a descriptive suffix when needed.
Task names and revisions belong in metadata; run IDs do not rename the stable
engineering project. Every output invocation uses a fresh directory. Record
the source/configuration hashes and selected native case with each invocation.

Keep live independent rebuild workspaces under the run's `work/` directory.
Keep their released OA snapshots with the corresponding reproduction evidence.
Only the authored engineering workspace belongs directly under `ads/`;
transient replay workspaces must not accumulate beside it or inside another
task's project.

## Start another ADS task

1. Read the authoritative `tasks/<task-id>/task.toml` and selected task revision.
   Set the stable engineering root to `workspaces/<task-id>/`; do not place a new
   task inside another task's source or use a run ID as the project root. Use
   lowercase `kebab-case` for `<task-id>` (recommended `<tech>-<block>-<variant>`
   or `<tech>-<block>-<variant>-<stage>`).
2. Scaffold the new `schema_version = 2` workspace with the repository initializer
   rather than copying an older project by hand:

   ```powershell
   python scripts/ads_workspace.py init --task-id <task-id> --stage <stage> --model-policy restricted-pdk --with-tools --with-tests
   ```

   Choose the block key, DUT library and DUT cell per the
   [ADS naming convention](ads-naming-convention.md), for example
   `--block-key LPF --dut-lib LPF_R01_lib --dut-cell LPF_Series_First
   --dut-ports rf_in,rf_out`. Pass `--vendored-libs` for byte-copied PDK
   libraries that must keep their installation names.

   Pass `--create-task` if the `tasks/<task-id>/` package does not exist yet,
   `--model-policy unrestricted-ideal` for open/ideal-only ADS schematics, or
   `--snapshot-spec` to freeze `tasks/<task-id>/` into `inputs/task-spec/`.
   Keep paths relative to `project.toml`, validate identity against the task
   package, reject paths outside the workspace, and reuse the existing task's
   workspace for later runs or revisions of that same task.
3. Establish the directory roles above and the policy-matched `.gitignore`
   before generating native files. Keep the single primary editable native
   source under `ads/design_wrk/` (or a short `ads/<name>_wrk/`), never storing
   `.zip` archives or dated backup copies in `ads/`. Keep runnable scripts in
   `tools/` and all `test_*.py` / `*_test.py` checks in `tests/`, and declare
   committed optional paths (`tools`, `tests`, `specification_snapshot`) in
   `project.toml` only when those directories exist.
4. Discover an accessible, authorized parent on each host and use the same
   `workspaces/<task-id>/` suffix below it. Record the selected ADS installation,
   connection entrypoint, workspace roots and PDK binding in
   `.local/ads-projects/<task-id>.json`, with the task ID and revision. Reuse
   the existing launcher or profile and reference the binding in `DEVELOPMENT.md`.
   If the binding is unresolved, record it as `pending-binding`. Confirm the
   filesystem mapping from the ADS process before making a live import or using
   host-specific paths.
5. Allocate a fresh UTC-named `results/<YYYYMMDDTHHMMSSZ>-<slug>/` for each
   execution (e.g. `python scripts/ads_workspace.py new-run --workspace workspaces/<task-id> --slug nominal`).
   Never place loose files directly in `results/` or omit the UTC timestamp.
   Keep live replay/simulation scratch below that run's `work/`, released
   evidence with its corresponding case or reproduction, and archives under
   `handoff/`. Check projected path lengths on the actual Windows hosts before
   allocating nested workspaces; keep `_wrk` names short while retaining full
   identities in metadata.
   New runs also receive `run.json`; select their workflow and requested
   deliverables, freeze the contract and apply the scaffold/ready/handoff
   checks in the [task workflow](engineering-task-workflow.md). Existing runs
   do not acquire a new record or change layout automatically.
6. Write the workspace README with the selected native design, reconstruction
   and verification entrypoints, input provenance and evidence locations. Link
   it from the task's `DEVELOPMENT.md`. Keep these operator materials outside
   blind solver input and complete the validator and handoff checks below.

## Schema v2 manifest and automated checks

New ADS workspaces use `schema_version = 2` in `project.toml`, enforced by
[the ADS workspace tool](../scripts/ads_workspace.py):

- **Static `project.toml` contract**: allow only `schema_version = 2`,
  `[project]` (`task_id`, `revision`, `task_version_id`, `stage`, `model_policy`),
  `[paths]` (`ads`, `docs`, `inputs`, `results`, plus optional `tools`, `tests`,
  `specification_snapshot`, `upstream`), and optional static `[design]`
  (`block_key`, `dut_lib`, `dut_cell`, `dut_ports`, `vendored_libs`) or
  `[ads_workspaces.<role>]` (`ads/aux_<role>_wrk` with `purpose`).
- **Keep dynamic state out of `project.toml`**: do not add `[planning]`,
  `[execution]`, `[evidence]`, `[qualification]`, `[pdk]`, or `[interface]`
  tables to `project.toml`. Record execution status and results in
  `docs/execution-record.md` and `results/<run-id>/`, and host/PDK bindings in
  `.local/ads-projects/<task-id>.json`.
- **Two-tier `.gitignore` policy**:
  - `restricted-pdk` (default): excludes `/ads/`, exports (`*.net`, `*.ds`,
    `*.sNp`, `*.zip`), `/inputs/pdk/`, `/inputs/upstream/`, and runtime locks;
    retain reconstruction scripts in `tools/`.
  - `unrestricted-ideal`: tracks `ads/` native source while excluding `/results/`,
    `/inputs/upstream/`, OA locks, `.prf`, logs, `simulation/`, and `data/`.
- **Validate before commit or handoff**:

  ```powershell
  python scripts/ads_workspace.py validate --workspace workspaces/<task-id>
  python scripts/ads_workspace.py validate --all-v2
  ```

These are static layout checks. A missing native project may still be valid
as an initialized scaffold. Apply the run's `ready` and `handoff` phases and
the task-owned electrical checks before making stronger claims. Dynamic run
selection and status stay in `run.json`; the execution record and README link
the selected record and explain its scope.

Existing `schema_version = 1` and pre-manifest workspaces retain their legacy
structure until an explicit migration is scoped (`python scripts/ads_workspace.py audit`
reports all workspaces without failing on legacy entries).

## Check the layout before handoff

- Confirm that the task package, project manifest and selected revision agree;
  exercise path resolution from another working directory. Primary ADS source
  belongs under the stable task root; dated directories occur only in results
  or explicitly retained migration history.
- Confirm the declared relative layout on each host and test the project's
  ignore rules for results, bytecode, ADS locks and session/simulation files.
  Preserve required native metadata such as `.oalib`.
- Open the declared native source, rebuild a selected case into a fresh run and
  apply the selected task's electrical checks. Record netlist and numerical
  comparisons; a matching directory tree alone does not establish correctness.
- Check that the handoff is self-contained, including its manifest, `.gitignore`,
  tools, required frozen inputs, native source and linked guides. Exclude live
  scratch, locks, private host settings and recursively included archives.
  Verify transferred ZIP hashes and every declared member's size and SHA-256.
- For a migration, retain the before/after file inventory and unchanged original
  evidence and ZIP bytes. Put fresh validation in a separate run, then switch
  entrypoints and host mappings. Follow the migration procedure below.

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
