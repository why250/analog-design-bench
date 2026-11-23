"""Build and verify an editable ADS layout for a series-first LPF ladder."""

import math
import re
from pathlib import Path


def _coordinate(point):
    return float(point.x), float(point.y)


def _box(box):
    return (*_coordinate(box.lower_left), *_coordinate(box.upper_right))


def _candidate_devices(candidate, profile):
    devices = candidate["devices"]
    if not devices or len(devices) % 2 == 0:
        raise ValueError("The editable layout requires an odd-order ladder.")
    names = set()
    for position, device in enumerate(devices):
        kind = "L" if position % 2 == 0 else "C"
        if device["kind"] != kind:
            raise ValueError("The layout requires alternating series inductors and shunt capacitors.")
        name = device["name"]
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) or name in names:
            raise ValueError(f"Invalid or duplicate ADS instance name: {name}")
        names.add(name)
        binding = profile["devices"][kind]
        parameters = device["parameters"]
        fixed = binding["fixed_parameters"]
        if parameters.keys() != set(binding["variables"]) | fixed.keys():
            raise ValueError(f"The candidate does not provide exactly the profile dimensions for {name}.")
        for key, value in parameters.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Invalid dimension for {name}.{key}: {value}")
            if key in fixed and value != fixed[key]:
                raise ValueError(f"The candidate changes the frozen dimension {name}.{key}.")
    return devices


def _layout_dimensions(layout, uu_per_um):
    keys = (
        "cell_gap_um", "launch_um", "signal_width_um", "ground_width_um",
        "ground_clearance_um", "contact_overlap_um",
    )
    dims = {key.removesuffix("_um"): float(layout[key]) * uu_per_um for key in keys}
    if not all(math.isfinite(value) and value > 0 for value in dims.values()):
        raise ValueError("Layout routing dimensions must be finite and positive.")
    if dims["launch"] <= dims["ground_width"] or dims["ground_clearance"] <= dims["ground_width"] / 2:
        raise ValueError("The layout needs clearance for the perimeter ground routes.")
    return dims


def _pin_position(instance, name, expected_layer):
    pin = instance.first_inst_pin_named(name)
    if pin is None or pin.get_snap_layer_id() != expected_layer:
        raise RuntimeError(f"{instance.name}.{name} is missing from the expected layer.")
    return _coordinate(pin.snap_point)


def _device_geometry(instance, binding, layers):
    left, right = binding["layout_signal_pins"]
    return {
        "bbox": _box(instance.bbox),
        "left": _pin_position(instance, left, layers["signal"]),
        "right": _pin_position(instance, right, layers["signal"]),
        "grounds": {
            name: _pin_position(instance, name, layers["ground"])
            for name in binding["layout_ground_pins"]
        },
    }


def _place_devices(design, de, db, devices, profile, layers, gap, tolerance):
    cursor = 0.0
    geometries = []
    for device in devices:
        binding = profile["devices"][device["kind"]]
        item = de.ItemInfo.for_placement(design, (binding["library"], binding["cell"], "layout"))
        item.inst_name = device["name"]
        instance = item.create_new_instance((0.0, 0.0))
        parameters = device["parameters"]
        for name, value in parameters.items():
            instance.parameters[name].value = f"{value:.12g} um"
        db.invoke_parameter_changed_callback(instance, list(parameters))
        geometry = _device_geometry(instance, binding, layers)
        instance.move((cursor - geometry["bbox"][0], -geometry["left"][1]))
        placed = _device_geometry(instance, binding, layers)
        if abs(placed["left"][1]) > tolerance or abs(placed["right"][1]) > tolerance:
            raise RuntimeError(f"{device['name']} signal pins are not on the routing centerline.")
        geometries.append(placed)
        cursor = placed["bbox"][2] + gap
    return geometries


def _plan_routes(geometries, dimensions):
    """Plan same-layer metal contacts using generated instance pin positions."""
    input_x = geometries[0]["bbox"][0] - dimensions["launch"]
    output_x = geometries[-1]["bbox"][2] + dimensions["launch"]
    overlap = dimensions["contact_overlap"]
    signal_half = dimensions["signal_width"] / 2
    ground_half = dimensions["ground_width"] / 2
    top = max(geometry["bbox"][3] for geometry in geometries) + dimensions["ground_clearance"]
    bottom = min(geometry["bbox"][1] for geometry in geometries) - dimensions["ground_clearance"]
    links = ["rfin", *(f"rf_link{i}" for i in range(1, len(geometries))), "rfout"]

    left_edges = [input_x, *(geometry["right"][0] - overlap for geometry in geometries)]
    right_edges = [*(geometry["left"][0] + overlap for geometry in geometries), output_x]
    if any(left >= right for left, right in zip(left_edges, right_edges)):
        raise RuntimeError("The generated pin order does not permit a straight signal route.")
    if any(right >= left for right, left in zip(right_edges, left_edges[1:])):
        raise RuntimeError("Signal interconnects would overlap across a device.")
    rectangles = [
        ("signal", net, (left, -signal_half, right, signal_half))
        for net, left, right in zip(links, left_edges, right_edges)
    ]

    rectangles.extend([
        ("ground", "gnd", (input_x, top - ground_half, output_x, top + ground_half)),
        ("ground", "gnd", (input_x, bottom - ground_half, output_x, bottom + ground_half)),
        ("ground", "gnd", (input_x, bottom, input_x + 2 * ground_half, top)),
        ("ground", "gnd", (output_x - 2 * ground_half, bottom, output_x, top)),
    ])
    for geometry in geometries:
        for x, y in geometry["grounds"].values():
            rail = top if y >= 0 else bottom
            rectangles.append(("ground", "gnd", (
                x - ground_half, min(y, rail) - overlap,
                x + ground_half, max(y, rail) + overlap,
            )))

    terminals = [
        ("rfin", 1, "signal", (input_x, 0.0), 180),
        ("rfout", 2, "signal", (output_x, 0.0), 0),
        ("gnd", 3, "ground", ((input_x + output_x) / 2, top), 90),
    ]
    return links, rectangles, terminals


