"""Build editable fixed-coefficient Stage 2 ADS DUTs and external-port benches.

Run in an ADS 2027 Python session. Task-owned support supplies workspace
switching, terminal creation and annotation helpers. Every zero parasitic branch
is omitted or bypassed explicitly.
"""

from __future__ import annotations

import copy
from pathlib import Path

from keysight.ads import de
from keysight.ads.de import db_uu as db
from keysight.ads.de.experimental import DesignBuilder
from keysight.ads.de.experimental.generate_symbol import SymbolGenerator

try:
    from . import ads_support as _support
    from .model import validate, validate_element
except ImportError:
    import ads_support as _support
    from model import validate, validate_element

LIBRARY = "inp_lpf_stage2_lib"
DUT = f"{LIBRARY}:inp_lpf:schematic"
SYMBOL = f"{LIBRARY}:inp_lpf:symbol"
TESTBENCH = f"{LIBRARY}:inp_lpf_sp:schematic"
_last_build = None


def _library(workspace_path):
    workspace_path = Path(workspace_path).resolve()
    workspace = _support._switch_workspace(workspace_path)
    if LIBRARY not in workspace.library_names:
        library_path = workspace_path / LIBRARY
        de.create_new_library(LIBRARY, library_path)
        workspace.add_library(LIBRARY, library_path, de.LibraryMode.NON_SHARED)
    return workspace


def _primitive(builder, kind, name, value, xy, *, angle=0, rs_ohm=0):
    instance = builder.place_instance(("ads_rflib", kind, "symbol"), xy,
                                      name=name, angle=angle)
    units = {"L": "H", "C": "F", "R": "Ohm"}
    instance.parameters[kind].value = f"{value:.17g} {units[kind]}"
    if kind == "L":
        instance.parameters["R"].value = f"{rs_ohm:.17g} Ohm"
        instance.parameters["Noise"].value = "no"
    return instance


def _inductor(builder, element, xy):
    name = element["name"]
    x, y = xy
    inductor = _primitive(builder, "L", name, element["value_si"], xy,
                          rs_ohm=element["rs_ohm"])
    instances = {name: inductor}
    if element["cp_f"] > 0:
        cap = _primitive(builder, "C", f"{name}_Cp", element["cp_f"], (x, y+3.0))
        builder.make_connection((inductor, 1), (cap, 1))
        builder.make_connection((cap, 2), (inductor, 2))
        instances[f"{name}_Cp"] = cap
    return (inductor, 1), (inductor, 2), instances


def _capacitor(builder, element, xy):
    name = element["name"]
    x, y = xy
    chain = []
    instances = {}
    if element["esr_ohm"] > 0:
        resistor = _primitive(builder, "R", f"{name}_ESR", element["esr_ohm"],
                               (x, y), angle=-90)
        chain.append(resistor)
        instances[f"{name}_ESR"] = resistor
    if element["esl_h"] > 0:
        inductor = _primitive(builder, "L", f"{name}_ESL", element["esl_h"],
                               (x, y-3*len(chain)), angle=-90)
        chain.append(inductor)
        instances[f"{name}_ESL"] = inductor
    capacitor = _primitive(builder, "C", name, element["value_si"],
                           (x, y-3*len(chain)), angle=-90)
    chain.append(capacitor)
    instances[name] = capacitor
    for index, (first, second) in enumerate(zip(chain[:-1], chain[1:]), 1):
        builder.make_connection((first, 2), (second, 1), f"{name}_series{index}")
    return (chain[0], 1), (chain[-1], 2), instances


def _symbol(design, overwrite):
    if overwrite:
        try:
            symbol = db.open_design(SYMBOL, "Append")
            symbol.clear_design()
        except RuntimeError:
            symbol = db.create_symbol(SYMBOL)
    else:
        symbol = db.create_symbol(SYMBOL)
    generator = SymbolGenerator(symbol, design, 0.5, 1.0)
    generator.is_dual_symbol_type = True
    generator.should_replace = True
    generator.pin_shape = "square"
    generator.generate_symbol()
    symbol.save_design()
    return symbol


