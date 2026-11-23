# Stage 2 execution record

Completed in UTC on 2026-10-28; run `stage2-20261027T113222Z`.

Study: **COMPLETE**. Primary stage decision: **TOPOLOGY REVIEW REQUIRED**.

Retained 225 filter request mappings and 219 unique physical circuits; candidate states: {"FAIL": 203, "PASS": 16}. E9 adds three fresh-workspace repetitions. E1 retains 55/55 valid isolated-device runs.

E6 combined-case request states: {"FAIL": 64}. E8 retained 20 additional parameter requests over its 20 seeds. Every sampled interval and unsearched interior remains explicit.

The maximum absolute ADS/independent complex-S disagreement over the unique filter cases is 1.18515017819e-11 (limit 1e-6). All cases passed full-matrix passivity, reciprocity, exact checkpoint, dense-grid, actual-model extrema and tracked local-refinement checks. The ideal recovery additionally passed unitarity.

Fresh-workspace repetitions passed 3/3 comparisons, with frozen sweeps, source/settings comparisons, exact saved-netlist diffs and OA snapshots taken after lock release.

The necessary DC common-Q bound of approximately 35.59 is weaker than RF requirements: loss-only Q=60 fails insertion loss, whereas Q=100 and Q=200 pass. The complete measured conditional envelope and individual failures are retained in the report; these two points do not establish a universal Q threshold.

The criterion-based readiness and the documented engineering judgment are both retained. Single-effect passing samples do not establish feasibility of the explored joint nonideal circuits. Same-topology retuning remains an optional follow-up after this untuned study.

Read the [full report](../results/stage2-20261027T113222Z/report.md), [learning record](../results/stage2-20261027T113222Z/learning.md), [audit](../results/stage2-20261027T113222Z/handoff-audit.json), and [reproduction evidence](../results/stage2-20261027T113222Z/reproduction.json).

The specification-stage task documents are preserved as the frozen research contract. This execution record supersedes their historical 'not executed' status only for this retained study. No official benchmark score or SPICE submission was produced. All coefficients are synthetic; no InP process, layout/EM, temperature-range, corner or yield claim follows.
