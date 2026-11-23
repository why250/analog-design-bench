# Reproduce the Toolkit and Momentum study

The original study is closed at the user's request. The reusable procedure
below documents existing capabilities; it does not authorize restarting that
study. See the [closeout report](closeout.md) for the retained result and gaps.

This procedure reproduces one assumed-stack device with the task-owned tools.
It is an execution guide, not a completed qualification report. The selected
screening candidate is `p09`: one octagonal turn, diameter 106 um, track width
20 um, gap 2 um, feed width 10 um and feed extension 5 um. Its finite Metal1
return has inner side 1.8 times the diameter and width 20 um. The center tap and
stacked-metal option are disabled. Numerical qualification remains incomplete;
no device PASS, foundry/InP qualification or parent LPF acceptance is claimed.

The governing records are the [research contract](../inputs/research-contract-r1.json),
[expanded physical stack](../inputs/effective-stack-r1.json),
[native AFS protocol r2](../inputs/numerical-protocol-amendment-r2.json),
[model-use contract](../inputs/model-use-contract-r1.json),
[frequency-method explanation](frequency-method-amendment.md), and
[execution history](execution-record.md). Use their unchanged electrical limits:
114--126 pH at exactly 65 GHz, 108--132 pH over 10--65 GHz, and positive terminal
reactance through 80 GHz with qualified uncertainty. Q is reported without an
invented minimum.

Frequency revision r1 converged, but its native dense output below 100 GHz had
a maximum spacing of about 1.146 GHz, exceeding the 1 GHz requirement, and its
original actual-sample gaps supplied only two intervals within 10--65 GHz.
Those retained results remain unqualified frequency evidence. Revision r2 used
a fresh native export and actual solve; it does not relabel or resample r1
results. Its independent AFS controls pass the unchanged numerical limits
through 80 GHz and fail those limits above 80 GHz. Retain only the unchanged
native derived samples in 5--80 GHz for nominal assembly. The frozen
[high-frequency direct fallback](../inputs/high-frequency-direct-fallback-r1.json)
requires 41 actual points at `80:1:100,105:5:200` GHz. That solve completed and
is retained separately; a complete nominal model was not assembled or finally
qualified before closeout. The material
model is unchanged, so `physics_revision` remains `passive-loss-r1`.

## Reusable automation chain

Use this implementation when a newly authorized study needs Toolkit-generated
on-chip artwork, actual full-wave EM and evidence-based candidate screening.
Resolve the task root through `project.toml`; supply the licensed ADS runtime,
the task-owned Toolkit copy and the frozen stack/port contract. Keep native
source under `ads/` and use fresh case paths under `results/<UTC-run-id>/`.

```text
Geometry parameters + frozen physical contract
  -> Toolkit artwork and native ADS cell/EM setup
  -> native export and physical-input validation
  -> Momentum full-wave solve and complete complex network
  -> constrained-current L/R/X/Q extraction
  -> recorded observations and candidate ranking/predictions
```

| Stage | Existing entrypoint | Input and retained output |
| --- | --- | --- |
| Generate native geometry | [build_ads.py](../tools/build_ads.py), task-copy [AEL adapter](../tools/toolkit-adapter.ael) | Diameter, width, gap, return-frame and mesh parameters become an editable cell, native ports/EM setup and `construction-receipt.json`. |
| Export and simulate | `build_ads.export_case`, [validate_inputs.py](../tools/validate_inputs.py), [run_momentum.py](../tools/run_momentum.py) | Application-mode native export is checked before `prepare`/`solve`; retain original/working decks, execution receipts, solver logs/dataset, `raw.s2p` and `raw-complex-s.csv`. |
| Extract metrics | [analyze_em.py](../tools/analyze_em.py) | Complete complex S matrices, reference impedance and declared excitation become `analysis.json`, `metrics.csv` and optional characterization plots. |
| Screen and predict | [optimize_geometry.py](../tools/optimize_geometry.py) | An explicit observation list plus the frozen research contract becomes ranked screens, diameter predictions, original evidence references and geometry-budget accounting. |

