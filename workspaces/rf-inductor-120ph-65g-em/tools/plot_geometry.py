"""Render actual Momentum EGS polygons, physical pins and port definitions.

Inputs are the unchanged exported proj_a, proj.pin and proj.prt files. Only
filled zero-width EGS polygons are supported; unsupported drawing commands fail
instead of being replaced by estimated geometry. Matplotlib is the sole external
dependency. SVG output retains editable polygons and text.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET


NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?"
POINT = re.compile(rf"({NUMBER})\s*,\s*({NUMBER})")
POLYGON = re.compile(rf"ADD\s+P(\d+)\s*:W({NUMBER})\s+(.+)", re.IGNORECASE | re.DOTALL)
LAYER_STYLES = {
    7: {"color": "#2476A8", "edge": "#155575", "label": "Metal1 (layer 7): finite return", "zorder": 1},
    35: {"color": "#EE8A26", "edge": "#AE5611", "label": "Metal6 (layer 35): inductor", "zorder": 2},
}
PIN_LABELS = {"P1": "P1 = p", "P2": "P2 = n", "P3": "P3 = center tap", "P4": "P4 = return"}


class GeometryError(ValueError):
    """An exported drawing or its port mapping is incomplete or unsupported."""


@dataclass(frozen=True)
class Polygon:
    layer: int
    points_um: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class Pin:
    name: str
    net: str
    layer: int
    x_um: float
    y_um: float


@dataclass(frozen=True)
class Port:
    number: int
    name: str
    plus_pins: tuple[str, ...]
    minus_pins: tuple[str, ...]
    reference_real_ohm: float
    reference_imag_ohm: float


def _number(text: str | None, label: str) -> float:
    try:
        value = float(text)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise GeometryError(f"Missing or invalid numeric {label}") from exc
    if not math.isfinite(value):
        raise GeometryError(f"Nonfinite {label}")
    return value


def parse_egs(text: str) -> tuple[Polygon, ...]:
    """Read explicit filled EGS polygons, converting declared units to um.

    The second UNITS field is the export grid resolution, not a scale factor
    applied to already dimensioned coordinate values.
    """
    statements = [part.strip() for part in text.lstrip("\ufeff").split(";") if part.strip()]
    if not statements:
        raise GeometryError("Empty EGS export")
    units = re.fullmatch(rf"UNITS\s+(UM|MM|NM|M)\s*,\s*({NUMBER})", statements[0], re.IGNORECASE)
    if units is None:
        raise GeometryError("Expected an explicit supported EGS UNITS declaration")
    if _number(units.group(2), "EGS grid resolution") <= 0:
        raise GeometryError("EGS grid resolution must be positive")
    scale = {"UM": 1.0, "MM": 1e3, "NM": 1e-3, "M": 1e6}[units.group(1).upper()]
    result: list[Polygon] = []
    edit_seen = False
    save_seen = False
    for statement in statements[1:]:
        if re.fullmatch(r"EDIT\s+[^\s;]+", statement, re.IGNORECASE):
            if edit_seen or result or save_seen:
                raise GeometryError("Repeated or misplaced EGS EDIT command")
            edit_seen = True
            continue
        if statement.upper() == "SAVE":
            if save_seen:
                raise GeometryError("Repeated EGS SAVE command")
            save_seen = True
            continue
        match = POLYGON.fullmatch(statement)
        if match is None or not edit_seen or save_seen:
            raise GeometryError("Unsupported or misplaced EGS drawing command")
        if _number(match.group(2), "EGS polygon width") != 0:
            raise GeometryError("Only filled :W0 polygons are supported; stroked paths require a separate reader")
        coordinates = match.group(3)
        point_matches = list(POINT.finditer(coordinates))
        residue = POINT.sub("", coordinates)
        if residue.strip() or len(point_matches) < 3:
            raise GeometryError("An EGS polygon has invalid or insufficient coordinate pairs")
        points = tuple((_number(p.group(1), "polygon x") * scale,
                        _number(p.group(2), "polygon y") * scale) for p in point_matches)
        if len(set(points)) < 3:
            raise GeometryError("An EGS polygon has fewer than three distinct vertices")
        area_twice = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2)
                         in zip(points, points[1:] + points[:1]))
        if area_twice == 0:
            raise GeometryError("A filled EGS polygon has zero signed area")
        result.append(Polygon(int(match.group(1)), points))
    if not edit_seen or not save_seen or not result:
        raise GeometryError("EGS export requires EDIT, filled polygons and SAVE")
    return tuple(result)


def parse_pins(text: str) -> tuple[Pin, ...]:
    """Read exported point pins; proj.pin coordinates are explicitly in meters."""
    try:
        xml = ET.fromstring(text)
    except ET.ParseError as exc:
        raise GeometryError("Invalid proj.pin XML") from exc
    if xml.tag != "pin_list":
        raise GeometryError("Expected pin_list in proj.pin")
    pins: list[Pin] = []
    for node in xml.findall("pin"):
        name = node.findtext("name", "").strip()
        net = node.findtext("net", "").strip()
        shapes = node.findall("layout/shape")
        if not name or not net or len(shapes) != 1:
            raise GeometryError("Each physical pin must have a name, net and one supported point shape")
        shape = shapes[0]
        points = shape.findall("point")
        if len(points) != 1 or len(list(shape)) != 3:
            raise GeometryError(f"Pin {name} is not an exported layer/purpose/point shape")
        try:
            layer = int(shape.findtext("layer", ""))
            int(shape.findtext("purpose", ""))
        except ValueError as exc:
            raise GeometryError(f"Pin {name} has an invalid layer or purpose") from exc
        pins.append(Pin(name, net, layer,
                        _number(points[0].findtext("x"), f"{name} x") * 1e6,
                        _number(points[0].findtext("y"), f"{name} y") * 1e6))
    if not pins or len({pin.name for pin in pins}) != len(pins):
        raise GeometryError("Physical pin names must be present and unique")
    return tuple(pins)


def parse_ports(text: str, pins: tuple[Pin, ...]) -> tuple[Port, ...]:
    """Read complete terminal reference mappings without assuming global ground."""
    try:
        xml = ET.fromstring(text)
    except ET.ParseError as exc:
        raise GeometryError("Invalid proj.prt XML") from exc
    if xml.tag != "port_setup":
        raise GeometryError("Expected port_setup in proj.prt")
    pin_names = {pin.name for pin in pins}
    result: list[Port] = []
    for node in xml.findall("port_list/port"):
        try:
            number = int(node.attrib["id"])
        except (KeyError, ValueError) as exc:
            raise GeometryError("A port lacks a numeric ID") from exc
        plus = tuple((p.text or "").strip() for p in node.findall("plus_pin"))
        minus = tuple((p.text or "").strip() for p in node.findall("minus_pin"))
        if not plus or not minus or not set(plus + minus).issubset(pin_names):
            raise GeometryError(f"Port {number} requires declared physical positive and negative pins")
        real = _number(node.findtext("impedance/real"), f"port {number} reference resistance")
        imag = _number(node.findtext("impedance/imag"), f"port {number} reference reactance")
        if number <= 0 or real <= 0:
            raise GeometryError("Port IDs and real reference impedances must be positive")
        result.append(Port(number, node.findtext("name", "").strip(), plus, minus, real, imag))
    result.sort(key=lambda p: p.number)
    if not result or [p.number for p in result] != list(range(1, len(result) + 1)):
        raise GeometryError("Port numbers must be unique and contiguous from one")
    return tuple(result)


def _bounds(polygons: tuple[Polygon, ...]) -> tuple[float, float, float, float]:
    points = [point for polygon in polygons for point in polygon.points_um]
    return min(x for x, _ in points), min(y for _, y in points), max(x for x, _ in points), max(y for _, y in points)


def read_export(input_dir: str | Path) -> tuple[tuple[Polygon, ...], tuple[Pin, ...], tuple[Port, ...]]:
    input_dir = Path(input_dir).resolve(strict=True)
    polygons = parse_egs((input_dir / "proj_a").read_text(encoding="utf-8-sig"))
    pins = parse_pins((input_dir / "proj.pin").read_text(encoding="utf-8-sig"))
    ports = parse_ports((input_dir / "proj.prt").read_text(encoding="utf-8-sig"), pins)
    layers = {polygon.layer for polygon in polygons}
    if any(pin.layer not in layers for pin in pins):
        raise GeometryError("A physical pin's conductor layer is missing from the exported polygons")
    return polygons, pins, ports


def render(input_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Create a standalone SVG/PNG from exported polygons and actual port maps."""
    input_dir = Path(input_dir).resolve(strict=True)
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise FileExistsError("Use a fresh output directory; prior renders are retained")
    polygons, pins, ports = read_export(input_dir)
    # Import after input validation so parser use has no graphics dependency.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Polygon as PolygonPatch

    output_dir.mkdir(parents=True, exist_ok=False)
    minimum_x, minimum_y, maximum_x, maximum_y = _bounds(polygons)
    width, height = maximum_x - minimum_x, maximum_y - minimum_y
    span = max(width, height)
    if span <= 0:
        raise GeometryError("The exported footprint has no physical extent")
    with matplotlib.rc_context({"font.family": "DejaVu Sans", "font.size": 10,
                                "svg.fonttype": "none", "axes.spines.top": False,
                                "axes.spines.right": False}):
        fig = plt.figure(figsize=(11.5, 8), facecolor="white")
        ax = fig.add_axes((0.085, 0.15, 0.67, 0.70))
        fig.suptitle("Single-turn inductor: exported EM geometry", x=0.085, y=0.965,
                     ha="left", fontsize=18, fontweight="bold", color="#182D3B")
        fig.text(0.085, 0.922, "Assumed on-chip research stack | No foundry qualification",
                 fontsize=11, color="#526673")
        for index, polygon in enumerate(sorted(polygons, key=lambda p: LAYER_STYLES.get(p.layer, {}).get("zorder", 0)), start=1):
            style = LAYER_STYLES.get(polygon.layer, {"color": "#AAB3BA", "edge": "#63727C", "zorder": 0})
            patch = PolygonPatch(polygon.points_um, closed=True, facecolor=style["color"],
                                 edgecolor=style["edge"], linewidth=0.75,
                                 zorder=style["zorder"])
            patch.set_gid(f"exported-metal-layer-{polygon.layer}-polygon-{index}")
            ax.add_patch(patch)
        offsets = {"P1": (-37, -27), "P2": (37, -27), "P3": (0, 22), "P4": (0, -31)}
        for pin in pins:
            offset = offsets.get(pin.name, (17, 17))
            ax.scatter([pin.x_um], [pin.y_um], s=33, facecolor="white", edgecolor="#152D3C",
                       linewidth=1.0, zorder=6)
            ax.annotate(PIN_LABELS.get(pin.name, pin.name), (pin.x_um, pin.y_um),
                        xytext=offset, textcoords="offset points", ha="center", va="center",
                        fontsize=9, fontweight="bold", color="#17384C",
                        bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": "#A9BBC6", "alpha": 0.96},
                        arrowprops={"arrowstyle": "-", "color": "#345366", "lw": 0.8}, zorder=8)
        ax.set_xlim(minimum_x - 0.09 * span, maximum_x + 0.09 * span)
        ax.set_ylim(minimum_y - 0.12 * span, maximum_y + 0.09 * span)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("x (µm)", labelpad=9)
        ax.set_ylabel("y (µm)", labelpad=8)
        ax.grid(color="#DBE4E9", linewidth=0.55, zorder=-2)
        ax.set_axisbelow(True)
        ax.tick_params(colors="#526673")
        for spine in ax.spines.values():
            spine.set_color("#C0CED7")
        layers = sorted({polygon.layer for polygon in polygons})
        handles = []
        for layer in layers:
            style = LAYER_STYLES.get(layer, {"color": "#AAB3BA", "edge": "#63727C", "label": f"Layer {layer}"})
            handles.append(Patch(facecolor=style["color"], edgecolor=style["edge"], label=style["label"]))
        fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.775, 0.85),
                   frameon=False, fontsize=9, handlelength=1.2, labelspacing=1.1)
        panel = ["ACTUAL EXPORTED BOUNDS", f"Width: {width:.3f} µm", f"Height: {height:.3f} µm",
                 "", "PORT CONNECTIONS"]
        for port in ports:
            plus = "+".join(port.plus_pins)
            minus = "+".join(port.minus_pins)
            reference = f"{port.reference_real_ohm:g}"
            if port.reference_imag_ohm:
                reference += f"{port.reference_imag_ohm:+g}j"
            panel.extend([f"{port.number}: {plus} → {minus}", f"    Reference: {reference} Ω"])
        panel.extend(["", f"{len(polygons)} exported polygons", "All coordinates from proj_a.",
                      "Point pins from proj.pin.", "Port mapping from proj.prt.", "", "Top view; layer heights", "are not drawn to scale."])
        fig.text(0.79, 0.69, "\n".join(panel), ha="left", va="top", fontsize=9,
                 color="#294C61", linespacing=1.55)
        fig.text(0.085, 0.065, "Finite return metal is part of the EM structure. Port excitation adds no drawn metal.",
                 fontsize=9, color="#526673")
        fig.text(0.085, 0.035, "Geometry and port visualization only; electrical acceptance requires the retained EM results.",
                 fontsize=9, color="#526673")
        fig.savefig(output_dir / "geometry.svg", format="svg", facecolor="white")
        fig.savefig(output_dir / "geometry.png", format="png", dpi=180, facecolor="white")
        plt.close(fig)
    receipt = {
        "schema_version": 1, "rendered_utc": datetime.now(timezone.utc).isoformat(),
        "geometry_source": "actual Momentum exported EGS filled polygons",
        "coordinate_units": "um", "stack_qualification": "assumed research stack; no foundry qualification",
        "bounds_um": {"minimum_x": minimum_x, "minimum_y": minimum_y,
                      "maximum_x": maximum_x, "maximum_y": maximum_y, "width": width, "height": height},
        "polygons": [asdict(polygon) for polygon in polygons],
        "pins": [asdict(pin) for pin in pins], "ports": [asdict(port) for port in ports],
        "sources": [{"name": name, "size_bytes": (input_dir / name).stat().st_size,
                     "sha256": hashlib.sha256((input_dir / name).read_bytes()).hexdigest()}
                    for name in ("proj_a", "proj.pin", "proj.prt")],
        "outputs": ["geometry.svg", "geometry.png"],
    }
    (output_dir / "geometry-receipt.json").write_text(
        json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True,
                        help="Retained Momentum export containing proj_a, proj.pin and proj.prt")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Fresh directory for editable geometry.svg, geometry.png and machine receipt")
    args = parser.parse_args()
    receipt = render(args.input_dir, args.output_dir)
    print(f"Rendered {len(receipt['polygons'])} exported polygons and {len(receipt['ports'])} ports")
    print(f"Saved geometry.svg and geometry.png in {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
