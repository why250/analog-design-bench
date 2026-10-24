# Structured electrical design contracts

An electrical design contract describes a task's design inputs, DUT interface,
measurements, operating conditions, bench mappings and required outputs in a
consistent, machine-readable form. The
[task development guide](task-development.md#circuit-design-lifecycle) owns the
design lifecycle and task-package layout. The
[KiCad workflow](kicad-spice-workflow.md) implements its manual-drawing path.

Contracts are operator-only indexes of existing task requirements. Original
instructions, starter, checker, benches and scoring remain authoritative. A
contract does not generate benches, replace the verifier or change a task's
score. Keep it, including hidden-bench references, outside blind solver input.

## Location and versioning

Store instances in `evaluation/design-contracts/<taskId>.json`. The current
instances describe
[NMOS LDO revision 1](../evaluation/design-contracts/sky130-nmos-pass-ldo-0p4v-pvt-mc.json)
and
[five-transistor OTA revision 3](../evaluation/design-contracts/sky130-ota-5t-gain40-pm60-noise50uv-pvt.json).
They are also concrete authoring examples. Other task packages have not been
automatically migrated by adding these files.

`schemaVersion: 1` selects the field contract below, enforced by the
[standard-library validator](../scripts/design_contracts.py). It is separate
from the task's `revision`, the task TOML schema version, the runner profile
schema version and the result-capture version. Require an explicit positive
task revision; do not infer revision 1 for historical tasks that lack one.

Adding or correcting an operator annotation does not itself create a new
electrical task. A changed interface, allowed environment or scoring contract
requires task versioning under the task development guide. Resolve discrepancies
with the original task before revising an instance; do not edit fixtures or
refresh hashes merely to make the validator pass.

## Version 1 field contract

Unknown fields and duplicate JSON keys are rejected. Fields are required except
where explicitly marked optional. Identifiers must be unique within each list;
all references must resolve within the same instance.

| Field | Contents |
| --- | --- |
| `schemaVersion` | Integer `1` |
| `taskId`, `revision`, `taskVersionId` | Exact task identity; version ID is `<taskId>-r<revision>` |
| `sources` | Hashed original instruction, metadata, starter, device guide, verifier entrypoint and measurement/scoring implementation |
| `artifact` | Container file path, required DUT subcircuit name and ordered port definitions |
| `constraints` | Allowed ideal-device policy and explicit device, topology and ownership requirements |
| `benchOwned` | External supplies, biasing, loads, clocks, feedback and injection networks |
| `conditionSets` | Named Cartesian matrices or explicit operating-point lists, with units and optional sampling |
| `benches` | Named original public/formal bench sources, analysis types and condition-set references |
| `metrics` | Named quantities, units, measurement definitions, numeric criteria, bench/condition references and aggregation |
| `acceptance` | Original verifier authority, prerequisite metrics, scoring/failure policy and report paths |
| `outputs` | Required submission files, optional design artifacts and retained verification evidence |

### Sources and portable content identity

Every source record has `path` and `sha256`. Paths are normalized,
repository-relative POSIX paths under the selected `tasks/<taskId>/`; references
to another task, `solution/`, parent traversal, symlinks and junctions are
rejected. The six required source entries are:

| Source key | Task-relative file |
| --- | --- |
| `instruction` | `instruction.md` |
| `metadata` | `task.toml` |
| `starter` | `environment/starter/circuit.spi` |
| `deviceGuide` | `environment/starter/SKY130_NETLIST_GUIDE.md` |
| `entrypoint` | `tests/test.sh` |
| `verifier` | `tests/verify.py` |

Optional `sources.supporting` is a list of further source records. Include
helpers that affect parsing/scoring, task Dockerfiles and other relevant task
dependencies. Both initial instances include `tests/utils.py` and the solver
and verifier Dockerfiles. Bench records carry their own source hashes.

For this schema, `sha256` identifies canonical UTF-8 text: decode UTF-8 with an
optional BOM, normalize CRLF and CR to LF, encode UTF-8 without a BOM, then hash.
Use `source_sha256(raw_bytes)` from the validator. This tolerates Windows/Linux
checkout newline differences without modifying the files; changes to other
characters still require review. This content identity is distinct from the
exact-byte SHA-256 required for frozen submissions, images, evidence archives
and retained simulation inputs. Keep those original byte hashes unchanged.
Static validation does not inspect the complete transitive dependency graph.

### DUT and external circuitry

`artifact` contains `path`, `subcircuit` and nonempty ordered `ports`. Each port
has `name`, `role`, `direction` and `description`. `direction` is `input`,
`output` or `inout`; it describes the task interface, not a proof of KiCad ERC
pin types. Port names must be unique ignoring case and match the starter's
ordered `.subckt` interface. `artifact.path` must match the original declared
artifact, currently a single file such as `/app/circuit.spi`.

`constraints` contains `allowedIdealDevices` and `requirements`. The ideal-device
list must match `metadata.checker_allow_ideal`. Record mandatory topology
constraints only when the task actually imposes them; document design objectives
and verifier eligibility accurately. Standardize the package and interface while
allowing the internal circuit choices permitted by each task.

Each `benchOwned` entry has `id`, `kind`, `ports` and `description`. Port references
must exist in the DUT interface. Record bias-current direction and the reference
node of each stimulus/load. A DUT return port may be perturbed by a supply-rejection
bench; grounding it internally can invalidate that measurement. The original
bench determines its exact connections.

### Conditions and bench mappings

Every condition set has `id`, `kind` and a `dimensions` object mapping dimension
names to units. Use numeric values with explicit units, for example `vdd` in
`V`, `temperature` in `degC` and `loadCurrent` in `A`; process labels use `corner`.
Use the same names/units for the same quantity within a contract.

- `kind: "cartesian"` requires `axes`, mapping every dimension to a nonempty,
  unique value list. All combinations are included.
- `kind: "points"` requires a nonempty `points` list. Every point has exactly
  the declared dimension keys. Use this for selected representative corners;
  three selected process/voltage/temperature triples are three points rather
  than a 27-point Cartesian matrix. Duplicate points are rejected.
- Optional `sampling` has positive integer `count` and a `method` description
  specifying the deterministic seed/sample policy and how samples are shared
  across operating points.

The report's `basePointCount` counts operating points, `sampleCount` defaults to
1, and `totalPointCount` is their product. Counts are per condition set, can
overlap across sets, and must not be added as unique coverage or interpreted as
ngspice process counts. The LDO mismatch bench measures both loads in one
invocation: 2 base points times 50 samples describes 100 sampled operating
points, produced by 50 invocations.

Each bench has `id`, hashed `source`, `visibility`, nonempty `analyses` and
`conditionSets`. `visibility` is `public` for sources under
`environment/starter/testbench/`, or `verifier` for sources under `tests/benches/`.
List the public scenarios as they actually exist; their conditions need not
equal the formal acceptance matrix. Referencing a condition set declares a
bench's coverage; the validator does not prove that its control script executes
that matrix.

### Metrics, acceptance and outputs

Each metric has `id`, `unit`, `description`, `measurement`, `criteria`,
`conditionSets`, `benchIds` and `aggregation`. A criterion has `expression`,
`operator` and numeric `value`; supported operators are `<`, `<=`, `>`, `>=`,
`==` and `!=`. Values must be finite numbers, excluding booleans. Preserve
strict/inclusive boundaries, frequency ranges, DC operating points, noise
integration limits, active-device exclusions and statistical estimators.

Every referenced condition must be covered by at least one referenced bench.
The initial metric lists describe formal acceptance quantities and nominal
prerequisites; public bench entries separately describe development coverage.
`measurement`, `expression` and `aggregation` are declarations reviewed against
the hashed original implementation. They are never evaluated as Python or used
to generate a competing measurement/scoring engine. A schema check cannot prove
the electrical meaning or completeness of those declarations.

`acceptance.authority` is `original-verifier`. `prerequisites` references metric
IDs; `scoring` explains score grouping and partial credit, and `failurePolicy`
explains blocking, missing data and failed simulations. `rewardPath` and
`reportPath` are distinct relative paths inside the verifier log mount; they
must also match a registered runner profile when one exists. Metric count is
not score-check count: multiple quantities may contribute to one original check.

`outputs` has string lists `required`, `optional` and `evidence`. Required
outputs must include `artifact.path`. Optional KiCad projects, parameter tables
and design notes are learning/design deliverables; they do not expand the
shared runner's single-SPICE submission interface. Store simulation evidence in
the workspace and formal campaigns in the existing
[result layout](evaluation-results.md), rather than in a new parallel archive.

## Run the offline checks

Python 3.11 or newer is sufficient; no Docker, PDK or model request is needed:

```powershell
python scripts/design_contracts.py --all
python scripts/design_contracts.py --task sky130-ota-5t-gain40-pm60-noise50uv-pvt
```

The command prints JSON with `scope: "static-contract-only"`, a `valid` flag,
per-contract counts and errors. Any error returns a nonzero exit code.
`--repo-root` selects another checkout. Optional `--output` also writes a report
to a fresh file whose parent exists; it refuses to overwrite an existing file.
Keep local reports under ignored `.local/` or a workspace's `results/`.

The checks cover field shape, finite criteria, references, source hashes and
paths, metadata identity/revision/artifact/ideal-device policy, ordered starter
ports and any matching registered profile. They do not run the structural
checker, benches or verifier, prove Spec/measurement equivalence, or establish
electrical acceptance.

Run the focused regression checks with:

```powershell
python -m unittest discover -s scripts -p test_design_contracts.py -v
```

To onboard another task, review its original contract, add an instance from the
examples, resolve every missing revision/interface/measurement definition and
run these checks. Then perform the task development guide's reference and
negative-case verification using the original pinned environment. Runner
registration, KiCad export readiness and formal electrical acceptance remain
separate milestones. Changes to old task requirements or frozen release
membership need their own explicit versioning work.
