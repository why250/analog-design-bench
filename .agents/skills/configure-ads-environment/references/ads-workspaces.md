# Portable ADS engineering workspace organization

Use this as a practical default for a new task-owned ADS workspace. Keep an existing
working instance, project identity, and directory convention unless migration is requested.
Describing this layout does not create files, transfer assets, or authorize ADS execution.

## Stable ownership and directory roles

The task specification owns requirements, revision, and acceptance policy. The engineering
workspace owns editable native source, reconstruction tools, selected inputs, and run evidence.
Keep its root stable across runs; a dated run directory is not the engineering project.
The following names are defaults to adapt, not prerequisites imposed on another repository.

```text
tasks/<task-id>/                       # Authoritative specification, when this convention exists
workspaces/<task-id>/                  # Stable engineering root
  README.md                           # Selected design, entrypoints, dependencies, evidence
  project.toml                        # Custom engineering identity and relative paths
  ads/<design-name>_wrk/               # Authored native ADS project
  tools/                              # Required reconstruction, execution, and analysis tools
  tests/                              # Only meaningful checks needed by the selected task
  inputs/
    task-spec/                        # Frozen specification for isolated execution or handoff
    <baseline-id>/                    # Selected baseline inputs and provenance, if applicable
  docs/execution-record.md             # Decisions, retained runs, limitations, next action
  results/<run-id>/                    # Fresh ordinary engineering evidence for one invocation
    cases/                            # Frozen per-candidate inputs and raw evidence, if needed
    reproductions/                    # Released replay evidence and native snapshots
    handoff/                          # Selected deliverables and transfer receipts, if requested
    work/                             # Live rebuild and simulation scratch
```

Create only directories the task uses. Keep formal benchmark campaigns in their established
result layout; organizing an engineering project does not register or score a benchmark.
Use a UTC run identifier, optionally with a short purpose suffix, and a fresh output location
for each invocation. Preserve completed runs rather than rewriting them to fit this diagram.

## A small engineering manifest

This TOML is an illustrative custom project manifest, not an ADS file format or runner schema.
Its example schema version belongs only to this illustration. The destination's actual
schema, initializer and validator take precedence; never downgrade an existing manifest or
introduce a parallel required schema. Replace the identity and design placeholders and
select the actual task revision; include optional paths only when their assets exist.

```toml
schema_version = 1

[project]
task_id = "{{task_id}}"
revision = 1
task_version_id = "{{task_id}}-r1"

[paths]
ads = "ads/{{design_name}}_wrk"
tools = "tools"
specification_snapshot = "inputs/task-spec"
docs = "docs"
results = "results"
```

Resolve paths from the manifest directory, independently of the caller's working directory.
Validate task identity and revision against the selected specification. Check resolved targets,
including links or junctions, stay within the intended workspace; reject traversal or accidental
references into another task's mutable source. Test resolution from a different working directory.
Keep full identity in metadata and account for host path-length limits when nesting scratch work.

Keep the manifest focused on stable engineering identity and paths. Put candidate selection,
run state and evidence decisions in the destination's run/checkpoint record. Before execution,
freeze the task and selected workflow/version with required input inventory; verify receipt at
the consumer. Keep source versions and exact integrity values in machine-readable receipts.
An initialized directory, even with a valid manifest, does not prove native/model readiness.

## Native ADS source and portability

- Separate the bare DUT schematic, ordered-terminal symbol, and testbench schematic. Identify
  exact library/cell/view names; distinguish the selected source from historical alternatives.
- Follow the destination project's ADS library, cell and view naming convention. If none exists,
  adopt one that encodes the task revision, the library role and the authoritative view, and keep
  experimental views clearly separated from authoritative source.
- Keep supplies, loads, Term ports, grounds, feedback, and required model includes with their
  declared DUT or bench owner. A copied bench does not establish correct wiring or analysis.
- Prefer relative project paths in native library definitions and supported installation
  variables such as `HPEESOF_DIR`; put private installation and PDK bindings in a host profile.
- Preserve required native library metadata, including hidden `.oalib` files. Inspect an inventory
  before excluding files; retain metadata needed to reopen libraries and resolve design views.
- Exclude transient OA locks, session state, generated simulation scratch, and bytecode from
  portable source. Native source and exports that expose restricted models require classification.
- Release locks through the authorized application workflow before freezing a portable snapshot;
  do not delete live locks or overwrite unsaved designs to make a copy appear clean.

## Cross-host copies and model bindings

Use the same workspace-relative suffix on each host where practical. Record each absolute root,
connection, filesystem mapping, installation, and license binding in a private execution profile.
Matching drive letters do not imply shared storage. Verify the actual ADS consumer's files.

When copying an existing project, preserve the original source, extracted samples, and completed
evidence. Retain required library metadata while omitting transient locks and scratch. Inspect
copied EM setup references such as `emSetup` paths: rebind source-root references in the copy only,
so extraction or cache lookup cannot silently read or write the original workspace. Record changed
configuration separately from unchanged sample payloads; a copy is not a new extraction.

Verify the declared file inventory and bytes at the consumer, not merely a transfer exit code.
Keep exact integrity values in machine-readable receipts; narrative records use names and links.
Confirm the selected copied workspace and its libraries in an authorized session before dependent
execution. An unopened copy remains pending verification even when its directory tree is complete.
Record actual models, generator versions, complete geometry, sample matches, interpolation state,
and validity warnings. Preserve provenance for frozen baseline inputs instead of live imports from
another workspace's tools. Do not bundle private PDK material to claim a self-contained handoff.

## Freeze, reproduce, and hand off

Retain the selected candidate and bench, parameter assignment, generated netlist, resolved model
bindings, simulator settings and logs, native dataset, measurements, and necessary exports together.
Link source to netlist to actual models to dataset; distinguish screening variants from the native
candidate. Rebuild into a fresh run's `work/` area and retain released comparisons and native
snapshots under its reproduction evidence. Keep transient replay projects out of the stable `ads/`.
Report reproduction, electrical acceptance, and model validity separately; unperformed checks stay
pending. Preserve original run bytes and use an amendment for later interpretations or relocation.
For a requested handoff, include selected source, required inputs, tools, manifest, and evidence
index; exclude live scratch, private profiles, locks, and recursively included prior handoffs.

Use the destination's common run index when one exists, without flattening task-specific raw
evidence into a universal directory tree. It should identify the task/run, frozen inputs and
workflow, selected native candidate, evidence links, timestamps, unresolved checks and next
action. Report execution completion, electrical outcome, model applicability and delivery
completeness independently. Failed/interrupted runs retain their actual state and evidence.
