"""Export exact ADS PCell samples and rerun fixed-topology candidates natively."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from .ideal import measure
from .search import _diagnostics, geometry_key, sample_passivity_note, validate_geometry, write_touchstone


_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_OUTPUT_LIBRARY = "inp_lpf_lib"
_DUT_CELL = "lpf_physical"
_TEST_CELL = "lpf_physical_sp"


def copy_workspace(source, target):
    """Copy source libraries and workspace settings into the run directory."""
    source, target = source.resolve(), target.resolve()
    if not (source / "lib.defs").is_file():
        raise ValueError(f"ADS source workspace has no lib.defs: {source}")
    if source == target or source in target.parents:
        raise ValueError("The ADS copy must be outside the original workspace")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source, target,
        ignore=shutil.ignore_patterns(
            "*.lck", "*.lock", "*.cdslck", "__pycache__", "data", "simulation", "verification",
        ),
    )
    for state in target.glob("*/*/em%*/emStateFile.xml"):
        if not state.is_file():
            continue
        original = state.read_bytes()
        patched = original
        for old, new in (
            (source.as_posix(), target.as_posix()),
            (str(source), str(target)),
        ):
            patched = re.sub(
                re.escape(old.encode("utf-8")) + rb'(?=[/\\<"\s]|$)',
                lambda _: new.encode("utf-8"), patched, flags=re.I,
            )
        if patched != original:
            state.write_bytes(patched)
    return target


def verify_em_workspace(workspace, family):
    """Reject extraction if the copied PCell still names a different workspace."""
    cell = workspace / family["library"] / family["cell"]
    for state in cell.glob("em%*/emStateFile.xml"):
        for text in ET.parse(state).findall(".//workspaceText"):
            if text.text and Path(text.text).resolve() != workspace.resolve():
                raise ValueError(f"Copied Momentum setup still names another workspace: {state}")


@contextmanager
def _open_workspace(path, profile):
    from keysight.ads import de

    if de.workspace_is_open():
        raise RuntimeError("Close the current ADS workspace before opening the run-owned copy")
    required = {family["library"] for family in profile["devices"].values()}
    required.add(profile.get("layout", {}).get("library", _OUTPUT_LIBRARY))
    definitions = (path / "lib.defs").read_text(encoding="utf-8-sig")
    for name in sorted(required):
        matches = re.findall(rf"(?im)^\s*DEFINE\s+{re.escape(name)}\s+([^\r\n]+)", definitions)
        if len(matches) != 1 or (path / matches[0].strip(' "\t')).resolve() != path / name:
            raise ValueError(f"Library {name} must resolve within the run-owned ADS workspace")
    directory = Path.cwd()
    try:
        workspace = de.open_workspace(path)
        if missing := required - set(workspace.library_names):
            raise ValueError(f"ADS source copy is missing libraries: {', '.join(sorted(missing))}")
        yield de
    finally:
        try:
            if de.workspace_is_open():
                de.close_workspace()
        finally:
            os.chdir(directory)


def _model_directory(workspace, family):
    return workspace / family["library"] / family["cell"] / "em%Model"


def _micrometers(text):
    match = re.fullmatch(rf"\s*({_NUMBER})\s*(?:um|µm)\s*", str(text))
    if match is None:
        raise ValueError(f"Expected a numeric ADS geometry in micrometers: {text!r}")
    return float(match[1])


def _cache_index(workspace, family):
    model = _model_directory(workspace, family)
    options = ET.parse(model / "emDataOptions.xml")
    parameter_options = options.find("cellParameters")
    if parameter_options is None or parameter_options.get("useInterpolation") != "no":
        raise ValueError(f"Exact geometry lookup needs interpolation disabled: {model}")
    index = ET.parse(model / "emDataIndex.xml")
    names = [item.text for item in index.findall("./emDatabase/ParameterNames/parameterName")]
    if set(names) != set(family["variables"]) | set(family["fixed_parameters"]):
        raise ValueError(f"ADS model parameters do not match the selected device profile: {model}")
    compiled_text = (model / "model.ndx").read_text(encoding="utf-8-sig")
    compiled_names = re.findall(r"(?m)^PARAM:\s*([^,]+),", compiled_text)
    if compiled_names != names:
        raise ValueError(f"Compiled ADS cache parameter order differs from the XML index: {model}")
    compiled = {}
    for match in re.finditer(
        r"(?m)^SAMPLEFILE:\s*(data\.\d+\.sio);\s*SAMPLE:\s*([^;]+);", compiled_text,
    ):
        compiled[match[1]] = [float(value.strip()) * 1e6 for value in match[2].split(",")]
    entries, issues = {}, []
    for item in index.findall("./emDatabase/databaseItems/databaseItem"):
        identifier = item.get("name", "")
        try:
            if re.fullmatch(r"data\.\d+", identifier) is None:
                raise ValueError("Unknown sample identifier format")
            values = [_micrometers(node.text) for node in item.findall("./parameterValues/value")]
            if len(values) != len(names):
                raise ValueError("Sample has incomplete geometry")
            expected = compiled.get(f"{identifier}.sio", [])
            if len(expected) != len(values) or not np.allclose(values, expected, rtol=0, atol=1e-7):
                raise ValueError("XML and compiled sample geometries disagree")
            parameters = dict(zip(names, values))
            validate_geometry(parameters, family)
            key = geometry_key(parameters)
            if key in entries:
                raise ValueError("Duplicate exact geometry in the native model cache")
            sio = model / f"{identifier}.sio"
            if not sio.is_file() or sio.stat().st_size == 0:
                raise ValueError("Native electromagnetic model payload is missing")
            frequencies = []
            for line in (model / f"{identifier}.sam").read_text(encoding="utf-8-sig").splitlines():
                if re.fullmatch(_NUMBER, line.strip()):
                    frequencies.append(float(line))
            if len(frequencies) < 2 or min(frequencies) < 0 or not np.isfinite(frequencies).all():
                raise ValueError("Native model has invalid frequency coverage")
            entries[key] = {
                "parameters": parameters,
                "native_sample": identifier,
                "native_sio_sha256": hashlib.sha256(sio.read_bytes()).hexdigest(),
                "solved_frequency_hz": sorted(frequencies),
                "notes": _sample_notes(model, identifier),
            }
        except (ValueError, OSError, zipfile.BadZipFile) as exc:
            issues.append({"native_sample": identifier, "family": family["cell"], "reason": str(exc)})
    return entries, issues


def _sample_notes(model, identifier):
    archive = model / f"{identifier}.log.zip"
    if not archive.is_file():
        return ["Native solver warning log was unavailable"]
    notes = set()
    with zipfile.ZipFile(archive) as logs:
        for name in logs.namelist():
            if not name.lower().endswith((".txt", ".log")):
                continue
            for line in logs.read(name).decode("utf-8", errors="replace").splitlines():
                if "electrically large" in line.lower() or "surface wave" in line.lower():
                    notes.add(line.strip())
    return sorted(notes)


def _port(design, number, name, coordinates, angle=0):
    from keysight.ads.de import db_uu as db

    term = design.add_numbered_term(
        design.find_or_add_net(name), name, number, db.TermType.INPUT_OUTPUT,
    )
    design.add_pin(term, design.add_dot_for_pin(coordinates), angle=angle)


def _place_device(builder, element, family, ground, position):
    validate_geometry(element["parameters"], family)
    instance = builder.place_instance(
        (family["library"], family["cell"], "symbol"), position, name=element["name"],
    )
    expected = dict(zip(
        family["signal_terms"] + family["ground_terms"],
        family["layout_signal_pins"] + family["layout_ground_pins"],
    ))
    terms = {
        number: instance.find_inst_term_named(name) or instance.find_inst_term_numbered(number)
        for number, name in expected.items()
    }
    if any(term is None for term in terms.values()) or len(list(instance.inst_terms)) != len(expected):
        raise ValueError(f"Unexpected ADS symbol terminal set for {instance.name}")
    for parameter, value in element["parameters"].items():
        instance.parameters[parameter].value = f"{value:.17g} um"
    for parameter, value in element["parameters"].items():
        if abs(_micrometers(instance.parameters[parameter].value) - value) > 1e-7:
            raise ValueError(f"Native geometry changed for {instance.name}.{parameter}")
    for number in family["ground_terms"]:
        builder.make_connection(terms[number], ground, "gnd" if ground == 3 else "")
    return tuple(terms[number] for number in family["signal_terms"])


def _devices(builder, devices, profile, ground):
    result = [
        _place_device(builder, element, profile["devices"][element["kind"]], ground, (3.0 + index * 5.0, 0))
        for index, element in enumerate(devices)
    ]
    for index in range(len(result) - 1):
        builder.make_connection(result[index][1], result[index + 1][0], f"n{index + 1}")
    return result[0][0], result[-1][1]


def _shunt_first(builder, devices, profile):
    if [element["kind"] for element in devices] != ["C", "L"] * (len(devices) // 2) + ["C"]:
        raise ValueError("Common-signal shunt mode requires alternating C/L with a shunt at both ends")
    previous = 1
    for index, element in enumerate(devices):
        shunt = element["kind"] == "C"
        first, second = _place_device(
            builder, element, profile["devices"][element["kind"]], 3,
            (3.0 + index * 5.0, -3 if shunt else 0),
        )
        node = "rfin" if index < 2 else "rfout" if index == len(devices) - 1 else f"n{index // 2}"
        builder.make_connection(previous, first, node)
        if shunt:
            builder.make_connection(first, second, node)
        else:
            previous = second
    builder.make_connection(previous, 2, "rfout")


def _sweep(builder, name, start, stop, points, index):
    controller = builder.place_instance(
        ("ads_simulation", "S_Param", "symbol"), (index % 5 * 5, 4 + index // 5 * 5), name=name,
    )
    for key, value in {
        "Start": f"{start:.17g} Hz", "Stop": f"{stop:.17g} Hz", "Lin": str(points),
        "Step": "", "Dec": "", "Log": "", "CalcNoise": "no",
    }.items():
        controller.parameters[key].value = value


def _testbench(builder, left, right, spec, sweeps, *, grounded_dut=None):
    for number, endpoint, position in ((1, left, (0, 0)), (2, right, (12, 0))):
        term = builder.place_instance(
            ("ads_simulation", "Term", "symbol"), position, name=f"Term{number}", angle=-90,
        )
        term.parameters["Num"].value = str(number)
        term.parameters["Z"].value = f'{spec["impedance_ohm"]:.17g} Ohm'
        term.parameters["Noise"].value = "no"
        ground = builder.place_instance(
            ("ads_rflib", "GROUND", "symbol"), (position[0], -1), name=f"Gnd{number}", angle=-90,
        )
        builder.make_connection((term, 2), (ground, 1))
        builder.make_connection((term, 1), endpoint, "rfin" if number == 1 else "rfout")
    if grounded_dut is not None:
        ground = builder.place_instance(
            ("ads_rflib", "GROUND", "symbol"), (0, -4), name="DeviceGround", angle=-90,
        )
        builder.make_connection(grounded_dut, (ground, 1))
    for index, (name, start, stop, points) in enumerate(sweeps):
        _sweep(builder, name, start, stop, points, index)
    builder.save_design()


def _build_candidate(profile, devices, spec, sweeps):
    from keysight.ads.de import db_uu as db
    from keysight.ads.de.experimental import DesignBuilder
    from keysight.ads.de.experimental.generate_symbol import SymbolGenerator

    library = profile.get("layout", {}).get("library", _OUTPUT_LIBRARY)
    dut = DesignBuilder.build_schematic(f"{library}:{_DUT_CELL}:schematic", overwrite=False)
    dut.allow_wires = False
    last_x = 6.0 + (len(devices) - 1) * 5.0
    _port(dut.design, 1, "rfin", (0, 0), 180)
    _port(dut.design, 2, "rfout", (last_x, 0))
    _port(dut.design, 3, "gnd", (0, -3), 180)
    if profile.get("capacitor_connection") == "common_signal_shunt":
        _shunt_first(dut, devices, profile)
    else:
        left, right = _devices(dut, devices, profile, 3)
        dut.make_connection(1, left, "rfin")
        dut.make_connection(right, 2, "rfout")
    dut.save_design()
    symbol = db.create_symbol(f"{library}:{_DUT_CELL}:symbol")
    generator = SymbolGenerator(symbol, dut.design, 0.5, 1.0)
    generator.is_dual_symbol_type = True
    generator.should_replace = True
    generator.pin_shape = "square"
    generator.generate_symbol()
    symbol.save_design()
    builder = DesignBuilder.build_schematic(f"{library}:{_TEST_CELL}:schematic", overwrite=False)
    instance = builder.place_instance((library, _DUT_CELL, "symbol"), (5, 0), name="DUT")
    _testbench(builder, (instance, 1), (instance, 2), spec, sweeps, grounded_dut=(instance, 3))
    return builder.design, f"{library}:{_DUT_CELL}:schematic", f"{library}:{_TEST_CELL}:schematic"


def _build_fixture(profile, element, spec, sweeps, *, cell=None):
    from keysight.ads.de.experimental import DesignBuilder

    library = profile.get("layout", {}).get("library", _OUTPUT_LIBRARY)
    name = cell or f"lpf_sample_{element['kind']}"
    builder = DesignBuilder.build_schematic(f"{library}:{name}:schematic", overwrite=cell is None)
    builder.allow_wires = False
    ground = builder.place_instance(
        ("ads_rflib", "GROUND", "symbol"), (0, -4), name="DeviceGround", angle=-90,
    )
    left, right = _devices(builder, [element], profile, (ground, 1))
    _testbench(builder, left, right, spec, sweeps)
    return builder.design


def _check_netlist(text, workspace, profile, devices, *, ground, impedance=None):
    flat = re.sub(r"\\\r?\n", " ", text)
    model_files = re.findall(r'\bmodelFile\s*=\s*"([^"]+)"', flat)
    referenced = {
        (workspace / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        for path in model_files
    }
    expected = {
        (_model_directory(workspace, profile["devices"][element["kind"]]) / "model.ndx").resolve()
        for element in devices
    }
    if referenced != expected:
        raise ValueError("Generated ADS netlist does not use exactly the run-owned PCell model caches")
    if impedance is not None:
        for number, node in ((1, "rfin"), (2, "rfout")):
            port = re.search(rf"(?m)^\s*Port:Term{number}\s+{node}\s+0\s+([^\n]+)", flat)
            if port is None or not re.search(rf"\bNum\s*=\s*{number}\b", port[1]):
                raise ValueError(f"Native external port {number} is not connected as specified")
            resistance = re.search(rf"\bZ\s*=\s*({_NUMBER})\s*Ohm\b", port[1])
            if resistance is None or float(resistance[1]) != impedance:
                raise ValueError(f"Native external port {number} has the wrong reference impedance")
    if ground == "gnd":
        dut = re.search(rf"(?ms)^define\s+{_DUT_CELL}\s*\(\s*rfin\s+rfout\s+gnd\s*\).*?^end\s+{_DUT_CELL}\b", flat)
        if dut is None:
            raise ValueError("Native DUT must expose rfin, rfout, gnd in that order")
        if not re.search(rf"(?m)^\s*{_DUT_CELL}:DUT\s+rfin\s+rfout\s+0\b", flat):
            raise ValueError("Native DUT reference is not tied to the testbench ground")
        body = dut[0]
    else:
        body = flat
    previous = "rfin"
    used = {"rfin", ground}
    shunt_first = ground == "gnd" and profile.get("capacitor_connection") == "common_signal_shunt"
    for index, element in enumerate(devices):
        family = profile["devices"][element["kind"]]
        match = re.search(rf"(?m)^\s*{re.escape(family['cell'])}:{re.escape(element['name'])}\s+(\S[^\n]*)", body)
        if match is None:
            raise ValueError(f"Missing native {family['cell']} instance {element['name']}")
        count = len(family["signal_terms"]) + len(family["ground_terms"])
        tokens = match[1].split()
        nodes = tokens[:count]
        left, right = (nodes[number - 1] for number in family["signal_terms"])
        if shunt_first and element["kind"] == "C":
            if left != previous or right != previous:
                raise ValueError(f"Native common-signal shunt connectivity disagrees at {element['name']}")
        else:
            last_series = len(devices) - (2 if shunt_first else 1)
            if left != previous or right in used or (index == last_series) != (right == "rfout"):
                raise ValueError(f"Native RF chain connectivity disagrees at {element['name']}")
            used.add(right)
            previous = right
        if any(nodes[number - 1] != ground for number in family["ground_terms"]):
            raise ValueError(f"Native ground reference disagrees at {element['name']}")
        for parameter, value in element["parameters"].items():
            found = re.search(rf"\b{re.escape(parameter)}\s*=\s*({_NUMBER})\s*um\b", match[1])
            if found is None or abs(float(found[1]) - value) > 1e-7:
                raise ValueError(f"Native netlist geometry disagrees for {element['name']}.{parameter}")


def bind_model_parameters(netlist, workspace, profile, devices):
    """Restore the compiled model's symbolic parameter map when headless ADS omits it."""
    receipt = []
    for kind in sorted({device["kind"] for device in devices}):
        family = profile["devices"][kind]
        name = family["cell"]
        model = _model_directory(workspace, family) / "model.ndx"
        records = re.findall(
            r"(?m)^PARAM:\s*([^,]+),([^;]+);", model.read_text(encoding="utf-8-sig"),
        )
        parameter_names = [parameter.strip() for parameter, _ in records]
        if set(parameter_names) != set(family["variables"]) | set(family["fixed_parameters"]):
            raise ValueError(f"Unexpected compiled parameter set for {name}")
        mapping = []
        for number, (parameter, fields) in enumerate(records):
            values = fields.split(",")
            if len(values) != 7 or not np.isfinite(float(values[4])) or float(values[4]) <= 0:
                raise ValueError(f"Invalid parameter resolution for {name}.{parameter}")
            mapping.append({
                "index": number, "name": parameter.strip(), "resolution_um": float(values[4]) * 1e6,
            })
        definition = re.compile(rf"(?ms)^define\s+{re.escape(name)}\s*\(.*?^end\s+{re.escape(name)}\b")
        matches = list(definition.finditer(netlist))
        if len(matches) != 1 or matches[0][0].count("MomCmpt:em_data") != 1:
            raise ValueError(f"Expected one native Momentum model definition for {name}")
        match = matches[0]
        body = match[0]
        assignments = re.findall(r'\bp(\d+)\s*=\s*"([^"]+)"', body)
        restored = not assignments
        if restored:
            anchor = re.search(r"(?m)^ +ModelReuse=", body)
            if anchor is None:
                raise ValueError(f"Missing native Momentum options for {name}")
            lines = []
            for entry in mapping:
                i, parameter, resolution = entry["index"], entry["name"], entry["resolution_um"]
                lines.append(f'    p{i}="{parameter}" v{i}={parameter} v{i}_Resolution={resolution:.12g} um \\')
            body = body[:anchor.start()] + "\n".join(lines) + "\n" + body[anchor.start():]
            netlist = netlist[:match.start()] + body + netlist[match.end():]
        if not restored and sorted(assignments) != sorted((str(row["index"]), row["name"]) for row in mapping):
            raise ValueError(f"Existing native Momentum parameter mapping disagrees for {name}")
        for entry in mapping:
            i, parameter, resolution = entry["index"], entry["name"], entry["resolution_um"]
            linked = re.search(
                rf'\bp{i}\s*=\s*"{re.escape(parameter)}"\s+v{i}\s*=\s*{re.escape(parameter)}\s+'
                rf'v{i}_Resolution\s*=\s*({_NUMBER})\s*um\b', body,
            )
            if linked is None or abs(float(linked[1]) - resolution) > 1e-9:
                raise ValueError(f"Unverified native Momentum mapping for {name}.{parameter}")
        receipt.append({"cell": name, "restored": restored, "parameters": mapping})
    return netlist, receipt


