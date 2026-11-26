# Execution record

Run records, preflight observations, netlists, raw data and measurements live
under `results/<run-id>/` and are deliberately kept out of git: that tree holds
machine-specific observations and large native data. This file records the
decisions and chronology that belong with the workspace manifest.

## WP0 Phase A preflight — 2026-11-25

- Run: `results/20261125T081633Z-wp0-native-smoke`; preflight: `preflight.json` (status ready, awaiting root review).
- Frozen contract verified 28/28 files locally and 28/28 on the selected Linux host.
- Remote root verified for real path, owner and mode (exact values kept in the private binding); the directory already existed and was not duplicated.
- Live Virtuoso PID 8859, IC25.1-64b, working directory aligned to the workspace, forced library empty.
- analogLib ideal devices verified: `ind` (l, no loss term), `cap` (c), `port` (r=50, num), `gnd` (`gnd!`); `si` netlister present; license environment recorded (checkout not yet tested).
- 22 workspace files transferred through eda-lab with receiver rehash: 0 mismatches.

## WP0 Phase B toolchain smoke — 2026-11-25

- Run sealed `completed`. Built `VLPF_R01_lib` with `VLPF_Smoke` (100 pH series L,
  100 fF shunt C) and `VLPF_SmokeTB`; the DUT symbol was generated natively with
  `schPinListToSymbol`.
- `si` produced the deck from the saved bench; two generations were byte
  identical. Two Spectre SP runs went through the product MCP `simulate`, and all
  four complex S entries were read from the native PSF.
- WP0 ABCD check passed at 4.17e-16 maximum absolute complex error; the repeat
  differed by 0.0.
- Decision: `si` cannot be driven netlist-only on this installation (`-command
  netlist` exits without a deck), so netlist generation restricts `PATH` to the
  dfII and system directories. The simulator is then absent and no solver job is
  started. Recorded in `results/20261125T081633Z-wp0-native-smoke/native-source/REPLAY.md`.
- Decision: the library is registered inside a `ddSetForcedLib` scope pointing at
  a task-owned session `cds.lib`, restored with `unwindProtect` and verified
  afterwards. The default `cds.lib` would have dropped an unrelated library that
  still had an open view.

## WP1 fixed-baseline reproduction — 2026-11-25

- Run `results/20261125T101303Z-wp1-baseline-reproduction`, sealed `completed`.
- Rebuilt the disclosed nine-pole ladder as `VLPF_Main` using the
  `inputs/baseline/schematic.net` literals. The consumed netlist reproduced every
  element literal exactly; worst absolute delta 0.0.
- Spectre matched the frozen ADS reference to 2.335e-15 across 3796 frequencies
  and all four S entries, and the independent ABCD cascade to 7.372e-13.
- H1 -21.000 dB at 49.7929 GHz, H2 -21.000 dB at 11.2871 GHz, H3 0.0346 dB at
  65 GHz, H4 -25.164 dB at 80 GHz, second capture at exactly 80 GHz.
- Repeat: byte-identical deck, complex S difference 0.0.

## WP2 same-spec design — 2026-11-25

- Run `results/20261125T103838Z-wp2-same-spec-design`, sealed `completed`,
  kind `design`.
- The operator profile moved to `kind = "design"` before this run was frozen, as
  the task contract requires before WP2. Sealed WP0 and WP1 runs keep their own
  frozen copies of the earlier profile.
- Candidate `VLPF_C11`: Chebyshev-1 ladder, order 11, 24 dB passband return loss.
  Even orders were rejected analytically rather than by trial: the
  equal-termination prototype table is not valid for even order, and an order-10
  / 22 dB evaluation gave a maximum S11 of -16.13 dB.
- Spectre matched the independent ABCD cascade to 5.870e-12. Coverage used 4076
  samples with 20 MHz passband spacing, exact 65 and 80 GHz, and local refinement
  of all six reflection extrema; the sampled passband maximum stayed within
  0.0004 dB of the analytic Chebyshev bound.
- H1 -24.000 dB at 42.566 GHz, H2 -24.000 dB at 62.367 GHz, H3 0.0173 dB at
  65 GHz, H4 -33.721 dB at 80 GHz.
- Repeat: byte-identical deck, complex S difference 0.0.
- `project.toml` `dut_cell` moved to `VLPF_C11`; the WP1 run keeps its own
  `VLPF_Main` selection.

## Open items

- Every result above is an ideal LC result. PDK, finite Q, parasitics, layout, EM
  and PVT remain outside this task's contract.
- The task has no registered official verifier; the comparisons used the frozen
  task tools and run-local checkers.
