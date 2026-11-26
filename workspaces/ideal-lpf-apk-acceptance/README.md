# ideal-lpf-apk-acceptance

Engineering workspace for `ideal-lpf-apk-acceptance-r1` (stage `ideal-lc-acceptance`).
Authoritative task contract: [tasks/ideal-lpf-apk-acceptance/instruction.md](../../tasks/ideal-lpf-apk-acceptance/instruction.md).

## Structure and design identity

- Manifest: [project.toml](project.toml) (`schema_version = 2`, `model_policy = "unrestricted-ideal"`)
- Primary ADS workspace: `ads/design_wrk`
- Selected DUT: `LPF_R01_lib:LPF_Ideal` with ordered ports `(rfin, rfout, gnd)`
- ADS naming: [convention](../../docs/ads-naming-convention.md)
- Execution log: [docs/execution-record.md](docs/execution-record.md)
- Run artifacts: `results/<YYYYMMDDTHHMMSSZ>-<slug>/` (gitignored)

## Source policy

Native ADS source under `ads/` uses unrestricted/ideal models and may be tracked without transient caches/locks.

## Validation and run allocation

```powershell
python scripts/ads_workspace.py validate --workspace workspaces/ideal-lpf-apk-acceptance
python scripts/ads_workspace.py new-run --workspace workspaces/ideal-lpf-apk-acceptance --slug nominal
```

<!-- engineering-run-index:start -->
## Latest retained engineering run

Run: [20261126T074605Z-ads2027-acceptance](results/20261126T074605Z-ads2027-acceptance/run.json).
Selected native design: `LPF_R01_lib:LPF_Ideal:schematic`.

| Facet | Recorded outcome |
|---|---|
| execution | completed |
| electrical | passed |
| models | not-applicable |
| delivery | complete |

[native_source 1](results/20261126T074605Z-ads2027-acceptance/source/native-inventory.json)

[native_source 2](results/20261126T074605Z-ads2027-acceptance/source/ads-project-kit.json)

[check_report 1](results/20261126T074605Z-ads2027-acceptance/ideal-output/report.md)

[check_report 2](results/20261126T074605Z-ads2027-acceptance/acceptance-summary.json)

This index describes the retained run; electrical acceptance follows its actual task reports.
<!-- engineering-run-index:end -->
