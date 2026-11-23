"""Check exact-size screening and native evidence gates without an ADS license."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

from scripts.lpf.ideal import abcd_s, synthesize
from scripts.lpf.search import _paired_assignments, load_touchstone, run_search, sample_passivity_note, write_touchstone


class SearchTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.spec = {
            "passband_hz": 65e9, "impedance_ohm": 50,
            "s11_max_db": -20, "s22_max_db": -20, "insertion_loss_max_db": 1,
            "stopbands": [{"frequency_hz": 80e9, "s21_max_db": -20}],
        }
        self.design = synthesize(self.spec)
        self.profile = {
            "devices": {
                "L": {"variables": ["diameter"], "fixed_parameters": {"gap": 10}},
                "C": {"variables": ["width"], "fixed_parameters": {"length": 12}},
            }
        }
        self.frequency = np.unique(np.r_[np.linspace(1e6, 120e9, 2401), 65e9, 80e9])
        self.budgets = {"paired_cases": 16, "unpaired_cases": 4, "ads_runs": 0, "new_samples": 0}

    def _catalog(self, *, cutoff=120e9, wrong_margin=False):
        entries = []
        for kind, variable in (("L", "diameter"), ("C", "width")):
            unique_values = sorted({
                round(item["value"], 22) for item in self.design["elements"] if item["kind"] == kind
            })
            for index, value in enumerate(unique_values):
                identifier = f"{kind}-{index}"
                path = self.root / f"{identifier}.s2p"
                frequency = self.frequency[self.frequency <= cutoff]
                s = abcd_s(frequency, {
                    "impedance_ohm": 50, "elements": [{"kind": kind, "value": value}],
                })
                write_touchstone(path, frequency, s, 50)
                parameters = {**self.profile["devices"][kind]["fixed_parameters"], variable: 10 + index}
                if wrong_margin and kind == "C":
                    parameters["length"] = 13
                entries.append({
                    "id": identifier, "kind": kind, "parameters": parameters, "touchstone": path.name,
                    "model_status": "conditional", "model_notes": ["Synthetic software-test data"],
                })
        index = self.root / "sample-index.json"
        index.write_text(json.dumps({"schema_version": 1, "samples": entries}), encoding="utf-8")
        return index

    def test_full_complex_touchstone_round_trip(self):
        p = self.root / "test.s2p"
        f = np.array([1e6, 2e6])
        s = np.arange(8).reshape(2, 2, 2) * (1 + 2j)
        write_touchstone(p, f, s, 75)
        measured_f, measured_s, z = load_touchstone(p)
        np.testing.assert_array_equal(measured_f, f)
        np.testing.assert_array_equal(measured_s, s)
        self.assertEqual(z, 75)

    def test_paired_search_uses_actual_full_two_ports_and_keeps_screen_status(self):
        index = self._catalog()
        result = run_search(self.spec, self.design, self.profile, self.root / "run",
                            sample_index=index, budgets=self.budgets)
        chosen = next(candidate for candidate in result["candidates"] if candidate["id"] == result["best_candidate_id"])
        self.assertTrue(chosen["passes"])
        self.assertEqual(chosen["verification"], "screen")
        self.assertEqual(chosen["model_status"], "conditional")
        ids = [device["sample_id"] for device in chosen["devices"]]
        self.assertEqual(ids, ids[::-1])
        self.assertEqual(result["search_counts"]["unpaired"], 0)
        self.assertLessEqual(result["search_counts"]["paired"], self.budgets["paired_cases"])
        self.assertTrue((self.root / "run" / chosen["screen_touchstone"]).is_file())

    def test_scaled_pairing_interleaves_priors_without_duplicate_cases(self):
        elements = [
            {"kind": "L", "value": 10}, {"kind": "C", "value": 10}, {"kind": "L", "value": 10},
        ]
        choices = {
            kind: [{"id": f"{kind}{value}", "effective_value": value} for value in (5, 7, 10)]
            for kind in ("L", "C")
        }
        spec = {"passband_hz": 50e9, "stopbands": [{"frequency_hz": 100e9}]}
        cases = [
            tuple(sample["id"] for sample in assignment)
            for assignment in _paired_assignments(spec, elements, choices)
        ]
        self.assertEqual(cases[:3], [("L10", "C10", "L10"), ("L7", "C7", "L7"), ("L5", "C5", "L5")])
        self.assertEqual(len(cases), len(set(cases)))
        self.assertEqual(len(cases), 9)

    def test_missing_frequency_coverage_is_not_an_electrical_failure(self):
        index = self._catalog(cutoff=75e9)
        budgets = self.budgets | {"paired_cases": 2}
        result = run_search(self.spec, self.design, self.profile, self.root / "run",
                            sample_index=index, budgets=budgets)
        self.assertEqual(result["candidates"], [])
        self.assertIsNone(result["best_near_miss_id"])
        self.assertEqual(result["search_counts"]["paired"], 2)
        self.assertEqual(result["search_counts"]["unpaired"], 4)
        self.assertTrue(all("cover" in issue["reason"] for issue in result["issues"]))

    def test_wrong_fixed_dimensions_cannot_enter_search(self):
        result = run_search(self.spec, self.design, self.profile, self.root / "run",
                            sample_index=self._catalog(wrong_margin=True), budgets=self.budgets)
        self.assertEqual(result["search_counts"]["paired"], 0)
        self.assertTrue(any("fixed parameter" in item["reason"] for item in result["issues"]))
        self.assertTrue(any(item.get("kind") == "C" for item in result["issues"]))

    def test_native_rerun_failure_does_not_promote_screen_result(self):
        from scripts.lpf import ads_pcell

        source = self.root / "source"
        with (
            patch.object(ads_pcell, "copy_workspace", return_value=source),
            patch.object(ads_pcell, "verify_candidate", side_effect=ValueError("missing native exact sample")),
        ):
            result = run_search(self.spec, self.design, self.profile, self.root / "run",
                                sample_index=self._catalog(), ads_workspace=source,
                                budgets=self.budgets | {"ads_runs": 1})
        self.assertEqual(result["search_counts"]["ads_runs"], 1)
        self.assertTrue(any("native_error" in item for item in result["candidates"]))
        self.assertTrue(all(item["verification"] == "screen" for item in result["candidates"]))
        self.assertEqual(result["search_counts"]["unpaired"], 4)

    def test_solver_passivity_overshoot_cannot_be_silent(self):
        frequency = np.array([1e9])
        self.assertIsNone(sample_passivity_note(frequency, np.array([np.eye(2)])))
        small = np.array([np.eye(2) * 1.00005])
        self.assertIn("passivity overshoot", sample_passivity_note(frequency, small))
        with self.assertRaisesRegex(ValueError, "passive-network"):
            sample_passivity_note(frequency, np.array([np.eye(2) * 1.001]))

    def test_headless_momentum_binding_restoration_is_checked_and_idempotent(self):
        from scripts.lpf.ads_pcell import bind_model_parameters

        self.profile["devices"]["L"].update(library="native", cell="spiral")
        model = self.root / "native" / "spiral" / "em%Model"
        model.mkdir(parents=True)
        (model / "model.ndx").write_text(
            "PARAM: diameter, 0, 0, 0, 1e-6, 1e-9, None, -1;\n"
            "PARAM: gap, 0, 0, 0, 1e-6, 1e-9, None, -1;\n",
            encoding="utf-8",
        )
        raw = "define spiral ( P1 P2 )\nMomCmpt:em_data P1 P2 \\\n    ModelReuse=1\nend spiral\n"
        bound, receipt = bind_model_parameters(raw, self.root, self.profile, [{"kind": "L"}])
        self.assertTrue(receipt[0]["restored"])
        self.assertIn('p0="diameter" v0=diameter v0_Resolution=0.001 um', bound)
        checked, checked_receipt = bind_model_parameters(bound, self.root, self.profile, [{"kind": "L"}])
        self.assertEqual(checked, bound)
        self.assertFalse(checked_receipt[0]["restored"])
        with self.assertRaisesRegex(ValueError, "disagrees"):
            bind_model_parameters(bound.replace('p0="diameter"', 'p0="other"'),
                                  self.root, self.profile, [{"kind": "L"}])


if __name__ == "__main__":
    unittest.main()
