"""Native headless ADS adapter for the ideal low-pass ladder."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .ideal import PHYSICS_TOLERANCE, PORT_ORDER


LIBRARY = "ideal_lpf_lib"
DUT_CELL = "ideal_lpf"
TESTBENCH_CELL = "ideal_lpf_sp"


def _place_port(design, db, number, name, xy, angle=0):
    net = design.find_or_add_net(name)
    term = design.add_numbered_term(net, name, number, db.TermType.INPUT_OUTPUT)
    design.add_pin(term, design.add_dot_for_pin(xy), angle=angle)


def _build_dut(de, db, design_builder, symbol_generator, design_values):
    builder = design_builder.build_schematic(f"{LIBRARY}:{DUT_CELL}:schematic")
    design = builder.design
    order = design_values["order"]
    output_x = 4 * ((order + 1) // 2)
    transaction = de.db.Transaction(design, "Build the ideal LC ladder")
    _place_port(design, db, 1, "rfin", (0, 0), 180)
    _place_port(design, db, 2, "rfout", (output_x, 0))
    _place_port(design, db, 3, "gnd", (0, -3.8), 180)
    inductors = []
    capacitors = []
    for position, element in enumerate(design_values["elements"], 1):
        value = element["value"]
        if element["kind"] == "L":
            x = 1.5 + 4 * ((position - 1) // 2)
            instance = builder.place_instance(
                ("ads_rflib", "L", "symbol"), (x, 0), name=element["name"]
            )
            instance.parameters["L"].value = f"{value:.17g} H"
            instance.parameters["R"].value = "0 Ohm"
            instance.parameters["Noise"].value = "no"
            inductors.append(instance)
        else:
            x = 4 * (position // 2)
            instance = builder.place_instance(
                ("ads_rflib", "C", "symbol"), (x, -1.4), name=element["name"], angle=-90
            )
            instance.parameters["C"].value = f"{value:.17g} F"
            capacitors.append(instance)
    builder.make_connection(1, (inductors[0], 1), "rfin")
    builder.make_connection((inductors[-1], 2), 2, "rfout")
    for index, capacitor in enumerate(capacitors):
        node = f"n{index + 1}"
        builder.make_connection((inductors[index], 2), (capacitor, 1), node)
        builder.make_connection((capacitor, 1), (inductors[index + 1], 1), node)
        x = 4 * (index + 1)
        design.add_wire([(x, -2.4), (x, -3.8)])
    if capacitors:
        design.add_wire([(0, -3.8), (output_x - 4, -3.8)])
    transaction.commit()
    builder.save_design()

    symbol = db.create_symbol(f"{LIBRARY}:{DUT_CELL}:symbol")
    generator = symbol_generator(symbol, design, 0.5, 1.0)
    generator.is_dual_symbol_type = True
    generator.should_replace = True
    generator.pin_shape = "square"
    generator.generate_symbol()
    symbol.save_design()


def _build_testbench(de, design_builder, impedance, sweeps):
    builder = design_builder.build_schematic(f"{LIBRARY}:{TESTBENCH_CELL}:schematic")
    testbench = builder.design
    transaction = de.db.Transaction(testbench, "Connect external ports and sweep controllers")
    dut = builder.place_instance((LIBRARY, DUT_CELL, "symbol"), (6, 0), name="DUT")
    ports = []
    for number, x in ((1, 0), (2, 14)):
        port = builder.place_instance(
            ("ads_simulation", "Term", "symbol"), (x, 0), name=f"Term{number}", angle=-90
        )
        port.parameters["Num"].value = str(number)
        port.parameters["Z"].value = f"{impedance:.17g} Ohm"
        port.parameters["Noise"].value = "no"
        ground = builder.place_instance(
            ("ads_rflib", "GROUND", "symbol"), (x, -1), name=f"GND{number}", angle=-90
        )
        builder.make_connection((port, 2), (ground, 1))
        ports.append(port)
    ground = builder.place_instance(
        ("ads_rflib", "GROUND", "symbol"), (8, -4), name="GND_DUT", angle=-90
    )
    builder.make_connection((ports[0], 1), (dut, 1), "rfin")
    builder.make_connection((dut, 2), (ports[1], 1), "rfout")
    builder.make_connection((dut, 3), (ground, 1))

    for index, (name, start, stop, points) in enumerate(sweeps):
        controller = builder.place_instance(
            ("ads_simulation", "S_Param", "symbol"),
            (index % 4 * 5, 4 + index // 4 * 5), name=name
        )
        for key, value in {
            "Start": f"{start:.17g} Hz",
            "Stop": f"{stop:.17g} Hz",
            "Step": "",
            "Lin": str(points),
            "Dec": "",
            "Log": "",
            "CalcNoise": "no",
        }.items():
            controller.parameters[key].value = value
    transaction.commit()
    builder.save_design()
    return testbench


def _read_dataset(dataset, path, sweeps):
    data = dataset.open(path)
    expected = {f"{name}.SP": count for name, _, _, count in sweeps}
    counts = {}
    by_frequency = {}
    for key in data:
        name = str(key)
        if name not in expected:
            continue
        frame = data[key].to_dataframe().reset_index()
        columns = {str(c).replace("[", "(").replace("]", ")"): c for c in frame.columns}
        required = ["freq", *(f"S({i + 1},{j + 1})" for i, j in PORT_ORDER)]
        if any(field not in columns for field in required):
            raise RuntimeError(f"Missing S-parameter columns in ADS analysis {name}.")
        counts[name] = len(frame)
        freq = frame[columns["freq"]].to_numpy(dtype=float)
        samples = np.empty((len(frame), 2, 2), dtype=complex)
        for i, j in PORT_ORDER:
            samples[:, i, j] = frame[columns[f"S({i + 1},{j + 1})"]].to_numpy(dtype=complex)
        for frequency, matrix in zip(freq, samples):
            if frequency in by_frequency and np.max(np.abs(matrix - by_frequency[frequency])) > PHYSICS_TOLERANCE:
                raise RuntimeError(f"Repeated ADS samples disagree at {frequency:.17g} Hz.")
            by_frequency[frequency] = matrix
    if counts != expected:
        raise RuntimeError(f"ADS sweep sample counts differ from the plan. Observed {counts}, expected {expected}.")
    freq = np.array(sorted(by_frequency))
    return freq, np.stack([by_frequency[frequency] for frequency in freq]), counts


def simulate_ideal(spec, design, sweeps, workspace_path: Path, output: Path):
    """Build a fresh ADS workspace, save raw evidence, and extract complex S data."""
    try:
        from keysight.ads import dataset, de
        from keysight.ads.de import db_uu
        from keysight.ads.de.experimental import DesignBuilder
        from keysight.ads.de.experimental.generate_symbol import SymbolGenerator
        from keysight.edatoolbox.ads import CircuitSimulator
    except ImportError as error:
        raise RuntimeError("Use an ADS Python environment with Design Environment and circuit simulation.") from error

    workspace_path = Path(workspace_path).resolve()
    output = Path(output).resolve()
    if workspace_path.exists():
        raise FileExistsError(f"ADS workspace already exists: {workspace_path}")
    if de.workspace_is_open():
        raise RuntimeError("Run the native ADS stage in a fresh headless Python process.")
    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=False)
    previous_directory = Path.cwd()
    try:
        workspace = de.create_workspace(workspace_path)
        workspace.open()
        library_path = workspace_path / LIBRARY
        de.create_new_library(LIBRARY, library_path)
        workspace.add_library(LIBRARY, library_path, de.LibraryMode.NON_SHARED)
        _build_dut(de, db_uu, DesignBuilder, SymbolGenerator, design)
        testbench = _build_testbench(de, DesignBuilder, spec["impedance_ohm"], sweeps)
        netlist = testbench.generate_netlist()
        settings = {
            "ads_product_version": de.product_version().strip(),
            "ads_python_package_version": str(de.__version__),
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "testbench": f"{LIBRARY}:{TESTBENCH_CELL}:schematic",
            "dut_ports": ["rfin", "rfout", "gnd"],
            "reference_impedance_ohm": spec["impedance_ohm"],
            "sweeps": [
                {"analysis": name, "start_hz": low, "stop_hz": high, "points": count}
                for name, low, high, count in sweeps
            ],
        }
        (output / "schematic.net").write_text(netlist, encoding="utf-8")
        settings_path = output / "settings.json"
        settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        CircuitSimulator().run_netlist(netlist, output_dir=str(output))
        path = output / f"{TESTBENCH_CELL}.ds"
        freq, samples, counts = _read_dataset(dataset, path, sweeps)
        settings["dataset_analyses"] = counts
        settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        return freq, samples, settings
    finally:
        try:
            if de.workspace_is_open():
                de.close_workspace()
        finally:
            os.chdir(previous_directory)