def _sweeps(builder, sweeps):
    instances = {}
    for index, (name, start, stop, points) in enumerate(sweeps):
        if start <= 0 or stop < start or points < 1:
            raise ValueError(f"Invalid positive-frequency sweep: {name}")
        controller = builder.place_instance(("ads_simulation", "S_Param", "symbol"),
                        (index % 5 * 6, 5 + index // 5 * 5), name=name)
        _set_sweep(controller, start, stop, points)
        instances[name] = controller
    return instances


def _set_sweep(controller, start, stop, points):
    for key, value in {"Start": f"{start:.17g} Hz", "Stop": f"{stop:.17g} Hz",
                       "Step": "", "Lin": str(points), "Dec": "", "Log": "",
                       "CalcNoise": "no"}.items():
        controller.parameters[key].value = value


def _termination(builder, number, x):
    port = builder.place_instance(("ads_simulation", "Term", "symbol"),
                                  (x, 0), name=f"Term{number}", angle=-90)
    port.parameters["Num"].value = str(number)
    port.parameters["Z"].value = "50 Ohm"
    port.parameters["Noise"].value = "no"
    ground = builder.place_instance(("ads_rflib", "GROUND", "symbol"),
                                    (x, -2), name=f"GND{number}", angle=-90)
    builder.make_connection((port, 2), (ground, 1))
    return port


def branch_signature(manifest):
    """Native topology signature; a zero/nonzero crossing requires a rebuild."""
    validate(manifest)
    return tuple((e["name"], e["cp_f"] > 0) if e["kind"] == "L" else
                 (e["name"], e["esr_ohm"] > 0, e["esl_h"] > 0)
                 for e in manifest["elements"])


def build(workspace_path, manifest, sweeps, *, overwrite=False):
    """Create the Stage 2 native DUT/symbol/bench and return its bench design.

    ``sweeps`` contains (name, start_hz, stop_hz, linear_point_count) tuples.
    Values are literal physical coefficients, with no Q/SRF generator equations
    left in ADS. The caller retains manifests, native snapshots and evidence.
    """
    global _last_build
    validate(manifest)
    _library(workspace_path)
    builder = DesignBuilder.build_schematic(DUT, overwrite=overwrite)
    design = builder.design
    transaction = de.db.Transaction(design, "Build Stage 2 fixed-coefficient RLC ladder")
    _support._port(design, 1, "rfin", (0, 0), 180)
    _support._port(design, 2, "rfout", (40, 0))
    _support._port(design, 3, "gnd", (0, -11), 180)
    inductors, capacitors, primitives = [], [], {}
    for element in manifest["elements"]:
        index = int(element["name"][1:])-1
        if element["kind"] == "L":
            first, last, placed = _inductor(builder, element, (4+8*index, 0))
            inductors.append((first, last))
        else:
            x = 8+8*index
            first, last, placed = _capacitor(builder, element, (x, -2))
            extra = int(element["esr_ohm"] > 0) + int(element["esl_h"] > 0)
            capacitors.append((first, last, (x, -3-3*extra)))
        primitives.update(placed)
    builder.make_connection(1, inductors[0][0], "rfin")
    builder.make_connection(inductors[-1][1], 2, "rfout")
    for index, (first, last, bottom_xy) in enumerate(capacitors):
        node = f"n{index+1}"
        builder.make_connection(inductors[index][1], first, node)
        builder.make_connection(first, inductors[index+1][0], node)
        # Keep ground below every optional series primitive. Long auto-routes
        # could otherwise cross a neighboring arm's internal ESR/ESL node.
        design.add_wire([bottom_xy, (bottom_xy[0], -11)])
    design.add_wire([(0, -11), (32, -11)])
    _support._text(design, "Stage 2 | fixed-coefficient synthetic RLC | 65 GHz / 50 Ohm",
                  (0, 5.0), .24)
    _support._text(design, "Series arm: (Rs + L) || Cp; shunt arm: ESR + ESL + C",
                  (0, 4.4), .18)
    _support._text(design, "Explicit DUT terminals: rfin, rfout, gnd | no internal loads",
                  (0, -12.0), .18)
    _support._text(design, "Zero loss/parasitics are bypassed or omitted | no PDK capability claim",
                  (0, -12.6), .18)
    transaction.commit()
    _support._format_annotations(design)
    builder.save_design()
    symbol = _symbol(design, overwrite)

    tbuilder = DesignBuilder.build_schematic(TESTBENCH, overwrite=overwrite)
    testbench = tbuilder.design
    transaction = de.db.Transaction(testbench, "Build external 50 Ohm Stage 2 bench")
    dut = tbuilder.place_instance((LIBRARY, "inp_lpf", "symbol"), (7, 0), name="DUT")
    p1 = _termination(tbuilder, 1, 0)
    p2 = _termination(tbuilder, 2, 16)
    ground = tbuilder.place_instance(("ads_rflib", "GROUND", "symbol"),
                                     (9, -4), name="GND_DUT", angle=-90)
    tbuilder.make_connection((p1, 1), (dut, 1), "rfin")
    tbuilder.make_connection((dut, 2), (p2, 1), "rfout")
    tbuilder.make_connection((dut, 3), (ground, 1))
    controllers = _sweeps(tbuilder, sweeps)
    _support._text(testbench, "External 50 Ohm ports; reference planes at bare DUT terminals",
                  (0, -5), .18)
    _support._text(testbench, "65 GHz passband edge | 80 GHz checkpoint | positive-frequency SP",
                  (0, -5.6), .18)
    transaction.commit()
    _support._format_annotations(testbench)
    tbuilder.save_design()
    _last_build = {"workspace": Path(workspace_path).resolve(), "manifest": copy.deepcopy(manifest),
                   "signature": branch_signature(manifest), "dut": design, "symbol": symbol,
                   "bench": testbench, "primitives": primitives, "controllers": controllers}
    return testbench


def update_values(manifest, sweeps=None):
    """Update literals in the most recent build without changing branch topology.

    The function refuses to update a different workspace or zero-branch pattern.
    Invoke ``build(..., overwrite=True)`` for such changes. Sweep names/counts
    must also stay fixed; frequency endpoints and point counts may change.
    """
    validate(manifest)
    if _last_build is None or not de.workspace_is_open():
        raise RuntimeError("No Stage 2 build is active in this Python process")
    if Path(de.active_workspace().path).resolve() != _last_build["workspace"]:
        raise RuntimeError("The active workspace differs from the last Stage 2 build")
    if branch_signature(manifest) != _last_build["signature"]:
        raise ValueError("Zero/nonzero parasitic branches changed; rebuild the native design")
    if sweeps is not None and [s[0] for s in sweeps] != list(_last_build["controllers"]):
        raise ValueError("Sweep names changed; rebuild the native bench")
    design = _last_build["dut"]
    transaction = de.db.Transaction(design, "Update Stage 2 physical coefficients")
    for element in manifest["elements"]:
        name, kind = element["name"], element["kind"]
        instance = _last_build["primitives"][name]
        instance.parameters[kind].value = f'{element["value_si"]:.17g} {"H" if kind == "L" else "F"}'
        if kind == "L":
            instance.parameters["R"].value = f'{element["rs_ohm"]:.17g} Ohm'
            if element["cp_f"] > 0:
                _last_build["primitives"][f"{name}_Cp"].parameters["C"].value = f'{element["cp_f"]:.17g} F'
        else:
            if element["esr_ohm"] > 0:
                _last_build["primitives"][f"{name}_ESR"].parameters["R"].value = f'{element["esr_ohm"]:.17g} Ohm'
            if element["esl_h"] > 0:
                _last_build["primitives"][f"{name}_ESL"].parameters["L"].value = f'{element["esl_h"]:.17g} H'
    transaction.commit()
    design.save_design()
    if sweeps is not None:
        bench = _last_build["bench"]
        transaction = de.db.Transaction(bench, "Update Stage 2 frequency sweeps")
        for name, start, stop, points in sweeps:
            _set_sweep(_last_build["controllers"][name], start, stop, points)
        transaction.commit()
        bench.save_design()
    _last_build["manifest"] = copy.deepcopy(manifest)
    return _last_build["bench"]


def build_unit(workspace_path, element, sweeps, *, cell="unit_device_sp", overwrite=False):
    """Create a native one-port device bench for impedance/admittance checks.

    The device spans the signal node and ideal bench ground. Its one-port
    reflection gives Z=50*(1+S11)/(1-S11), or Y=(1-S11)/(50*(1+S11)) near an
    impedance pole. The caller chooses conditioning and retains both where valid.
    """
    validate_element(element)
    _library(workspace_path)
    view = f"{LIBRARY}:{cell}:schematic"
    builder = DesignBuilder.build_schematic(view, overwrite=overwrite)
    design = builder.design
    transaction = de.db.Transaction(design, "Build isolated Stage 2 one-port device")
    port = _termination(builder, 1, 0)
    if element["kind"] == "L":
        first, last, _ = _inductor(builder, element, (5, 0))
        ground_xy = (8, -2)
    else:
        first, last, _ = _capacitor(builder, element, (5, 0))
        ground_xy = (5, -10)
    ground = builder.place_instance(("ads_rflib", "GROUND", "symbol"),
                                    ground_xy, name="GND_DEVICE", angle=-90)
    builder.make_connection((port, 1), first, "device_input")
    builder.make_connection(last, (ground, 1))
    _sweeps(builder, sweeps)
    _support._text(design, "Isolated synthetic device | external 50 Ohm one-port reference",
                  (0, -12), .18)
    transaction.commit()
    _support._format_annotations(design)
    builder.save_design()
    return design


def print_schematic(path):
    """Export the native Stage 2 DUT drawing without changing its circuit."""
    design = db.open_design(DUT)
    design.print_design(str(Path(path)), box=de.BoxF(x1=-2, y1=-14, x2=44, y2=7))