def _simulate(netlist, out, sweeps, *, native_netlist=None, bindings=None):
    from keysight.ads import dataset
    from keysight.edatoolbox import ads

    out.mkdir(parents=True, exist_ok=False)
    if native_netlist is not None:
        (out / "schematic.native.net").write_text(native_netlist, encoding="utf-8")
        (out / "model-binding.json").write_text(json.dumps(bindings, indent=2) + "\n", encoding="utf-8")
    (out / "schematic.net").write_text(netlist, encoding="utf-8")
    try:
        ads.CircuitSimulator().run_netlist(netlist, output_dir=str(out))
    except subprocess.SubprocessError as exc:
        detail = []
        for log in sorted(out.glob("*.out")):
            detail.extend(
                line.strip() for line in log.read_text(errors="replace").splitlines()
                if "Gemx" in line or "Fatal error" in line
            )
        raise RuntimeError(f"ADS simulation failed. {' '.join(detail)} Evidence: {out}") from exc
    files = list(out.glob("*.ds"))
    if len(files) != 1:
        raise RuntimeError("Expected one fresh ADS dataset")
    data = dataset.open(files[0])
    samples = {}
    for name, start, stop, count in sweeps:
        key = f"{name}.SP"
        if key not in data.keys():
            raise ValueError(f"ADS dataset is missing analysis {key}")
        frame = data[key].to_dataframe().reset_index()
        frequencies = frame["freq"].to_numpy(float)
        if (
            len(frequencies) != count or abs(frequencies[0] - start) > 1.0
            or abs(frequencies[-1] - stop) > 1.0
        ):
            raise ValueError(f"ADS analysis {name} did not return the requested frequency grid")
        for row_index, frequency in enumerate(frequencies):
            values = np.array([
                [frame["S[1,1]"].iat[row_index], frame["S[1,2]"].iat[row_index]],
                [frame["S[2,1]"].iat[row_index], frame["S[2,2]"].iat[row_index]],
            ], dtype=complex)
            if frequency in samples and not np.allclose(samples[frequency], values, rtol=0, atol=1e-8):
                raise ValueError(f"Conflicting native ADS samples at {frequency:.17g} Hz")
            samples[frequency] = values
    frequency = np.array(sorted(samples))
    return frequency, np.stack([samples[f] for f in frequency])


