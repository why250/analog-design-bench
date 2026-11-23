"""Control snapshots must preserve domains, complete matrices and evidence gaps."""

import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from summarize_controls import SummaryError, summarize, write_summary


def comparison(profile="mesh", deltas=(1.0, 2.0, 3.0, 800.0, 1200.0), *, revision="passive-loss-r1", ports=2):
    """Synthetic comparison-receipt fixture, never an engineering solver result."""
    frequencies = [1e9, 10e9, 65e9, 80e9, 120e9]
    points = []
    for frequency, delta in zip(frequencies, deltas):
        matrix = [[[0.0, 0.0] for _ in range(ports)] for _ in range(ports)]
        matrix[-1][-1] = [3e-5, 4e-5]
        afs = profile == "afs"
        points.append({
            "frequency_hz": frequency, "candidate_kind": "actual", "comparison_state": "PASS",
            "reference_sample": {"kind": "linearly interpolated AFS-derived reference" if afs else "actual",
                                 "interpolated": afs, "source_indices": [0, 1] if afs else [0],
                                 "source_frequencies_hz": [0.5e9, 200e9] if afs else [frequency],
                                 "weights": [0.4, 0.6] if afs else [1.0]},
            "S": {"maximum_absolute_difference": 5e-5, "complete_complex_candidate_minus_reference": matrix},
            "L_pH": {"status": "FINITE", "absolute_difference": delta, "signed_difference": -delta},
            "R_ohm": {"status": "FINITE", "absolute_difference": 0.02, "signed_difference": -0.02},
            "Q": {"status": "FINITE", "absolute_relative_difference": 0.04},
            "Zd": {"status": "FINITE", "signed_imag_difference_ohm": -2 * math.pi * frequency * delta * 1e-12},
            "candidate_metrics": {"differential_solver": {"ill_conditioned": False}},
        })
    document = {
        "schema_version": 1, "control_profile": profile, "control_result": "PASS", "port_count": ports,
        "reference_ohm": 50.0, "complete_comparison": True, "all_candidate_points_compared": True,
        "selection_domain": {"candidate_samples": len(points), "candidate_points_omitted": 0, "candidate_frequency_hz": frequencies},
        "reference_kind": "AFS-derived" if profile == "afs" else "actual", "candidate_kind": "actual",
        "reference_interpolation_performed": profile == "afs", "source_models": {"reference": {"path": "test-reference.s2p"}, "candidate": {"path": "test-candidate.s2p"}},
        # Deliberately unusable for the 10--65 GHz budget.
        "maxima": {"absolute_L_difference_pH": {"value": max(deltas), "frequency_hz": 120e9}}, "points": points,
    }
    if revision is not None:
        document["physics_revision"] = revision
    return document


def put(root, path, document):
    target = Path(root) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, allow_nan=False), encoding="utf-8")
    return target


