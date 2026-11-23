"""Independent numerical checks for end-to-end extraction and raw data handling."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

import numpy as np

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import analyze_em as analyzer


def s_from_z(z, reference=50):
    z = np.asarray(z, dtype=complex)
    identity = np.eye(len(z))
    return np.linalg.solve((z + reference * identity).T, (z - reference * identity).T).T


class ExtractionTests(unittest.TestCase):
    def test_nonsymmetric_full_device_normalization(self):
        z = np.array([[4 + 20j, 1 + 6j], [2 + 3j, 5 + 15j]])
        row = analyzer.point_metrics(65e9, s_from_z(z), 50)
        expected = z[0, 0] + z[1, 1] - z[0, 1] - z[1, 0]
        self.assertAlmostEqual(row["differential"]["R_ohm"], expected.real)
        self.assertAlmostEqual(row["differential"]["L_h"], expected.imag / (2 * np.pi * 65e9), places=20)
        grounded = z[0, 0] - z[0, 1] * z[1, 0] / z[1, 1]
        self.assertAlmostEqual(row["grounded_terminal_2"]["impedance"]["imag_ohm"], grounded.imag)
        self.assertNotAlmostEqual(expected.imag, grounded.imag)

    def test_center_tap_is_open_not_matched(self):
        z = np.array([[7 + 40j, 2 + 15j, 1 + 9j], [2 + 15j, 8 + 42j, 2 + 4j], [1 + 9j, 2 + 4j, 12 + 20j]])
        row = analyzer.point_metrics(65e9, s_from_z(z), 50)
        expected = z[0, 0] + z[1, 1] - z[0, 1] - z[1, 0]
        matched = z[:2, :2] - np.outer(z[:2, 2], z[2, :2]) / (z[2, 2] + 50)
        matched_zd = matched[0, 0] + matched[1, 1] - matched[0, 1] - matched[1, 0]
        observed = row["differential"]["impedance"]
        self.assertAlmostEqual(observed["real_ohm"], expected.real)
        self.assertAlmostEqual(observed["imag_ohm"], expected.imag)
        self.assertGreater(abs(expected - matched_zd), 0.1)

    def test_exact_singular_common_mode_keeps_unique_differential(self):
        series = 2 + 49j
        r, t = series / (series + 100), 100 / (series + 100)
        row = analyzer.point_metrics(65e9, np.array([[r, t], [t, r]]), 50)
        self.assertEqual(row["s_to_z"]["status"], "SINGULAR_FULL_Z")
        self.assertEqual(row["differential"]["status"], "CONSTRAINED_FINITE")
        self.assertAlmostEqual(row["differential"]["R_ohm"], series.real)
        self.assertAlmostEqual(row["differential"]["impedance"]["imag_ohm"], series.imag)
        self.assertAlmostEqual(row["grounded_terminal_2"]["impedance"]["imag_ohm"], series.imag)
        json.dumps(row, allow_nan=False)

    def test_open_network_is_typed_not_regularized(self):
        row = analyzer.point_metrics(65e9, np.eye(2), 50)
        self.assertEqual(row["differential"]["status"], "INCOMPATIBLE_CURRENT_OPEN_LIMIT")
        self.assertIsNone(row["differential"]["L_h"])
        json.dumps(row, allow_nan=False)

    def test_lossless_q_is_typed(self):
        metric = analyzer._metric(49j, 65e9, "FINITE")
        self.assertEqual(metric["Q"]["status"], "POSITIVE_INFINITY_LIMIT")
        self.assertIsNone(metric["Q"]["value"])
        json.dumps(metric, allow_nan=False)

    def test_matrix_passivity_catches_gain_when_each_entry_below_one(self):
        s = np.full((2, 2), 0.8, dtype=complex)
        row = analyzer.point_metrics(65e9, s, 50)
        self.assertLess(np.max(abs(s)), 1)
        self.assertEqual(row["passivity"]["state"], "FAIL")
        self.assertAlmostEqual(row["passivity"]["minimum_eigenvalue"], -1.56)

    def test_no_device_pass_without_numerical_evidence(self):
        frequencies = np.array([10e9, 65e9, 80e9])
        s = np.array([s_from_z([[20 + 1j * 2 * np.pi * f * 60e-12, 20], [20, 20 + 1j * 2 * np.pi * f * 60e-12]]) for f in frequencies])
        report = analyzer.analyze_network(analyzer.Network(frequencies, s, 50))
        self.assertEqual(report["criteria"]["L65"]["nominal_state"], "PASS")
        self.assertEqual(report["device_target_result"], "INDETERMINATE")
        self.assertEqual(report["full_filter_acceptance"], "NOT EVALUATED")
        json.dumps(report, allow_nan=False)

    def test_inclusive_bound_with_uncertainty(self):
        self.assertEqual(analyzer._interval_state(115, 1, 114, 126), "PASS")
        self.assertEqual(analyzer._interval_state(114, 1, 114, 126), "INDETERMINATE")
        self.assertEqual(analyzer._interval_state(112, 1, 114, 126), "FAIL")

    def test_actual_reference_resistance_is_used(self):
        z = np.array([[7 + 25j, 1 + 7j], [1 + 7j, 8 + 26j]])
        row = analyzer.point_metrics(65e9, s_from_z(z, 75), 75)
        self.assertAlmostEqual(row["differential"]["impedance"]["imag_ohm"], 37)
        self.assertAlmostEqual(row["differential"]["R_ohm"], 13)

    def test_sparse_grid_cannot_pass_with_operator_coverage_flags(self):
        frequencies = np.array([10e9, 65e9, 80e9])
        matrices = np.array([s_from_z(20 * np.ones((2, 2)) + np.eye(2) * (0.5 + 1j * 2 * np.pi * f * 60e-12)) for f in frequencies])
        evidence = {"L_absolute_pH": 1, "reactance_absolute_ohm": 0,
                    "coverage_10_65": True, "coverage_through_80": True,
                    "checks": {name: True for name in analyzer.REQUIRED_CHECKS}}
        report = analyzer.analyze_network(analyzer.Network(frequencies, matrices, 50), evidence)
        self.assertEqual(report["device_target_result"], "INDETERMINATE")
        self.assertFalse(report["sampling"]["flatness_10_65"]["grid_complete"])

    def test_complete_grid_and_evidence_allow_pass(self):
        frequencies = np.r_[np.array([0.01, 0.1, 1]), np.arange(5, 81)] * 1e9
        matrices = np.array([s_from_z(20 * np.ones((2, 2)) + np.eye(2) * (0.5 + 1j * 2 * np.pi * f * 60e-12)) for f in frequencies])
        evidence = {"L_absolute_pH": 1, "reactance_absolute_ohm": 0,
                    "coverage_10_65": True, "coverage_through_80": True,
                    "checks": {name: True for name in analyzer.REQUIRED_CHECKS}}
        report = analyzer.analyze_network(analyzer.Network(frequencies, matrices, 50), evidence)
        self.assertEqual(report["device_target_result"], "PASS")
        self.assertEqual(report["gaps"], [])

    def test_ill_conditioning_is_reported_without_regularization(self):
        row = analyzer.point_metrics(65e9, np.diag([1 - 1e-14, 0]).astype(complex), 50)
        self.assertEqual(row["differential"]["status"], "FINITE")
        self.assertTrue(row["differential_solver"]["ill_conditioned"])
        self.assertGreater(row["differential_solver"]["condition_number"], analyzer.CONDITION_WARNING)


class TouchstoneTests(unittest.TestCase):
    def test_two_port_legacy_order(self):
        network = analyzer.parse_touchstone("# GHz S RI R 50\n65 1 2 3 4 5 6 7 8\n", 2)
        np.testing.assert_array_equal(network.s[0], [[1 + 2j, 5 + 6j], [3 + 4j, 7 + 8j]])
        self.assertEqual(network.frequency_hz[0], 65e9)

    def test_three_port_row_order_with_continuations(self):
        text = "# Hz S RI R 75\n1 1 0 2 0 3 0\n 4 0 5 0 6 0\n 7 0 8 0 9 0\n"
        network = analyzer.parse_touchstone(text, 3)
        np.testing.assert_array_equal(network.s[0], np.arange(1, 10).reshape(3, 3))
        self.assertEqual(network.reference_ohm, 75)

    def test_ma_and_db(self):
        ma = analyzer.parse_touchstone("# MHz S MA R 50\n1 1 90 0 0 0 0 1 -90", 2)
        db = analyzer.parse_touchstone("# MHz S DB R 50\n1 0 90 -400 0 -400 0 0 -90", 2)
        self.assertAlmostEqual(ma.s[0, 0, 0].imag, 1)
        self.assertAlmostEqual(db.s[0, 1, 1].imag, -1)

    def test_reject_missing_or_nonfinite_and_repeated_frequency(self):
        for text in ["# Hz S RI R 50\n1 0 0", "# Hz S RI R 50\n1 nan 0 0 0 0 0 0 0", "# Hz S RI R 50\n1 0 0 0 0 0 0 0 0\n1 0 0 0 0 0 0 0 0"]:
            with self.assertRaises(analyzer.NetworkError):
                analyzer.parse_touchstone(text, 2)


if __name__ == "__main__":
    unittest.main()