def _terminal_nets(binding, links, index):
    left, right = binding["layout_signal_pins"]
    return {
        left: links[index], right: links[index + 1],
        **dict.fromkeys(binding["layout_ground_pins"], "gnd"),
    }


def _build_design(design, de, db, devices, profile, layers, dimensions, tolerance):
    geometries = _place_devices(
        design, de, db, devices, profile, layers, dimensions["cell_gap"], tolerance,
    )
    links, rectangles, terminals = _plan_routes(geometries, dimensions)
    for layer, net, (x1, y1, x2, y2) in rectangles:
        shape = design.add_rectangle(layers[layer], (x1, y1), (x2, y2))
        shape.net = design.find_or_add_net(net)
    for index, device in enumerate(devices):
        instance = design.get_instance(device["name"])
        binding = profile["devices"][device["kind"]]
        for pin, net in _terminal_nets(binding, links, index).items():
            instance.inst_term_named(pin).net = design.find_or_add_net(net)
    for name, number, layer, point, angle in terminals:
        term = design.add_numbered_term(design.find_or_add_net(name), name, number)
        design.add_pin(term, design.add_dot(layers[layer], point), angle=angle)
    design.save_design()
    return links, geometries, rectangles, terminals


def _matches_coordinates(first, second, tolerance):
    return all(abs(left - right) <= tolerance for left, right in zip(first, second, strict=True))


def _check_route_contacts(contacts, rectangles):
    for role, net, label, (x, y) in contacts:
        actual = {
            route_net for route_role, route_net, (x1, y1, x2, y2) in rectangles
            if role == route_role and x1 <= x <= x2 and y1 <= y <= y2
        }
        if actual != {net}:
            raise RuntimeError(f"{label} has an open or short in its {role} routing.")
    signals = sorted(bounds for role, _net, bounds in rectangles if role == "signal")
    if any(left[2] >= right[0] for left, right in zip(signals, signals[1:])):
        raise RuntimeError("The reopened signal interconnects overlap across a device.")


def _verify_reopened(design, devices, profile, layers, expected, tolerance):
    links, geometries, rectangles, terminals = expected
    contacts = []
    if not design.is_layout or {instance.name for instance in design.instances} != {d["name"] for d in devices}:
        raise RuntimeError("The reopened ADS layout has an unexpected instance inventory.")
    for index, device in enumerate(devices):
        binding = profile["devices"][device["kind"]]
        instance = design.get_instance(device["name"])
        if not instance.is_pcell or (instance.library_name, instance.cell_name) != (binding["library"], binding["cell"]):
            raise RuntimeError(f"The native layout did not retain the editable PCell {instance.name}.")
        for name, value in device["parameters"].items():
            actual_um = float(instance.pcell_parameters[name].value) * 1e6
            if not math.isclose(actual_um, value, rel_tol=1e-10, abs_tol=1e-9):
                raise RuntimeError(f"The reopened {instance.name}.{name} has the wrong dimension.")
        actual = _device_geometry(instance, binding, layers)
        expected_geometry = geometries[index]
        for role in ("left", "right", "bbox"):
            if not _matches_coordinates(actual[role], expected_geometry[role], tolerance):
                raise RuntimeError(f"The reopened {instance.name} has different {role} coordinates.")
        for pin, point in actual["grounds"].items():
            if not _matches_coordinates(point, expected_geometry["grounds"][pin], tolerance):
                raise RuntimeError(f"The reopened {instance.name}.{pin} has a different ground position.")
        pin_nets = _terminal_nets(binding, links, index)
        for pin, net in pin_nets.items():
            terminal = instance.inst_term_named(pin)
            if terminal.net is None or terminal.net.name != net:
                raise RuntimeError(f"The reopened {instance.name}.{pin} is not bound to {net}.")
        contacts.extend(
            ("signal", pin_nets[pin], f"{instance.name}.{pin}", actual[role])
            for pin, role in zip(binding["layout_signal_pins"], ("left", "right"), strict=True)
        )
        contacts.extend(("ground", "gnd", f"{instance.name}.{pin}", point)
                        for pin, point in actual["grounds"].items())

    actual_rectangles = [shape for shape in design.shapes if type(shape).__name__ != "Dot"]
    if len(actual_rectangles) != len(rectangles):
        raise RuntimeError("The reopened layout has an unexpected conductor inventory.")
    observed = []
    for role, net, bounds in rectangles:
        for index, shape in enumerate(actual_rectangles):
            if (type(shape).__name__ == "Rect" and shape.layer == layers[role].layer
                    and shape.net is not None and shape.net.name == net
                    and _matches_coordinates(_box(shape.bbox), bounds, tolerance)):
                observed.append((role, net, _box(shape.bbox)))
                actual_rectangles.pop(index)
                break
        else:
            raise RuntimeError(f"The reopened layout is missing a {role} route on {net}.")

    if {terminal.name for terminal in design.terms} != {entry[0] for entry in terminals}:
        raise RuntimeError("The reopened layout has an unexpected external terminal inventory.")
    for name, number, layer, position, _angle in terminals:
        term = design.find_term(name)
        pin = design.first_pin_of_term(name)
        if (term.number != number or term.net is None or term.net.name != name or pin is None
                or pin.snap_layer_id != layers[layer]
                or not _matches_coordinates(_coordinate(pin.snap_point), position, tolerance)):
            raise RuntimeError(f"The reopened external terminal {name} does not match the port map.")
        contacts.append((layer, name, name, _coordinate(pin.snap_point)))
    _check_route_contacts(contacts, observed)