These are callable stages. Native export requires an ADS application session;
construction and solving use an independent runtime. The observation list is
an explicit handoff assembled from metric reports and construction/execution
receipts. There is no single unattended command that controls every stage.

### Replay a candidate screen

Follow [construction](#construct-and-configure-in-an-independent-session) and
[application export](#export-through-an-ads-application-session) first, including
the native-input validator. With the variables defined in the preparation
section and a validated `$NativeExport`, the screening continuation is:

```powershell
$Case = Join-Path $Run "candidate-screen"
& $AdsPython tools/run_momentum.py prepare $NativeExport $Case `
  --ads-root $AdsRoot --native-workspace $NativeWorkspace --mesh-um 4 `
  --frequency-ghz 10 65 80 --threads 4
& $AdsPython tools/run_momentum.py solve $Case --ads-root $AdsRoot
& $AdsPython tools/analyze_em.py "$Case/raw.s2p" `
  --output-dir "$Run/candidate-screen-metrics" --no-plots
```

This three-frequency invocation characterizes a candidate; it does not establish
continuous-band acceptance. Repeat only for candidates in the newly authorized
study budget, retaining all attempts. For this baseline the extraction is
`I1=I, I2=-I, Icm=0`, `Zd=Z11+Z22-Z12-Z21`,
`L=Im(Zd)/(2*pi*f)` and `Q=Im(Zd)/Re(Zd)`, with no division by two.

Each observation record requires `case`, `D_um`, `w_um`, `L65_pH`, `Q65` and
`valid_fullwave`. Include `X80_ohm`, `model_group` and `evidence_paths` so the
signed-reactance screen and evidence can be reviewed. Assert `valid_fullwave`
only after checking actual full-wave completion, physical inputs and port
mapping; the planner does not establish those facts. Use separate model groups
for different physics revisions, stacks, returns, planes or topologies, and
never pool them for a geometry fit. Then invoke:

```powershell
& $AdsPython tools/optimize_geometry.py --observations "$Run/observations.json" `
  --contract "$TaskRoot/inputs/research-contract-r1.json" `
  --output "$Run/candidate-ranking.json"
```

The planner ranks admissible point screens by Q at 65 GHz, then distance from
the target. It fits diameter changes only within fixed-width/model groups;
any suggested geometry requires a new native build and actual EM solve.
Retain predictions before the proposed solve. Failed and invalid observations
remain in the supplied history and geometry-budget accounting. The current
planner is deliberately pinned to this task's 120 pH contract and is not a
generic optimizer for another target or PDK.

### Boundaries of reuse

Full-wave mode must be established by the working deck and actual `uW` log,
not the wrapper flag or process exit alone. Validate the exported passive-loss
sign, expanded metal elevations, actual polygons and physical return before
batching candidates. Keep full complex networks and distinguish actual samples
from native AFS-derived samples. Use the established read-only library export
procedure when another workspace is open; avoid global save/close operations.

Candidate ranking is separate from qualification. Continue to the detailed
frequency, mesh, port, return, DC/LF, reproduction and consumer checks below
only within the authorized scope and budget. Missing evidence leaves acceptance
unresolved. A scalar L/Q result or a ranked candidate does not make the model
ready for a different stack or for parent-filter integration.

## Prepare a portable task root

Use Windows with a licensed ADS 2027 Momentum installation and its configured
Python runtime. Keep installation paths and license/session bindings in ignored
local configuration. Ordinary preparation and tests need Python 3.11 or later;
numerical analysis needs NumPy, independent DC solvers need SciPy, scientific plots need Matplotlib, and native
construction/dataset export need the ADS Python packages. Solver preparation
uses the installed `bin/adsMomWrapper.bat` through the retained runner.

Copy this complete task root, including `project.toml`, tools, frozen inputs,
and the permitted task-owned Toolkit Open dependency to the same relative
layout on the execution host. Follow the dependency and license records in
`inputs/`; do not substitute a machine's global Toolkit installation. Exact
replay also requires the retained native/material input snapshot: public helper
source alone does not contain every native OA or solver artifact.

The copied technology must contain the corrected passive `ResearchOpen`
substrate/material definitions, and the copied shape PCell must use
`task_pH_2port` from [toolkit-adapter.ael](../tools/toolkit-adapter.ael). That
wrapper calls `mi_octa_singleturn` with both center-tap and stacked-metal flags
false. The native PCell retains its original library/cell name; the builder
checks its actual AEL generator and refuses the stock three-port generator.
Perform any dependency adaptation only in this task-owned copy, preserving the
upstream license and original evidence.

The intended positive dielectric loss tangent is 0.005. ADS direct imaginary
permittivity must be negative: sub -0.0195, ResearchOx1 -0.021, mixed oxide
-0.0188, pass1 -0.021 and pass2 -0.0395. The initial positive-imaginary runs are
invalid for this passive contract and remain historical evidence. Do not reuse
their electrical results in a corrected model. The nominal input table and
the expanded-stack record have distinct roles: conductor `EXPAND_UP` changes
the actual dielectric profile and conductor elevations.

In the following PowerShell examples replace each angle-bracket placeholder.
Every output directory/file must be fresh; retain failed attempts and use a new
identifier for retries.

```powershell
$TaskRoot = "<TASK_ROOT>"
$AdsRoot = "<ADS_INSTALL_ROOT>"
$AdsPython = "<ADS_PYTHON_EXECUTABLE>"
$Run = Join-Path $TaskRoot "results/<UTC-run-id>"
$NativeWorkspace = Join-Path $TaskRoot "ads/inductor_120ph_wrk"
$Cell = "p09_repro"
Set-Location $TaskRoot
```

Run the focused source tests before an expensive solve:

```powershell
& $AdsPython -m unittest discover -s tests
```

## Construct and configure in an independent session

Run construction in an independent headless ADS Python session. The builder
refuses to replace another active workspace. It creates a fresh cell, attaches
the task technology, updates the Toolkit PCell, adds the actual finite frame
and pins, and saves native port definitions before writing the EM setup.

```powershell
& $AdsPython tools/build_ads.py --root $TaskRoot --cell $Cell `
  --diameter-um 106 --width-um 20 --gap-um 2 --frame-factor 1.8 --mesh-um 4
```

Retain the cell's `construction-receipt.json`. The complete baseline is two
50-ohm signal ports, P1/P4 and P2/P4. P1/P2 are on Metal6, P4 is physically on
the lower finite Metal1 frame, and P3 is absent. No pads or feed removal are
introduced. Feed-end reference planes remain in the model.

Configure the native frequency plan before application-mode export. The helper
does not access an ADS session; its amendment directory must be fresh, within
the task root and outside the native workspace. Run this Python code with the
task tools directory on `sys.path`:

```python
from pathlib import Path
import sys

root = Path("<TASK_ROOT>")
sys.path.insert(0, str(root / "tools"))
from build_ads import configure_native_afs_plan

configure_native_afs_plan(
    root, "p09_repro",
    amendment_dir="results/<UTC-run-id>/native-afs-amendment",
    start_ghz=5, stop_ghz=200, adaptive_max_samples=48,
    forced_ghz=[10, 20, 40, 65, 80, 100],
)
```

This retains before/after XML and a machine receipt. It changes only
`MomSimFreqTable/freqPlanMap`, proving that other XML is equivalent and other
bytes are unchanged. Native encoding uses one adaptive type-0 plan and six
type-3 single plans. The exporter adds the six forced plans to the adaptive
budget of 48, so the expected combined cap remains 54. Verify the actual native export;
do not infer the solver stimulus solely from the editable XML.

## Export through an ADS application session

Classic `dex_em_writeSimulationFiles` is available in the tested ADS application
session and unavailable in the tested headless session. Close the independent
construction session before refreshing libraries for export.

Before and after application export, retain machine-readable byte-identity
snapshots of the surrounding parent OA sources and library definitions, plus
the active workspace identity. Review any difference; the export helper does
not certify that ADS-managed state is unchanged. The executed study retains
its own preservation evidence. Do not switch the parent workspace or edit its
`lib.defs` to export this task.

In the existing ADS application's Python console, refresh only these three
task libraries and open them read-only, in technology/shape/task order. Use
the actual source task root and a fresh export path:

```python
from pathlib import Path
import sys
from keysight.ads import de

root = Path("<TASK_ROOT>")
cell = "p09_repro"
export_dir = root / "results/<UTC-run-id>/native-export"
sys.path.insert(0, str(root / "tools"))
from build_ads import load_minimal_toolkit, export_case

libraries = [
    ("Inductor_Generic_Layers_IC_lib",
     root / "inputs/toolkit-open/Inductor_Generic_Layers_IC_lib"),
    ("Inductor_Shapes_lib", root / "inputs/toolkit-open/Inductor_Shapes_lib"),
    ("inductor_120ph_lib", root / "ads/inductor_120ph_wrk/inductor_120ph_lib"),
]
for name, path in libraries:
    try:
        de.Library.get(name).close()
    except RuntimeError:
        pass
for name, path in libraries:
    de.Library.open(name, path, de.LibraryMode.READ_ONLY)
load_minimal_toolkit(root)
export_case("inductor_120ph_lib", cell, "emsetup", export_dir)
```

If library lookup reports a different missing-library exception in the installed
runtime, handle that specific lookup outcome; preserve unexpected failures.
`load_minimal_toolkit` loads seven task-copy AEL modules plus the adapter and
disables the Toolkit's save-all/close-all simulation preferences. Export itself
does not open or close a workspace. The native view name is `emsetup`, although
its saved setup directory is `emSetup`.

The exporter requires all seven solver input files and checks the actual
`proj.prt` for exactly P1/P4 and P2/P4 with 50+j0-ohm references. Native XML port
edits alone are insufficient: ADS refreshes ports from native OA definitions.
Inspect actual `proj_a`, `proj.pin`, `proj.prt`, `proj.ltd`, `proj.opt` and
`proj.sti`, preserving the original export.

```powershell
$NativeExport = Join-Path $Run "native-export"
$Construction = Join-Path $NativeWorkspace "inductor_120ph_lib/$Cell/construction-receipt.json"
& $AdsPython tools/validate_inputs.py --root $TaskRoot --input-dir $NativeExport `
  --geometry-receipt $Construction --output "$Run/native-input-validation.json"
& $AdsPython tools/plot_geometry.py --input-dir $NativeExport `
  --output-dir "$Run/geometry"
```

The validator checks the full nominal native stack, passive material signs,
active metal properties, open AIR halfspaces, actual polygon/pin incidence and
finite return. The editable SVG/PNG is rendered from exported polygons, rather
than a reconstructed outline. An input-consistency result is separate from
electrical qualification.

## Prepare and execute full-wave cases

Use the ordinary licensed process environment. `prepare` preserves original
exports and creates explicit working-deck amendments. It sets mesh cells in
micrometres, dataset paths, thread count and `SimulationMode 1`. The latter is
essential: `--objMode=MW` alone did not override an exported RF mode. `solve`
requires the actual log to report full-wave `Simulation Mode: uW`, completed
outputs and consistent ports. Cases execute serially with a sibling lock; do
not delete an active lock or overwrite an attempted case.

First retain exact full-stack controls at 65/80 GHz:

```powershell
& $AdsPython tools/run_momentum.py prepare $NativeExport "$Run/fullstack-control" `
  --ads-root $AdsRoot --native-workspace $NativeWorkspace --mesh-um 4 `
  --frequency-ghz 65 80 --threads 4
& $AdsPython tools/run_momentum.py solve "$Run/fullstack-control" --ads-root $AdsRoot
```

The solve retains input snapshots, command/execution receipts, console logs,
generated substrate, full dataset, `proj.sio`, `raw.s2p` and complex-S CSV.
Dataset export uses the ADS Python runtime. A successful process exit by itself
does not establish numerical qualification or device acceptance.

Canonical stack compression is optional and requires separate evidence. It
removes only inactive interfaces while preserving the corrected complex
background profile and both active conductor faces. It must not replace the
actual expanded profile with the nominal dielectric sum.

```powershell
& $AdsPython tools/canonicalize_stack.py --source $NativeExport `
  --reference-sub "$Run/fullstack-control/proj.sub" --output "$Run/canonical-export"
& $AdsPython tools/run_momentum.py prepare "$Run/canonical-export" "$Run/canonical-control" `
  --ads-root $AdsRoot --native-workspace $NativeWorkspace --mesh-um 4 `
  --frequency-ghz 65 80 --threads 4
& $AdsPython tools/run_momentum.py solve "$Run/canonical-control" --ads-root $AdsRoot
& $AdsPython tools/compare_networks.py --reference "$Run/fullstack-control/raw.s2p" `
  --candidate "$Run/canonical-control/raw.s2p" --profile canonical `
  --physics-revision passive-loss-r1 --output-dir "$Run/canonical-comparison"
```

Also call `canonicalize_stack.verify_generated_sub(ltd_text, sub_text)` on the
canonical solve's actual `proj.ltd` and `proj.sub`, retaining its returned
receipt in a fresh JSON file. The helper's pre-write algebraic proof is not a
substitute for this generated-profile check and independent complex-network
control. Frozen canonical limits are max absolute complex-S error 0.0001,
relative L 0.002 and relative Q 0.01. Compare corrected passive full/canonical
inputs to each other. `validate_inputs.py` checks the nominal native source;
use the canonical proof and generated-profile check for the compressed form.

Choose the validated source directory explicitly. Preserve the native AFS
stimulus bytes; do not rebuild undocumented stimulus syntax:

```powershell
$SelectedExport = $NativeExport
# After canonical controls are accepted, this may instead be the retained canonical-export.
& $AdsPython tools/run_afs.py prepare $SelectedExport "$Run/afs-m4" `
  --ads-root $AdsRoot --native-workspace $NativeWorkspace --mesh-um 4 --threads 4
& $AdsPython tools/run_afs.py solve "$Run/afs-m4" --ads-root $AdsRoot
```

`run_afs.prepare` validates the observed native r2 profile: 5--200 GHz, forced
10/20/40/65/80/100 GHz, `AFS S_50 MAXSAMPLES 54 SAMPLING ALL NORMAL`. `S_50` is the
native response selector, not an output-point count. The tool retains the
initial exact-plan preparation and the explicit AFS amendment.

## Keep actual solves and the dense AFS model distinct

The AFS exporter preserves complete matrices and original frequency arrays:

| Artifact | Meaning |
| --- | --- |
| `raw_MomMW.ds`, `proj.sio`, `raw-discrete.s2p` | Actually solved EM samples, including forced frequencies. |
| `raw_MomMW_a.ds`, `dense-afs.s2p` | ADS rational-model dense output; derived samples require independent validation. |
| `afs-model-receipt.json` | Dataset identities, actual/derived grids, missing display points and warning observations. |

Inspect both datasets for passivity and reciprocity and inspect all AFS
convergence/coverage warnings. Require the adopted dense spacing, including
exact boundary data: at most 1 GHz through 100 GHz and at most 5 GHz through
200 GHz. A dense curve or a missing-warning observation does not prove
continuous-band accuracy. No tool-generated resampling, passivity repair or
extrapolation is a substitute for the declared evidence.

The executed r2 native dense grid has four 1.25 GHz gaps between 35 and 40 GHz.
The qualification planner retains the original actual/dense grids and schedules
independent actual solves at 35.625, 36.875, 38.125 and 39.375 GHz. Its general
coverage-fill rule splits original union intervals equally using
`ceil(width/limit)`, with a 1 GHz limit through 100 GHz and a 5 GHz limit above
100 GHz, and requires an actual 100 GHz boundary. Planned points provide no
evidence until solved and compared. The native model is not resampled or fitted.

## Run the qualification suite and physical sensitivities

Generate controls from the completed 4 um AFS baseline:

```powershell
& $AdsPython tools/run_qualification.py plan "$Run/afs-m4" `
  --output "$Run/qualification-plan.json"
& $AdsPython tools/run_qualification.py prepare "$Run/qualification-plan.json" `
  "$Run/qualification" --ads-root $AdsRoot --native-workspace $NativeWorkspace --threads 4
& $AdsPython tools/run_qualification.py execute "$Run/qualification" --ads-root $AdsRoot `
  --native-ten-digit-realization
```

The plan selects at least seven midpoints of the largest actual-AFS sampling
gaps, including at least three in 10--65 GHz; this selection depends on gaps,
not target margins. It tracks actual and dense-predicted extrema and adds
independent actual solves at required boundaries and extrema. Its cases are:

| Case | Role |
| --- | --- |
| `a4` | Independent actual controls for AFS, including every frequency required by the finer mesh comparison. |
| `m3` | 3 um mesh control against actual 4 um controls at identical frequencies. |
| `lf4` | Actual 0.01/0.1/1/2/3/4/5 GHz probes, separate from DC. |
| `pplus2`, `pminus2`, `gplus10` | Transverse signal/reference contact shifts proven to remain on the original conductor, with unchanged signal reference-plane y coordinates. |

Contact controls are included by default; omitting them leaves that evidence
open. AFS limits are max absolute complex-S error 0.0001, relative L 0.002 and
relative Q 0.01. Mesh limits are relative L 0.02 and relative Q 0.05. The suite
separates application controls through 80 GHz from diagnostics above 80 GHz,
retaining both outcomes. Its completion receipt does not declare a physical
device PASS or establish continuous coverage by itself.

The example explicitly opts in to the observed native frequency-coordinate
realization; the default remains the original strict export policy. The Python
API is `execute_controls(suite_dir, native_ten_digit_realization=True)`.
Before each new solve, `native-frequency-realization-policy.json` records the
unchanged requested frequencies, planned `float(format(requested_hz, '.10g'))`
coordinates and protected exact points. Export accepts only exact equality to
that native realization and retains `native-frequency-realization.json` with
requested/actual/canonical arrays, deviations and source identities. The raw
model receipt records both requested and actual coordinates.

In the executed `a4` control, requested frequencies 116666666650, 141666666650
and 166666666650 Hz were stored 50 Hz lower by the native dataset; the other
18 frequencies, including exactly 65 and 80 GHz, were unchanged. The opt-in
does not alter the stimulus, prepared receipt, midpoint requests, raw dataset,
electrical limits or comparison tolerances, and performs no interpolation.
Retain the original incomplete export/control attempt. Existing attempted
cases are not re-executed or relabelled by this option. To export a completed
case separately, use `run_momentum.export_dataset(case_dir,
native_ten_digit_realization=True)` or `tools/run_momentum.py export <CASE>
--native-ten-digit-realization` in the ADS Python runtime.

The suite does not replace finite-return or independent reproduction work.
Build fresh cells at frame factors 1.5 and 2.2, retaining D/w/gap/leads and
signal planes; configure and export them natively using the same process.
Validate their inputs with `--sensitivity --frame-factor <FACTOR>` and compare
actual matrices with `compare_networks.py --profile return`. Contact and return
profiles report observed changes without inventing acceptance thresholds.
Include those changes conservatively in the uncertainty review.

Rebuild/re-export the selected nominal candidate independently and solve exact
frequencies required by the research contract, including 65/80 GHz. Compare
all complete matrices with `--profile reproduction --physics-revision
passive-loss-r1`. The frozen limits are absolute complex-S error 0.00001 and
relative L 0.002; Q is reported. Reusing the same prepared inputs alone does
not demonstrate independent regeneration of the native candidate.

## Establish DC/LF support and assemble the complete model

Run the independent finite-conductivity sheet calculation on actual exported
geometry, with the declared feed-end contact model and grid refinement:

```powershell
& $AdsPython tools/dc_resistance.py --input-dir $NativeExport --output-dir "$Run/dc" `
  --construction-receipt $Construction --grids-um 0.5 0.25 0.125 0.0625 --contact-width-um 10
& $AdsPython tools/dc_fem.py --input-dir $NativeExport --output-dir "$Run/dc-fem" `
  --grids-um 0.5 0.25 0.125
```

The finer 0.0625 um finite-volume calculation shows that the earlier 0.125 um
finite-volume estimate was not converged. The independent conforming FEM uses
the unchanged geometry, material and full 10 um equipotential end-face contacts,
with insulating side boundaries. Its 0.5/0.25/0.125 um study gives a finest
resistance of about 0.624486745 ohm and a last refinement change of about
0.0000914 ohm. This observed refinement difference is not a rigorous continuum
error bound, and RF/DC excitation agreement remains unestablished. Neither
estimate establishes final device qualification. Do not add a DC anchor to
the current nominal model.

Review its convergence, contact assumptions and contribution of the return
under the declared Icm=0 excitation. Compare against the actual LF probes;
none of those positive-frequency probes is a DC EM solve. A derived DC anchor
is optional and requires explicit DC/LF agreement, consistent planes and a
reviewed contact model. `combine_models.py --include-dc` additionally requires
`--dc-resistance-json` and `--lf-agreement-json`; inspect its checked agreement
fields before preparing that operator evidence. Keep the derived DC endpoint
distinct from actual RF samples and justify the low-frequency inductive limit
separately.

After the pending direct fallback completes, validate its fullwave logs,
complete matrix, ports, material and source identity before nominal assembly.
The frozen frequency list can be replayed without editing it:

```powershell
$DirectFrequencies = (Get-Content inputs/high-frequency-direct-fallback-r1.json -Raw | ConvertFrom-Json).direct_frequency_GHz
& $AdsPython tools/run_momentum.py prepare $SelectedExport "$Run/high-frequency-direct" `
  --ads-root $AdsRoot --native-workspace $NativeWorkspace --mesh-um 4 `
  --frequency-ghz $DirectFrequencies --threads 4
& $AdsPython tools/run_momentum.py solve "$Run/high-frequency-direct" --ads-root $AdsRoot
```

Select only unchanged original native dense rows in 5--80 GHz into a fresh
`dense-afs-5-to-80.s2p`. Retain a separate `source-domain-selection.json` with
the original dataset/export identity, retained source-row indices, original
frequencies and selected file identity. This is domain selection, with every
selected complete matrix unchanged; it is not interpolation, resampling or a
claim that the rejected higher-frequency AFS segment passed. Preserve the
complete original `dense-afs.s2p` and its failed diagnostic comparisons.

Combine that selected derived segment with all nominal actual segments and
one assembly receipt. Do not run this example until the selected segment,
direct fallback and their receipts exist:

```powershell
& $AdsPython tools/combine_models.py `
  --segment actual "$Run/afs-m4/raw-discrete.s2p" `
  --segment actual "$Run/qualification/a4/raw.s2p" `
  --segment actual "$Run/qualification/lf4/raw.s2p" `
  --segment actual "$Run/high-frequency-direct/raw.s2p" `
  --segment AFS-derived "$Run/dense-afs-5-to-80.s2p" `
  --physics-revision passive-loss-r1 --output "$Run/model.s2p" `
  --receipt "$Run/model-assembly.json"
```

The assembler retains every complete matrix and per-point source; actual
samples take precedence at overlaps, inconsistent actual overlaps are refused,
and no interpolation/fitting is performed. Do not include mesh/contact/return
variant networks in the nominal model. Review source input validations before
declaring the common physics revision; that declaration alone does not validate
materials or geometry.

Use the [model-use contract](../inputs/model-use-contract-r1.json) when consuming
the file: explicitly select linear interpolation of complex S in rectangular
coordinates (`InterpMode="linear"`, `InterpDom="ri"`). An RI Touchstone header
does not select that ADS interpolation domain by itself. No extrapolation or
passivity enforcement is authorized. Preserve the same P1/P2/P4 convention and
the complete finite-return network.

Follow the [standalone S2P consumer control](s2p-roundtrip.md) and its
[adopted protocol](../inputs/consumer-roundtrip-protocol-r1.json). Native ADS
consumption at exactly 10/65/80 GHz has actually passed that RF comparison;
this is consumer interoperability evidence, separate from physical device
qualification. A fresh assembled model needs its own source-linked control:

```powershell
& $AdsPython tools/validate_s2p_roundtrip.py --model "$Run/model.s2p" `
  --assembly-receipt "$Run/model-assembly.json" --output-dir "$Run/consumer-rf" `
  --max-absolute-s-error 1e-8 --max-absolute-zd-error-ohm 0.0001
```

The current model has no supported DC anchor; omit `--require-dc-anchor`.
The existing RF consumer result does not establish 0--10 MHz consumer behavior,
RF/DC agreement, continuous-band accuracy or parent-filter acceptance.

## Analyze with explicit provenance and uncertainty

Use the current [analyzer interface](../tools/analyze_em.py). Final qualification
requires both the exact model's assembly receipt and the explicit adopted
protocol. An invocation without the protocol is characterization only.

```powershell
& $AdsPython tools/analyze_em.py "$Run/model.s2p" --output-dir "$Run/analysis" `
  --assembly-receipt "$Run/model-assembly.json" `
  --protocol inputs/numerical-protocol-amendment-r2.json `
  --uncertainty-json "$Run/uncertainty.json"
```

Prepare `uncertainty.json` from the completed controls, not example truth
flags. The current source interface requires:

- `physics_revision: "passive-loss-r1"` in both assembly and operator evidence.
- `L_absolute_pH` conservatively including observed numerical sensitivities and
  the protocol's 0.005 times 120 pH interpolation reserve.
- Evidence-backed `checks` for mesh, port, boundary, material, dc_low_frequency,
  reproduction and afs, plus justified `coverage_10_65` and
  `coverage_through_80`. Missing checks remain open.
- `reactance_frequency_envelope` with
  `validation_kind: "actual-control-comparisons"`,
  `interpolation_rule: "interval-max-equivalent-L"`, ordered actual control
  `points` containing `frequency_hz`, `direct_X_absolute_ohm` and
  `L_absolute_pH`, and retained `evidence_files`.
- `low_frequency_limit` with `status: "SUPPORTED_BY_DC_AND_ACTUAL_LF"`, the
  actual `first_actual_frequency_hz`, justified `inductive_limit_positive`,
  and retained `evidence_files`.

Evidence paths resolve relative to the operator JSON. The frequency envelope
uses the larger equivalent-L error at each validated interval's endpoints and
scales it as deltaX(f) = 2*pi*f*deltaL. It includes the global L bound, makes
no extrapolation outside the actual-control domain, and does not infer
manufacturing uncertainty. Do not also supply the legacy uniform
`reactance_absolute_ohm` when using this envelope. DC and the interval below
the first RF point require their separate supported-limit evidence.

The analyzer checks the complete matrix for passivity and reciprocity and
evaluates the constrained-current terminal impedance
`Zd = Z11 + Z22 - Z12 - Z21` with `I1=I`, `I2=-I` and `Icm=0`. Signed terminal
`L=Im(Zd)/(2*pi*f)` and `Q=Im(Zd)/Re(Zd)` retain their physical reference planes.
The numerical implementation solves the observable without arbitrary matrix
regularization. Retain raw networks, reported conditioning/gaps, Q/R values,
crossings, extrema, plots and all source receipts.

Read the resulting study completion, device result, model readiness and parent
acceptance separately. Missing convergence, source, interval, uncertainty or
physical checks require an incomplete/indeterminate conclusion. A qualified
single-device assumed-stack model would still need a separate parent-stack
compatibility review and full LPF verification before integration acceptance.
