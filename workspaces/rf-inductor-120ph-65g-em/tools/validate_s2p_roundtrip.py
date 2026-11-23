"""Validate native ADS consumption of a complete two-port S2P in isolation.

Run only in a new headless ADS Python process. The helper creates its own fresh
workspace and generates native S2P/Term/S_Param netlists with public APIs, then
uses keysight.edatoolbox.ads.CircuitSimulator.run_netlist. It never opens the
parent workspace or modifies a filter. No simulation is performed on import.

The expected consumer response uses complex rectangular linear interpolation
of every S entry, without extrapolation. This is an import/interpolation control,
not another EM solve or an extension of the model's physical qualification.
Required tolerances are caller-declared numerical roundtrip limits.

Sources: ADS 2027 Python API simulation/run, simulation/results, Library,
Design, Instance, InstTerm and Param; installed ccsim S2P component guide and
ads_datacmps S2P / ads_simulation Term definitions. Native probes confirmed
S2P terminal order 1/2/3 = p/n/reference, Mode0="linear", ID1="ri", Type1=
"touchstone", and Term 1/2 = positive/negative with Num and Z parameters.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
from typing import Any

import numpy as np

from analyze_em import Network, point_metrics, read_assembly_receipt, read_touchstone
from convert_cti import SNetwork, write_touchstone


def _identity(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {"name": path.name, "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest()}


def _json(path: Path, value: Any) -> None:
    payload = json.dumps(value, indent=2, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)


def _positive(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return value


def rectangular_linear(network: Network, frequency_hz: float) -> np.ndarray:
    """Compute the declared consumer expectation without altering source data."""
    frequency = float(frequency_hz)
    if not math.isfinite(frequency) or frequency < network.frequency_hz[0] or frequency > network.frequency_hz[-1]:
        raise ValueError("Roundtrip expectation cannot extrapolate outside source data")
    index = int(np.searchsorted(network.frequency_hz, frequency))
    if index < len(network.frequency_hz) and network.frequency_hz[index] == frequency:
        return network.s[index].copy()
    if index == 0 or index == len(network.frequency_hz):
        raise ValueError("The requested consumer frequency has no source bracket")
    low, high = float(network.frequency_hz[index - 1]), float(network.frequency_hz[index])
    weight = (frequency - low) / (high - low)
    return (1 - weight) * network.s[index - 1] + weight * network.s[index]


def frequency_groups(network: Network, require_dc_anchor: bool) -> list[dict[str, Any]]:
    """Use one LF sweep and three exact RF controls, all within the source."""
    if network.port_count != 2 or network.reference_ohm != 50:
        raise ValueError("The standalone bench requires the complete two-port with equal real 50-ohm references")
    if require_dc_anchor and (network.frequency_hz[0] != 0 or len(network.frequency_hz) < 2
                              or network.frequency_hz[1] != 10e6):
        raise ValueError("The declared DC-anchor test requires source endpoints at exactly 0 and 10 MHz")
    groups = []
    if network.frequency_hz[0] == 0:
        if network.frequency_hz[-1] < 10e6:
            raise ValueError("The source does not cover the complete 0-10 MHz consumer test")
        groups.append({"name": "lf_0_to_10mhz", "frequencies_hz": [float(i * 1e6) for i in range(11)],
                       "start_hz": 0.0, "stop_hz": 10e6, "step_hz": 1e6})
    for ghz in (10, 65, 80):
        frequency = float(ghz * 1e9)
        if not network.frequency_hz[0] <= frequency <= network.frequency_hz[-1]:
            raise ValueError("The source does not cover every required 10/65/80 GHz roundtrip control")
        groups.append({"name": f"exact_{ghz}ghz", "frequencies_hz": [frequency],
                       "start_hz": frequency, "stop_hz": frequency, "step_hz": 1.0})
    return groups


def validate_native_netlist(netlist: str, copied_model: Path) -> dict[str, Any]:
    """Require the observed native topology and explicit interpolation settings."""
    flat = netlist.replace("\\\r\n", " ").replace("\\\n", " ")
    component = re.findall(r"(?m)^\s*S2P:S2P1\s+(\S+)\s+(\S+)\s+(\S+)\s+([^\r\n]+)", flat)
    if len(component) != 1 or component[0][:3] != ("p", "n", "0"):
        raise ValueError("Native S2P topology does not preserve p/n/common-reference order")
    parameters = component[0][3]
    files = re.findall(r'\bFile\s*=\s*"([^"\r\n]*)"(?=\s|$)', parameters)
    if len(files) != 1:
        raise ValueError("Native S2P netlist must identify exactly one quoted File")
    # ADS can canonicalize a POSIX-style input path to native Windows separators.
    # Normalize separators only; do not decode backslash escapes or alter input.
    native_file = Path(files[0].replace("\\", "/"))
    try:
        same_file = native_file.is_absolute() and native_file.resolve(strict=True) == copied_model.resolve(strict=True)
    except OSError as error:
        raise ValueError("Native S2P File does not resolve to the retained model copy") from error
    if not same_file:
        raise ValueError("Native S2P File does not resolve to the retained model copy")
    for name, expected in (("Type", "touchstone"), ("InterpMode", "linear"), ("InterpDom", "ri")):
        if not re.search(rf'\b{re.escape(name)}\s*=\s*"{re.escape(expected)}"(?=\s|$)', parameters):
            raise ValueError(f"Native S2P netlist lacks the explicit required {name}")
    if not re.search(r"\bTemp\s*=\s*25(?:\.0+)?(?=\s|$)", parameters):
        raise ValueError("Native S2P temperature is not explicitly 25 degrees C")
    enforcement = re.search(r"\bEnforcePassivity\s*=\s*(\S+)", parameters)
    if enforcement and enforcement.group(1).strip('"').lower() not in ("no", "0", "false"):
        raise ValueError("Passivity enforcement must be disabled")
    for number, positive in ((1, "p"), (2, "n")):
        records = re.findall(rf"(?m)^\s*Port:T{number}\s+(\S+)\s+(\S+)\s+([^\r\n]+)", flat)
        if len(records) != 1 or records[0][:2] != (positive, "0"):
            raise ValueError("Native stimulus ports do not share the S2P physical-reference node")
        terms = records[0][2]
        if not re.search(rf"\bNum\s*=\s*{number}(?=\s|$)", terms):
            raise ValueError("Native stimulus numbering differs from the S2P signal order")
        if not re.search(r"\bZ\s*=\s*50(?:\.0+)?\s+Ohm(?=\s|$)", terms, re.I):
            raise ValueError("Native stimulus reference is not explicitly 50 ohms")
        if not re.search(r"\bTemp\s*=\s*25(?:\.0+)?(?=\s|$)", terms):
            raise ValueError("Native stimulus temperature is not explicitly 25 degrees C")
    return {"native_topology": "S2P(p,n,0); T1(p,0); T2(n,0)",
            "source_physical_reference": "P4 finite return already included inside the complete model",
            "interpolation": "linear in rectangular complex S", "temperature_c": 25,
            "reference_ohm": 50, "passivity_enforcement": False}


def _stub(design: Any, instance: Any, terminal_number: int, label: str, offset: tuple[float, float]) -> None:
    point = instance.inst_term_numbered(terminal_number).first_inst_pin.snap_point
    x, y = float(point.x), float(point.y)
    design.add_wire([(x, y), (x + offset[0], y + offset[1])]).add_wire_label(label)


def _wire_references_to_ground(design: Any, references: list[tuple[Any, int]], ground: Any) -> None:
    """Connect actual reference pins to GROUND geometrically, without aliases.

    Official ADS schematic examples connect wires to the GROUND pin. A local
    name on that connection can override the intended ground-node identity;
    no local reference labels are used on this shared physical circuit bus.
    Native netlisting must still independently demonstrate node 0.
    """
    ground_terms = list(ground.inst_terms)
    if len(ground_terms) != 1:
        raise ValueError("The standalone reference marker must have exactly one terminal")
    ground_point = ground_terms[0].first_inst_pin.snap_point
    gx, gy = float(ground_point.x), float(ground_point.y)
    for instance, number in references:
        point = instance.inst_term_numbered(number).first_inst_pin.snap_point
        x, y = float(point.x), float(point.y)
        route = [(x, y)]
        for next_point in ((x, gy), (gx, gy)):
            if next_point != route[-1]:
                route.append(next_point)
        if len(route) < 2:
            raise ValueError("A stimulus/reference pin must not overlap the GROUND marker pin")
        design.add_wire(route)


def _create_design(workspace: Any, copied_model: Path) -> tuple[Any, Any, dict[str, Any]]:
    from keysight.ads import de
    from keysight.ads.de import db_uu as db

    library_path = Path(workspace.path) / "s2p_roundtrip_lib"
    library = de.Library.create("s2p_roundtrip_lib", library_path)
    workspace.add_library(library.name, library_path, de.LibraryMode.SHARED)
    library.setup_schematic_tech()
    design = db.create_schematic("s2p_roundtrip_lib:roundtrip:schematic")
    component = design.add_instance(("ads_datacmps", "S2P", "symbol"), (0, 0), name="S2P1")
    if {terminal.term_number for terminal in component.inst_terms} != {1, 2, 3}:
        raise ValueError("Installed S2P terminals differ from the verified three-terminal definition")
    component.parameters["File"].value = f'"{copied_model.as_posix()}"'
    for name, form, expected in (("Type", "Type1", '"touchstone"'),
                                 ("InterpMode", "Mode0", '"linear"'),
                                 ("InterpDom", "ID1", '"ri"')):
        parameter = component.parameters[name]
        parameter.form_name = form
        if parameter.netlist_value != expected:
            raise ValueError(f"Installed native {name} form differs from the verified ADS 2027 definition")
    component.parameters["Temp"].value = "25"
    component.parameters["EnforcePassivity"].value = "no"
    if component.parameters["EnforcePassivity"].netlist_value.strip('"').lower() not in ("no", "0", "false"):
        raise ValueError("Native S2P passivity enforcement was not disabled")
    _stub(design, component, 1, "p", (-0.125, 0))
    _stub(design, component, 2, "n", (0.125, 0))
    references = [(component, 3)]
    for number, label, origin in ((1, "p", (-3, 1)), (2, "n", (3, 1))):
        term = design.add_instance(("ads_simulation", "Term", "symbol"), origin, name=f"T{number}")
        if {terminal.term_number for terminal in term.inst_terms} != {1, 2}:
            raise ValueError("Installed Term terminals differ from the verified positive/negative definition")
        term.parameters["Num"].value = str(number)
        term.parameters["Z"].value = "50 Ohm"
        term.parameters["Temp"].value = "25"
        _stub(design, term, 1, label, (0, 0.125))
        references.append((term, 2))
    ground = design.add_instance(("ads_rflib", "GROUND", "symbol"), (0.5, -2), name="G1")
    _wire_references_to_ground(design, references, ground)
    controller = design.add_instance(("ads_simulation", "S_Param", "symbol"), (0, -4), name="SP1")
    settings = {name: {"form": component.parameters[name].form_name,
                       "netlist_value": component.parameters[name].netlist_value}
                for name in ("Type", "InterpMode", "InterpDom", "Temp", "EnforcePassivity")}
    return design, controller, settings


def _dataset_network(dataset_path: Path) -> Network:
    from keysight.ads import dataset

    table = dataset.open(dataset_path)["SP1.SP"].to_dataframe().reset_index()
    if "freq" not in table.columns:
        raise ValueError("The circuit dataset lacks its frequency variable")
    columns = {}
    for i in (1, 2):
        for j in (1, 2):
            matches = [name for name in (f"S[{i},{j}]", f"S({i},{j})") if name in table.columns]
            if len(matches) != 1:
                raise ValueError("The circuit dataset lacks one unambiguous complete S entry")
            columns[i, j] = matches[0]
    observed_columns = {str(name) for name in table.columns if re.fullmatch(r"S[\[(][0-9]+,[0-9]+[\])]", str(name))}
    if observed_columns != set(columns.values()):
        raise ValueError("The circuit dataset does not contain exactly the declared complete two-port")
    frequencies = np.asarray(table["freq"], dtype=float)
    matrices = np.asarray([[[complex(row[columns[i, j]]) for j in (1, 2)] for i in (1, 2)]
                           for _, row in table.iterrows()], dtype=complex)
    if not np.all(np.isfinite(frequencies)) or not np.all(np.isfinite(matrices)) or np.any(np.diff(frequencies) <= 0):
        raise ValueError("Circuit consumer samples must be finite, unique and increasing")
    return Network(frequencies, matrices, 50.0)


def compare_consumption(source: Network, observed: Network, max_s_error: float,
                        max_zd_error_ohm: float) -> dict[str, Any]:
    """Compare every complex S entry and the same full-network Zd observable."""
    max_s_error = _positive(max_s_error, "Absolute S tolerance")
    max_zd_error_ohm = _positive(max_zd_error_ohm, "Absolute Zd tolerance")
    if source.port_count != 2 or observed.port_count != 2 or source.reference_ohm != 50 or observed.reference_ohm != 50:
        raise ValueError("Roundtrip comparisons require complete equal-reference 50-ohm two-ports")
    points = []
    for frequency, matrix in zip(observed.frequency_hz, observed.s, strict=True):
        expected = rectangular_linear(source, float(frequency))
        expected_metrics = point_metrics(float(frequency), expected, 50)
        observed_metrics = point_metrics(float(frequency), matrix, 50)
        delta_s = float(np.max(np.abs(matrix - expected)))
        expected_z = expected_metrics["differential"]["impedance"]
        observed_z = observed_metrics["differential"]["impedance"]
        delta_z = (abs(complex(observed_z["real_ohm"], observed_z["imag_ohm"])
                       - complex(expected_z["real_ohm"], expected_z["imag_ohm"]))
                   if expected_z is not None and observed_z is not None else None)
        points.append({"frequency_hz": float(frequency), "maximum_absolute_complex_S_error": delta_s,
                       "absolute_Zd_error_ohm": delta_z,
                       "expected_full_network_metrics": expected_metrics,
                       "ADS_consumed_full_network_metrics": observed_metrics,
                       "control_result": "PASS" if delta_s <= max_s_error and delta_z is not None
                       and delta_z <= max_zd_error_ohm else "FAIL_OR_UNRESOLVED_OBSERVABLE"})
    if not points:
        raise ValueError("No actual circuit-consumption samples were supplied")
    return {"schema_version": 1,
            "control_result": "PASS" if all(point["control_result"] == "PASS" for point in points) else "FAIL_OR_INCOMPLETE",
            "comparison": "native ADS S2P consumption versus full-matrix rectangular-linear source expectation",
            "maximum_absolute_complex_S_error": max(point["maximum_absolute_complex_S_error"] for point in points),
            "maximum_absolute_Zd_error_ohm": max((point["absolute_Zd_error_ohm"] for point in points if point["absolute_Zd_error_ohm"] is not None), default=None),
            "caller_declared_limits": {"maximum_absolute_complex_S_error": max_s_error,
                                       "maximum_absolute_Zd_error_ohm": max_zd_error_ohm},
            "signal_order": ["p", "n"], "physical_reference": "common finite P4 already included in source model",
            "interpolation": "linear complex RI", "extrapolation": False,
            "new_EM_solve_claimed": False, "physical_device_acceptance": "NOT DECIDED",
            "parent_filter_acceptance": "NOT EVALUATED", "points": points}


def run_roundtrip(model: str | Path, output_dir: str | Path, *, max_s_error: float,
                  max_zd_error_ohm: float, require_dc_anchor: bool = False,
                  assembly_receipt: str | Path | None = None) -> dict[str, Any]:
    """Build and run only this owned standalone circuit; retain every attempt."""
    model, output = Path(model).resolve(strict=True), Path(output_dir).resolve()
    network = read_touchstone(model)
    groups = frequency_groups(network, require_dc_anchor)
    max_s_error = _positive(max_s_error, "Absolute S tolerance")
    max_zd_error_ohm = _positive(max_zd_error_ohm, "Absolute Zd tolerance")
    assembly = read_assembly_receipt(Path(assembly_receipt).resolve(strict=True), model, network) if assembly_receipt else None
    if require_dc_anchor and (assembly is None or assembly["assembly"].get("DC_anchor", {}).get("included") is not True):
        raise ValueError("A declared derived DC anchor needs its verified model assembly receipt")
    if output.exists():
        raise FileExistsError("Use a fresh standalone consumer directory; preserve failed attempts")
    if any(character in model.as_posix() or character in output.as_posix() for character in ('"', "\r", "\n")):
        raise ValueError("Native S2P paths contain an unsupported quoting delimiter")
    from keysight.ads import de
    from keysight.edatoolbox import ads

    if de.is_pde_app() or de.workspace_is_open():
        raise RuntimeError("Use a new headless ADS Python process with no active workspace")
    identity = _identity(model)
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / "input"
    inputs.mkdir()
    copied_model = inputs / "model.s2p"
    shutil.copyfile(model, copied_model)
    if copied_model.read_bytes() != model.read_bytes():
        raise RuntimeError("The standalone input copy differs from the source model")
    if assembly_receipt is not None:
        shutil.copyfile(Path(assembly_receipt).resolve(strict=True), inputs / "model-assembly.json")
    receipt: dict[str, Any] = {"schema_version": 1, "started_utc": datetime.now(timezone.utc).isoformat(),
                               "status": "PREPARING_STANDALONE_CONSUMER", "model": identity,
                               "frequency_groups": groups, "require_dc_anchor": require_dc_anchor,
                               "assembly_receipt_verified": assembly is not None,
                               "assembly_receipt_source": assembly["assembly_receipt_source"] if assembly else None,
                               "parent_filter_acceptance": "NOT EVALUATED"}
    workspace_path = output / "native" / "s2p_roundtrip_wrk"
    workspace_path.parent.mkdir()
    workspace = de.create_workspace(str(workspace_path))
    workspace.open()
    try:
        design, controller, settings = _create_design(workspace, copied_model)
        receipt["native_parameter_settings"] = settings
        matrices, frequencies = [], []
        for group in groups:
            case = output / group["name"]
            case.mkdir()
            for name, value in (("Start", group["start_hz"]), ("Stop", group["stop_hz"]), ("Step", group["step_hz"])):
                controller.parameters[name].value = f"{value:.17g} Hz"
            controller.parameters["Dec"].value = ""
            design.save_design()
            native = design.generate_netlist()
            (case / "native.net").write_text(native, encoding="utf-8")
            guard = validate_native_netlist(native, copied_model)
            _json(case / "native-configuration.json", {**guard, "frequency_group": group,
                                                       "S2P_parameter_settings": settings})
            with (case / "simulator-console.log").open("x", encoding="utf-8") as console:
                with redirect_stdout(console), redirect_stderr(console):
                    ads.CircuitSimulator().run_netlist(native, output_dir=case)
            dataset_path = case / "roundtrip.ds"
            observed = _dataset_network(dataset_path)
            if len(observed.frequency_hz) != len(group["frequencies_hz"]) or not np.allclose(
                    observed.frequency_hz, group["frequencies_hz"], rtol=1e-12, atol=0.001):
                raise ValueError("Actual circuit-consumption frequencies differ from the declared control group")
            frequencies.extend(map(float, observed.frequency_hz))
            matrices.extend(observed.s)
        order = np.argsort(frequencies)
        observed = Network(np.asarray(frequencies)[order], np.asarray(matrices)[order], 50.0)
        report = compare_consumption(network, observed, max_s_error, max_zd_error_ohm)
        rendered = io.StringIO()
        write_touchstone(SNetwork(tuple(map(float, observed.frequency_hz)),
                                  tuple(tuple(tuple(complex(value) for value in row) for row in matrix) for matrix in observed.s),
                                  "ADS_S2P_consumer_roundtrip"), rendered, 50)
        payload = "! Actual ADS circuit consumer samples; not new EM solves.\n" + "\n".join(rendered.getvalue().splitlines()[1:]) + "\n"
        (output / "consumed.s2p").write_text(payload, encoding="ascii", newline="\n")
        _json(output / "comparison.json", report)
        if _identity(model) != identity or copied_model.read_bytes() != model.read_bytes():
            raise RuntimeError("The source model or standalone copy changed during consumption validation")
        receipt.update(status="CONSUMER_CONTROL_COMPLETED", control_result=report["control_result"],
                       source_model_unchanged=True, actual_frequency_hz=list(map(float, observed.frequency_hz)),
                       artifacts={name: _identity(output / name) for name in ("consumed.s2p", "comparison.json")})
        return report
    except Exception as error:
        receipt.update(status="CONSUMER_CONTROL_INCOMPLETE", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
        _json(output / "roundtrip-receipt.json", receipt)
        if de.workspace_is_open() and Path(de.active_workspace().path).resolve() == workspace_path:
            de.close_workspace()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--assembly-receipt", type=Path)
    parser.add_argument("--require-dc-anchor", action="store_true")
    parser.add_argument("--max-absolute-s-error", type=float, required=True)
    parser.add_argument("--max-absolute-zd-error-ohm", type=float, required=True)
    args = parser.parse_args()
    report = run_roundtrip(args.model, args.output_dir, max_s_error=args.max_absolute_s_error,
                           max_zd_error_ohm=args.max_absolute_zd_error_ohm,
                           require_dc_anchor=args.require_dc_anchor, assembly_receipt=args.assembly_receipt)
    print(f"Standalone S2P consumption: {report['control_result']}; parent filter NOT EVALUATED")
    if report["control_result"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
