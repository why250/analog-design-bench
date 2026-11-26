# ADS library, cell and view naming convention

This convention applies to **new** task-owned ADS engineering workspaces and
new revisions. Existing workspaces keep their names until a separate migration
is scoped; they are grandfathered by the validator.

The goal is that a library, cell or view name alone answers three questions:
which task revision it belongs to, what role it plays, and whether it is an
authoritative source or an experiment.

## One workspace, several role libraries

A task owns one stable workspace root, `workspaces/<task-id>/`, with one primary
native ADS project under `ads/<short-name>_wrk`. Inside that project, use
several role libraries instead of one mixed library:

| Library pattern | Role | Cell rule |
| --- | --- | --- |
| `<BLOCK>_R<NN>_lib` | Authoritative DUT, symbol and layout | Cells start with `<BLOCK>_` |
| `<BLOCK>_R<NN>_tb_lib` | Testbenches only | `TB_<DUT_CELL>_<SIM>[_<PURPOSE>]` |
| `<BLOCK>_R<NN>_pcell_lib` | Task-owned writable PCell copies | Mirrors the source PCell names |
| `<BLOCK>_R<NN>_em_lib` | EM extraction fixtures and derived structures | `EM_<DEVICE>_<GEOMETRY>` |
| `<BLOCK>_R<NN>_aux_lib` | Ideal, auxiliary and exploratory cells | `AUX_<NAME>` |

Create only the roles the task actually uses, but when a role library exists,
follow its row.

## Grammar

```text
<BLOCK>_R<NN>[_<ROLE>]_lib
<ROLE_TAG>_<BLOCK>_<NAME>[_<CANDIDATE>][_<SIM>][_<PURPOSE>]
```

- `<BLOCK>`: uppercase block key, `[A-Z][A-Z0-9]{0,15}`, for example `LPF`,
  `LNA`, `DEC`.
- `<NN>`: two-digit task revision, equal to `project.revision` in
  `project.toml` and `task.toml`. `R01` is revision 1, never a design
  iteration.
- `<ROLE>`: empty for the DUT library, otherwise `tb`, `pcell`, `em` or `aux`.
- `<ROLE_TAG>`: `TB`, `EM` or `AUX`. DUT cells have no role tag; they start
  with `<BLOCK>_`.
- `<SIM>`: one of `SP`, `HB`, `TRAN`, `AC`, `DC`, `EM`.
- `<PURPOSE>`: optional uppercase token such as `DENSE`, `CHECKPOINT`, `MC`.
- `<CANDIDATE>`: optional `_C<NN>` design-candidate suffix; the selected
  candidate is recorded in the run's `run.json` and linked from the execution
  record, never renamed. `project.toml` retains the static DUT declaration;
  dynamic candidate selection does not add execution state to it.

## Revisions versus design iterations

`R<NN>` in the library is a **contract revision** boundary:

- Create a new library only when `task.toml` gets a new revision.
- Keep the previous library and its evidence unchanged.
- Within one revision, name design candidates `<BLOCK>_<NAME>_C01`, `_C02`,
  and so on. Do not create `R02`, `V2`, `new` or `final` libraries for
  candidate iterations.
- Never reuse a consumed revision number or candidate number.

## Testbench naming

A testbench is named for the DUT cell it instantiates:

```text
TB_<DUT_CELL>_<SIM>[_<PURPOSE>]
```

Examples:

- `TB_LPF_Series_First_SP`
- `TB_LPF_Series_First_SP_DENSE`
- `TB_LPF_Series_First_HB`

Rules:

- The testbench library contains testbenches only: sources, terminations,
  controllers, display templates and bench-owned wiring.
- The DUT, its symbol and its layout stay in the DUT library.
- For each analysis type there should be one authoritative bench. Variants
  add a purpose token.
- The testbench cell's name must resolve to an existing DUT cell in the same
  revision's DUT library. The validator checks this when the libraries exist
  on disk.

## Views

Authoritative view names are the ADS-native ones:

```text
schematic  symbol  layout  emSetup  emModel  emModel_mw
```

- Each cell has at most one authoritative `schematic`.
- Derived or experimental views must start with `x_`, for example
  `x_schematic_m1` or `x_emModel_tense`, and must be listed in the workspace
  README with a one-line purpose.
- Do not use `_v1`, `_new`, `_final`, `_copy`, bare `_m1` or similar suffixes
  for an authoritative view.
- A new design candidate is a new cell, not an overloaded view.

## Ports and parameters

- DUT terminals use functional lowercase names: `rf_in`, `rf_out`, `gnd`,
  `vdd`, `bias_*`. The ordered port list is declared in
  `project.toml` under `[design] dut_ports`.
- Parameter names are lowercase `snake_case` without embedded units. Values
  carry units, for example `inner_diameter=25 um`. Do not rename existing PDK
  PCell parameters.

## Vendored PDK libraries

A byte-for-byte copy of a PDK library may keep its original name, because
schematic instances reference it by that name. Declare each such library in
`project.toml`:

```toml
[design]
block_key = "LPF"
dut_lib = "LPF_R01_lib"
dut_cell = "LPF_Series_First"
dut_ports = ["rf_in", "rf_out"]
vendored_libs = ["example_pcells_lib"]
```

Vendored libraries are exempt from the task prefix but still must be
task-local (under the workspace) and are not modified in the source
installation.

## Cross-workspace reuse

Short library names are workspace-local. Do not link a task-owned library into
another workspace under the same short name. If a library must be shared
across workspaces, give it a globally unique task-qualified name, for example
`INP65_LPF_R01_lib`, and record the link in the ignored
`.local/ads-projects/<task-id>.json` binding. Read-only PDK libraries keep
their installation names.

## Declaration and enforcement

New schema v2 workspaces declare the naming root in `project.toml`:

```toml
[design]
block_key = "LPF"
dut_lib = "LPF_R01_lib"
dut_cell = "LPF_Series_First"
dut_ports = ["rf_in", "rf_out"]
```

Initialize with:

```powershell
python scripts/ads_workspace.py init --task-id <task-id> --stage <stage> `
  --block-key LPF --dut-lib LPF_R01_lib --dut-cell LPF_Series_First `
  --dut-ports rf_in,rf_out --create-task --with-tools --with-tests
```

`python scripts/ads_workspace.py validate --workspace workspaces/<task-id>`
then checks, when the native project exists:

- task-local library names match the declared block and revision;
- DUT cells start with `<BLOCK>_`;
- testbench cells match `TB_<DUT_CELL>_<SIM>[_<PURPOSE>]` and name an existing
  DUT cell;
- EM and auxiliary cells use their role prefixes;
- the declared DUT cell exists and has `schematic` and `symbol` views;
- non-standard views are reported as warnings and should use the `x_` prefix.

If `block_key` is absent, naming checks are skipped with a warning so legacy
workspaces continue to validate.

## Migration

Do not rename a completed task's libraries or cells to adopt this convention;
that would break evidence links. Adopt it for the next new task or the next
contract revision, and record any migration as its own scoped change with
before/after hashes.
