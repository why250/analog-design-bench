"""Checks for point provenance, port ordering, conflicts and explicit DC anchors."""

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from analyze_em import Network, point_metrics, read_touchstone
from combine_models import CombinationError, Segment, assemble, combine_networks, dc_series_matrix
from convert_cti import SNetwork, write_touchstone


def segment(kind, frequencies, matrices, name="segment.s2p"):
    return Segment(kind, Path(name), Network(np.array(frequencies, dtype=float), np.array(matrices, dtype=complex), 50.0), {"path": name})


def write_segment(path, frequencies, matrices):
    buf = io.StringIO()
    write_touchstone(SNetwork(tuple(frequencies), tuple(tuple(tuple(row) for row in item) for item in matrices), "test"), buf, 50)
    path.write_text(buf.getvalue(), encoding="ascii")


class CombinationTests(unittest.TestCase):
    def test_sorted_asymmetric_matrix_association(self):
        a = np.array([[0.1 + 0.2j, 0.3 + 0.4j], [0.5 + 0.6j, 0.7 + 0.8j]])
        b = a * 0.5
        network, receipt = combine_networks([segment("actual", [80e9], [a]), segment("AFS-derived", [65e9], [b])])
        np.testing.assert_array_equal(network.frequency_hz, [65e9, 80e9])
        np.testing.assert_array_equal(network.s, [b, a])
        self.assertTrue(receipt["contains_AFS_derived_samples"])
        self.assertEqual(receipt["point_provenance"][0]["segment_index"], 1)

    def test_duplicate_actual_preferred_and_complete_delta_retained(self):
        actual = np.array([[0.1, 0.2], [0.3, 0.4j]], dtype=complex)
        afs = actual + (0.01 + 0.02j)
        network, receipt = combine_networks([segment("AFS-derived", [65e9], [afs]), segment("actual", [65e9], [actual])])
        np.testing.assert_array_equal(network.s[0], actual)
        self.assertEqual(receipt["point_provenance"][0]["kind"], "actual")
        comparison = receipt["duplicate_frequency_comparisons"][0]["comparisons"][0]
        np.testing.assert_allclose(np.array(comparison["complete_complex_delta_S"]), np.tile([-0.01, -0.02], (2, 2, 1)))
        json.dumps(receipt, allow_nan=False)

    def test_conflicting_actuals_rejected_all_pairs(self):
        a = np.zeros((2, 2), complex)
        with self.assertRaises(CombinationError):
            combine_networks([segment("actual", [65e9], [a]), segment("actual", [65e9], [a + 2e-5])])
        with self.assertRaises(CombinationError):
            combine_networks([segment("actual", [65e9], [a]), segment("actual", [65e9], [a + 0.9e-5]), segment("actual", [65e9], [a - 0.9e-5])])

    def test_complete_three_port_preserved(self):
        matrix = np.arange(9).reshape(3, 3) * (0.01 + 0.02j)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, receipt = root / "source.s3p", root / "assembled.s3p", root / "assembly.json"
            write_segment(source, [65e9], [matrix])
            assemble([("actual", source)], output, receipt)
            loaded = read_touchstone(output)
            self.assertEqual(loaded.port_count, 3)
            np.testing.assert_array_equal(loaded.s[0], matrix)
            with self.assertRaises(CombinationError):
                assemble([("actual", source)], root / "truncated.s2p", root / "other.json")

    def test_near_frequencies_are_not_collapsed(self):
        matrix = np.zeros((2, 2), complex)
        network, receipt = combine_networks([segment("actual", [65e9], [matrix]), segment("AFS-derived", [65e9 + 0.01], [matrix])])
        self.assertEqual(len(network.frequency_hz), 2)
        self.assertEqual(receipt["duplicate_frequency_comparisons"], [])

    def test_dc_matrix_has_expected_series_R_and_is_passive(self):
        resistance = 0.25
        matrix = dc_series_matrix(resistance)
        row = point_metrics(0, matrix, 50)
        self.assertAlmostEqual(row["differential"]["R_ohm"], resistance, places=12)
        self.assertEqual(row["s_to_z"]["status"], "SINGULAR_FULL_Z")
        self.assertEqual(row["passivity"]["state"], "PASS")
        self.assertEqual(row["reciprocity"]["state"], "PASS")
        np.testing.assert_allclose(matrix, [[resistance / 100.25, 100 / 100.25], [100 / 100.25, resistance / 100.25]])

    def test_no_implicit_dc_and_explicit_reviewed_anchor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "lf.s2p"
            resistance = 0.25
            write_segment(source, [1e7], [dc_series_matrix(resistance)])
            dc = root / "dc.json"
            dc.write_text(json.dumps({"status": "NUMERICAL_DC_SHEET_ESTIMATE", "finest_R_ohm": resistance}))
            evidence = root / "agreement.json"
            evidence.write_text(json.dumps({"state": "AGREEMENT_ESTABLISHED", "dc_resistance_ohm": resistance,
                "rf_frequency_hz": 1e7, "rf_resistance_ohm": resistance, "absolute_tolerance_ohm": 1e-10,
                "reference_planes_consistent": True, "contact_model_reviewed": True,
                "low_frequency_justification": "Fixture with frequency-independent series resistance", "evidence_files": ["lf.s2p"]}))
            ordinary = assemble([("actual", source)], root / "ordinary.s2p", root / "ordinary.json")
            self.assertFalse(ordinary["DC_anchor"]["included"])
            self.assertEqual(len(read_touchstone(root / "ordinary.s2p").frequency_hz), 1)
            with self.assertRaises(CombinationError):
                assemble([("actual", source)], root / "implicit.s2p", root / "implicit.json", dc_resistance_json=dc)
            anchored = assemble([("actual", source)], root / "anchored.s2p", root / "anchored.json", include_dc=True, dc_resistance_json=dc, lf_agreement_json=evidence)
            self.assertTrue(anchored["DC_anchor"]["included"])
            self.assertEqual(read_touchstone(root / "anchored.s2p").frequency_hz[0], 0)
            self.assertIn("DERIVED_DC_ANCHOR", anchored["model_classification"])

    def test_afs_output_is_not_labeled_actual_or_raw(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "afs.s2p"
            write_segment(source, [65e9], [np.zeros((2, 2), complex)])
            report = assemble([("AFS-derived", source)], root / "composite.s2p", root / "receipt.json")
            self.assertEqual(report["model_classification"], "COMPOSITE_CONTAINING_AFS_DERIVED_SAMPLES")
            self.assertNotIn("Complete raw", (root / "composite.s2p").read_text())

    def test_reject_reference_mismatch_and_loosened_conflict_limit(self):
        first = segment("actual", [65e9], [np.zeros((2, 2), complex)])
        other = Segment("actual", Path("other.s2p"), Network(np.array([80e9]), np.zeros((1, 2, 2), complex), 75), {"path": "other.s2p"})
        with self.assertRaises(CombinationError):
            combine_networks([first, other])
        with self.assertRaises(CombinationError):
            combine_networks([first], 1e-4)

    def test_existing_output_preserves_source_and_prior_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "input.s2p", root / "assembled.s2p"
            write_segment(source, [65e9], [np.zeros((2, 2), complex)])
            original = source.read_bytes()
            output.write_text("Prior artifact")
            with self.assertRaises(FileExistsError):
                assemble([("actual", source)], output, root / "assembly.json")
            self.assertEqual(output.read_text(), "Prior artifact")
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
