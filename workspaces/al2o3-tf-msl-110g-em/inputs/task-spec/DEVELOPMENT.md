# Development and preflight: al2o3-tf-msl-110g-em-r1

**Prepared 2026-11-19; revision-1 engineering task.** This package defines
future single-line geometry and EM work. No component result is claimed by
creating its task/workspace files.

## Current state

- Readiness: **Ready for preflight**. Goal, stack, band, design freedom and
  deliverables are settled; ADS 2027/Momentum availability and the configured ADS host
  path mapping are not yet observed.
- Engineering verification: planned, not executed.
- Formal benchmark status: unregistered engineering task; no official verifier.
- Local environment binding key: `.local/ads-projects/al2o3-tf-msl-110g-em.json`.

## Scope and relationship to other work

The user requested a task for a thin-film Al2O3 microstrip line to be modeled
and simulated in ADS 2027 on the configured ADS host. The stack comes from the user's
cross-section drawing: Al2O3 127 um with er 9.9, 4.5 um Au on both faces, and
coupons of 6 mm or 3 mm length. The user selected a 50 ohm design at 110 GHz
plus characterization, 0.1-110 GHz coverage, width as the design variable, and
typical loss assumptions.

This is a standalone interconnect/line task. It does not modify or reopen the
InP LPF tasks. Its S-parameter model may later support circuit work, but filter
acceptance and full-circuit integration are separate future tasks.

## Confirmed decisions

| Date | Decision | Authority |
| --- | --- | --- |
| 2026-11-19 | Stack: Al2O3 127 um, er 9.9; Au 4.5 um top and bottom | user drawing |
| 2026-11-19 | Coupon lengths: 3 mm and 6 mm | user drawing |
| 2026-11-19 | Goal: select width for 50 ohm, then characterize | user |
| 2026-11-19 | Band: 0.1-110 GHz | user |
| 2026-11-19 | Nominal 50 ohm acceptance frequency: 110 GHz | user (changed from the proposed 65 GHz) |
| 2026-11-19 | Width is a design variable, not a fixed input | user |
| 2026-11-19 | Loss values: tan(delta)=1e-4, sigma(Au)=4.1e7 S/m, smooth | user-approved typical assumptions |
| 2026-11-19 | ADS 2027, Momentum on the configured ADS host | user |
| 2026-11-20 | Ground is a full-plane 4.5 um Au cover (`Al2O3_MSL_GND` with the PERFECT_CONDUCTOR cover replaced by Au); the finite 2.0/4.0 mm bottom-Au polygon was a misinterpretation | user clarification |

## G0 items to freeze before acceptance runs

| Item | Proposed value | Resolution owner |
| --- | --- | --- |
| Dielectric/top layout transverse width | 2.0 mm | execution owner; report as assumption; ground is a full-plane cover |
| Loss-value provenance | typical assumptions as selected | execution owner; ask for measured values if available |
| Port calibration and reference planes | declare and hold fixed | execution owner |
| Width legal range and minimum feature | 50-300 um coarse; freeze a narrower legal range | execution owner |
| Search and control budget | 11 coarse + 10 refine + 8 controls + 1 reproduction | execution owner |

These are engineering defaults inside the authorized scope. They do not require
another permission round unless a material user-intent conflict or a genuinely
unavailable input appears.

## Execution prerequisites and available resources

Preflight must establish, with evidence:

- ADS 2027 installation and Momentum microwave license on the configured ADS host;
- the MCP or other approved connection route and the actual ADS process host;
- the repository-visible path on the ADS host and that the same
  `workspaces/al2o3-tf-msl-110g-em/` relative root is usable there;
- that no unsaved design in an existing ADS session would be disturbed by
  switching the active workspace.

Use [the task-owned workspace](../../workspaces/al2o3-tf-msl-110g-em/README.md)
and the [shared layout contract](../../docs/engineering-workspace-layout.md).
The native ADS project is `ads/al2o3_msl_wrk`; task-owned libraries follow
[the naming convention](../../docs/ads-naming-convention.md): `MSL_R01_lib`
for DUT cells and `MSL_R01_tb_lib`/`MSL_R01_em_lib` only if the task actually
uses those roles. The selected DUT cell (a `_C<NN>` candidate) is recorded in
`project.toml` and the execution record after G2; do not create a new library
revision for candidate iterations.

## Contract and result boundaries

- [instruction.md](instruction.md) owns the objective, confirmed inputs, target
  and work packages.
- [model-plan.md](model-plan.md) owns the stack table, ports, extraction
  definitions and numerical checks.
- [verification-plan.md](verification-plan.md) owns acceptance, coverage,
  gates and result states.
- The workspace [project.toml](../../workspaces/al2o3-tf-msl-110g-em/project.toml)
  owns portable identity and relative paths.

This EM task has no registered shared-runner submission interface. Task
metadata therefore declares no runner artifact. Required engineering
deliverables remain explicit in the instruction.

A converged EM result supports only the declared geometry, stack, ports and
solver conditions. It does not establish fabrication accuracy, a measured
material, a connector/launch model or full-circuit acceptance.

## Handoff to the execution session

The execution session should first inspect dirty workspace state and the task
sources, then carry W0-W5 through a bounded design and EM loop. Preserve
existing work. Ask only for genuinely missing inputs that cannot be resolved
within the authorized scope. Report model gaps and solver failures
transparently; do not infer a result from an analytic estimate.

The task-authoring step did not start ADS, create a native project or consume a
license.

## Preflight checklist

- [ ] Confirm ADS version, transport/MCP session and workspace path mapping.
- [ ] Confirm Momentum microwave license, thick-metal support and solver version.
- [ ] Confirm the ADS host can see `workspaces/al2o3-tf-msl-110g-em/`.
- [ ] Freeze `inputs/task-spec/` before isolated execution
      (`python scripts/ads_workspace.py snapshot-spec --workspace workspaces/al2o3-tf-msl-110g-em`).
