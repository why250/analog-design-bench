"""Task-owned ADS workspace and drawing helpers.

These small helpers are extracted without behavioral changes from
workspaces/inp-lpf/tools/rebuild_ads.py at baseline commit
558504a1d5106fd08ca3e740a3ecc0860cbac603. The normalized task does not import
the live Stage 1 engineering workspace or its synthesis/simulation runner.
"""
from __future__ import annotations

from pathlib import Path

from keysight.ads import ael, de
from keysight.ads.de import db_uu as db


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