def _range_and_notes(spec, entries, families):
    start = max(1e6, *(entry["solved_frequency_hz"][0] for entry in entries))
    end = min(entry["solved_frequency_hz"][-1] for entry in entries)
    last_stop = max(item["frequency_hz"] for item in spec["stopbands"])
    if start >= spec["passband_hz"] or end < last_stop:
        raise ValueError("Exact ADS device models do not jointly cover the requested checkpoints")
    notes = sorted({note for entry in entries for note in entry["notes"]})
    if start > 1e6:
        notes.append(f"Native model coverage starts at {start:g} Hz; lower frequencies remain unverified")
    for threshold in sorted({
        family["unqualified_above_hz"] for family in families
        if family.get("unqualified_above_hz") is not None and last_stop > family["unqualified_above_hz"]
    }):
        notes.append(f"Device-model applicability above {threshold:g} Hz is conditional")
    return start, end, notes


def _sweeps(spec, start, end, points):
    last_stop = max(point["frequency_hz"] for point in spec["stopbands"])
    return [
        ("SP_broad", start, min(end, 1.5 * last_stop), 1201),
        ("SP_passband", start, spec["passband_hz"], points),
        *((f"SP_stop{index}", point["frequency_hz"], point["frequency_hz"], 1)
          for index, point in enumerate(spec["stopbands"], 1)),
    ]


