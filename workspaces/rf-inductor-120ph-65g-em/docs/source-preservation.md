# Source-preservation audit and scope

This audit records the scope of retained source comparisons. It does not claim
that every historical remote parent byte was preserved, identify a cause for
observed differences, or evaluate the parent LPF. The unit design and source
preservation are separate conclusions.

## Historical parent captures

The earlier run `results/20261028T070547Z-toolkit-em-r1` contains an initial
`parent-before-export` capture and a later `parent-c02-c04-preservation`
baseline. Two OA files differ between those captures:

- `inp_lpf_lib/inp_lpf_sp/schematic/sch.oa`
- `inp_lpf_lib/inp_lpf/schematic_real/sch.oa`

The retained receipt-file metadata spans **07:33:12--07:49:20 UTC** on
2026-10-28. This is the capture interval established by those records, not an
observed event time for either source change. The cause, timing within that
interval and semantic effect of the differences remain undetermined.

The binary material retained under `private-parent-before-c02-c04` matches the
later baseline and does not match the initial capture. An audit of this old
run, including its retained snapshots and archives, did not locate a binary
matching the initial capture for the differing files. That finding is limited
to the audited run. It does not establish that no matching backup exists
elsewhere on the server or in another retained location.

No automatic restoration follows from this evidence. Replacing current source
without establishing the intended version and semantic differences would be a
blind restoration. Preserve the captures and comparisons while their
interpretation remains open.

## Capture sets are not interchangeable

The initial comparison tracked six entries and included `.oalib`. A later
comparison tracked five entries, omitted `.oalib`, and added a Cap1 layout
entry. These are different observation sets.

A later receipt with `changed_paths=[]` demonstrates no detected change for
the paths listed in that receipt and its own comparison baseline. It does not
demonstrate preservation of the initial six-entry set, every parent source,
the entire workspace, or every file type. Do not join these receipts into an
unqualified whole-history preservation claim.

## Corrected-run application exports

In the corrected run `results/20261028T092348Z-passive-loss-r1`, each final GUI
export batch compared its own before/after snapshots of the recorded `*.oa`
files and `lib.defs`. Those batch comparisons detected no changes in their
recorded sets.

This is evidence for those batches, paths and capture boundaries. It does not
resolve the earlier capture differences or cover file types omitted from the
batch snapshots. An unchanged library-definition file alone also does not
establish unchanged OA sources; retain both parts of the recorded comparison.

## Local repository checkpoint

The closeout check on 2026-10-29 compared the 82 pre-existing dirty files
outside this task's file set against their retained initial checkpoint.
It found no content changes or missing files within that set. The private
machine-readable closeout receipt is retained in the local operator notes.

This local checkpoint is a separate observation from the remote parent-source
audit. It must not be used to infer complete historical preservation of the
remote workspace or files outside its recorded local set.

## Unit provenance and delivery interpretation

The standalone inductor geometry is generated from the task-owned copied
RFIC Inductor Toolkit and its retained task inputs. Reproducing this unit does
not depend on the current versions of the old parent OA files. Its complete
two-port network, assumed physical stack, finite return and numerical
qualification still require their own evidence. This provenance does not
settle the separate historical parent-source differences.

The parent LPF remains **NOT EVALUATED**. The final design report must link to
this audit and retain its observation-set and time-boundary limitations. It
must not state that all historical remote parent bytes were preserved.
