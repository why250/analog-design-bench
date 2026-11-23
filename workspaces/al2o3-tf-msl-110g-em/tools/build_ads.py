"""Build one uniform-microstrip candidate in the task-owned ADS workspace.

Run this inside the ADS 2027 application session (classic Momentum export is
only available in application mode).  The workspace, ``MSL_R01_lib`` library
and ``Al2O3_MSL`` substrate must already exist; ``setup_workspace.py`` creates
them from an empty workspace.

The builder never replaces an existing cell.  Every candidate keeps its native
layout, copied emSetup view, construction receipt and exported solver deck.

Example (inside ADS):
    exec(open(r"...\\tools\\build_ads.py").read())
    build("MSL_Line_C01", length_mm=3.0, width_um=120.0, mesh_um=50.0,
          export_dir=r"...\\cases\\C01\\export")
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

import keysight.ads.de as de
from keysight.ads.de import db_uu as db
import keysight.ads.ael as ael

try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # exec() inside ADS
    _HERE = os.getcwd()
ROOT = os.environ.get("MSL_WORKSPACE_ROOT") or (
    os.path.dirname(_HERE) if os.path.basename(_HERE).lower() == "tools" else _HERE
)
WORKSPACE_NAME = "al2o3_msl_wrk"
LIBRARY = "MSL_R01_lib"
SUBSTRATE = "Al2O3_MSL"
GROUND_SUBSTRATE = "Al2O3_MSL_GND"
AU_GND_SUBSTRATE = "Al2O3_MSL_AuGND"
TEMPLATE_DIR = os.path.join(ROOT, "tools", "templates", "emSetup")
TEMPLATE = os.path.join(TEMPLATE_DIR, "emStateFile.xml")
COUPON_WIDTH_UM = 2000.0


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _portable_path(value: str) -> str:
    try:
        return os.path.relpath(value, ROOT).replace(os.sep, "/")
    except ValueError:
        return os.path.basename(value)


def _active_workspace():
    ws = de.active_workspace()
    if os.path.normcase(os.path.basename(str(ws.path))).lower() != WORKSPACE_NAME.lower():
        raise RuntimeError(f"Active workspace is not {WORKSPACE_NAME}: {ws.path}")
    return ws


def _set_text(root: ET.Element, path: str, text: str) -> None:
    el = root.find(path)
    if el is None:
        raise ValueError(f"Template lacks required element {path}")
    el.text = text


def _patch_emsetup(state_path: str, cell: str, length_mm: float, width_um: float,
                   mesh_um: float, workspace_path: str) -> None:
    tree = ET.parse(state_path)
    root = tree.getroot()
    _set_text(root, ".//MomLayout/workspaceText", workspace_path)
    _set_text(root, ".//MomLayout/libraryText", LIBRARY)
    _set_text(root, ".//MomLayout/cellText", cell)
    _set_text(root, ".//MomLayout/viewText", "layout")
    _set_text(root, ".//MomSubstrate/libSubstName", f"{LIBRARY}:{SUBSTRATE}")
    _set_text(root, ".//MomSubstrate/alternateSubstrate", "False")
    plan = root.find(".//MomSimFreqTable/freqPlanMap/MomSimFreqTableDef")
    if plan is None:
        raise ValueError("Template lacks the Momentum frequency plan")
    plan.find("startFreq").text = "0.1"
    plan.find("stopFreq").text = "110"
    plan.find("ptsFreq").text = "100 (max)"
    plan.find("startFreqUnit").text = "GHz"
    plan.find("stopFreqUnit").text = "GHz"
    mesh = root.find(".//MomSimOptMeshGlobal")
    if mesh is None:
        raise ValueError("Template lacks the Momentum mesh settings")
    mesh.find("MeshDensityMaxCellsizeEnabled").text = "True"
    mesh.find("MeshDensityMaxCellsize").text = f"{mesh_um:.17g}"
    mesh.find("MeshDensityMaxCellsizeUnit").text = "3"
    mesh.find("EdgeMeshEnabled").text = "True"
    mesh.find("MeshReductionEnabled").text = "False"
    for tag in ("givenDatasetName", "givenDdsName"):
        el = root.find(".//MomSimDataset/" + tag)
        if el is not None:
            el.text = cell
    # The template is the verified two-port explicit-reference setup.  Keep
    # P1/P2 on the signal line and P3/P4 on the bottom Au; fail loudly if the
    # template port structure has drifted.
    ports = root.findall(".//PortEditorDialog/PortView/Ports/Port")
    if len(ports) != 2:
        raise ValueError(f"Template must provide exactly two ports, found {len(ports)}")
    for port in ports:
        num = int(port.findtext("portNum"))
        plus = [x.text for x in port.findall("PlusPinNames/stdItem")]
        minus = [x.text for x in port.findall("MinusPinNames/stdItem")]
        expected = (["P1"], ["P3"]) if num == 1 else (["P2"], ["P4"])
        if (plus, minus) != expected:
            raise ValueError(f"Template port {num} has {plus}/{minus}, expected {expected}")
    tree.write(state_path, encoding="utf-8", xml_declaration=True)


def build(cell: str, length_mm: float, width_um: float, mesh_um: float,
          export_dir: str, *, model: str = "finite",
          frequency_max_samples: int = 100) -> dict:
    if not (cell.startswith("MSL_Line_C") and cell[10:].isdigit()):
        raise ValueError("Candidate cells must be MSL_Line_C<NN>")
    if model not in ("finite", "ground", "au_ground"):
        raise ValueError("model must be 'finite', 'ground' or 'au_ground'")
    if not (50.0 <= width_um <= 300.0):
        raise ValueError("Width is outside the frozen 50-300 um search range")
    if length_mm not in (3.0, 6.0):
        raise ValueError("Only the frozen 3.0 mm and 6.0 mm coupons are allowed")
    if not (5.0 <= mesh_um <= 100.0):
        raise ValueError("Mesh size is outside the practical frozen range")
    ws = _active_workspace()
    lib = de.Library.get(LIBRARY)
    if lib is None or not lib.is_writable:
        raise RuntimeError(f"{LIBRARY} is not an open writable library")
    if lib.cell_exists(cell):
        raise FileExistsError(f"Retained cell {cell!r} already exists")
    if not os.path.isfile(TEMPLATE):
        raise FileNotFoundError(TEMPLATE)
    if os.path.exists(export_dir):
        raise FileExistsError("Use a fresh export directory for every candidate")

    substrate = {"finite": SUBSTRATE, "ground": GROUND_SUBSTRATE,
                 "au_ground": AU_GND_SUBSTRATE}[model]
    length_um = length_mm * 1000.0
    design = db.create_layout(f"{LIBRARY}:{cell}:layout")
    top = design.create_layer_id("cond")
    pins = []
    if model == "finite":
        bottom = design.create_layer_id("cond2")
        design.add_rectangle(top, (0.0, -width_um / 2.0), (length_um, width_um / 2.0))
        design.add_rectangle(bottom, (0.0, -COUPON_WIDTH_UM / 2.0), (length_um, COUPON_WIDTH_UM / 2.0))
        layout_pins = ((1, 0.0, "cond", top), (2, length_um, "cond", top),
                       (3, 0.0, "cond2", bottom), (4, length_um, "cond2", bottom))
        expected = [[["P1"], ["P3"], 50.0, 0.0, 0, 0.0],
                    [["P2"], ["P4"], 50.0, 0.0, 0, 0.0]]
        expected_mapping = [["P1", "P3"], ["P2", "P4"]]
    else:
        design.add_rectangle(top, (0.0, -width_um / 2.0), (length_um, width_um / 2.0))
        layout_pins = ((1, 0.0, "cond", top), (2, length_um, "cond", top))
        expected = [[["P1"], [], 50.0, 0.0, 1, 0.0],
                    [["P2"], [], 50.0, 0.0, 1, 0.0]]
        expected_mapping = [["P1", None], ["P2", None]]
    for number, x, layer_name, layer in layout_pins:
        dot = design.add_dot(layer, (x, 0.0))
        net = design.find_or_add_net(f"P{number}")
        design.add_pin(design.add_term(net, f"P{number}"), dot)
        pins.append({"number": number, "x_um": x, "y_um": 0.0, "layer": layer_name})
    ael.call.db_set_port_definitions(design, expected)
    observed = ael.call.db_get_port_definitions(design)
    if hasattr(observed, "as_python_value"):
        observed = observed.as_python_value(convert=True)
    design.save_design()
    design.close_design()

    # A freshly created cell is not visible to the library's in-memory view
    # list until the library is refreshed.  Reopen it before registering the
    # emSetup view, otherwise create_view can return a non-persistent view.
    library_path = str(lib.path)
    lib.close()
    lib = de.Library.open(LIBRARY, library_path, de.LibraryMode.SHARED)

    # Register the emSetup view through the OA database.  ADS encodes upper
    # case cell names in the on-disk directory (for example MSL_Line_C03
    # becomes %M%S%L_%Line_%C03), so the view path must come from ADS, not a
    # hand-built path.
    cell_obj = lib.cell(cell)
    view = cell_obj.create_view("emSetup", "eesof_em_setup")
    target_dir = str(view.path)
    if not os.path.isdir(target_dir):
        raise RuntimeError(f"ADS did not create the emSetup directory {target_dir}")
    state_path = os.path.join(target_dir, "emStateFile.xml")
    shutil.copyfile(TEMPLATE, state_path)
    _patch_emsetup(state_path, cell, length_mm, width_um, mesh_um, str(ws.path))
    if model in ("ground", "au_ground"):
        tree = ET.parse(state_path)
        root = tree.getroot()
        _set_text(root, ".//MomSubstrate/libSubstName", f"{LIBRARY}:{substrate}")
        pin_parent = root.find(".//PortEditorDialog/PinView/Pins")
        for pin in list(pin_parent.findall("Pin")):
            if pin.findtext("pinName") in ("P3", "P4"):
                pin_parent.remove(pin)
        for port in root.findall(".//PortEditorDialog/PortView/Ports/Port"):
            port.find("feedType").text = "TML"
            gnd = port.find("gndLayer")
            if gnd is not None:
                gnd.text = ""
            minus = port.find("MinusPinNames")
            for item in list(minus):
                minus.remove(item)
            ET.SubElement(minus, "stdItem").text = "::__GND__"
        tree.write(state_path, encoding="utf-8", xml_declaration=True)

    os.makedirs(os.path.dirname(export_dir), exist_ok=True)
    result = ael.call.dex_em_writeSimulationFiles(LIBRARY, cell, "emSetup", export_dir)
    if not os.path.isdir(export_dir):
        raise RuntimeError(f"Momentum export did not create {export_dir}")
    required = ("proj.prt", "proj.pin", "proj.ltd", "proj.opt", "proj.sti")
    missing = [name for name in required if not os.path.isfile(os.path.join(export_dir, name))]
    if missing:
        raise RuntimeError(f"Export is missing {missing}")
    prt = ET.parse(os.path.join(export_dir, "proj.prt")).getroot()
    ports = prt.findall("./port_list/port")
    if len(ports) != 2:
        raise RuntimeError(f"Exported deck has {len(ports)} ports, expected 2")
    mapping = []
    for port in ports:
        mapping.append([port.findtext("plus_pin"), port.findtext("minus_pin")])
    if mapping != expected_mapping:
        raise RuntimeError(f"Exported port mapping is {mapping}, expected {expected_mapping}")

    receipt = {
        "schema_version": 1,
        "task_version_id": "al2o3-tf-msl-110g-em-r1",
        "created_utc": _utc(),
        "cell": cell,
        "library": LIBRARY,
        "model": model,
        "substrate": substrate,
        "workspace": _portable_path(str(ws.path)),
        "geometry": {"length_mm": length_mm, "width_um": width_um,
                     "dielectric_top_layout_width_um": COUPON_WIDTH_UM,
                     "coupon_width_um": COUPON_WIDTH_UM if model == "finite" else None,
                     "top_metal_um": 4.5,
                     "bottom_metal_um": 4.5 if model in ("finite", "au_ground") else None,
                     "dielectric_um": 127.0},
        "pins": pins,
        "native_port_definitions": observed,
        "exported_port_mapping": mapping,
        "expected_port_mapping": expected_mapping,
        "frequency_plan": {"start_ghz": 0.1, "stop_ghz": 110.0,
                           "adaptive_max_samples": frequency_max_samples},
        "requested_mesh_um": mesh_um,
        "export_dir": _portable_path(export_dir),
        "template": _portable_path(TEMPLATE),
        "export_result": repr(result),
    }
    with open(os.path.join(os.path.dirname(target_dir), "construction-receipt.json"), "w",
              encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2, default=str)
        stream.write("\n")
    with open(os.path.join(export_dir, "construction-receipt.json"), "w",
              encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2, default=str)
        stream.write("\n")
    return receipt


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cell", required=True)
    parser.add_argument("--length-mm", type=float, required=True)
    parser.add_argument("--width-um", type=float, required=True)
    parser.add_argument("--mesh-um", type=float, required=True)
    parser.add_argument("--export-dir", required=True)
    parser.add_argument("--model", choices=("finite", "ground", "au_ground"), default="finite")
    args = parser.parse_args()
    print(json.dumps(build(args.cell, args.length_mm, args.width_um,
                           args.mesh_um, args.export_dir, model=args.model),
                     indent=2, default=str))
