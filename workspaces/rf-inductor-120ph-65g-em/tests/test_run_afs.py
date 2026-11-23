"""Validate the actual native c10 AFS export without running ADS."""

from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_afs import _verify_profile, validate_native_stimulus
from run_momentum import RunError, _json, _sha


# Exact c10 native exporter output: one statement, not three separate sweeps.
NATIVE_C10_STIMULUS = (
    "START 5 STOP 200 STEP 195,\n"
    "PT 10,\n"
    "PT 65,\n"
    "PT 80,\n"
    "PT 100,\n"
    "AFS S_50 MAXSAMPLES 54 SAMPLING ALL NORMAL;\n"
)
NATIVE_R2_STIMULUS = NATIVE_C10_STIMULUS.replace("PT 10,\n", "PT 10,\nPT 20,\nPT 40,\n")


class NativeAfsTests(unittest.TestCase):
    def test_actual_native_c10_profile(self):
        original = NATIVE_C10_STIMULUS
        profile = validate_native_stimulus(original)
        self.assertEqual(profile["forced_exact_GHz"], [10, 65, 80, 100])
        self.assertEqual(profile["required_exact_GHz"], [65, 80])
        self.assertEqual(profile["adaptive"]["adaptive_sample_budget"], 50)
        self.assertEqual(profile["adaptive"]["forced_point_count"], 4)
        self.assertEqual(profile["adaptive"]["exported_combined_maximum_samples"], 54)
        self.assertEqual(profile["band_GHz"], [5, 200])
        self.assertFalse(profile["target_and_thresholds_changed"])
        self.assertEqual(original, NATIVE_C10_STIMULUS)

    def test_r2_uses_six_forced_points_and_the_same_combined_cap(self):
        profile = validate_native_stimulus(NATIVE_R2_STIMULUS)
        self.assertEqual(profile["forced_exact_GHz"], [10, 20, 40, 65, 80, 100])
        self.assertEqual(profile["adaptive"]["adaptive_sample_budget"], 48)
        self.assertEqual(profile["adaptive"]["forced_point_count"], 6)
        self.assertEqual(profile["adaptive"]["exported_combined_maximum_samples"], 54)
        self.assertTrue(profile["name"].endswith("-r2"))
        self.assertNotEqual(profile["name"], validate_native_stimulus(NATIVE_C10_STIMULUS)["name"])
        with self.assertRaises(RunError):
            validate_native_stimulus(NATIVE_R2_STIMULUS.replace("MAXSAMPLES 54", "MAXSAMPLES 56"))
        with self.assertRaises(RunError):
            validate_native_stimulus(NATIVE_R2_STIMULUS.replace("PT 20,\nPT 40,", "PT 40,\nPT 20,"))

    def test_original_r1_receipt_shape_remains_identical(self):
        expected = {
            "name": "native-afs-5-to-200-forced-10-65-80-100-r1",
            "adaptive": {"start_GHz": 5.0, "stop_GHz": 200.0, "native_step_GHz": 195.0,
                         "selector": "S_50", "adaptive_sample_budget": 50, "forced_point_count": 4,
                         "exported_combined_maximum_samples": 54, "sampling": "ALL NORMAL"},
            "required_exact_GHz": [65.0, 80.0], "forced_exact_GHz": [10.0, 65.0, 80.0, 100.0],
            "band_GHz": [5.0, 200.0], "dense_grid": "ADS-generated; spacing is observed, not assumed",
            "target_and_thresholds_changed": False,
        }
        self.assertEqual(validate_native_stimulus(NATIVE_C10_STIMULUS), expected)

    def test_legacy_r1_verifies_without_relabeling_and_cannot_be_upgraded(self):
        with tempfile.TemporaryDirectory(prefix="native-afs-r1-") as temporary:
            case = Path(temporary)
            (case / "proj.sti").write_text(NATIVE_C10_STIMULUS, encoding="utf-8", newline="\n")
            before = case / "pre-afs-amendment"
            before.mkdir()
            (before / "prepared-case.json").write_text("{}\n", encoding="utf-8")
            (before / "proj.sti").write_text("START 65 STOP 65 STEP 1;\n", encoding="utf-8")
            prepared = {"frequency_profile": validate_native_stimulus(NATIVE_C10_STIMULUS)}
            _json(case / "prepared-case.json", prepared)
            _json(case / "afs-profile-amendment.json", {
                "profile": prepared["frequency_profile"], "amended_prepared_receipt": _sha(case / "prepared-case.json"),
                "old_prepared_receipt": _sha(before / "prepared-case.json"), "old_exact_stimulus": _sha(before / "proj.sti"),
                "native_afs_stimulus": _sha(case / "proj.sti"),
            })
            original_bytes = (case / "prepared-case.json").read_bytes()
            self.assertTrue(_verify_profile(case)["frequency_profile"]["name"].endswith("-r1"))
            self.assertEqual((case / "prepared-case.json").read_bytes(), original_bytes)
            prepared["frequency_profile"] = validate_native_stimulus(NATIVE_R2_STIMULUS)
            (case / "prepared-case.json").write_text(json.dumps(prepared), encoding="utf-8")
            with self.assertRaisesRegex(RunError, "profile or amendment differs"):
                _verify_profile(case)

    def test_wrong_cap_forced_points_selector_and_band_fail(self):
        changes = (
            ("MAXSAMPLES 54", "MAXSAMPLES 50"),
            ("PT 65,", "PT 66,"),
            ("PT 80,\n", ""),
            ("S_50", "S_200"),
            ("START 5", "START 4"),
            ("STEP 195", "STEP 1"),
            ("PT 100,", "PT 100;"),
        )
        for before, after in changes:
            with self.subTest(change=after), self.assertRaises(RunError):
                validate_native_stimulus(NATIVE_C10_STIMULUS.replace(before, after))


if __name__ == "__main__":
    unittest.main()
