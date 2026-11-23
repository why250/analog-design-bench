# Synthetic nonideal LC feasibility study

This task-owned engineering workspace implements
`inp-passive-lpf-65g-nonideal-lc-feasibility-r1`. Its stable name matches the
task ID. The disclosed ideal revision-2 baseline is pinned in
[project.toml](project.toml). All loss and parasitic coordinates are synthetic
research assumptions.

The [execution record](docs/execution-record.md) links the completed study and
its retained reports. Study completion, candidate electrical acceptance and
readiness for PDK mapping are separate conclusions. This task has no official
benchmark verifier or score. The supplied native source corresponds to anchor
B, a `FAIL` case retained for the required nonideal analysis.

The [migration record](docs/migration-record.md) documents the completed
directory normalization, preserved archive hashes and fresh layout checks.

## Selected native reference: anchor B

The editable native source represents the preselected combined nonideal case
`e6-q80-fl0-320g-esr0.1-esl2p`. It supplies the common E7 sensitivity reference
and one E9 reproduction target, with the Stage 1 nominal L/C values:

| Generator coordinate | B setting | Model meaning |
| --- | --- | --- |
| `Q_L_ref` | 80 | Internal series-RL branch Q at 65 GHz; generates each inductor's fixed Rs. |
| `f_L0` | 320 GHz | Lossless resonance label; generates each inductor's terminal-to-terminal Cp. |
| Capacitor ESR | 0.1 ohm | Fixed series resistance on every capacitor. |
| Capacitor ESL | 2 pH | Fixed series parasitic inductance on every capacitor. |

All five inductors and all four capacitors use these settings simultaneously.
Individual Rs/Cp values follow each nominal L. Terminal Q varies with frequency,
and actual lossy self-resonance is calculated from the complete model. The
[model contract](inputs/task-spec/model-plan.md) owns those equations.

B is a synthetic reference condition with a retained `FAIL` result. Its
passband matching and insertion-loss failures remain visible in the
[study report](results/stage2-20261027T113222Z/report.md). Optional same-topology
retuning and real PDK calibration were not executed in the completed study.

## Project structure

```text
project.toml                     # Identity and portable relative paths
ads/inp_lpf_nonideal_wrk/        # Editable DUT, symbol and external-port bench
tools/                          # Reconstruction, simulation and analysis
tests/                          # Regression and rejection tests
inputs/baseline-r2/              # Pinned baseline snapshots, hashes and support
inputs/task-spec/                # Task snapshot for an isolated ADS host
docs/execution-record.md         # Entry point to the completed research record
results/<run-id>/                # Ignored ordinary engineering evidence
  cases/
  units/
  reproductions/
  handoff/original/              # Original archives and verification receipts
  work/                          # Live independent rebuild scratch
```

The authoritative [task specification](../../tasks/inp-passive-lpf-65g-nonideal-lc-feasibility/instruction.md)
stays in the repository's task package. An isolated host uses the declared
[task snapshot](inputs/task-spec/instruction.md). The [engineering layout contract](../../docs/engineering-workspace-layout.md)
defines stable project ownership, cross-host mirroring and migration rules.
Absolute host roots, connection settings and ADS sessions belong in ignored
repository `.local/` records.

`project.toml` resolves paths from this project root. The same relative
`workspaces/<task-id>/` path is used on the ADS host. Run timestamps belong under
`results/`. The ideal task remains in its existing `workspaces/inp-lpf/`
workspace; this project's tools use their own ADS support module and pinned
baseline inputs.

## Implementation

- `tools/model.py`, `cases.py` and `analysis.py` define the frozen-coefficient
  model, deterministic request mappings and independent rational-network checks.
- `tools/ads_support.py` provides local ADS workspace and drawing helpers.
  `build_ads.py` creates `inp_lpf_stage2_lib:inp_lpf` schematic/symbol and the
  separate `inp_lpf_sp` bench with external 50-ohm ports.
