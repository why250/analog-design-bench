"""Generate an isolated native S2P probe netlist without running a simulator.

Use the ADS Python interpreter in a new headless process. Public API references:
ADS 2027 Library, Design, Instance, InstTerm and Param; simulation/run.
The installed ads_datacmps S2P item definition supplies Mode0 (linear),
ID1 (rectangular/ri), Type1 (touchstone), and StdForm temperature.
This probe discovers and labels every terminal rather than assuming pin order.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any


def probe(workspace_path: str | Path, model_path: str | Path) -> dict[str, Any]:
    """Create a fresh owned workspace, retain diagnostics, and close only it."""
    from keysight.ads import de
    from keysight.ads.de import db_uu as db

    if de.is_pde_app() or de.workspace_is_open():
        raise RuntimeError("Use a new headless process with no active workspace")
    workspace_path = Path(workspace_path).resolve()
    model_path = Path(model_path).resolve(strict=True)
    if workspace_path.exists():
        raise FileExistsError("Use a fresh probe workspace; preserve prior probes")
    if model_path.suffix.casefold() != ".s2p" or any(c in model_path.as_posix() for c in '\"\r\n'):
        raise ValueError("Supply an existing S2P file with an ordinary quoted path")
    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    workspace = de.create_workspace(str(workspace_path))
    workspace.open()
    report: dict[str, Any] = {"schema_version": 1,
                             "created_utc": datetime.now(timezone.utc).isoformat(),
                             "status": "PROBE_STARTED_NO_SIMULATION",
                             "simulation_executed": False,
                             "parent_filter_acceptance": "NOT EVALUATED"}
    try:
        library_path = workspace_path / "s2p_probe_lib"
        library = de.Library.create("s2p_probe_lib", library_path)
        workspace.add_library(library.name, library_path, de.LibraryMode.SHARED)
        library.setup_schematic_tech()
        design = db.create_schematic("s2p_probe_lib:probe:schematic")
        instance = design.add_instance(("ads_datacmps", "S2P", "symbol"),
                                       (0, 0), name="S2P1")
        parameters = {}
        for name in ("File", "Type", "InterpMode", "InterpDom", "ExtrapMode", "Temp",
                     "CheckPassivity", "EnforcePassivity"):
            parameter = instance.parameters[name]
            parameters[name] = {"original_form": parameter.form_name,
                                "original_value": parameter.value,
                                "original_netlist_value": parameter.netlist_value}
        report["parameters"] = parameters
        instance.parameters["File"].value = f'"{model_path.as_posix()}"'
        for name, form, expected in (("Type", "Type1", '"touchstone"'),
                                     ("InterpMode", "Mode0", '"linear"'),
                                     ("InterpDom", "ID1", '"ri"')):
            parameter = instance.parameters[name]
            parameter.form_name = form
            if parameter.netlist_value != expected:
                raise RuntimeError(f"Native {name} form did not produce the documented netlist value")
        instance.parameters["Temp"].value = "25"
        for name, record in parameters.items():
            parameter = instance.parameters[name]
            record.update({"effective_form": parameter.form_name,
                           "effective_value": parameter.value,
                           "effective_netlist_value": parameter.netlist_value})
        terminals = []
        for terminal in instance.inst_terms:
            number = terminal.term_number
            try:
                name = terminal.term_name
            except RuntimeError:
                name = None
            point = terminal.first_inst_pin.snap_point
            x, y = float(point.x), float(point.y)
            radius = math.hypot(x, y)
            dx, dy = (0.25 * x / radius, 0.25 * y / radius) if radius else (0.25, 0.0)
            label = f"probe_t{number}"
            design.add_wire([(x, y), (x + dx, y + dy)]).add_wire_label(label)
            terminals.append({"number": number, "name": name,
                              "snap_point_uu": [x, y], "net_label": label})
        report["terminals"] = terminals
        design.save_design()
        netlist = design.generate_netlist()
        (workspace_path / "probe.net").write_text(netlist, encoding="utf-8")
        report.update(status="NATIVE_NETLIST_GENERATED_NOT_SIMULATED",
                      native_netlist="probe.net", component="ads_datacmps:S2P:symbol")
        print(json.dumps(report, indent=2, allow_nan=False))
        print(netlist)
        return report
    except Exception as error:
        report.update(status="PROBE_INCOMPLETE", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        (workspace_path / "probe-receipt.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        de.close_workspace()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True,
                        help="Fresh standalone probe workspace in task-owned active/work")
    parser.add_argument("--model", type=Path, required=True,
                        help="Existing complete 50-ohm two-port S2P file")
    args = parser.parse_args()
    probe(args.workspace, args.model)


if __name__ == "__main__":
    main()
