"""Create the task-owned ADS workspace, library and frozen substrates.

Run inside the ADS 2027 application session from an empty or already-open
workspace.  The script is idempotent for the workspace/library/material
definitions; it refuses to replace a substrate that already exists.

    exec(open(r"...\\tools\\setup_workspace.py").read())
    setup()

Substrates:
  Al2O3_MSL      - 127 um Al2O3, 4.5 um Au top and finite 4.5 um Au bottom,
                   open AIR above and below (the frozen DUT stack).
  Al2O3_MSL_GND  - same dielectric and top metal, but the bottom is the solver
                   PERFECT_CONDUCTOR cover (declared numerical control only).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import keysight.ads.de as de
from keysight.ads import subst

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


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _open_workspace() -> tuple[object, object]:
    workspace_path = os.path.join(ROOT, "ads", WORKSPACE_NAME)
    os.makedirs(os.path.dirname(workspace_path), exist_ok=True)
    if os.path.isdir(workspace_path) and not os.listdir(workspace_path):
        os.rmdir(workspace_path)
    if os.path.isdir(workspace_path):
        ws = de.open_workspace(workspace_path)
    else:
        ws = de.create_workspace(workspace_path)
    ws.open()
    library_path = os.path.join(workspace_path, LIBRARY)
    if LIBRARY in ws.library_names:
        lib = de.Library.get(LIBRARY)
    else:
        lib = de.create_new_library(LIBRARY, library_path)
        ws.add_library(LIBRARY, library_path, de.LibraryMode.SHARED)
    if not lib.has_tech:
        lib.create_layout_tech_std_ads("micron", 1000)
    if not lib.is_writable:
        raise RuntimeError("MSL_R01_lib must be writable")
    return ws, lib


def _install_materials(lib) -> None:
    materials = subst.copy_predefined_materials()
    if not any(item.name == "Al2O3_MSL" for item in materials.dielectrics):
        dielectric = subst.SubstrateDielectric("Al2O3_MSL")
        dielectric.er_real = "9.9"
        dielectric.er_loss_tangent = "1e-4"
        materials.dielectrics.add(dielectric)
    subst.save_materials(os.path.join(str(lib.path), "materials.matdb"), materials)
    lib.close()
    reopened = de.Library.open(LIBRARY, str(lib.path), de.LibraryMode.SHARED)
    if "Al2O3_MSL" not in subst.get_dielectric_names(reopened):
        raise RuntimeError("Al2O3_MSL material was not loaded from materials.matdb")
    return reopened


def _make_finite_substrate(lib) -> None:
    if subst.substrate_exists(lib, SUBSTRATE):
        return
    substrate = subst.create_substrate(lib, SUBSTRATE)
    substrate.insert_material_and_interface_above(0)
    dielectric = substrate.materials[1]
    dielectric.material_name = "Al2O3_MSL"
    dielectric.thickness_expr = "127"
    dielectric.thickness_unit = subst.Unit.MICRON
    top = substrate.insert_layer(substrate.interfaces[2], de.ProcessRole.CONDUCTOR)
    top.layer_number = 1
    top.material_name = "Au"
    top.sheet = False
    top.expand = True
    top.thickness_expr = "4.5"
    top.thickness_unit = subst.Unit.MICRON
    top.is_above = True
    bottom = substrate.insert_layer(substrate.interfaces[1], de.ProcessRole.CONDUCTOR)
    bottom.layer_number = 2
    bottom.material_name = "Au"
    bottom.sheet = False
    bottom.expand = True
    bottom.thickness_expr = "4.5"
    bottom.thickness_unit = subst.Unit.MICRON
    bottom.is_above = False
    substrate.save_substrate()


def _make_ground_substrate(lib) -> None:
    if subst.substrate_exists(lib, GROUND_SUBSTRATE):
        return
    substrate = subst.create_substrate(lib, GROUND_SUBSTRATE)
    substrate.interfaces[0].convert_to_cover()
    dielectric = substrate.materials[0]
    dielectric.material_name = "Al2O3_MSL"
    dielectric.thickness_expr = "127"
    dielectric.thickness_unit = subst.Unit.MICRON
    top = substrate.insert_layer(substrate.interfaces[1], de.ProcessRole.CONDUCTOR)
    top.layer_number = 1
    top.material_name = "Au"
    top.sheet = False
    top.expand = True
    top.thickness_expr = "4.5"
    top.thickness_unit = subst.Unit.MICRON
    top.is_above = True
    substrate.save_substrate()


def setup() -> dict:
    ws, lib = _open_workspace()
    lib = _install_materials(lib)
    _make_finite_substrate(lib)
    _make_ground_substrate(lib)
    receipt = {
        "schema_version": 1,
        "task_version_id": "al2o3-tf-msl-110g-em-r1",
        "created_utc": _utc(),
        "workspace": str(ws.path),
        "library": LIBRARY,
        "library_path": str(lib.path),
        "substrates": [SUBSTRATE, GROUND_SUBSTRATE],
        "materials": {
            "Al2O3_MSL": {"er": 9.9, "loss_tangent": "1e-4"},
            "Au": {"conductivity": "4.1e7"},
        },
        "geometry": {"dielectric_um": 127.0, "metal_um": 4.5},
    }
    run_dir = os.path.join(ROOT, "results", "20261119T065241Z-msl-em-execution", "work", "setup")
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "setup-receipt.json"), "w", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return receipt


if __name__ == "__main__":
    print(json.dumps(setup(), indent=2))
