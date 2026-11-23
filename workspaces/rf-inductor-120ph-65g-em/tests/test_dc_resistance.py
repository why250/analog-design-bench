"""Physical checks for the independent sheet-resistor calculation."""

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from dc_resistance import DCError, locate_contact, material_from_ltd, solve_sheet
from plot_geometry import Pin


class DCTests(unittest.TestCase):
    def rectangle(self, length=10, width=2):
        points = ((0, 0), (length, 0), (length, width), (0, width))
        contacts = [locate_contact(points, Pin("P1", "P1", 35, 0, width / 2), width),
                    locate_contact(points, Pin("P2", "P2", 35, length, width / 2), width)]
        return points, contacts

    def test_uniform_rectangle_exact_including_half_cells(self):
        points, contacts = self.rectangle()
        for grid in (0.5, 0.25, 0.125):
            solved = solve_sheet(points, contacts, 2, 0.5, grid)
            self.assertAlmostEqual(solved.metrics["R_ohm"], 5, places=10)
            self.assertLess(solved.metrics["relative_terminal_current_imbalance"], 1e-10)
            self.assertLess(solved.metrics["relative_dissipation_error"], 1e-10)

    def test_conductivity_and_thickness_scaling(self):
        points, contacts = self.rectangle()
        a = solve_sheet(points, contacts, 2, 0.5, 0.25).metrics["R_ohm"]
        b = solve_sheet(points, contacts, 4, 0.5, 0.25).metrics["R_ohm"]
        c = solve_sheet(points, contacts, 2, 1, 0.25).metrics["R_ohm"]
        self.assertAlmostEqual(a / b, 2)
        self.assertAlmostEqual(a / c, 2)

    def test_reversing_polygon_orientation_preserves_result(self):
        points, _ = self.rectangle()
        reversed_points = tuple(reversed(points))
        contacts = [locate_contact(reversed_points, Pin("P1", "P1", 35, 0, 1), 2),
                    locate_contact(reversed_points, Pin("P2", "P2", 35, 10, 1), 2)]
        self.assertAlmostEqual(solve_sheet(reversed_points, contacts, 1, 1, 0.5).metrics["R_ohm"], 5, places=10)

    def test_bent_path_increases_resistance_and_stays_connected(self):
        # U-shaped conductor with two terminal faces on the lower boundary.
        points = ((0, 0), (2, 0), (2, 8), (8, 8), (8, 0), (10, 0), (10, 10), (0, 10))
        contacts = [locate_contact(points, Pin("P1", "P1", 35, 1, 0), 2),
                    locate_contact(points, Pin("P2", "P2", 35, 9, 0), 2)]
        solution = solve_sheet(points, contacts, 1, 1, 0.25)
        self.assertGreater(solution.metrics["R_ohm"], 10)
        self.assertEqual(solution.metrics["connected_components"], 1)

    def test_unresolved_terminal_contact_is_rejected(self):
        points, contacts = self.rectangle()
        with self.assertRaises(DCError):
            solve_sheet(points, contacts, 1, 1, 1)
        with self.assertRaises(DCError):
            locate_contact(points, Pin("P1", "P1", 35, 5, 1), 2)

    def test_disconnected_mask_is_rejected(self):
        # Two islands represented with a repeated zero-width connector. Such an
        # input must not be mistaken for a conducting through path.
        points = ((0, 0), (2, 0), (2, 2), (0, 2), (0, 0),
                  (4, 0), (6, 0), (6, 2), (4, 2), (4, 0))
        contacts = [locate_contact(points, Pin("P1", "P1", 35, 0, 1), 2),
                    locate_contact(points, Pin("P2", "P2", 35, 6, 1), 2)]
        with self.assertRaisesRegex(DCError, "disconnected"):
            solve_sheet(points, contacts, 1, 1, 0.25)

    def test_actual_material_units_and_bulk_values(self):
        text = """UNITS
 DISTANCE=METRE
 CONDUCTIVITY=SIEMENS/M
END_UNITS
 MATERIAL Metal6 CONDUCTIVITY=2.405e7 IMAG_CONDUCTIVITY=0 PERMEABILITY=1
 OPERATION Thickness EXPAND=9.9e-7 UP
 MASK 35 Name=Metal6 MATERIAL=Metal6 OPERATION=Thickness
"""
        material = material_from_ltd(text)
        self.assertAlmostEqual(material["sheet_resistance_ohm"], 1 / (2.405e7 * 9.9e-7))
        with self.assertRaises(DCError):
            material_from_ltd(text.replace("IMAG_CONDUCTIVITY=0", "IMAG_CONDUCTIVITY=1"))
        with self.assertRaises(DCError):
            material_from_ltd(text.replace("DISTANCE=METRE", "DISTANCE=MICRON"))


if __name__ == "__main__":
    unittest.main()
