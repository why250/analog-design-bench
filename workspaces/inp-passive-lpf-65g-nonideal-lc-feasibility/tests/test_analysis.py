"""Synthetic rejection/regression fixtures; these are not ADS evidence."""

import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

try:
    from . import _bootstrap
except ImportError:
    import _bootstrap

try:
    from . import analysis, model
except ImportError:
    import analysis
    import model


def fixture(manifest, prediction):
    f = np.unique(np.r_[np.linspace(1e6, 120e9, 2401),
                         np.linspace(1e6, 65e9, 1301), 65e9, 80e9,
                         [max(1e6, min(65e9, r + off)) for r in prediction['extrema_hz']
                          for off in [-400e3, -200e3, -100e3, 0, 100e3, 200e3, 400e3]]])
    s = model.abcd_s(f, manifest)
    rounds = []
    for spacing in [400e3, 200e3, 100e3]:
        rounds.append(analysis.measured_round(f, s, prediction, spacing))
    return f, s, rounds


class AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = model.baseline()
        cls.prediction = analysis.predict(cls.manifest)
        cls.f, cls.s, cls.history = fixture(cls.manifest, cls.prediction)

    def test_baseline_actual_stationary_roots_and_full_contract(self):
        self.assertTrue(self.prediction['coverage_justified'])
        peaks = 65e9 * np.cos(np.arange(5) * np.pi / 9)
        all_candidates = np.array(self.prediction['extrema_hz'])
        for peak in peaks:
            self.assertLess(np.min(abs(all_candidates - peak)), 1)
        report = analysis.verify(self.f, self.s, self.manifest,
                                 self.prediction, self.history)
        self.assertEqual(report['state'], 'PASS')
        json.dumps(report, allow_nan=False)
        self.assertAlmostEqual(report['metrics']['s11_worst']['value_db'], -21, places=8)
        self.assertAlmostEqual(report['metrics']['s21_80']['value_db'], -25.1637752971, places=8)

    def test_sample_only_cannot_pass_continuous_contract(self):
        report = analysis.verify(self.f, self.s, self.manifest, self.prediction)
        self.assertEqual(report['state'], 'INDETERMINATE')

    def test_missing_checkpoint_rejected(self):
        keep = abs(self.f - 80e9) > 1
        report = analysis.verify(self.f[keep], self.s[keep], self.manifest,
                                 self.prediction, self.history)
        self.assertEqual(report['state'], 'INDETERMINATE')
        self.assertFalse(report['coverage']['exact_80ghz'])
        self.assertEqual(report['metrics']['s21_80']['state'], 'INDETERMINATE')

    def test_nonfinite_and_corrupt_complex_data_invalid(self):
        bad = self.s.copy()
        bad[0, 0, 0] = np.nan
        self.assertEqual(analysis.verify(self.f, bad, self.manifest)['state'], 'INVALID')
        bad = self.s.copy()
        bad[0, 1, 0] = 1.01
        self.assertEqual(analysis.verify(self.f, bad, self.manifest)['state'], 'INVALID')

    def test_conflicting_duplicates_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.csv'
            with path.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.writer(stream)
                writer.writerow(analysis.FIELDS)
                writer.writerow([1e6, 0, 0, 1, 0, 1, 0, 0, 0])
                writer.writerow([1e6, 0, 0, .99, 0, 1, 0, 0, 0])
            with self.assertRaisesRegex(ValueError, 'Conflicting'):
                analysis.read_csv(path)

    def test_shifted_model_extrema_not_ideal_seeds(self):
        manifest = model.resolve(q=80, f_l0_hz=320e9, esr_ohm=.1, esl_h=2e-12)
        prediction = analysis.predict(manifest)
        self.assertTrue(prediction['coverage_justified'])
        roots = prediction['extrema_hz']
        self.assertTrue(any(min(abs(r - ideal) for ideal in self.prediction['extrema_hz']) > 1e6
                            for r in roots if r < 65e9))
        f, s, history = fixture(manifest, prediction)
        # Give the verifier an actual nonideal response with baseline-only extrema
        # coverage; it must withhold continuous acceptance.
        report = analysis.verify(self.f, model.abcd_s(self.f, manifest), manifest,
                                 prediction, history)
        self.assertFalse(report['coverage']['continuous_band_justified'])

    def test_violating_dc_sample_can_fail_incomplete_coverage(self):
        manifest = model.resolve(q=10)
        prediction = analysis.predict(manifest)
        f, s, _ = fixture(manifest, prediction)
        report = analysis.verify(f, s, manifest, prediction)
        self.assertEqual(report['state'], 'FAIL')
        self.assertFalse(report['coverage']['continuous_band_justified'])
        self.assertGreater(report['dc_limit']['il_worst']['value_db'], 1)

    def test_invalid_coefficient_rejected(self):
        manifest = model.baseline()
        manifest['elements'][0]['cp_f'] = -1e-15
        self.assertEqual(analysis.verify(self.f, self.s, manifest)['state'], 'INVALID')

    def test_prediction_must_match_resolved_physical_manifest(self):
        manifest = model.resolve(q=80)
        report = analysis.verify(self.f, model.abcd_s(self.f, manifest), manifest,
                                 self.prediction, self.history)
        self.assertEqual(report['state'], 'INVALID')

    def test_strict_limits_and_overlapping_uncertainty(self):
        for name, threshold in [('s11_worst', .1), ('s22_worst', .1),
                                ('il_worst', 10 ** (-1 / 20))]:
            equality = analysis._metric_record(name, threshold, 65e9, 0,
                                                threshold, threshold, True, [])
            self.assertEqual(equality['state'], 'FAIL')
            uncertain = analysis._metric_record(name, threshold, 65e9, 1e-6,
                                                 threshold - 1e-6, threshold + 1e-6,
                                                 True, [])
            self.assertEqual(uncertain['state'], 'INDETERMINATE')

    def test_incomplete_tracked_extrema_cannot_establish_pass(self):
        history = json.loads(json.dumps(self.history))
        for observation in history:
            observation['tracked_extrema']['s11_worst'].pop()
        report = analysis.verify(self.f, self.s, self.manifest, self.prediction, history)
        self.assertEqual(report['state'], 'INDETERMINATE')

    def test_rational_poles_are_stable_and_have_small_residuals(self):
        for manifest in [self.manifest, model.resolve(q=40, f_l0_hz=100e9, esr_ohm=.5, esl_h=10e-12)]:
            report = analysis.poles(manifest)
            self.assertTrue(report['residuals_ok'])
            self.assertEqual(report['pole_count'], report['denominator_degree'])
            self.assertTrue(all(p['stability'] == 'LHP' for p in report['poles']))

    def test_clustered_real_poles_survive_companion_seed_variation(self):
        manifest = model.resolve(q=200, f_l0_hz=640e9, esr_ohm=.1, esl_h=0)
        specification = analysis.rational_polynomials(manifest, precision=110)
        full = np.array([float(v) for v in specification['denominator']])
        full /= max(abs(full))
        original_polyroots = np.polynomial.polynomial.polyroots
        seen_reduced = []

        def perturbed_seeds(coefficients):
            coefficients = np.asarray(coefficients)
            # On the ADS host the full denominator companion matrix supplied
            # a spurious conjugate pair near -95; both Newton iterations then
            # converged to one real pole. That seed source must be bypassed.
            if coefficients.shape == full.shape and np.allclose(coefficients, full, rtol=1e-13, atol=0):
                raise AssertionError('Ill-conditioned full companion seed path reused')
            roots = original_polyroots(coefficients)
            if len(coefficients) == 9:
                seen_reduced.append(True)
                roots = roots + np.array([complex((-1)**j, (-1)**(j//2))
                                          for j in range(len(roots))]) * 1e-4
            return roots

        with patch.object(np.polynomial.polynomial, 'polyroots', side_effect=perturbed_seeds):
            report = analysis.poles(manifest)
        self.assertTrue(seen_reduced)
        self.assertTrue(report['residuals_ok'])
        self.assertEqual(report['denominator_degree'], 14)
        self.assertEqual(report['real_pole_count'], 6)
        self.assertTrue(all(report['root_completeness_checks'].values()))
        cluster = [p for p in report['poles'] if abs(p['normalized_p_real'] + 95) < 1
                   and abs(p['normalized_p_imag']) < 1e-12]
        self.assertEqual(len(cluster), 2)
        separation = abs(cluster[0]['normalized_p_real'] - cluster[1]['normalized_p_real'])
        self.assertGreater(separation, 1e-8)
        self.assertLess(separation, 2e-8)
        self.assertLess(report['coefficient_reconstruction_relative_error'], 1e-50)
        self.assertTrue(all(p['numerical_isolation_disk']['one_root_numerically_isolated']
                            for p in report['poles']))
        json.dumps(report, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
