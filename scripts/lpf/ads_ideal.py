"""Native headless ADS adapter for the ideal low-pass ladder."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

from .ideal import PHYSICS_TOLERANCE, PORT_ORDER


DUT_LIBRARY = "LPF_R01_lib"
TB_LIBRARY = "LPF_R01_tb_lib"
DUT_CELL = "LPF_Ideal"
TESTBENCH_CELL = "TB_LPF_Ideal_SP"


def _runtime_helper():
    try:
        from scripts import ads_project_kit_runtime as runtime

        return runtime
    except ImportError:
        scripts_dir = str(Path(__file__).resolve().parents[1])
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import ads_project_kit_runtime as runtime

        return runtime


def _place_port(design, db, number, name, xy, angle=0):
    net = design.find_or_add_net(name)
    term = design.add_numbered_term(net, name, number, db.TermType.INPUT_OUTPUT)
    design.add_pin(term, design.add_dot_for_pin(xy), angle=angle)


def _build_dut(de, db, design_builder, symbol_generator, design_values, *, dut_lib=DUT_LIBRARY, dut_cell=DUT_CELL):
    builder = design_builder.build_schematic(f"{dut_lib}:{dut_cell}:schematic")
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

    symbol = db.create_symbol(f"{dut_lib}:{dut_cell}:symbol")
    generator = symbol_generator(symbol, design, 0.5, 1.0)
    generator.is_dual_symbol_type = True
    generator.should_replace = True
    generator.pin_shape = "square"
    generator.generate_symbol()
    symbol.save_design()


def _build_testbench(
    de,
    design_builder,
    impedance,
    sweeps,
    *,
    dut_lib=DUT_LIBRARY,
    dut_cell=DUT_CELL,
    tb_lib=TB_LIBRARY,
    tb_cell=TESTBENCH_CELL,
):
    builder = design_builder.build_schematic(f"{tb_lib}:{tb_cell}:schematic")
    testbench = builder.design
    transaction = de.db.Transaction(testbench, "Connect external ports and sweep controllers")
    dut = builder.place_instance((dut_lib, dut_cell, "symbol"), (6, 0), name="DUT")
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


def simulate_ideal(
    spec,
    design,
    sweeps,
    workspace_path: Path,
    output: Path,
    *,
    ads_project_kit_src: Path | None = None,
    dut_lib: str = DUT_LIBRARY,
    tb_lib: str = TB_LIBRARY,
    dut_cell: str = DUT_CELL,
    tb_cell: str = TESTBENCH_CELL,
):
    """Build a fresh convention-compliant ADS workspace via ads_project_kit and simulate."""
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
    if not workspace_path.name.endswith("_wrk") or len(workspace_path.name) <= 4:
        raise ValueError(f"ADS workspace directory must end with '_wrk': {workspace_path.name!r}")
    project_name = workspace_path.name[:-4]

    runtime = _runtime_helper()
    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    created = runtime.create_ads_project(
        workspace_path,
        project_name,
        (dut_lib, tb_lib),
        setup_schematic_tech=True,
        src_path=ads_project_kit_src,
        validate_native=True,
    )

    output.mkdir(parents=True, exist_ok=False)
    previous_directory = Path.cwd()
    workspace = None
    try:
        workspace = de.open_workspace(workspace_path)
        _build_dut(
            de,
            db_uu,
            DesignBuilder,
            SymbolGenerator,
            design,
            dut_lib=dut_lib,
            dut_cell=dut_cell,
        )
        testbench = _build_testbench(
            de,
            DesignBuilder,
            spec["impedance_ohm"],
            sweeps,
            dut_lib=dut_lib,
            dut_cell=dut_cell,
            tb_lib=tb_lib,
            tb_cell=tb_cell,
        )
        netlist = testbench.generate_netlist()
        settings = {
            "ads_product_version": de.product_version().strip(),
            "ads_python_package_version": str(de.__version__),
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "ads_project_kit": created["ads_project_kit"],
            "project_validation": created["validation"],
            "dut": f"{dut_lib}:{dut_cell}:schematic",
            "testbench": f"{tb_lib}:{tb_cell}:schematic",
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
        path = output / f"{tb_cell}.ds"
        if not path.is_file():
            datasets = list(output.glob("*.ds"))
            if len(datasets) != 1:
                raise RuntimeError(f"Expected one ADS dataset in {output}, found {len(datasets)}")
            path = datasets[0]
        freq, samples, counts = _read_dataset(dataset, path, sweeps)
        settings["dataset_analyses"] = counts
        settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            if workspace is not None and workspace.is_open:
                workspace.close()
            elif de.workspace_is_open():
                de.close_workspace()
        finally:
            os.chdir(previous_directory)

    reopened_validation = runtime.validate_ads_project(
        workspace_path,
        native=True,
        src_path=ads_project_kit_src,
    )
    settings["reopened_validation"] = reopened_validation
    (output / "settings.json").write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    if not reopened_validation["native_validated"]:
        raise runtime.AdsProjectKitError(
            "Post-simulation native validation failed for ADS workspace: "
            + json.dumps(reopened_validation, ensure_ascii=False)
        )
    return freq, samples, settings