def _export_entry(spec, profile, workspace, kind, entry, out):
    family = profile["devices"][kind]
    identifier = f"{kind}-{entry['native_sample']}"
    start, end, notes = _range_and_notes(spec, [entry], [family])
    sweeps = _sweeps(spec, start, end, 1301)
    sweeps += [(f"SP_diagnostic{index}", f, f, 1)
               for index, f in enumerate(profile.get("candidate_diagnostics_hz", []), 1)]
    device = {"name": "Device", "kind": kind, "parameters": entry["parameters"]}
    fixture = _build_fixture(
        profile, device, spec, sweeps, cell=f"lpf_sample_{kind}_{entry['native_sample'].split('.')[-1]}",
    )
    netlist = fixture.generate_netlist()
    _check_netlist(netlist, workspace, profile, [device], ground="0", impedance=spec["impedance_ohm"])
    bound, bindings = bind_model_parameters(netlist, workspace, profile, [device])
    frequency, s = _simulate(bound, out / identifier, sweeps, native_netlist=netlist, bindings=bindings)
    note = sample_passivity_note(frequency, s)
    if note:
        notes.append(note)
    path = out / identifier / "model.s2p"
    write_touchstone(path, frequency, s, spec["impedance_ohm"])
    return {
        "id": identifier, "kind": kind, "parameters": entry["parameters"],
        "touchstone": str(path.resolve()), "native_sample": entry["native_sample"],
        "native_sio_sha256": entry["native_sio_sha256"],
        "model_status": "conditional" if notes else "qualified", "model_notes": notes,
    }


