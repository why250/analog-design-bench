"""Build or replay the shunt-first ideal filter with ADS automation Python."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tomllib

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "inputs" / "tool-source"))

from lpf import ads_ideal, ideal
from lpf.specification import load_spec


def synthesize_dual(spec):
    """Use the reciprocal impedance dual of the series-first prototype."""
    design = ideal.synthesize(spec)
    z_squared = design["impedance_ohm"] ** 2
    for position, element in enumerate(design["elements"], start=1):
        name = (position + 1) // 2
        if element["kind"] == "L":
            element.update(name=f"C{name}", kind="C", unit="F",
                           connection="shunt_to_ground", value=element["value"] / z_squared)
        else:
            element.update(name=f"L{name}", kind="L", unit="H",
                           connection="series", value=element["value"] * z_squared)
    design["family"] = "chebyshev_i_shunt_first_dual"
    return design


def build_dut(de, db, builder_type, generator_type, values):
    library, cell = ads_ideal.LIBRARY, ads_ideal.DUT_CELL
    builder = builder_type.build_schematic(f"{library}:{cell}:schematic")
    design = builder.design
    transaction = de.db.Transaction(design, "Build the shunt-first ideal LC ladder")
    last_shunt = values["order"] // 2
    output_x = 4 * last_shunt + 4
    ads_ideal._place_port(design, db, 1, "rfin", (0, 0), 180)
    ads_ideal._place_port(design, db, 2, "rfout", (output_x, 0))
    ads_ideal._place_port(design, db, 3, "gnd", (0, -3.8), 180)
    inductors, capacitors = [], []
    for index, element in enumerate(values["elements"]):
        x = 2 + 4 * (index // 2)
        if element["kind"] == "C":
            capacitor = builder.place_instance(
                ("ads_rflib", "C", "symbol"), (x, -1.4), name=element["name"], angle=-90
            )
            capacitor.parameters["C"].value = f'{element["value"]:.17g} F'
            capacitors.append(capacitor)
            design.add_wire([(x, -2.4), (x, -3.8)])
        else:
            inductor = builder.place_instance(
                ("ads_rflib", "L", "symbol"), (x + 1.5, 0), name=element["name"]
            )
            inductor.parameters["L"].value = f'{element["value"]:.17g} H'
            inductor.parameters["R"].value = "0 Ohm"
            inductor.parameters["Noise"].value = "no"
            inductors.append(inductor)
    builder.make_connection(1, (capacitors[0], 1), "rfin")
    builder.make_connection((capacitors[-1], 1), 2, "rfout")
    nodes = ["rfin", *(f"n{k}" for k in range(1, last_shunt)), "rfout"]
    for index, inductor in enumerate(inductors):
        builder.make_connection((capacitors[index], 1), (inductor, 1), nodes[index])
        builder.make_connection((inductor, 2), (capacitors[index + 1], 1), nodes[index + 1])
    design.add_wire([(0, -3.8), (output_x - 2, -3.8)])
    design.add_text(
        db.LayerId(231), "Shunt-first Chebyshev-I LC low-pass filter", (0, 1.8), "Arial", 0.20
    )
    transaction.commit()
    builder.save_design()

    symbol = db.create_symbol(f"{library}:{cell}:symbol")
    generator = generator_type(symbol, design, 0.5, 1.0)
    generator.is_dual_symbol_type = True
    generator.should_replace = True
    generator.pin_shape = "square"
    generator.generate_symbol()
    symbol.save_design()


def check_netlist(netlist, design):
    cell = ads_ideal.DUT_CELL
    pattern = rf"^define {cell}\s*\(\s*rfin\s+rfout\s+gnd\s*\)\s*\n(.*?)^end {cell}\s*$"
    match = re.search(pattern, netlist, re.MULTILINE | re.DOTALL)
    if match is None:
        raise ValueError("Netlisted DUT terminal order differs from the task.")
    records = {
        parts[0]: parts[1:]
        for line in match[1].splitlines()
        if (parts := line.split()) and not parts[0].startswith(";")
    }
    count = design["order"] // 2
    nodes = ["rfin", *(f"n{k}" for k in range(1, count)), "rfout"]
    for element in design["elements"]:
        kind, name = element["kind"], element["name"]
        index = int(name[1:]) - 1
        expected = [nodes[index], "gnd"] if kind == "C" else nodes[index:index + 2]
        actual, terminal, value, unit, *extra = records.pop(f"{kind}:{name}")
        if ([actual, terminal] != expected or unit != element["unit"]
                or not value.startswith(f"{kind}=")
                or not math.isclose(float(value[2:]), element["value"], rel_tol=1e-13)
                or (kind == "L" and extra[:2] != ["R=0", "Ohm"])):
            raise ValueError(f"Netlist parameters or connections disagree for {name}.")
    if records:
        raise ValueError("The DUT netlist contains unexpected elements.")
    ports = re.findall(r"^Port:Term[12]\s+(\w+)\s+0\s+Num=(\d+)\s+Z=(\d+) Ohm", netlist, re.M)
    impedance = f'{design["impedance_ohm"]:g}'
    if ports != [("rfin", "1", impedance), ("rfout", "2", impedance)]:
        raise ValueError("The testbench does not own the required numbered terminations.")
    if not re.search(rf"^{cell}:DUT\s+rfin\s+rfout\s+0\s*$", netlist, re.M):
        raise ValueError("The testbench does not connect the DUT in port order.")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def simulate(workspace_path, output, spec, design, sweeps, replay):
    from keysight.ads import dataset, de
    from keysight.ads.de import db_uu
    from keysight.ads.de.experimental import DesignBuilder
    from keysight.ads.de.experimental.generate_symbol import SymbolGenerator
    from keysight.edatoolbox.ads import CircuitSimulator

    if de.is_pde_app() or de.workspace_is_open():
        raise RuntimeError("Run in a fresh ADS automation process.")
    output.mkdir()
    previous_directory = Path.cwd()
    testbench_view = f"{ads_ideal.LIBRARY}:{ads_ideal.TESTBENCH_CELL}:schematic"
    try:
        if replay:
            de.open_workspace(workspace_path)
            testbench = db_uu.open_design(testbench_view)
        else:
            workspace_path.parent.mkdir(exist_ok=True)
            workspace = de.create_workspace(workspace_path)
            workspace.open()
            library_path = workspace_path / ads_ideal.LIBRARY
            de.create_new_library(ads_ideal.LIBRARY, library_path)
            workspace.add_library(ads_ideal.LIBRARY, library_path, de.LibraryMode.NON_SHARED)
            build_dut(de, db_uu, DesignBuilder, SymbolGenerator, design)
            testbench = ads_ideal._build_testbench(de, DesignBuilder, spec["impedance_ohm"], sweeps)
        netlist = testbench.generate_netlist()
        (output / "schematic.net").write_text(netlist, encoding="utf-8")
        check_netlist(netlist, design)
        settings = {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "ads_product_version": de.product_version().strip(),
            "ads_python_package_version": str(de.__version__),
            "execution_mode": "automation",
            "testbench": testbench_view,
            "dut_ports": ["rfin", "rfout", "gnd"],
            "reference_impedance_ohm": spec["impedance_ohm"],
            "netlist_sha256": hashlib.sha256(netlist.encode("utf-8")).hexdigest(),
            "sweeps": [
                {"analysis": name, "start_hz": start, "stop_hz": stop, "points": points}
                for name, start, stop, points in sweeps
            ],
        }
        write_json(output / "settings.json", settings)
        CircuitSimulator().run_netlist(netlist, output_dir=str(output))
        dataset_path = output / f"{ads_ideal.TESTBENCH_CELL}.ds"
        freq, samples, settings["dataset_analyses"] = ads_ideal._read_dataset(
            dataset, dataset_path, sweeps
        )
        write_json(output / "settings.json", settings)
        return freq, samples, settings
    finally:
        try:
            if de.workspace_is_open():
                de.close_workspace()
        finally:
            os.chdir(previous_directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="Fresh UTC-named results subdirectory")
    parser.add_argument("--replay", action="store_true", help="Use the existing native ADS source")
    parser.add_argument("--synthesize", action="store_true", help="Print synthesis as JSON")
    args = parser.parse_args()
    with (PROJECT / "project.toml").open("rb") as stream:
        project = tomllib.load(stream)
    paths = {key: (PROJECT / path).resolve() for key, path in project["paths"].items()}
    if any(not path.is_relative_to(PROJECT) for path in paths.values()):
        raise ValueError("The project manifest contains a path outside the workspace.")
    with (paths["specification_snapshot"] / "task.toml").open("rb") as stream:
        task = tomllib.load(stream)["metadata"]
    identity = project["project"]
    if any(identity[key] != task[key] for key in ("task_id", "revision")):
        raise ValueError("The project and frozen task disagree.")
    spec = load_spec(paths["inputs"] / "spec.toml")
    design = synthesize_dual(spec)
    if args.synthesize:
        print(json.dumps(design, indent=2, allow_nan=False))
        return 0
    if not args.run_id or not re.fullmatch(r"\d{8}T\d{6}Z-[a-z0-9-]+", args.run_id):
        parser.error("--run-id must be a UTC timestamp followed by a descriptive suffix")
    if paths["ads"].exists() != args.replay:
        parser.error("Use --replay for an existing native workspace. A build needs a fresh ADS path.")
    output = paths["results"] / args.run_id
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "design.json", design)
    sweeps = ideal.sweep_plan(spec, design)
    freq, samples, settings = simulate(
        paths["ads"], output / "ads-simulation", spec, design, sweeps, args.replay
    )
    measurement = ideal._verify(spec, design, sweeps, freq, samples)
    report = {
        "passed": measurement["passes"],
        "verification": "ads",
        "design": design,
        "measurement": measurement,
        "sample_count": len(freq),
        "frequency_range_hz": [float(freq[0]), float(freq[-1])],
        "sweeps": settings["sweeps"],
        "ads": settings,
        "task": identity,
        "run_id": args.run_id,
    }
    ideal._write_sparameters(output, freq, samples, spec["impedance_ohm"], "ADS circuit simulation")
    ideal._write_plot(output, spec, freq, samples, "ADS circuit simulation")
    ideal._write_report(output, spec, report)
    write_json(output / "ideal.json", report)
    print(f"{'PASS' if report['passed'] else 'FAIL'} {output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
