# Development record

Revision 1 defines the ideal shunt-first dual. The previous ideal task supplies
the electrical limits. The [all-pole topology study](../../workspaces/inp-passive-lpf-65g-allpole-loss-topology/docs/loss-design-conclusions.md)
supplies the analytical precedent for the nine-pole dual. This task verifies
that topology with its own editable ADS source and simulation evidence.

Use the established ADS engineering environment through a programmatic ADS
route. The ideal bench needs ADS circuit simulation and its standard L, C and
Term primitives. The task-owned [engineering workspace](../../workspaces/inp-passive-lpf-65g-shunt-first-ideal/README.md)
records execution evidence and the selected handoff.

## Selection and verification

Selected run `20261111T071536Z-ads-ideal` verifies the nine-pole dual in ADS.
Worst passband S11 and S22 are both −21.000 dB, worst insertion loss is
0.034635 dB, and S21 at exactly 80 GHz is −25.163775 dB. The 1 MHz–120 GHz
sweep includes 65 GHz, 80 GHz and all five ideal passband extrema. All four
complex S-parameters agree with the independent ABCD cascade to within
`1.7e-15` absolute. A fresh ADS process reopened the schematic and reproduced
the netlist and complex exports.

The selected response is the requested shunt-first dual of the previous ideal
response. Freeze this run and the nine-element order for the PCell task.
