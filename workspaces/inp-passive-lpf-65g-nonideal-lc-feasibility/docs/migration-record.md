# Engineering layout migration record

Completed on 2026-10-28 for
`inp-passive-lpf-65g-nonideal-lc-feasibility-r1`. This records the engineering
directory migration and its validation. The completed study remains
[`stage2-20261027T113222Z`](../results/stage2-20261027T113222Z/report.md), with
219 unique circuits, 55 device validations and three original E9 reproductions.
Its electrical conclusions and official benchmark status are unchanged.

## Stable ownership

Both hosts now use the same relative project root:

```text
workspaces/inp-passive-lpf-65g-nonideal-lc-feasibility/
  project.toml
  ads/inp_lpf_nonideal_wrk/
  tools/
  tests/
  inputs/baseline-r2/
  inputs/task-spec/
  docs/
  results/<run-id>/
```

`project.toml` owns the task identity and portable relative paths. The active
ADS source uses `ads/inp_lpf_nonideal_wrk/`; its library and DUT/symbol/bench
cell identities remain unchanged. The canonical native anchor-B design opens
with the same generated electrical netlist.

Stage 1 retains its original engineering roots. Stage 2's active imports now
resolve its own `tools/ads_support.py`. The minimal frozen baseline helper
source is under `inputs/baseline-r2/tools/`, with selected inputs, upstream
commit and file hashes retained beside it. Reconstruction no longer depends on
the location of a live Stage 1 tools directory.

## Preserved evidence

Completed run files were relocated with their internal relative paths and bytes
intact. Source/destination inventories were checked independently on each host
by relative path, byte size and SHA-256. Host totals differ because each host
retained its own receipts and staging material; cross-host totals were not
used as a substitute for those per-host comparisons.

Original archives and transfer/recheck receipts now belong under the run's
`handoff/original/` directory. Both original ZIP files passed integrity checks
and retain their original bytes:

| Original archive | Verification |
| --- | --- |
| [Full study](../results/stage2-20261027T113222Z/handoff/original/stage2-20261027T113222Z-full-study-20261028T024844Z-5af7b7a4.zip) | Passed; original ZIP unchanged |
| [Selected handoff](../results/stage2-20261027T113222Z/handoff/original/stage2-20261027T113222Z-selected-handoff-20261028T024844Z-5af7b7a4.zip) | Passed; original ZIP unchanged |

Detailed machine-readable integrity records and transfer/recheck receipts remain
in the [original handoff records](../results/stage2-20261027T113222Z/handoff/original/).

The timestamp-named staging project and retired source were removed from the
active engineering roots after verification. Their historical material remains
in ignored migration storage. Private absolute path mappings and inventory
receipts are retained in repository `.local/` records.

## Validation after relocation

The normalized task suite passed **28 tests**. The frozen ideal baseline suite
passed **7 tests**. A fresh
[layout-validation run](../results/layout-validation-20261028T032828Z/validation-summary.json),
`layout-validation-20261028T032828Z`, rebuilt E0 and anchor B through the new
project layout:

| Case | Electrical state | Maximum frequency difference | Maximum complex-S difference | Generated netlist |
| --- | --- | ---: | ---: | --- |
| E0 | PASS | 0 Hz | 0 | Exact byte identity |
| Anchor B | FAIL | 0 Hz | 0 | Exact byte identity |

This layout-validation record is separate from the original completed study.
The migration changed directory ownership and path resolution; it did not
alter component coefficients, electrical limits, the retained stage decision
or an official score. The original study remains **COMPLETE**, with the primary
decision **TOPOLOGY REVIEW REQUIRED** under its declared synthetic RLC scope.

Read the [project entrypoint](../README.md),
[original execution record](execution-record.md) and shared
[engineering layout contract](../../../docs/engineering-workspace-layout.md)
for current paths, commands and retention rules.
