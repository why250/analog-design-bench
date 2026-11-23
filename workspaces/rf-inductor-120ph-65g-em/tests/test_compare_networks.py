"""Numerical-control profile, full-port, association and interpolation checks."""

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from analyze_em import Network
from compare_networks import ComparisonError, compare_files, compare_networks
from convert_cti import SNetwork, write_touchstone


def s_from_z(z):
    z = np.asarray(z, complex)
    identity = np.eye(len(z))
    return np.linalg.solve((z + 50 * identity).T, (z - 50 * identity).T).T


def network(frequencies=(65e9, 80e9), inductance=120e-12, resistance=1):
    return Network(np.array(frequencies, float), np.array([s_from_z(20 * np.ones((2, 2)) + np.eye(2) * (resistance / 2 + 1j * np.pi * frequency * inductance)) for frequency in frequencies]), 50)


class ComparisonTests(unittest.TestCase):
    def test_identical_network_passes_canonical_all_points(self):
        source = network()
        report = compare_networks(source, source, "canonical")
        self.assertEqual(report["control_result"], "PASS")
        self.assertEqual(len(report["points"]), 2)
        self.assertTrue(report["all_candidate_points_compared"])
        self.assertEqual(report["maxima"]["absolute_S_difference"]["value"], 0)
        json.dumps(report, allow_nan=False)

    def test_port_profile_has_no_invented_pass_threshold(self):
        report = compare_networks(network(), network(inductance=140e-12), "port")
        self.assertEqual(report["control_result"], "REPORT_ONLY")
        self.assertIsNone(report["points"][0]["checks"]["relative_L"]["inclusive_limit"])
        self.assertGreater(report["maxima"]["absolute_L_difference_pH"]["value"], 19.9)

    def test_mesh_uses_L_and_Q_but_reports_S(self):
        reference, candidate = network(), network(inductance=121e-12)
        report = compare_networks(reference, candidate, "mesh")
        self.assertEqual(report["control_result"], "PASS")
        self.assertEqual(report["points"][0]["checks"]["maximum_absolute_S"]["state"], "REPORT_ONLY")
        failed = compare_networks(reference, network(inductance=124e-12), "mesh")
        self.assertEqual(failed["control_result"], "FAIL")

    def test_reproduction_Q_is_report_only(self):
        report = compare_networks(network(), network(), "reproduction")
        self.assertEqual(report["points"][0]["checks"]["relative_Q"]["state"], "REPORT_ONLY")
        self.assertEqual(report["inclusive_limits"]["maximum_absolute_S"], 1e-5)

    def test_missing_exact_reference_and_no_extrapolation(self):
        reference = network((60e9, 80e9))
        candidate = network((65e9,))
        with self.assertRaises(ComparisonError):
            compare_networks(reference, candidate, "afs")
        with self.assertRaises(ComparisonError):
            compare_networks(reference, network((90e9,)), "afs", "linear", "AFS-derived")
        with self.assertRaises(ComparisonError):
            compare_networks(reference, candidate, "afs", "linear", "actual")

    def test_linear_AFS_reference_records_complete_asymmetric_brackets(self):
        first = np.array([[0.1 + 0.1j, 0.15 + 0.02j], [0.2 + 0.03j, 0.1 + 0.05j]])
        second = first + np.array([[0.01j, 0.02], [-0.01j, 0.03j]])
        interpolated = 0.75 * first + 0.25 * second
        reference = Network(np.array([60e9, 80e9]), np.array([first, second]), 50)
        candidate = Network(np.array([65e9]), np.array([interpolated]), 50)
        report = compare_networks(reference, candidate, "return", "linear", "AFS-derived")
        point = report["points"][0]
        self.assertEqual(point["S"]["maximum_absolute_difference"], 0)
        self.assertEqual(point["reference_sample"]["source_frequencies_hz"], [60e9, 80e9])
        self.assertEqual(point["reference_sample"]["weights"], [0.75, 0.25])
        self.assertTrue(report["reference_interpolation_performed"])
        self.assertFalse(report["interpolated_reference_is_actual_solve"])

    def test_all_three_ports_participate_in_maximum_S_difference(self):
        z = np.diag([20 + 30j, 20 + 30j, 50 + 10j])
        first = s_from_z(z)
        second = first.copy()
        second[2, 2] += 1e-3
        reference = Network(np.array([65e9]), first[None], 50)
        candidate = Network(np.array([65e9]), second[None], 50)
        report = compare_networks(reference, candidate, "canonical")
        self.assertEqual(report["port_count"], 3)
        self.assertEqual(report["control_result"], "FAIL")
        self.assertAlmostEqual(report["points"][0]["S"]["maximum_absolute_difference"], 1e-3)
        with self.assertRaises(ComparisonError):
            compare_networks(reference, network((65e9,)), "canonical")

    def test_open_limit_is_typed_and_not_finite_Q(self):
        source = Network(np.array([65e9]), np.eye(2, dtype=complex)[None], 50)
        report = compare_networks(source, source, "canonical")
        self.assertEqual(report["control_result"], "INDETERMINATE")
        self.assertEqual(report["points"][0]["Q"]["relative_status"], "UNDEFINED_DERIVED_VALUE")
        self.assertEqual(report["points"][0]["Zd"]["status"], "UNDEFINED_IMPEDANCE_LIMIT")
        json.dumps(report, allow_nan=False)

    def test_near_frequency_is_not_silently_exact(self):
        with self.assertRaises(ComparisonError):
            compare_networks(network((65e9,)), network((65e9 + 0.01,)), "reproduction")

    def test_a_matching_prefix_cannot_hide_uncompared_candidate_points(self):
        with self.assertRaises(ComparisonError):
            compare_networks(network((65e9,)), network((65e9, 80e9)), "canonical")

    def test_fresh_file_outputs_and_source_integrity(self):
        source = network()
        buffer = io.StringIO()
        write_touchstone(SNetwork(tuple(source.frequency_hz), tuple(tuple(tuple(row) for row in matrix) for matrix in source.s), "test"), buffer, 50)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "input.s2p"
            model.write_text(buffer.getvalue(), encoding="ascii")
            original = model.read_bytes()
            output = root / "comparison"
            report = compare_files(model, model, "reproduction", output, csv_output=True)
            self.assertEqual(report["control_result"], "PASS")
            self.assertEqual(len((output / "comparison.csv").read_text().splitlines()), 3)
            self.assertEqual(json.loads((output / "comparison.json").read_text())["source_models"]["candidate"]["path"], str(model))
            with self.assertRaises(FileExistsError):
                compare_files(model, model, "reproduction", output)
            self.assertEqual(model.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