- `tools/run_study.py`, `units.py` and `boundaries.py` retain pre-run predictions,
  native input snapshots, generated netlists, raw datasets/logs, complex exports,
  local frequency refinements and E8 parameter-search accounting.
- `tools/reproduce.py` replays E0, B and the near-resonance case in fresh native
  workspaces, then releases OA locks before taking portable snapshots.
- `tools/reporting.py`, `handoff.py` and `finalize.py` create the learning record,
  explicit stage decision, raw-evidence audit and portable archives.

The native interface has ordered terminals `rfin, rfout, gnd`. The testbench owns
the two 50-ohm RF ports and ideal common ground. The declared five series and
four shunt arms and all electrical limits remain those of the task contract.

## Execute a new study

Follow the [ADS MCP workflow](../../docs/ads-mcp-workflow.md): discover the
session, inspect unsaved designs and confirm an accessible parent before
opening the project. In an ADS Python session, select this project explicitly:

```python
from datetime import datetime, timezone
from pathlib import Path
import sys

project = Path("/authorized/analog-design-bench/workspaces/inp-passive-lpf-65g-nonideal-lc-feasibility")
sys.path.insert(0, str(project / "tools"))
from project_config import load_project
import run_study

config = load_project(project)
run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
root = config["paths"]["results"] / run_id
workspace = config["paths"]["ads"]
run_study.prepare(root)
run_study.batch(root, workspace, limit=1, families=["E0"])
```

Validate E1 before the nonideal filter campaign, then run bounded batches:

```python
import json
import units, boundaries, reproduce, reporting, handoff

while True:
    result = units.run(root, workspace, limit=5)
    assert result["valid"] == result["completed"], "Diagnose invalid unit evidence"
    if result["e1_complete"]:
        break
    assert result["new_results"], "Diagnose missing progress"
while run_study.batch(root, workspace, limit=5):
    pass
while True:
    row = boundaries.next_request(root)
    if row is None:
        break
    if not (root / "cases" / row["case_id"] / "summary.json").exists():
        run_study.run_case(root, row, workspace)
assert boundaries.summarize(root)["complete"]
checks = json.loads((root / "study_checks.json").read_text())
checks["e8_complete"] = True
run_study.write_json(root / "study_checks.json", checks)
while True:
    result = reproduce.run(root, limit=1)
    assert result["passed"] == result["completed"], "Diagnose reproduction differences"
    if result["e9_complete"]:
        break
    assert result["new_results"], "Diagnose missing progress"
reporting.aggregate(root)
assert handoff.audit(root)["ok"]
reporting.aggregate(root)
receipt = handoff.package(project, root)
```

Use a fresh run directory. Preserve and diagnose unfinished attempts before
resuming; completed counts alone do not establish numerical or electrical
validity. Pure-Python final analysis and packaging can run outside the ADS UI
process. The three measured local grids use 400, 200 and 100 kHz spacing;
stationary-root coverage and an independent dense grid also remain required.
DC is the analytic model limit, while ADS SP requests use positive frequencies.

## Validate and retain

From the repository root, with NumPy available:

```text
python -m unittest discover -s workspaces/inp-passive-lpf-65g-nonideal-lc-feasibility/tests -p "test_*.py" -v
python -m unittest discover -s workspaces/inp-passive-lpf-65g-nonideal-lc-feasibility/inputs/baseline-r2/tools -p test_analyze.py -v
```

Completed evidence retains its original internal file paths and bytes. Original
ZIPs and transfer/recheck receipts belong under the run's `handoff/original/`
directory. Live independent rebuilds default to the run's `work/reproductions/`.
Directory normalization uses a separate copy/hash migration record and a fresh
validation run. It does not rerun or relabel the completed study. Derive new
audits or presentation exports into a fresh declared output location.

This workspace stores ordinary engineering studies. Registered formal model
campaigns retain the repository-root [evaluation result layout](../../docs/evaluation-results.md).
Synthetic RLC results establish the declared conditional circuit behavior;
PDK mapping, physical layout/EM and later robustness work keep their own scope.
