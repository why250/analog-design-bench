"""Physical-limit and experiment-contract tests for Stage 2 analysis inputs."""

import copy
import importlib.util
import json
import math
from pathlib import Path
import unittest

import numpy as np

try:
    from ._bootstrap import BASELINE_TOOLS
except ImportError:
    from _bootstrap import BASELINE_TOOLS

try:
    from . import cases, model
except ImportError:
    import cases
    import model


class ModelTests(unittest.TestCase):
    def test_pinned_synthesis_is_unchanged(self):
        source = BASELINE_TOOLS/"analyze.py"
        spec = importlib.util.spec_from_file_location("ideal_baseline", source)
        ideal = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ideal)
        manifest = model.baseline()
        self.assertEqual([e["value_si"] for e in manifest["elements"]],
                         [e["value_si"] for e in ideal.synthesize()["elements"]])
        frequencies = np.r_[0., np.linspace(1e6, 120e9, 1201), 65e9, 80e9]
        np.testing.assert_allclose(model.abcd_s(frequencies, manifest), ideal.abcd_s(frequencies), atol=2e-12)

    def test_dc_loss_bound_and_units(self):
        manifest = model.resolve(q=40)
        resistance = sum(e["rs_ohm"] for e in manifest["elements"] if e["kind"] == "L")
        self.assertAlmostEqual(resistance, 395.466382381918/40, places=12)
        np.testing.assert_allclose(model.abcd_s([0., 1e-6], manifest),
                                   np.repeat(model.dc_s(manifest)[None], 2, axis=0), atol=1e-14)
        for q, passes_dc_match in ((30, False), (40, True)):
            self.assertEqual(abs(model.dc_s(model.resolve(q=q))[0, 0]) < .1, passes_dc_match)

    def test_series_arm_parasitic_is_terminal_to_terminal(self):
        manifest = model.resolve(q=80, f_l0_hz=100e9)
        element = manifest["elements"][4]
        self.assertAlmostEqual(element["cp_f"]*1e15, 10.1653724348, places=9)
        expected_srf = math.sqrt((2*math.pi*100e9)**2-(element["rs_ohm"]/element["value_si"])**2)/(2*math.pi)
        diagnostics = model.device_diagnostics(element)
        self.assertAlmostEqual(diagnostics["actual_srf_hz"]/expected_srf, 1., places=14)
        z = model.device_impedance([expected_srf*.999, expected_srf*1.001], element)
        self.assertGreater(z[0].imag, 0)
        self.assertLess(z[1].imag, 0)

    def test_frozen_coefficient_perturbation(self):
        original = model.resolve(**cases.ANCHOR_B)
        altered = model.perturb(original, {"L3": 1.01, "C1": .99})
        for before, after in zip(original["elements"], altered["elements"]):
            for key in ("rs_ohm", "cp_f", "esr_ohm", "esl_h"):
                self.assertEqual(before.get(key), after.get(key))
        self.assertNotEqual(model.physical_hash(original), model.physical_hash(altered))
        self.assertEqual(original["elements"][4]["value_si"], model.baseline()["elements"][4]["value_si"])

    def test_lossless_resonances_have_finite_scattering(self):
        for f0 in (80e9, 100e9, 120e9):
            manifest = model.resolve(f_l0_hz=f0)
            frequencies = np.array([f0*(1-1e-8), f0, f0*(1+1e-8)])
            s = model.abcd_s(frequencies, manifest)
            self.assertTrue(np.isfinite(s).all())
            self.assertLess(abs(s[1, 1, 0]), 1e-12)
            self.assertLess(np.max(abs(np.swapaxes(s.conj(), 1, 2)@s-np.eye(2))), 1e-8)
        manifest = model.resolve(esl_h=40e-12)
        for element in manifest["elements"]:
            if element["kind"] == "C":
                f0 = model.device_diagnostics(element)["actual_srf_hz"]
                self.assertTrue(np.isfinite(model.abcd_s([f0], manifest)).all())

    def test_all_initial_cases_are_passive_and_reciprocal(self):
        frequencies = np.r_[0., np.linspace(1e6, 120e9, 121), 65e9, 80e9]
        for row in cases.unique_cases():
            s = model.abcd_s(frequencies, row["manifest"])
            self.assertLess(np.max(abs(s[:, 1, 0]-s[:, 0, 1])), 1e-10, row["case_id"])
            power = np.eye(2)-np.swapaxes(s.conj(), 1, 2)@s
            self.assertGreaterEqual(np.min(np.linalg.eigvalsh(power)), -1e-10, row["case_id"])
        # Separate MNA construction cross-checks nontrivial lossy and resonant cases.
        for manifest in (model.resolve(**cases.ANCHOR_B), model.resolve(**cases.NEAR_RESONANCE)):
            for frequency in (1e6, 30e9, 65e9, 80e9, 100e9, 120e9):
                np.testing.assert_allclose(model.abcd_s([frequency], manifest)[0],
                                           model._nodal_s(frequency, manifest), atol=1e-11)

    def test_invalid_coefficients_and_topology_are_rejected(self):
        for value in (-1., math.inf, math.nan, True, "1"):
            with self.assertRaises(ValueError):
                model.resolve(q=value)
        for key in ("value_si", "rs_ohm", "cp_f"):
            manifest = model.baseline()
            manifest["elements"][0][key] = -1.
            with self.assertRaises(ValueError):
                model.validate(manifest)
        manifest = model.baseline()
        manifest["elements"].reverse()
        with self.assertRaises(ValueError):
            model.validate(manifest)


class ManifestTests(unittest.TestCase):
    def test_matrix_counts_and_anchor_selections(self):
        rows = cases.requests()
        counts = {family: sum(row["family"] == family for row in rows)
                  for family in ("E0", "E2", "E3", "E4", "E5", "E6", "E7", "E8")}
        self.assertEqual(counts, {"E0": 1, "E2": 10, "E3": 9, "E4": 17,
                                  "E5": 62, "E6": 64, "E7": 22, "E8": 20})
        self.assertEqual(len({r["request_id"] for r in rows}), 205)
        self.assertEqual(sum(bool(r["labels"].get("anchor_b")) for r in rows), 1)
        self.assertEqual(sum(bool(r["labels"].get("e9_near_resonance")) for r in rows), 1)
        self.assertEqual(len(cases.repetition_requests(rows)), 3)

    def test_dedupe_retains_mappings_without_shared_mutable_manifests(self):
        rows = cases.requests()
        self.assertLess(len(cases.unique_cases(rows)), len(rows))
        canonical = {r["case_id"]: r["physical_sha256"] for r in cases.unique_cases(rows)}
        for row in rows:
            self.assertEqual(canonical[row["case_id"]], model.physical_hash(row["manifest"]))
        encoded = json.dumps(rows, allow_nan=False, sort_keys=True)
        self.assertEqual(encoded, json.dumps(cases.requests(), allow_nan=False, sort_keys=True))
        duplicate = next(row for row in rows if row["case_id"] != row["request_id"])
        first = next(row for row in rows if row["request_id"] == duplicate["case_id"])
        snapshot = copy.deepcopy(first["manifest"])
        duplicate["manifest"]["elements"][0]["value_si"] *= 2
        self.assertEqual(first["manifest"], snapshot)


if __name__ == "__main__":
    unittest.main()
