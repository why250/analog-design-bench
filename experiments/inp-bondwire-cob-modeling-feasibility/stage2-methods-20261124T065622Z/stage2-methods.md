# Stage 2: ADS bonding-wire modeling methods

**Task:** `inp-bondwire-cob-modeling-feasibility`, revision 1.  
**Scope:** Documentation and read-only tool-documentation investigation,
2026-11-24. This is a study record, not a prepared ADS engineering run. No ADS
session was started or attached, no native source was created, and no circuit or
EM simulation, experiment, or measurement was performed. Stage 1 and this
stage's task/workflow baseline are preserved under `baseline/`; the task
contract and verification plan remain authoritative.

**Evidence labels.** [Doc] is a dated or versioned published source; [MCP-Doc]
is documentation returned by the configured documentation interface, retained
in [mcp-documentation-observations.json](mcp-documentation-observations.json);
[Interp] is an engineering inference; [Pending] is not established. The MCP
documentation index reports version `0.0.0`; that label does not establish an
exact match with the installed ADS build. The environment plan identifies ADS
2027 as the intended route, not the actual update level, running session,
solver availability, license, or readiness.

## 1. Evidence and method-selection matrix

| Topic | Documented or observed | Unestablished for this task / disposition |
| --- | --- | --- |
| Circuit bondwire | [Doc] An [ADS 2011 distributed-components manual](https://edadownload.software.keysight.com/eedl/ads/2011_01/pdf/ccdist.pdf) describes the historic BONDW1–50 Philips/TU Delft circuit model: coupled wire inductances, segmented geometry, an ideal ground plane, DC loss and approximate skin loss. It explicitly excludes wire-to-wire and ground capacitance, radiation, and proximity-effect redistribution. Keysight's older [SPDT example](https://edadownload.software.keysight.com/eedl/ads/2016_01/pdf/SPDT_Module_Design.pdf) uses `ads_bondwires:EBOND`; its [SmartMount/RFPro workshop](https://edadownload.software.keysight.com/eedl/ads/pdf/SmartMount_RFPro_Hands-on_Workshop_short.pdf) illustrates EBOND between a die pad and board. | [Pending] The active version's component library, circuit model, inputs, ground reference, frequency range, exclusions, and their compatibility with the chosen return path are not verified. Old BONDW limitations must not be attributed automatically to EBOND. Compare version-matched help and inspect the model before selection; use the explicitly coupled lumped circuit from Stage 1 as the independent conceptual alternative. Avoid omitting or double-counting pad/ground capacitance and return inductance. |
| Native bondwire and shape | [Doc] The [ADS 2027 Update 1.0 release description](https://www.keysight.com/jp/content/lib/software-detail/computer-software/pathwave-advanced-design-system-ads-software-2212036.html) announces native bondwire layout technology. [MCP-Doc] `api/keysight.ads.de.db_uu/Bondwire` describes a layout object with profile, end layers, points and radius; `api/keysight.ads.de.tech/BondwireProfile` describes radius, material, ground layer and shape-related properties. The metal-model enumeration names surface impedance and interior meshing. | [Pending] No evidence identifies the installation as Update 1.0, validates a concrete constructor workflow, displays the shape, checks connectivity, or demonstrates its transfer to either solver. Capture version-specific documentation and a later authorized geometry/connection inspection before relying on it. If unsupported, investigate a documented compatible parameterized 3D component or another authorized modeling route; do not silently substitute an ideal wire. |
| 3D FEM | [Doc] Keysight describes the [FEM element](https://www.keysight.com/be/en/assets/7018-02062/flyers/5990-3632.pdf) as a full-wave 3D simulator integrated into ADS, including parameterized wire-bond structures and adaptive meshing. Its [EMPro brochure](https://www.keysight.com/hk/en/assets/7018-02343/brochures/5990-4819.pdf) describes FEM for structures with 3D vertical variation and integration with ADS layouts. | [Interp] FEM is the preferred **candidate** for a deliberately modeled wire arch, pads, finite die/substrate and return geometry, subject to representability and adequate numerical checks. [Pending] The selected installation, FEM license, exact feature set and numerical cost are not verified. If unavailable, document the limitation and investigate a supported alternative or partial result; do not equate a reduced model with full 3D validation. |
| Momentum | [Doc] Keysight describes [Momentum](https://www.keysight.com/es/en/lib/resources/training-materials/momentum-key-features-1936424.html) as a 3D-planar method-of-moments solver for layered planar structures, with S/Y/Z outputs. Its [product flyer](https://www.keysight.com/vn/en/assets/7018-02063/flyers/5990-3633.pdf) explicitly lists an efficient bondwire model. | [Interp] Momentum is a candidate for planar pads/traces and, where the documented bondwire representation is applicable, a lower-cost comparison. It is incorrect to claim it cannot model bondwires at all. [Pending] Its actual arch representation, return, substrate assumptions, loss and error for this geometry and frequency remain to be established. Any FEM comparison must hold physical port planes, geometry, conditions and normalization consistent or explicitly account for differences. |
| Ports, reference planes, return and de-embedding | [Doc] Keysight's older [ADS electromagnetic guide](https://edadownload.software.keysight.com/eedl/ads/2012_08/pdf/em.pdf) explains ports as two-terminal excitations and distinguishes calibration/de-embedding choices. [Doc] The [2025 release notes](https://www.keysight.com/zz/en/lib/resources/software-releases/advanced-design-system-ads-2025-update-10.html) mention RFPro port feed options; neither source establishes which options are available or suitable in the selected installation. | [Pending] Specify P1 and P2 signal **and local return**, physical closure via connected ground bond/plane, mode, impedance, feed geometry, polarity, reference plane, calibration and fixture/de-embedding. 50 ohms is a proposed comparison normalization only. Inspect port fields/current paths and geometry when separately authorized. If an equivalent physical reference or calibration cannot be established, do not compare models as though they had identical boundaries. |
| Material, die and substrate | [MCP-Doc] `BondwireProfile` lists material and substrate-related properties; `create_empro_view` accepts a substrate reference. [Doc] The [ADS 2017 electromagnetic manual](https://edadownload.software.keysight.com/eedl/ads/2017/pdf/Electromagnetic.pdf) discusses substrate dielectric, conductor and ground-plane representations. | [Pending] No real InP or ceramic stack, conductivity, thickness, dispersion, dielectric loss or ground-plane extent is supplied. Explicitly mark generic values and sources, frequency validity and excluded structures; document a finite or infinite ground plane and its implications. An infinite idealized ground is not evidence of a realistic finite return. Do not transfer old-version assumptions automatically to 2027. |
| Boundaries and field domain | [Doc] The [FEM element document](https://www.keysight.com/be/en/assets/7018-02062/flyers/5990-3632.pdf) describes full-wave modeling; [Keysight's solver comparison](https://www.keysight.com/content/dam/keysight/en/doc/gate/white-papers/5990-9759.pdf) explains the different geometry assumptions of volumetric and layered-planar methods. | [Pending] Actual surrounding volume, metal enclosure or open boundary, die boundary, fixture, conductor continuity and radiation treatment are not fixed. Investigate version-specific boundary options and their physical meaning. If geometry/boundary assumptions are insufficient, limit conclusions rather than treating the model as measured hardware. |
| Mesh and convergence | [Doc] The FEM flyer describes an adaptive mesher. The 2025 release notes discuss meshing improvements; the 2017 guide notes mesh density can alter modeled metal loss. | [Interp] Before any solve, select mesh controls and comparison criteria; retain mesh/refinement history and complex S-parameter changes at selected low/mid/high frequencies and near response features. Separately assess frequency sampling and, where needed, port and boundary sensitivity. [Pending] Solver-specific controls, tolerances, case count and budget need review; a single solve, or adaptive convergence alone, does not establish physical accuracy. |
| S-parameter extraction | [Doc] Momentum's feature page documents S/Y/Z outputs. [MCP-Doc] `simulation/results` describes dataset access and complex `S(2,1)` for an example circuit analysis. | [Pending] Actual FEM/RFPro dataset structure, all four complex S entries, port ordering, Touchstone export, calibration and renormalization are not verified here. Preserve actual raw data, logs and frequency list; independently compare on common planes. Do not equate a circuit dataset example with a proven RFPro automation route. |
| Python / MCP | [MCP-Doc] `Bondwire`, `BondwireProfile` and `BondwireMetalModelType` document relevant object declarations; `keysight.ads.emtools.create_empro_view` documents creation of an EM view from a layout and substrate. The supplied RFPro example describes conversion from an existing EM Setup. [Doc] The public [Python execution guide](https://edadownload.software.keysight.com/eedl/API_Doc/designenvironment/620/html/pydocs/concepts/execution.html) is for ADS 2025 Update 2, not evidence of this installation. | [Pending] No code was run and no end-to-end automated FEM geometry, ports, solve, mesh checks or extraction was demonstrated. The example includes destructive temporary-directory cleanup and must not be copied blindly. Inspect actual-version public documentation and tool schemas; use a separately consented manual procedure if needed, or document the unsupported step. |
| Environment, licensing and resources | The prior read-only project environment plan selects an ADS 2027 route and reports execution not ready; the documentation server answered the above documentation queries. | [Pending] Actual ADS process/version, update, client binding, solver license, model access, installed documentation, workspace mapping, authorization and runtime budget are not proven. The plan is not a reservation or functional test. Follow the repository environment and readiness workflow before native work. |

## 2. Proposed model comparison and prediction

[Interp] The Stage 1 two-conductor circuit retains separate signal and physical
return impedances, magnetic coupling and explicitly allocated pad capacitances.
It is a transparent low-frequency baseline, not a complete field solution.
The primary candidate for the future 3D comparison is full-wave FEM because the
question includes an arched wire, spatially distinct pads, die/ceramic interface
and current return. Momentum's specialized bondwire representation and planar
environment are a legitimate additional candidate where their documented
assumptions fit. The final choice is conditional on the actual installation,
license, geometry support, physical boundary and approved budget.

[Interp] Before any run, predict that shortening the signal/return loop and
bringing a properly connected return closer may reduce the loop inductance in
the controlled low-frequency case. A change can also alter pad capacitance,
current crowding, radiation and resonances, so an S-parameter improvement is
not guaranteed or necessarily monotonic. Preserve predictions before observing
results; no observation exists yet.

## 3. Proposed bounded Stage 3 plan — not authorized to execute here

1. **Resolve physical inputs and boundaries.** Agree the idealized geometry and
   sources, die and ceramic stacks, loss laws, pad dimensions, wire profile,
   conductor contacts and a continuous, physically connected return. Mark
   everything generic and avoid representing it as an InP PDK. Draw the
   two-port device boundary: P1 die-side signal/local return; P2 substrate-side
   signal/local return. Specify planes, polarities, modes, fixture, impedance and
   de-embedding for both circuit and EM representations.
2. **Preflight and budget before native work.** Verify actual ADS release/update,
   installed help, product MCP, intended workspace mapping, solver and license.
   Freeze task/workflow and an authorized scope, then select the numerical
   tolerances, frequency sampling, maximum cases and resource ceiling. The
   present research range of 1–110 GHz is not a dense-sweep instruction.
3. **Build a minimal candidate, once separately authorized.** Create one
   signal bond with an explicit ground return and documented pads/substrate;
   retain a corresponding coupled circuit with no ideal short that bypasses
   return impedance. Inspect actual geometry, material assignments, connections
   and EM port feeds before solving. Start with the simplest defensible geometry;
   do not automatically run a broad multi-geometry study.
4. **Bound numerical evidence.** Propose representative low, middle, high and
   expected feature frequencies within the approved budget. Specify mesh levels,
   predeclared convergence metrics for complex S and extracted parameters, and
   frequency, boundary and port checks as needed. Treat representative samples
   only as sampled evidence. Stop if resources or predeclared tolerances cannot
   be met; do not infer continuous-band convergence.
5. **Compare and retain.** Compare all complex S entries and input impedance
   on compatible planes and normalization; report extraction methods, coverage,
   passivity and reciprocity, model limitations and reproducibility separately.
   The baseline gate requires a credible model under stated conditions before
   optional sensitivity studies. Convergence is not measured-hardware validity.

**Stop conditions:** Missing authorization, budget, continuous return, port
definitions, material provenance, confirmed solver/license or necessary input
data blocks dependent work. Preserve any later failed or inconclusive evidence;
never turn a missing result into electrical PASS or FAIL. Alternatives requiring
extra software, a GUI, a process launch or further computational cost need their
own applicable authorization and environment checks.

## 4. Review and outstanding questions

The documentation review supports the conditional method choice and identifies
specific checks for the next stage; it does not establish execution readiness,
selected-model accuracy, a 1–110 GHz validity band, product performance, or
benchmark acceptance. Important unresolved decisions are wire/pad/return
geometry, exact material stacks, fixtures and port planes, actual tool update,
solver/license availability, finite-domain treatment and computational budget.
Obtain version-matched, installed documentation before asserting precise
component parameters or an executable API route. Stage 2 is available for
engineering review with these gaps; it is not evidence of an ADS engineering
run or a verified model.

The engineering workspace is not yet initialized. Preserve this report and
its Stage 1 predecessor as the source for later append-only learning notes at
`workspaces/inp-bondwire-cob-modeling-feasibility/learning-notes.md`, when the
workspace is created through the approved workflow. The learning overlay does
not alter task scope or acceptance.
