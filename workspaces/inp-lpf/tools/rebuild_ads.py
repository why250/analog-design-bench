"""Build and simulate the revision-2 ideal LC filter with ADS 2027 Python."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from keysight.ads import ael, de, dataset
from keysight.ads.de import db_uu as db
from keysight.ads.de.experimental import DesignBuilder
from keysight.ads.de.experimental.generate_symbol import SymbolGenerator

from analyze import synthesize, reflection_extrema_hz

LIBRARY = "inp_lpf_lib"
DUT = f"{LIBRARY}:inp_lpf:schematic"
TESTBENCH = f"{LIBRARY}:inp_lpf_sp:schematic"


def _switch_workspace(path: Path):
    if de.workspace_is_open():
        if Path(de.active_workspace().path).resolve() == path.resolve():
            return de.active_workspace()
        if de.is_pde_app():
            from keysight.ads.de import app
            for kind in (app.WindowType.SCHEMATIC_WINDOW,
                         app.WindowType.SYMBOL_WINDOW,
                         app.WindowType.LAYOUT_WINDOW):
                for window in app.find_windows_by_type(kind):
                    design = app.get_design_in_uu_from_window(window)
                    if bool(ael.call.db_design_is_modified(design)):
                        raise RuntimeError("Save existing modified designs before switching workspace.")
        de.close_workspace()
    if path.exists():
        return de.open_workspace(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    workspace = de.create_workspace(path)
    workspace.open()
    return workspace


def _design(cellview: str, overwrite: bool):
    return DesignBuilder.build_schematic(cellview, overwrite=overwrite)


def _text(design, text, xy, height=0.14):
    design.add_text(db.LayerId(231), text, xy, "Arial", height)


def _port(design, number, name, xy, angle=0):
    net = design.find_or_add_net(name)
    term = design.add_numbered_term(net, name, number, db.TermType.INPUT_OUTPUT)
    return design.add_pin(term, design.add_dot_for_pin(xy), angle=angle)


def _format_annotations(design):
    design.select_all()
    design.edit.modify_selected_instance_annotations(points=8)
    design.deselect_all()


def build(workspace_path: Path, *, overwrite=False):
    workspace = _switch_workspace(workspace_path)
    if LIBRARY not in workspace.library_names:
        lib_path = workspace_path / LIBRARY
        de.create_new_library(LIBRARY, lib_path)
        workspace.add_library(LIBRARY, lib_path, de.LibraryMode.NON_SHARED)
    design_values = synthesize()
    builder = _design(DUT, overwrite)
    design = builder.design
    transaction = de.db.Transaction(design, "Build ideal nine-pole LC ladder")
    _port(design, 1, "rfin", (0, 0), 180)
    _port(design, 2, "rfout", (20, 0))
    _port(design, 3, "gnd", (0, -3.8), 180)
    inductors = []
    capacitors = []
    for element in design_values["elements"]:
        position = element["position"]
        if element["kind"] == "L":
            x = 1.5 + 4 * ((position - 1) // 2)
            instance = builder.place_instance(
                ("ads_rflib", "L", "symbol"), (x, 0), name=element["name"])
            instance.parameters["L"].value = f'{element["value_si"]:.17g} H'
            instance.parameters["R"].value = "0 Ohm"
            instance.parameters["Noise"].value = "no"
            inductors.append(instance)
        else:
            x = 4 * (position // 2)
            instance = builder.place_instance(
                ("ads_rflib", "C", "symbol"), (x, -1.4),
                name=element["name"], angle=-90)
            instance.parameters["C"].value = f'{element["value_si"]:.17g} F'
            capacitors.append(instance)
    builder.make_connection(1, (inductors[0], 1), "rfin")
    builder.make_connection((inductors[-1], 2), 2, "rfout")
    for index, cap in enumerate(capacitors):
        builder.make_connection((inductors[index], 2), (cap, 1), f"n{index+1}")
        builder.make_connection((cap, 1), (inductors[index+1], 1), f"n{index+1}")
        x = 4 * (index + 1)
        design.add_wire([(x, -2.4), (x, -3.8)])
    design.add_wire([(0, -3.8), (16, -3.8)])
    _text(design, "Ideal 9th-order Chebyshev LC LPF | 50 Ohm | fp = 65 GHz", (0, 2.0), 0.22)
    _text(design, "DUT: ideal positive L/C only; gnd is an explicit third terminal", (0, 1.5))
    _text(design, "RL target = 21 dB | passband ripple = 0.0346349774554594 dB", (0, -4.6))
    _text(design, "DC through path: series inductors become shorts; shunt capacitors open", (0, -5.0))
    transaction.commit()
    _format_annotations(design)
    builder.save_design()

    symbol_view = f"{LIBRARY}:inp_lpf:symbol"
    if overwrite:
        try:
            symbol = db.open_design(symbol_view, "Append")
            symbol.clear_design()
        except RuntimeError:
            symbol = db.create_symbol(symbol_view)
    else:
        symbol = db.create_symbol(symbol_view)
    generator = SymbolGenerator(symbol, design, 0.5, 1.0)
    generator.is_dual_symbol_type = True
    generator.should_replace = True
    generator.pin_shape = "square"
    generator.generate_symbol()
    symbol.save_design()

    tbuilder = _design(TESTBENCH, overwrite)
    testbench = tbuilder.design
    transaction = de.db.Transaction(testbench, "Create external 50 Ohm testbench")
    dut = tbuilder.place_instance((LIBRARY, "inp_lpf", "symbol"), (6, 0), name="DUT")
    p1 = tbuilder.place_instance(("ads_simulation", "Term", "symbol"),
                                (0, 0), name="Term1", angle=-90)
    p2 = tbuilder.place_instance(("ads_simulation", "Term", "symbol"),
                                (14, 0), name="Term2", angle=-90)
    for number, instance in enumerate((p1, p2), 1):
        instance.parameters["Num"].value = str(number)
        instance.parameters["Z"].value = "50 Ohm"
        instance.parameters["Noise"].value = "no"
        ground = tbuilder.place_instance(("ads_rflib", "GROUND", "symbol"),
                    (0 if number == 1 else 14, -1), name=f"GND{number}", angle=-90)
        tbuilder.make_connection((instance, 2), (ground, 1))
    ground = tbuilder.place_instance(("ads_rflib", "GROUND", "symbol"),
                                     (8, -4), name="GND_DUT", angle=-90)
    tbuilder.make_connection((p1, 1), (dut, 1), "rfin")
    tbuilder.make_connection((dut, 2), (p2, 1), "rfout")
    tbuilder.make_connection((dut, 3), (ground, 1))

    sweeps = [
        ("SP_broad", 1e6, 120e9, 2401),
        ("SP_passband", 1e6, 65e9, 1301),
        ("SP_checkpoints", 65e9, 80e9, 2),
    ]
    for index, frequency in enumerate(reflection_extrema_hz(), 1):
        low = frequency - 1e6
        high = min(frequency + 1e6, 65e9)
        points = 11 if frequency >= 65e9 else 21
        sweeps.append((f"SP_ext{index}", low, high, points))
    for index, (name, start, stop, points) in enumerate(sweeps):
        controller = tbuilder.place_instance(("ads_simulation", "S_Param", "symbol"),
                    (index % 4 * 5, 4 + index // 4 * 5), name=name)
        for key, value in {
            "Start": f"{start:.17g} Hz", "Stop": f"{stop:.17g} Hz",
            "Step": "", "Lin": str(points), "Dec": "", "Log": "",
            "CalcNoise": "no",
        }.items():
            controller.parameters[key].value = value
    _text(testbench, "50 Ohm ports are testbench-owned | DUT reference planes at rfin/rfout", (0, -5.0))
    _text(testbench, "65 GHz = passband edge | 80 GHz = single stopband checkpoint", (0, -5.4))
    transaction.commit()
    _format_annotations(testbench)
    tbuilder.save_design()
    return testbench, design_values, sweeps


def print_schematic(path: Path):
    """Export the native ADS DUT drawing with space for terminal annotations."""
    design = db.open_design(DUT)
    bounds = de.BoxF(x1=-1.5, y1=-5.8, x2=22.0, y2=3.0)
    design.print_design(str(path), box=bounds)


def simulate(testbench, output_dir: Path, *, design_values=None, sweeps=None):
    from keysight.edatoolbox import ads
    output_dir.mkdir(parents=True, exist_ok=False)
    netlist = testbench.generate_netlist()
    (output_dir / "schematic.net").write_text(netlist, encoding="utf-8")
    settings = {
        "task_revision": 2,
        "ads_product_version": de.product_version().strip(),
        "ads_python_package_version": str(de.__version__),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "testbench": TESTBENCH,
        "dut_ports": ["rfin", "rfout", "gnd"],
        "reference_impedance_ohm": 50,
        "model": "ideal positive L/C; no loss or parasitics",
        "netlist_sha256": hashlib.sha256(netlist.encode("utf-8")).hexdigest(),
        "sweeps": [{"analysis": n, "start_hz": a, "stop_hz": b, "points": c}
                   for n, a, b, c in (sweeps or [])],
    }
    (output_dir / "settings.json").write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    (output_dir / "synthesis.json").write_text(json.dumps(design_values or synthesize(), indent=2) + "\n", encoding="utf-8")
    simulator = ads.CircuitSimulator()
    simulator.run_netlist(netlist, output_dir=str(output_dir))
    return output_dir


def export_csv(output_dir: Path):
    import numpy as np
    data = dataset.open(output_dir / "inp_lpf_sp.ds")
    all_rows = []
    analysis_rows = {}
    for key in data:
        if not str(key).endswith(".SP"):
            continue
        frame = data[key].to_dataframe().reset_index()
        columns = {str(c).replace("[", "(").replace("]", ")"): c for c in frame.columns}
        required = ["S(1,1)", "S(2,1)", "S(1,2)", "S(2,2)"]
        if "freq" not in columns or any(c not in columns for c in required):
            raise RuntimeError(f"Unexpected ADS dataset columns: {list(frame.columns)}")
        rows = []
        for _, row in frame.iterrows():
            values = [float(row[columns["freq"]])]
            for name in required:
                value = complex(row[columns[name]])
                values.extend((value.real, value.imag))
            rows.append(values)
        analysis_rows[str(key)] = len(rows)
        all_rows.extend(rows)
    if not all_rows:
        raise RuntimeError("No SP data exported.")
    all_rows.sort(key=lambda row: row[0])
    # Preserve exact checkpoint/analytic samples; remove only exact duplicates.
    unique = {}
    for row in all_rows:
        frequency = row[0]
        if frequency in unique and np.max(np.abs(np.array(row[1:]) - np.array(unique[frequency][1:]))) > 1e-8:
            raise RuntimeError("Repeated ADS frequency samples disagree.")
        unique[frequency] = row
    with (output_dir / "ads_sparameters.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["freq_hz", "s11_real", "s11_imag", "s21_real", "s21_imag",
                         "s12_real", "s12_imag", "s22_real", "s22_imag"])
        writer.writerows(unique.values())
    settings_path = output_dir / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["dataset_analyses"] = analysis_rows
    settings["exported_frequency_count"] = len(unique)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return output_dir / "ads_sparameters.csv"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="Fresh run directory; never reuses previous simulation outputs.")
    parser.add_argument("--rebuild", action="store_true",
                        help="Replace only this project's named schematic/symbol views.")
    parser.add_argument("--schematic-pdf", action="store_true",
                        help="Also export a native ADS schematic PDF after simulation.")
    args = parser.parse_args()
    tb, values, sweeps = build(args.workspace.resolve(), overwrite=args.rebuild)
    simulate(tb, args.output.resolve(), design_values=values, sweeps=sweeps)
    print(export_csv(args.output.resolve()))
    if args.schematic_pdf:
        print_schematic(args.output.resolve() / "inp_lpf_schematic.pdf")


if __name__ == "__main__":
    main()
