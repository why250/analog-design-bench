# ideal-lpf-apk-acceptance (revision 1)

- Task ID: `ideal-lpf-apk-acceptance`
- Revision: `1`
- Stage: `ideal-lc-acceptance`
- Status: `Ready for preflight`

## Objective

Verify end-to-end integration of `analog-design-bench`, `ai-eda-lab`, and
`ads-project-kit` in a real Keysight ADS 2027 runtime using a simple ideal
50-ohm LC low-pass filter.

## DUT interface and ownership

- DUT library: `LPF_R01_lib`
- DUT cell: `LPF_Ideal` (`schematic` and `symbol` views)
- Ordered DUT ports: `rfin`, `rfout`, `gnd`
- Testbench library: `LPF_R01_tb_lib`
- Testbench cell: `TB_LPF_Ideal_SP` (`schematic` view; owns 50-ohm `Term` ports, `GROUND`, and `S_Param` controllers)

## Electrical specification

- Reference impedance: `50 Ohm`
- Passband edge: `10 GHz` (`S11 < -15 dB`, `S22 < -15 dB`)
- Stopband checkpoint: `20 GHz` (`S21 <= -20 dB`)
- Insertion loss policy: `<= 1.0 dB` across passband (`1 MHz` to `10 GHz`)
- Topology: ideal lossless series-first Chebyshev-I LC ladder (`ads_rflib:L` and `ads_rflib:C`)

## Deliverables

- Native ADS workspace (`ads/design_wrk`) created and validated via `ads_project_kit`
- Saved and reopened DUT schematic/symbol and S-parameter testbench
- Real ADS 2027 S-parameter simulation results and naming compliance check
- Traceable acceptance report
