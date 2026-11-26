# Execution record: ideal-lpf-apk-acceptance-r1

- Stage: `ideal-lc-acceptance`
- Task specification: [instruction.md](../../../tasks/ideal-lpf-apk-acceptance/instruction.md)
- Verification plan: [verification-plan.md](../../../tasks/ideal-lpf-apk-acceptance/verification-plan.md)
- Acceptance report: [ads-project-kit-acceptance.md](../../../docs/reports/ads-project-kit-acceptance.md)

## Retained runs

| Run ID | Purpose | Outcome | Notes |
| --- | --- | --- | --- |
| `20261126T074605Z-ads2027-acceptance` | Real ADS 2027 cross-repo integration acceptance | `passed` (`execution=completed`, `electrical=passed`, `delivery=complete`) | Created `ads/design_wrk` via `ads_project_kit`, validated open/closed in ADS 2027 (`650`), built 5th-order LPF + `TB_LPF_Ideal_SP`, simulated S-parameters (`S11=-16.0 dB`, `S21@20GHz=-35.29 dB`) |

## Decisions and limitations

- Uses `model_policy = "unrestricted-ideal"` with `ads_rflib` ideal `L`/`C` components and schematic-only technology (`setup_schematic_tech=True`).
- External PDKs, layout geometry, and EM extraction are out of scope for this acceptance task.
