"""Load and normalize the electrical specification used by every stage."""

from math import isfinite
from pathlib import Path
import tomllib


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(f"{field} must be a finite number") from error
    if not isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def _positive(value, field):
    result = _number(value, field)
    if result <= 0:
        raise ValueError(f"{field} must be positive")
    return result


def _negative(value, field):
    result = _number(value, field)
    if result >= 0:
        raise ValueError(f"{field} must be negative (20 log10 magnitude)")
    return result


def _fields(table, required, optional, label):
    if not isinstance(table, dict):
        raise ValueError(f"{label} must be a TOML table")
    missing = required - table.keys()
    unexpected = table.keys() - required - optional
    if missing or unexpected:
        raise ValueError(f"{label}: missing {sorted(missing)}, unknown {sorted(unexpected)}")


def normalize_spec(raw):
    """Resolve units and defaults and reject ambiguous acceptance criteria."""
    _fields(
        raw,
        {"schema_version", "impedance_ohm", "passband_hz", "s11_max_db",
         "s22_max_db", "stopbands", "insertion_loss"},
        {"return_loss_margin_db", "max_order"},
        "specification",
    )
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    edge = _positive(raw["passband_hz"], "passband_hz")
    stopbands = raw["stopbands"]
    if not isinstance(stopbands, list) or not stopbands:
        raise ValueError("Specify at least one [[stopbands]] checkpoint")
    stops = []
    for stop in stopbands:
        _fields(stop, {"frequency_hz", "s21_max_db"}, set(), "stopbands entry")
        frequency = _positive(stop["frequency_hz"], "stopbands.frequency_hz")
        if frequency <= edge:
            raise ValueError("Every stopband checkpoint must be above the passband edge")
        stops.append({"frequency_hz": frequency,
                      "s21_max_db": _negative(stop["s21_max_db"], "stopbands.s21_max_db")})
    if len({stop["frequency_hz"] for stop in stops}) != len(stops):
        raise ValueError("Stopband checkpoint frequencies must be distinct")
    stops.sort(key=lambda stop: stop["frequency_hz"])

    loss = raw["insertion_loss"]
    _fields(loss, {"mode"}, {"max_db"}, "insertion_loss")
    if loss["mode"] == "limit" and "max_db" in loss:
        max_loss = _positive(loss["max_db"], "insertion_loss.max_db")
    elif loss["mode"] == "report_only" and "max_db" not in loss:
        max_loss = None
    else:
        raise ValueError('Use insertion_loss.mode = "limit" with max_db, or "report_only" alone')

    margin = _number(raw.get("return_loss_margin_db", 1.0), "return_loss_margin_db")
    if margin < 0:
        raise ValueError("return_loss_margin_db must be nonnegative")
    order = raw.get("max_order", 15)
    if type(order) is not int or order < 3 or order % 2 == 0:
        raise ValueError("max_order must be an odd integer of at least 3")
    return {
        "schema_version": 1,
        "impedance_ohm": _positive(raw["impedance_ohm"], "impedance_ohm"),
        "passband_hz": edge,
        "s11_max_db": _negative(raw["s11_max_db"], "s11_max_db"),
        "s22_max_db": _negative(raw["s22_max_db"], "s22_max_db"),
        "stopbands": stops,
        "insertion_loss_max_db": max_loss,
        "return_loss_margin_db": margin,
        "max_order": order,
    }


def load_spec(path: Path):
    with path.open("rb") as source:
        return normalize_spec(tomllib.load(source))
