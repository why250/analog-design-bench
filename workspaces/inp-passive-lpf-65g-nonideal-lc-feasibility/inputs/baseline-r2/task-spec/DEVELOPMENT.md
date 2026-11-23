# InP 65 GHz passive LPF — ideal-design task development (revision 2)

**Status: first ideal ADS schematic milestone completed / engineering verification passed / unregistered.** A reproducible nine-pole Chebyshev-I ideal LC design, native ADS workspace and retained simulation evidence are available in the [design workspace](../../workspaces/inp-lpf/README.md). This is revision-2 engineering verification; an official independent benchmark verifier and official reference acceptance remain unimplemented. Follow [Task development](../../docs/task-development.md).

## Design contract confirmed by the user

- Single-ended, passive, reciprocal two-port LPF intended for future InP on-chip use, with **50 Ω external input and output ports**.
- **DC–65 GHz inclusive passband**: \`dB(S11) < -20 dB\` and \`dB(S22) < -20 dB\` at every passband frequency.
- **DC–65 GHz passband insertion loss < 1 dB** (equivalently \`dB(S21) > -1 dB\`), also across the full band.
- **At 80 GHz only**, \`dB(S21) <= -20 dB\`. **No continuous stopband requirement** is specified.
- **Current stage:** ideal **L/C** in ADS, no real-device layout, EM, PDK components, finite passive Q, corner or silicon measurement verification.
- Filter order, LC topology and exact element values were design variables. The completed baseline uses a nine-pole Chebyshev-I ladder with five series inductors and four shunt capacitors. Its retained ADS results verify the selected values; earlier exploratory candidates remain unverified. Ideal TLIN comparison remains optional.

These hard thresholds and the deliberate **ideal-only design scope** are what changed from revision 1 to revision **2**. The task ID remains unchanged because the design objective is the same; revision 1 results must not be silently relabelled as revision 2.

## Lifecycle status and immediate milestone

| Stage | Current state | Exit condition |
| --- | --- | --- |
| Define | **Completed: revision 2 contract** | Pass/fail semantics, 50 Ω ports, ideal models and stage scope confirmed |
| Establish ideal tests | **Completed: executable engineering bench and analysis** | Exact 65/80 GHz samples, full-band sampling, analytic extrema refinement and result export retained |
| Design ideal topology | **Completed: nine-pole Chebyshev-I LC ladder** | Native ADS DUT, symbol, external-port testbench, synthesis and parameter table saved |
| Ideal simulation and iterate | **Completed: all four electrical checks passed** | 3796 unique ADS frequency samples and an independent ABCD cross-check retained |
| Freeze ideal milestone | **Completed: baseline and fresh-workspace reproduction retained** | Native workspace, raw dataset, source snapshots, exports, plots, settings and metric summary saved; repeated S data and netlist identical |
| Physical InP implementation | **Explicitly postponed** | Requires new, separately approved stage/revision with PDK and EM |
| Official runnable benchmark | **Not registered** | Verified starter/bench/verifier/reference, source hashes, isolated runtime, reviewed release decision |

## Completed ideal milestone evidence

The [workspace README](../../workspaces/inp-lpf/README.md) documents the topology,
component values, synthesis, sweep settings, native workspace and reproduction
commands. The saved ADS workspace is `workspaces/inp-lpf/ads/inp_lpf_wrk`.
The baseline evidence is retained under
`workspaces/inp-lpf/results/baseline-20261027/`, ignored by Git.

| Electrical check | Baseline ADS result | Requirement | Result |
| --- | ---: | --- | --- |
| Worst passband dB(S11) | -21.000000 dB | < -20 dB | PASS |
| Worst passband dB(S22) | -21.000000 dB | < -20 dB | PASS |
| Maximum passband insertion loss | 0.0346349774555 dB | < 1 dB | PASS |
| dB(S21) at exactly 80 GHz | -25.1637752971 dB | <= -20 dB | PASS |

The 3796 unique positive-frequency samples include exact 65 and 80 GHz points
and all five analytic passband reflection maxima with local refinement. The
Chebyshev response bounds the entire ideal passband; the low-frequency limit
and DC-through topology are recorded without claiming a zero-Hz S-parameter
simulation. Worst-case frequencies and full-precision values are in the retained
summary and report. The maximum absolute complex ADS-versus-ABCD difference is
`7.24065e-13`.

Retained evidence includes the native ADS `.ds` dataset, simulator log, generated
netlist, native schematic PDF, complex CSV and Touchstone exports, plots,
`summary.json`, `settings.json` and source-input snapshots. A fresh-workspace
rebuild reproduced identical frequency samples, complex S data and netlist;
seven numerical and failure-rejection tests passed. Run-specific software
versions and settings remain with the evidence. These results establish the
ideal engineering milestone only; they are not an official benchmark score or
a physical InP feasibility result.

## Package and workflow boundaries

- \`instruction.md\` is the intended public design brief; \`verification-plan.md\` defines the operator measurement protocol. Executable engineering setup and analysis are provided in the linked workspace; there is still **no official independent benchmark verifier**.
- \`task.toml\` reserves the existing single-file \`/app/circuit.spi\` interface for a **future** official benchmark. Current hands-on deliverable is an **ADS ideal schematic/workspace**; there is no verified ADS-to-SPICE export path.
- \`checker_allow_ideal = ["L", "C"]\` reflects intended ideal SPICE elements **if** a checker is added. It is **not proof** that the current runner supports this task. Ideal TLIN remains an optional ADS-only comparison until a formal submission representation is specified.
- Do not create fake \`environment/\`, \`tests/\`, \`solution/\`, result scores or \`evaluation/design-contracts/\` source-hash records. Implement these against actual future assets if the work is promoted to a runnable benchmark.
- **Do not change \`tasks/benchmark.toml\`**: the current benchmark release is frozen. This development-only task is not registered in \`evaluation/tasks/\` and has no official score.
- No need to obtain/distribute proprietary company InP PDK, machine-local paths or foundry information to complete this milestone.

## First-milestone design acceptance checklist

- [x] 50 Ω source/load and passband defined.
- [x] 0–65 GHz S11 and S22 < −20 dB confirmed.
- [x] 0–65 GHz insertion loss < 1 dB confirmed.
- [x] 80 GHz S21 ≤ −20 dB confirmed; **no continuous stopband** requirement.
- [x] Ideal-only ADS schematic scope; no layout, EM or PDK in this revision.
- [x] Provide the initial ideal LC topology and parameter table.
- [x] Provide a runnable ADS ideal schematic/workspace and port wiring.
- [x] Save reproducible S-parameter sweep data covering the full passband and **exact** 65 and 80 GHz.
- [x] Record worst-case S11, S22, insertion loss and 80 GHz S21, with pass/fail decision.
- [x] Independently cross-check the ideal S-parameter results using synthesis/ABCD relations.
- [x] Freeze the ideal milestone evidence (not an official benchmark score).
- [x] Rebuild in a fresh workspace and reproduce identical S data and netlist.
- [x] Pass seven numerical and invalid/incomplete-evidence rejection tests.

See [verification-plan.md](verification-plan.md) for precise acceptance expressions
and the [workspace README](../../workspaces/inp-lpf/README.md) for the implemented
ADS procedure and retained evidence.
