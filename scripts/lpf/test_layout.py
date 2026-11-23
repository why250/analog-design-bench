"""Layout geometry and connectivity tests that run without ADS."""

import tomllib
import unittest
from pathlib import Path

from scripts.lpf.ads_layout import (
    _candidate_devices, _check_route_contacts, _layout_dimensions, _plan_routes, _terminal_nets,
)


def _profile():
    return tomllib.loads((Path(__file__).parent / "profiles" / "example-inp.toml").read_text(encoding="utf-8"))


def _device(profile, name, kind, **variables):
    return {
        "name": name, "kind": kind,
        "parameters": {**profile["devices"][kind]["fixed_parameters"], **variables},
    }


def _geometry(start, span, half_height):
    return {
        "bbox": (start, -half_height, start + span, half_height),
        "left": (start + 2, 0),
        "right": (start + span - 2, 0),
        "grounds": {"top": (start + span / 2, half_height), "bottom": (start + span / 2, -half_height)},
    }


class LayoutTests(unittest.TestCase):
    def test_candidate_respects_profile_and_order(self):
        profile = _profile()
        devices = [
            _device(profile, "L1", "L", inner_diameter=25),
            _device(profile, "C1", "C", cap_length=11, cap_width=11),
            _device(profile, "L2", "L", inner_diameter=47),
        ]
        self.assertEqual(_candidate_devices({"devices": devices}, profile), devices)
        with self.assertRaisesRegex(ValueError, "odd-order"):
            _candidate_devices({"devices": devices[:2]}, profile)
        with self.assertRaisesRegex(ValueError, "alternating"):
            _candidate_devices({"devices": [devices[0], devices[2], devices[1]]}, profile)
        devices[1]["parameters"]["margin_top"] += 1
        with self.assertRaisesRegex(ValueError, "frozen dimension"):
            _candidate_devices({"devices": devices}, profile)

    def test_routes_use_actual_pin_coordinates_at_multiple_orders(self):
        profile = _profile()
        dimensions = _layout_dimensions(profile["layout"], 1.0)
        for order in (3, 9, 11):
            with self.subTest(order=order):
                geometries = []
                cursor = 0
                for index in range(order):
                    span = 64 + index if index % 2 == 0 else 26
                    geometries.append(_geometry(cursor, span, 43 + index))
                    cursor += span + dimensions["cell_gap"]
                links, rectangles, terminals = _plan_routes(geometries, dimensions)
                signals = [bounds for role, _net, bounds in rectangles if role == "signal"]
                self.assertEqual(len(links), order + 1)
                self.assertEqual(len(signals), order + 1)
                self.assertEqual([name for name, *_ in terminals], ["rfin", "rfout", "gnd"])
                for index, geometry in enumerate(geometries):
                    self.assertGreater(signals[index][2], geometry["left"][0])
                    self.assertLess(signals[index + 1][0], geometry["right"][0])
                    self.assertLess(signals[index][2], signals[index + 1][0])
                self.assertEqual(signals[0][0], terminals[0][3][0])
                self.assertEqual(signals[-1][2], terminals[1][3][0])

    def test_capacitor_through_pins_are_distinct_from_ground(self):
        profile = _profile()
        links = ["rfin", "rf_link1", "rf_link2", "rfout"]
        self.assertEqual(_terminal_nets(profile["devices"]["C"], links, 1), {
            "P5": "rf_link1", "P6": "rf_link2", "P3": "gnd", "P4": "gnd",
        })
        self.assertEqual(_terminal_nets(profile["devices"]["L"], links, 0), {
            "P1": "rfin", "P2": "rf_link1", "P3": "gnd", "P4": "gnd", "P5": "gnd", "P6": "gnd",
        })

    def test_route_planner_rejects_signal_bypass(self):
        dimensions = _layout_dimensions(_profile()["layout"], 1.0)
        geometry = _geometry(0, 26, 43)
        geometry["right"] = geometry["left"]
        with self.assertRaisesRegex(RuntimeError, "overlap"):
            _plan_routes([geometry], dimensions)

    def test_route_contacts_detect_open_and_short(self):
        contact = [("signal", "rfin", "L1.P1", (0.0, 0.0))]
        left = ("signal", "rfin", (-5.0, -1.5, 1.0, 1.5))
        _check_route_contacts(contact, [left])
        with self.assertRaisesRegex(RuntimeError, "L1.P1 has an open or short"):
            _check_route_contacts(contact, [])
        with self.assertRaisesRegex(RuntimeError, "L1.P1 has an open or short"):
            _check_route_contacts(contact, [left, ("signal", "rfout", (0.0, -1.5, 4.0, 1.5))])
        with self.assertRaisesRegex(RuntimeError, "interconnects overlap"):
            _check_route_contacts(contact, [left, ("signal", "rfout", (0.5, -1.5, 4.0, 1.5))])


if __name__ == "__main__":
    unittest.main()