def export_geometry(spec, profile, workspace, device, out):
    """Export a specific geometry after the native cache confirms the extraction."""
    kind = device["kind"]
    entries, _ = _cache_index(workspace, profile["devices"][kind])
    entry = entries.get(geometry_key(device["parameters"]))
    if entry is None:
        raise ValueError("Extraction did not produce an exact, indexed ADS sample")
    with _open_workspace(workspace, profile):
        return _export_entry(spec, profile, workspace, kind, entry, out)


def export_samples(spec, design, profile, workspace, out):
    """Export cached exact geometries through native two-port ADS fixtures."""
    out.mkdir(parents=True, exist_ok=False)
    samples, issues = [], []
    desired = {element["kind"] for element in design["elements"]}
    with _open_workspace(workspace, profile):
        for kind in sorted(desired):
            family = profile["devices"][kind]
            entries, rejected = _cache_index(workspace, family)
            issues.extend(rejected)
            for entry in entries.values():
                identifier = f"{kind}-{entry['native_sample']}"
                try:
                    sample = _export_entry(spec, profile, workspace, kind, entry, out)
                    sample["touchstone"] = Path(sample["touchstone"]).relative_to(out).as_posix()
                    samples.append(sample)
                except (ValueError, RuntimeError, OSError) as exc:
                    issues.append({"sample_id": identifier, "reason": str(exc)})
    path = out / "sample-index.json"
    path.write_text(json.dumps({"schema_version": 1, "samples": samples, "issues": issues}, indent=2) + "\n",
                    encoding="utf-8")
    return path


