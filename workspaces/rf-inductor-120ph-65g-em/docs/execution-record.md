# Single-device execution record

The revision-1 research contract is frozen in
[research-contract-r1.json](../inputs/research-contract-r1.json) before candidate
EM runs. The user's execution instruction permits adopting the initial research
limits and an explicitly assumed on-chip stack. The follow-up request selects
RFIC Inductor Toolkit for automatic design.

The selected path uses Toolkit Open 2.3.1 diameter synthesis and single-turn
artwork, followed by task-owned full-wave Momentum simulations. Its stock
low-frequency calibration is a prediction and cannot establish acceptance.
The open example stack is an assumed research platform, with a finite conducting
return frame and open backside replacing its perfect infinite ground.

The native project and copied open dependencies belong to this workspace.
Construction uses an independent automation session. Classic EM export requires
an application session; it opens task libraries read only without switching the
active workspace or adding them to that workspace's library definitions. Source
preservation receipts accompany export. The installed toolkit is read only;
stock synthesis commands that modify its templates are excluded. Copyright and
permission notices accompany copied dependencies.

Initial candidates use one turn and widths of 4, 8 and 12 micrometres. At a
2 micrometre gap the toolkit predicts diameters of approximately 33.51, 44.38
and 53.83 micrometres for 120 pH. Wider metal lowers conductor resistance but
requires a larger loop, which increases substrate loading and footprint.
These predictions precede EM and are retained even if inaccurate.

Raw complex networks, solver logs, input snapshots and failed attempts belong
below fresh UTC directories in `results/`. No full LPF acceptance or InP device
qualification follows from this study.

## Initial actual EM observations

**Invalidated material realization.** The following historical EM observations
used positive direct imaginary permittivity. ADS requires a negative direct
imaginary part for the intended positive passive loss tangent. These values
remain historical evidence and are not device performance or acceptance data.

Run `20261028T070547Z-toolkit-em-r1` retains initial sources, failed launches,
exported inputs and solver logs. The first 33.513 micrometre diameter,
4 micrometre width candidate retains the stock center tap. Full-wave solves
at exact 65 and 80 GHz yielded approximately 41.95 and 42.16 pH, with signed
terminal Q of 15.39 and 17.96. These numbers describe only the invalid material
realization. They establish neither PASS nor FAIL for the physical candidate;
the corrected passive realization requires new EM results and qualification.

The stock toolkit diameter calibration needs EM feedback for the changed stack
and return environment. The next candidates use its diameter synthesis with a
higher synthesis input while retaining the physical 120 pH target. They use the
supported no-center-tap artwork option. The copied PCell calls
`mi_octa_singleturn` with center-tap and stacked-metal options disabled. The
complete model then has two signal ports referenced to the finite frame.

## Runtime and input reconciliation

The classic exporter is unavailable in the tested independent headless session;
its documented AEL call works in application mode. A setup folder with an
unescaped capital letter is discovered as native view `emsetup`; the builder
uses that actual view name when exporting.

The exported default `SimulationMode 2` selects RF mode even when the wrapper
receives `--objMode=MW`. Acceptance inputs explicitly select `SimulationMode 1`,
and actual logs must state `Simulation Mode: uW`. The first RF diagnostic is
retained separately. Its material/port warnings exclude it from acceptance.

Native mesh-unit and cached oxide defaults are reconciled in fresh solver input
copies before solving. Retain original exports and amendment receipts; verify
the cell dimension in micrometres, frozen oxide permittivity and loss, physical
port references and task-owned output directories. No limit is changed.

One concurrent substrate-generation attempt failed with a substrate-directory
write message. Its evidence is retained; subsequent substrate cache generation
is serialized. A solver launch or zero exit status alone does not establish PASS.

## Passive-material realization correction

The intended dielectric loss tangent remains positive 0.005. The initial direct
imaginary-permittivity encoding had the wrong sign. The ADS 2027 User Guide's
Material Definitions section explicitly defines the passive direct imaginary
part as minus the positive loss tangent times the real permittivity.

The initial run is marked INVALID for passive EM acceptance, preserving all
inputs, predictions, launches and raw results. A fresh run,
`20261028T092348Z-passive-loss-r1`, uses the corrected negative direct imaginary
parts and repeats the required electrical and numerical work. Geometry and
conductor-only DC calculations may inform predictions but do not rescue the
invalid EM results. No electrical target or numerical tolerance is relaxed.

The [expanded-stack record](../inputs/effective-stack-r1.json) retains the old
interpretation separately and describes the corrected passive realization.
Before accepting any compressed-stack result, compare corrected full and
compressed representations under the same material signs, active conductor
heights, physical ports and declared control tolerances.

## Current disposition

Status recorded at **2026-10-28 09:40:42 UTC**. The corrected passive run
`20261028T092348Z-passive-loss-r1` is awaiting the required validation. This
snapshot does not treat the existence of a corrected source or a solver launch
as completed qualification.

| Conclusion | Current state | Basis |
| --- | --- | --- |
| Study completion | INCOMPLETE | Geometry, automation and retained historical evidence exist; the corrected passive design and model qualification remain open. |
| Device target result | INDETERMINATE | The initial positive-imaginary EM evidence is INVALID and cannot establish PASS or FAIL. The corrected passive realization must meet the unchanged research criteria with qualified evidence. |
| Network integration readiness | NOT READY | A corrected complete complex network still requires the declared mesh, port, boundary, frequency, low-frequency/DC and independent-reproduction evidence. Earlier invalid networks are retained for diagnosis. |
| Parent LPF acceptance | NOT EVALUATED | This task authorizes one device. A later parent integration must check physical compatibility and the original full-filter limits. |

The selected platform remains an explicitly assumed on-chip research stack.
No foundry qualification, qualified InP device or passing full LPF is claimed.
