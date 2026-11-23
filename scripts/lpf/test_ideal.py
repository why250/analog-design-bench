"""Regression checks for the parametric ideal low-pass stage."""

from pathlib import Path
import tempfile
import unittest

import numpy as np

from .ideal import abcd_s, measure, run_ideal, synthesize


BASE_SPEC = {
    "schema_version": 1,
    "impedance_ohm": 50.0,
    "passband_hz": 65e9,
    "s11_max_db": -20.0,
    "s22_max_db": -20.0,
    "stopbands": [{"frequency_hz": 80e9, "s21_max_db": -20.0}],
    "insertion_loss_max_db": 1.0,
    "return_loss_margin_db": 1.0,
    "max_order": 15,
}


class IdealTests(unittest.TestCase):
    def test_legacy_filter_matches_the_retained_synthesis(self):
        design = synthesize(BASE_SPEC)
        self.assertEqual(design["order"], 9)
        self.assertAlmostEqual(design["order_bound"], 8.103339204775397, places=12)
        values = [element["value"] for element in design["elements"]]
        self.assertAlmostEqual(values[0] * 1e12, 120.674157213694, places=9)
        self.assertAlmostEqual(values[1] * 1e15, 71.5588254888531, places=9)
        np.testing.assert_allclose(values, list(reversed(values)), rtol=1e-13, atol=0)
        freq = np.array([1e6, 65e9, 80e9])
        result = measure(BASE_SPEC, freq, abcd_s(freq, design))
        self.assertTrue(result["passes"])
        self.assertAlmostEqual(result["metrics"]["s11_worst"]["value_db"], -21.0, places=9)
        self.assertAlmostEqual(result["metrics"]["s22_worst"]["value_db"], -21.0, places=9)
        self.assertAlmostEqual(result["metrics"]["il_worst"]["value_db"], 0.0346349774555, places=10)
        self.assertAlmostEqual(result["metrics"]["stopbands"][0]["value_db"], -25.1637752971, places=8)
        np.testing.assert_allclose(abcd_s(0, design)[0], [[0, 1], [1, 0]], atol=0)

    def test_new_mask_and_impedance_change_the_synthesis_and_evidence(self):
        spec = {
            **BASE_SPEC,
            "impedance_ohm": 75.0,
            "passband_hz": 50e9,
            "stopbands": [{"frequency_hz": 75e9, "s21_max_db": -25.0}],
        }
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            report = run_ideal(spec, out)
            self.assertTrue(report["passed"])
            self.assertEqual(report["verification"], "analytic")
            self.assertIsNone(report["ads"])
            self.assertEqual(report["design"]["order"], 7)
            self.assertEqual(report["measurement"]["metrics"]["stopbands"][0]["sample_hz"], 75e9)
            self.assertIn("# Hz S RI R 75", (out / "sparameters.s2p").read_text())
            self.assertIn("Analytical prediction", (out / "report.md").read_text(encoding="utf-8"))
            with self.assertRaises(FileExistsError):
                run_ideal(spec, out)

    def test_missing_stop_sample_cannot_pass(self):
        spec = {**BASE_SPEC, "stopbands": [
            {"frequency_hz": 80e9, "s21_max_db": -20.0},
            {"frequency_hz": 81e9, "s21_max_db": -20.0},
        ]}
        freq = np.array([1e6, 65e9, 80e9])
        result = measure(spec, freq, abcd_s(freq, synthesize(spec)))
        self.assertFalse(result["passes"])
        self.assertIsNone(result["metrics"]["stopbands"][1]["sample_hz"])

    def test_neighboring_checkpoints_cannot_share_a_sample(self):
        spec = {**BASE_SPEC, "stopbands": [
            {"frequency_hz": 80e9, "s21_max_db": -20.0},
            {"frequency_hz": 80e9 + 0.5, "s21_max_db": -20.0},
        ]}
        freq = np.array([1e6, 65e9, 80e9])
        result = measure(spec, freq, abcd_s(freq, synthesize(spec)))
        self.assertFalse(result["passes"])
        self.assertIsNone(result["metrics"]["stopbands"][1]["sample_hz"])

    def test_strict_match_and_inclusive_stop(self):
        freq = np.array([1e6, 65e9, 80e9])
        samples = np.full((3, 2, 2), 0.1, dtype=complex)
        samples[:2, 1, 0] = 1
        report_only = {**BASE_SPEC, "insertion_loss_max_db": None}
        result = measure(report_only, freq, samples)
        self.assertFalse(result["metrics"]["s11_worst"]["passes"])
        self.assertTrue(result["metrics"]["stopbands"][0]["passes"])
        self.assertIsNone(result["metrics"]["il_worst"]["passes"])

    def test_nonfinite_data_is_rejected(self):
        freq = np.array([1e6, 65e9, 80e9])
        samples = abcd_s(freq, synthesize(BASE_SPEC))
        samples[0, 0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "finite"):
            measure(BASE_SPEC, freq, samples)

    def test_maximum_order_is_enforced(self):
        with self.assertRaisesRegex(ValueError, "odd order 9"):
            synthesize({**BASE_SPEC, "max_order": 7})

    def test_zero_requested_margin_still_meets_the_strict_match(self):
        spec = {**BASE_SPEC, "return_loss_margin_db": 0.0}
        design = synthesize(spec)
        freq = np.array([1e6, 65e9, 80e9])
        self.assertTrue(measure(spec, freq, abcd_s(freq, design))["passes"])


if __name__ == "__main__":
    unittest.main()