def verify_candidate(spec, profile, candidate, source, out, *, workspace_target=None):
    """Create a native DUT and testbench and rerun the selected exact geometries."""
    workspace = copy_workspace(source, workspace_target if workspace_target is not None else out / "ads")
    devices = candidate["devices"]
    families = [profile["devices"][element["kind"]] for element in devices]
    catalogs = {
        kind: _cache_index(workspace, profile["devices"][kind])[0]
        for kind in {element["kind"] for element in devices}
    }
    entries = []
    for element in devices:
        entry = catalogs[element["kind"]].get(geometry_key(element["parameters"]))
        if entry is None:
            raise ValueError(f"Native ADS model cache has no exact sample for {element['name']}")
        if element.get("native_sample") not in (None, entry["native_sample"]):
            raise ValueError(f"Native ADS sample ID differs for {element['name']}")
        if element.get("native_sio_sha256") not in (None, entry["native_sio_sha256"]):
            raise ValueError(f"Native ADS payload differs for {element['name']}")
        entries.append(entry)
    start, end, notes = _range_and_notes(spec, entries, families)
    start = max(start, profile.get("candidate_start_hz", start))
    sweeps = _sweeps(spec, start, end, 13001)
    sweeps += [(f"SP_diagnostic{index}", f, f, 1)
               for index, f in enumerate(profile.get("candidate_diagnostics_hz", []), 1)]
    with _open_workspace(workspace, profile) as de:
        testbench, dut, test = _build_candidate(profile, devices, spec, sweeps)
        netlist = testbench.generate_netlist()
        _check_netlist(netlist, workspace, profile, devices, ground="gnd", impedance=spec["impedance_ohm"])
        bound, bindings = bind_model_parameters(netlist, workspace, profile, devices)
        frequency, s = _simulate(bound, out / "initial", sweeps, native_netlist=netlist, bindings=bindings)
        band = frequency[frequency <= spec["passband_hz"]]
        spacing = (spec["passband_hz"] - start) / 13000
        measurements = measure(spec, frequency, s)
        extrema = sorted({
            measurements["metrics"][name]["frequency_hz"] for name in ("s11_worst", "s22_worst", "il_worst")
        })
        refinement = [
            (f"SP_refine{index}", max(band[0], point - 2 * spacing),
             min(band[-1], point + 2 * spacing), 101)
            for index, point in enumerate(extrema, 1)
        ]
        from keysight.ads.de.experimental import DesignBuilder

        library = profile.get("layout", {}).get("library", _OUTPUT_LIBRARY)
        refined_view = f"{library}:{_TEST_CELL}_refined:schematic"
        builder = DesignBuilder.build_schematic(refined_view, overwrite=False)
        instance = builder.place_instance((library, _DUT_CELL, "symbol"), (5, 0), name="DUT")
        _testbench(
            builder, (instance, 1), (instance, 2), spec, sweeps + refinement, grounded_dut=(instance, 3),
        )
        netlist = builder.design.generate_netlist()
        _check_netlist(netlist, workspace, profile, devices, ground="gnd", impedance=spec["impedance_ohm"])
        bound, bindings = bind_model_parameters(netlist, workspace, profile, devices)
        frequency, s = _simulate(
            bound, out / "refined", sweeps + refinement, native_netlist=netlist, bindings=bindings,
        )
        settings = {
            "ads_version": de.product_version().strip(),
            "dut": dut, "testbench": refined_view, "initial_testbench": test, "sweeps": sweeps + refinement,
            "exact_samples": entries, "reference_impedance_ohm": spec["impedance_ohm"],
            "lowest_verified_frequency_hz": start,
        }
    diagnostics = _diagnostics(s)
    if diagnostics["passivity_max_sv"] > 1.00001 or diagnostics["reciprocity_max_abs"] > 1e-4:
        raise ValueError("ADS candidate failed the passive or reciprocal network check")
    write_touchstone(out / "native.s2p", frequency, s, spec["impedance_ohm"])
    (out / "settings.json").write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return {
        **measure(spec, frequency, s), "verification": "ads", "diagnostics": diagnostics,
        "ads_workspace": str(workspace), "ads_dut": dut, "ads_testbench": refined_view,
        "native_binding_mode": "headless_parameter_mapping_restored" if any(
            entry["restored"] for entry in bindings
        ) else "application_native_mapping",
        "native_touchstone": str((out / "native.s2p").resolve()),
        "model_notes": sorted(set(candidate["model_notes"] + notes)),
        "model_status": "conditional" if notes or candidate["model_status"] == "conditional" else "qualified",
    }