def build_layout(candidate, profile, out: Path, *, ads_workspace: Path):
    """Build an isolated native layout, close it, and verify its persisted contents."""
    from keysight.ads import de
    from keysight.ads.de import db_uu as db

    from . import ads_pcell

    devices = _candidate_devices(candidate, profile)
    layout = profile["layout"]
    source = Path(ads_workspace).resolve(strict=True)
    out = Path(out).resolve()
    if de.workspace_is_open():
        raise RuntimeError("An ADS workspace is already open in the layout process.")

    dut = candidate.get("ads_dut")
    testbench = candidate.get("ads_testbench")
    if bool(dut) != bool(testbench):
        raise ValueError("The selected ADS DUT and testbench must be supplied together.")
    if dut:
        library, cell, view = dut.split(":")
        if library != layout["library"] or view != "schematic":
            raise ValueError("The selected DUT does not use the configured ADS schematic library.")
    else:
        library = layout["library"]
        cell_suffix = re.sub(r"[^A-Za-z0-9_]", "_", str(candidate["id"]))
        cell = f"lpf_layout_{cell_suffix}"
    cellview = (library, cell, "layout")
    target = ads_pcell.copy_workspace(source, out / "ads" / source.name)
    with ads_pcell._open_workspace(target, profile):
        if testbench:
            test = db.open_design(testbench, db.DesignMode.READ_ONLY)
            netlist = test.generate_netlist()
            ads_pcell._check_netlist(netlist, target, profile, devices, ground="gnd")
            (out / "selected-schematic.net").write_text(netlist, encoding="utf-8")
        design = db.create_layout(cellview)
        uu_per_um = design.meter_to_uu_factor * 1e-6
        tolerance = 2 * design.dbu_to_uu_factor
        layers = {role: design.create_layer_id(layout[f"{role}_layer"]) for role in ("signal", "ground")}
        if layers["signal"] == layers["ground"]:
            raise ValueError("The layout profile must specify distinct signal and ground layers.")
        dimensions = _layout_dimensions(layout, uu_per_um)
        expected = _build_design(design, de, db, devices, profile, layers, dimensions, tolerance)

    with ads_pcell._open_workspace(target, profile):
        design = db.open_design(cellview, db.DesignMode.READ_ONLY)
        _verify_reopened(design, devices, profile, layers, expected, tolerance)
        bounds_um = [coordinate / uu_per_um for coordinate in _box(design.bbox)]

    links, geometries, rectangles, terminals = expected
    return {
        "verified": True,
        "candidate_id": candidate["id"],
        "source_ads_workspace": str(source),
        "ads_workspace": str(target),
        "cellview": ":".join(cellview),
        "schematic_cellview": dut,
        "schematic_testbench": testbench,
        "bounds_um": bounds_um,
        "route_rectangles": len(rectangles),
        "devices": [
            {"name": device["name"], "kind": device["kind"], "parameters_um": device["parameters"],
             "bounds_um": [coordinate / uu_per_um for coordinate in geometry["bbox"]],
             "terminal_nets": _terminal_nets(profile["devices"][device["kind"]], links, index)}
            for index, (device, geometry) in enumerate(zip(devices, geometries, strict=True))
        ],
        "terminals": [
            {"name": name, "number": number, "layer": layout[f"{layer}_layer"],
             "position_um": [coordinate / uu_per_um for coordinate in position]}
            for name, number, layer, position, _angle in terminals
        ],
        "verification_scope": "Native reopen, PCell dimensions, port bindings and conductor contacts.",
    }