class SummaryTests(unittest.TestCase):
    def test_budget_uses_band_points_class_maxima_and_separate_AFS_reserve(self):
        with tempfile.TemporaryDirectory() as root:
            cases = [
                ("qualification/controls-r2/m3/comparison-application/comparison.json", "mesh", 3),
                ("qualification/low-frequency-checks/mesh3/comparison/comparison.json", "mesh", 2),
                ("qualification/controls-r2/gplus10/comparison-application/comparison.json", "port", 4),
                ("qualification/frame22/comparison/comparison.json", "return", 5),
                ("qualification/canonical-control/comparison.json", "canonical", 6),
                ("qualification/repro/comparison/comparison.json", "reproduction", 7),
                ("qualification/skin-explicit/comparison/comparison.json", "mesh", 8),
                ("qualification/controls-r2/a4/comparison-application/comparison.json", "afs", 0.8),
            ]
            for path, profile, delta in cases:
                put(root, path, comparison(profile, (delta / 4, delta / 2, delta, 800, 1200)))
            report = summarize(root)
            budget = report["L_budget_proposal"]
            self.assertAlmostEqual(budget["proposed_L_absolute_pH"], 33.8)
            self.assertEqual(budget["category_terms_pH"]["mesh"]["value"], 3)
            self.assertAlmostEqual(budget["AFS_reserve_pH"], 0.8)
            self.assertEqual(budget["missing_categories"], [])
            mesh = report["categories"]["mesh"]["domains"]
            self.assertEqual(mesh["L_band_10_65_GHz"]["all_reported"]["maxima"]["absolute_L_difference_pH"]["value"], 3)
            self.assertEqual(mesh["reactance_positive_through_80_GHz"]["all_reported"]["maxima"]["absolute_L_difference_pH"]["value"], 800)
            self.assertEqual(mesh["diagnostic_above_80_GHz"]["all_reported"]["maxima"]["absolute_L_difference_pH"]["value"], 1200)
            self.assertEqual(report["device_target_result"], "NOT_EVALUATED")
            self.assertEqual(report["continuous_band_coverage"], "NOT_ESTABLISHED_BY_THIS_SUMMARY")
            self.assertFalse(budget["ready_for_qualification"])
            self.assertIn("EXPECTED_REPORTS_NOT_FOUND", [item["kind"] for item in budget["adoption_blockers"]])
            json.dumps(report, allow_nan=False)

    def test_complete_third_port_and_reference_interpolation_are_retained(self):
        with tempfile.TemporaryDirectory() as root:
            source = comparison("afs", ports=3)
            put(root, "qualification/controls-r2/a4/comparison-application/comparison.json", source)
            report = summarize(root)
            point = report["reports"][0]["points"][2]
            self.assertEqual(point["comparison"]["S"]["complete_complex_candidate_minus_reference"], source["points"][2]["S"]["complete_complex_candidate_minus_reference"])
            self.assertAlmostEqual(point["metrics"]["maximum_absolute_complete_S_difference"], 5e-5)
            self.assertEqual(point["comparison"]["reference_sample"]["weights"], [0.4, 0.6])
            self.assertEqual(report["reports"][0]["metadata"]["port_count"], 3)
            self.assertTrue(report["reports"][0]["numerical_observations_usable"])

    def test_missing_terms_and_undefined_values_are_never_zero_filled(self):
        with tempfile.TemporaryDirectory() as root:
            document = comparison("mesh")
            document["points"][2]["L_pH"] = {"status": "UNDEFINED_DERIVED_VALUE", "absolute_difference": None}
            document["points"][2]["Q"] = {"absolute_relative_difference": None, "relative_status": "ZERO_REFERENCE_LIMIT"}
            put(root, "mesh/comparison.json", document)
            report = summarize(root)
            term = report["L_budget_proposal"]["category_terms_pH"]["mesh"]
            self.assertEqual(term["value"], 2)
            self.assertEqual(term["undefined_point_count"], 1)
            self.assertIsNone(report["L_budget_proposal"]["proposed_L_absolute_pH"])
            self.assertEqual(report["L_budget_proposal"]["categories_with_undefined_L"], ["mesh"])
            self.assertEqual(report["L_budget_proposal"]["AFS_evidence_state"], "MISSING_NOT_REPLACED_BY_FLOOR")
            self.assertIsNone(report["L_budget_proposal"]["observed_AFS_error_pH"]["value"])
            self.assertEqual(report["L_budget_proposal"]["AFS_reserve_pH"], 0.6)
            self.assertIn("port", report["L_budget_proposal"]["missing_categories"])
            q = report["categories"]["mesh"]["domains"]["L_band_10_65_GHz"]["all_reported"]["maxima"]["absolute_relative_Q_difference"]
            self.assertEqual(q["undefined_point_count"], 1)
            self.assertIsNone(report["reports"][0]["points"][2]["comparison"]["Q"]["absolute_relative_difference"])

    def test_diagnostic_failure_keeps_its_domain_and_does_not_change_application_states(self):
        with tempfile.TemporaryDirectory() as root:
            document = comparison("canonical")
            document["control_result"] = "FAIL"
            document["points"][-1]["comparison_state"] = "FAIL"
            put(root, "canonical-control/comparison.json", document)
            report = summarize(root)
            self.assertEqual(report["application_control_issues"], [])
            domains = report["categories"]["canonical"]["domains"]
            self.assertEqual(domains["L_band_10_65_GHz"]["all_reported"]["comparison_state_counts"], {"PASS": 2})
            self.assertEqual(domains["diagnostic_above_80_GHz"]["all_reported"]["comparison_state_counts"], {"FAIL": 1})
            self.assertEqual(report["reports"][0]["metadata"]["control_result"], "FAIL")

    def test_explicit_wrong_revision_excluded_undeclared_preserved_with_provenance_gap(self):
        with tempfile.TemporaryDirectory() as root:
            put(root, "old/mesh/comparison.json", comparison("mesh", revision="invalid-positive-loss"))
            put(root, "repro/comparison.json", comparison("reproduction", revision=None))
            manifest = put(root, "upstream.json", {"physics_revision": "passive-loss-r1", "binding": "operator-reviewed source chain"})
            report = summarize(root, upstream_manifest=manifest)
            self.assertEqual(report["categories"]["mesh"]["domains"]["L_band_10_65_GHz"]["all_reported"]["point_count"], 2)
            self.assertEqual(report["categories"]["mesh"]["domains"]["L_band_10_65_GHz"]["usable_numerical_observations"]["point_count"], 0)
            reproduction = next(row for row in report["reports"] if row["category"] == "reproduction")
            self.assertEqual(reproduction["physics_revision_state"], "UNDECLARED")
            self.assertTrue(reproduction["numerical_observations_usable"])
            self.assertTrue(reproduction["provenance_review_required"])
            self.assertEqual(report["upstream_manifest"]["manifest"]["physics_revision"], "passive-loss-r1")
            self.assertEqual(len(report["provenance_gaps"]), 2)

    def test_future_case_inventory_and_contact_frame_classification(self):
        with tempfile.TemporaryDirectory() as root:
            put(root, "qualification/low-frequency-checks/gplus10/comparison/comparison.json", comparison("port"))
            put(root, "qualification/low-frequency-checks/frame15/comparison/comparison.json", comparison("mesh"))
            report = summarize(root)
            self.assertEqual(len(report["categories"]["port"]["report_indices"]), 1)
            self.assertEqual(len(report["categories"]["return"]["report_indices"]), 1)
            inventory = {row["case"]: row["state"] for row in report["expected_control_reports"]}
            self.assertEqual(inventory["qualification/low-frequency-checks/gplus10/**/comparison.json"], "REPORT_PRESENT")
            self.assertEqual(inventory["qualification/controls-r2/a4/comparison-application/comparison.json"], "NOT_FOUND_NOT_ASSUMED_COMPLETE")

    def test_AFS_path_requires_AFS_profile_and_derived_reference_at_every_point(self):
        with tempfile.TemporaryDirectory() as root:
            put(root, "qualification/controls-r2/a4/comparison-application/comparison.json", comparison("mesh"))
            wrong_point = comparison("afs")
            wrong_point["points"][1]["reference_sample"]["kind"] = "actual"
            put(root, "other-AFS/comparison.json", wrong_point)
            report = summarize(root)
            self.assertEqual(report["retained_report_count"], 2)
            self.assertTrue(all(not item["numerical_observations_usable"] for item in report["reports"]))
            self.assertIsNone(report["L_budget_proposal"]["observed_AFS_error_pH"]["value"])
            self.assertEqual(report["categories"]["AFS"]["domains"]["L_band_10_65_GHz"]["all_reported"]["point_count"], 4)

    def test_malformed_object_type_does_not_abort_other_reports(self):
        with tempfile.TemporaryDirectory() as root:
            bad_selection = comparison()
            bad_selection["selection_domain"] = []
            put(root, "bad-selection/comparison.json", bad_selection)
            bad_metric = comparison()
            bad_metric["points"][0]["L_pH"] = None
            put(root, "bad-metric/comparison.json", bad_metric)
            put(root, "good/comparison.json", comparison())
            report = summarize(root)
            self.assertEqual(report["retained_report_count"], 1)
            self.assertEqual(len(report["ingestion_errors"]), 2)
            self.assertIn("REPORT_INGESTION_ERRORS", [item["kind"] for item in report["L_budget_proposal"]["adoption_blockers"]])

    def test_malformed_matrix_nonfinite_json_and_incomplete_selection_are_explicit_errors(self):
        with tempfile.TemporaryDirectory() as root:
            truncated = comparison(ports=3)
            truncated["points"][0]["S"]["complete_complex_candidate_minus_reference"].pop()
            put(root, "truncated/comparison.json", truncated)
            wrong_maximum = comparison()
            wrong_maximum["points"][0]["S"]["maximum_absolute_difference"] = 0
            put(root, "wrong-maximum/comparison.json", wrong_maximum)
            incomplete = comparison()
            incomplete["selection_domain"]["candidate_points_omitted"] = 1
            put(root, "incomplete/comparison.json", incomplete)
            nonfinite = Path(root) / "nonfinite/comparison.json"
            nonfinite.parent.mkdir()
            nonfinite.write_text('{"value": 1e999}', encoding="utf-8")
            report = summarize(root)
            self.assertEqual(report["discovered_report_count"], 4)
            self.assertEqual(report["retained_report_count"], 0)
            self.assertEqual(len(report["ingestion_errors"]), 4)
            self.assertIsNone(report["L_budget_proposal"]["proposed_L_absolute_pH"])

    def test_fresh_output_and_source_bytes_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            source = put(root, "mesh/comparison.json", comparison())
            before = source.read_bytes()
            output = Path(root) / "control-summary.json"
            write_summary(root, output)
            self.assertTrue(output.is_file())
            self.assertEqual(source.read_bytes(), before)
            with self.assertRaises(FileExistsError):
                write_summary(root, output)
            with self.assertRaises(SummaryError):
                write_summary(root, Path(root) / "other/comparison.json")
            self.assertEqual(summarize(root)["discovered_report_count"], 1)


if __name__ == "__main__":
    unittest.main()
