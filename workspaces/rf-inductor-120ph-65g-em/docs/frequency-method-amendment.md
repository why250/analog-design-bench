# Frequency method amendment

This amendment is adopted before final frequency-domain acceptance runs. It
preserves the original research contract and all previous evidence. The target
windows, physical excitation, mesh limits and 80 GHz requirement are unchanged.
Its machine-readable specification is
[numerical-protocol-amendment-r1.json](../inputs/numerical-protocol-amendment-r1.json).

ADS Momentum supports native adaptive frequency sampling (AFS). Its installed
2027 guides distinguish the dataset of actually simulated samples from the
densely sampled rational-model dataset with an `_a` suffix. Non-adaptive plans
execute before the adaptive plan, so exact 65/80 GHz solves can be retained
alongside the adaptive model. The official Microstrip-line example supplies the
native encoding of single-frequency plans.

Retain the complete two-port actual samples, the complete derived dense model,
their original datasets, settings and raw solver files. Label them separately.
An AFS-derived curve is not another set of raw EM solves. Inspect its actual
frequency spacing rather than assuming a display grid from the stimulus syntax.

Qualify the frequency model with a separate run at the declared boundaries and
at unsampled interval midpoints selected solely from frequency gaps. Compare
complex S, terminal L and Q, reserve explicit interpolation uncertainty, and
check full-matrix passivity and reciprocity of both datasets. Preserve failures.
If these checks do not establish the required coverage and accuracy, return to
the original explicit-frequency method or report INDETERMINATE.

DC and the low-frequency extension use independent evidence. A rational model
starting at 5 GHz does not establish zero-Hz behavior. The result remains an
assumed-stack single-device model; parent LPF acceptance is not evaluated.

## Native coverage refinement, revision 2

The first corrected passive AFS run converged without listed warnings. Its
actual samples supplied only two original gaps within 10-65 GHz, and its native
dense output had a maximum spacing of about 1.146 GHz below 100 GHz. It therefore
does not satisfy the declared independent-gap and output-coverage protocol.
The original datasets and unsuccessful qualification-plan attempt are retained.

[Revision 2](../inputs/numerical-protocol-amendment-r2.json) adds forced actual
samples at 20 and 40 GHz before a fresh native export and run. Six forced
frequencies and at most 48 adaptive samples retain the previous combined cap
of 54. The extra boundaries provide at least three original in-band intervals
and shorten the native dense-output segments. Their actual spacing must still
be checked after the new solve. No self-resampling replaces the native output.

This strengthens the sampling experiment. The electrical targets, numerical
comparison tolerances, seven independent midpoints and interpolation reserve
are unchanged. The first passive AFS run remains identified as revision 1;
it is not relabeled as qualified revision-2 evidence.

The completed revision-2 native fit still returned four 1.25 GHz intervals
between 35 and 40 GHz. The
[actual coverage-fill record](../inputs/actual-frequency-coverage-fill-r2.json)
freezes independent solves at their midpoints before running those controls.
They supplement the unchanged native grid with actual data and participate in
the original complex-S/L/Q comparisons. No fitted values are resampled or
relabeled as actual. Final spacing is checked on the union of retained native
samples and completed actual controls; the native output's original spacing
remains visible in its receipt.
