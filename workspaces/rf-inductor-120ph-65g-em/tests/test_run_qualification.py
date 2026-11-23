"""Check auditable gap selection and transverse contact proof without ADS."""

from pathlib import Path
import json
import math
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_qualification import _compare_bands, plan_coverage_fill, propose_pin_shift, select_midpoints, track_actual_extrema, track_dense_extrema
from run_momentum import RunError
from convert_cti import SNetwork, write_touchstone
import run_qualification as qualification


class GapSelectionTests(unittest.TestCase):
    def test_seven_original_gaps_and_three_in_band(self):
        samples = [frequency * 1e9 for frequency in (5, 10, 15, 20, 30, 45, 65, 80, 100, 140, 200)]
        result = select_midpoints(samples)
        self.assertEqual(len(result["selected_midpoints"]), 7)
        self.assertGreaterEqual(result["selected_in_band_count"], 3)
        self.assertTrue(all(point not in samples for point in result["selected_frequency_hz"]))
        self.assertTrue(all(item["midpoint_hz"] == (item["lower_hz"] + item["upper_hz"]) / 2 for item in result["selected_midpoints"]))
        # The widest global gap is retained despite the explicit in-band quota.
        self.assertIn(170e9, result["selected_frequency_hz"])
        self.assertFalse(result["virtual_or_interpolated_source_boundaries"])

    def test_insufficient_band_gaps_and_duplicate_sources_fail(self):
        for frequencies in ((5, 10, 65, 80, 100, 120, 140, 160, 180, 200),
                            (5, 10, 15, 20, 30, 45, 65, 65, 100, 140, 200)):
            with self.subTest(frequencies=frequencies), self.assertRaises(RunError):
                select_midpoints(frequency * 1e9 for frequency in frequencies)

    def test_actual_extrema_use_finite_observations_only(self):
        points = []
        for frequency, inductance in ((10e9, 110e-12), (40e9, 120e-12), (65e9, 125e-12), (80e9, 130e-12), (200e9, 200e-12)):
            points.append({"frequency_hz": frequency, "differential": {"status": "FINITE", "L_h": inductance,
                           "R_ohm": 2, "Q": {"status": "FINITE", "value": 10},
                           "impedance": {"real_ohm": 2, "imag_ohm": frequency * inductance}}})
        result = track_actual_extrema(points)
        maximum = next(item for item in result["tracked"] if item["name"] == "maximum_L10_65")
        self.assertEqual(maximum["frequency_hz"], 65e9)
        self.assertFalse(maximum["continuous_extremum_proven"])

    def test_dense_internal_extremum_remains_a_prediction_requiring_actual_control(self):
        points = []
        for frequency, inductance in ((10e9, 110e-12), (30e9, 125e-12), (40e9, 120e-12), (65e9, 124e-12), (80e9, 130e-12), (200e9, 200e-12)):
            points.append({"frequency_hz": frequency, "differential": {"status": "FINITE", "L_h": inductance,
                           "R_ohm": 2, "Q": {"status": "FINITE", "value": 10},
                           "impedance": {"real_ohm": 2, "imag_ohm": frequency * inductance}}})
        result = track_dense_extrema(points)
        internal = [item for item in result["internal_extrema"] if item["metric"] == "L_h"]
        self.assertEqual([(item["frequency_hz"], item["kind"]) for item in internal], [(30e9, "maximum"), (40e9, "minimum")])
        self.assertIn(30e9, result["frequency_hz"])
        self.assertIn(40e9, result["frequency_hz"])
        self.assertTrue(all(item["source_kind"] == "AFS-derived prediction" for item in internal))


class CoverageFillTests(unittest.TestCase):
    def test_four_sparse_native_intervals_request_actual_midpoints_without_changing_sources(self):
        actual = [frequency * 1e9 for frequency in (5, 10, 20, 40, 65, 80, 100, 400 / 3, 150, 550 / 3, 200)]
        dense = [frequency * 1e9 for frequency in (*range(5, 36), 36.25, 37.5, 38.75, 40, *range(41, 201))]
        original_actual, original_dense = actual.copy(), dense.copy()
        result = plan_coverage_fill(actual, dense)
        self.assertEqual(result["planned_actual_frequency_hz"], [frequency * 1e9 for frequency in (35.625, 36.875, 38.125, 39.375)])
        sparse = [interval for interval in result["original_union_intervals"] if interval["planned_internal_actual_frequency_hz"]]
        self.assertEqual(len(sparse), 4)
        for interval in sparse:
            self.assertEqual(interval["original_width_hz"], 1.25e9)
            self.assertEqual(interval["subintervals"][0]["equal_subdivision_count"], 2)
            self.assertEqual(interval["subintervals"][0]["planned_spacing_hz"], 0.625e9)
        self.assertEqual(actual, original_actual)
        self.assertEqual(dense, original_dense)
        self.assertEqual(result["source_frequency_hz"], {"actual_EM": actual, "ADS-derived_dense_AFS": dense})
        self.assertEqual(result["status"], "PLANNED_ACTUAL_SOLVES_NOT_COMPLETED_EVIDENCE")
        self.assertFalse(result["coverage_achieved_by_this_plan_alone"])
        self.assertTrue(result["derived_samples_are_not_actual_EM_samples"])

    def test_boundary_crossing_requires_actual_100_and_preserves_original_interval(self):
        result = plan_coverage_fill([5e9, 65e9, 80e9, 200e9], [5e9, 99e9, 104e9, 200e9])
        self.assertIn(100e9, result["planned_actual_frequency_hz"])
        self.assertFalse(result["required_boundary_already_actual"])
        interval = next(item for item in result["original_union_intervals"] if item["original_lower_endpoint"]["frequency_hz"] == 99e9)
        self.assertEqual(interval["original_upper_endpoint"]["frequency_hz"], 104e9)
        self.assertEqual(interval["original_width_hz"], 5e9)
        self.assertTrue(interval["split_at_required_100_GHz_boundary"])
        self.assertEqual([item["maximum_spacing_hz"] for item in interval["subintervals"]], [1e9, 5e9])
        boundary = interval["subintervals"][0]["upper_endpoint"]
        self.assertEqual(boundary["original_source_kinds"], [])
        self.assertFalse(boundary["is_original_actual_EM_sample"])
        self.assertTrue(boundary["planned_required_actual_boundary"])
        self.assertEqual(interval["original_lower_endpoint"]["original_source_kinds"], ["ADS-derived_dense_AFS"])

    def test_actual_union_points_reduce_gaps_and_above_100_uses_equal_subdivision(self):
        result = plan_coverage_fill([5e9, 35.625e9, 100e9, 200e9], [5e9, 35e9, 36.25e9, 100e9, 111e9, 200e9])
        local = [point for point in result["planned_actual_frequency_hz"] if 35e9 < point < 36.25e9]
        self.assertEqual(local, [])
        interval = next(item for item in result["original_union_intervals"] if item["original_lower_endpoint"]["frequency_hz"] == 100e9)
        subdivision = interval["subintervals"][0]
        self.assertEqual(subdivision["equal_subdivision_count"], 3)
        self.assertEqual(subdivision["planned_actual_frequency_hz"], [100e9 + 11e9 / 3, 100e9 + 22e9 / 3])
        self.assertLessEqual(subdivision["planned_spacing_hz"], 5e9)
        for actual, dense in (([5e9, 200e9], [5e9, 5e9, 200e9]),
                              ([5e9, float("nan"), 200e9], [5e9, 200e9]),
                              ([5e9, 200e9], [5e9, 199e9])):
            with self.subTest(actual=actual, dense=dense), self.assertRaises(RunError):
                plan_coverage_fill(actual, dense)


class ContactProofTests(unittest.TestCase):
    def test_transverse_shift_stays_on_same_original_polygon(self):
        with tempfile.TemporaryDirectory(prefix="qualification-pins-") as temporary:
            root = Path(temporary)
            (root / "proj_a").write_text("UNITS UM,0.001;EDIT simple;ADD P35:W0 -5,-5 5,-5 5,5 -5,5;ADD P35:W0 7,-5 17,-5 17,5 7,5;ADD P7:W0 -20,-40 40,-40 40,-20 -20,-20;SAVE;", encoding="utf-8")
            pins = "<pin_list>" + "".join(f"<pin><name>P{number}</name><net>P{number}</net><layout><shape><layer>{layer}</layer><purpose>-1</purpose><point><x>{x}</x><y>{y}</y></point></shape></layout></pin>"
                                                   for number, layer, x, y in ((1, 35, 0, -5e-6), (2, 35, 12e-6, -5e-6), (4, 7, 0, -30e-6))) + "</pin_list>"
            (root / "proj.pin").write_text(pins, encoding="utf-8")
            (root / "proj.prt").write_text("<port_setup><port_list>" + "".join(f"<port id='{number}'><name>P{number}</name><plus_pin>P{number}</plus_pin><minus_pin>P4</minus_pin><impedance><real>50</real><imag>0</imag></impedance></port>" for number in (1, 2)) + "</port_list></port_setup>", encoding="utf-8")
            for variant in ("pplus2", "pminus2", "gplus10"):
                content, proof = propose_pin_shift(root, variant)
                self.assertTrue(content)
                self.assertTrue(proof["signal_reference_plane_y_unchanged"])
                self.assertTrue(proof["geometry_layers_nets_and_port_mapping_unchanged"])
            self.assertEqual((root / "proj.pin").read_text(), pins)
            (root / "proj_a").write_text("UNITS UM,0.001;EDIT simple;ADD P35:W0 -1,-5 1,-5 1,5 -1,5;ADD P35:W0 11,-5 13,-5 13,5 11,5;ADD P7:W0 -20,-40 40,-40 40,-20 -20,-20;SAVE;", encoding="utf-8")
            with self.assertRaises(RunError):
                propose_pin_shift(root, "pplus2")


class BandComparisonTests(unittest.TestCase):
    def test_diagnostic_failure_does_not_replace_application_result(self):
        frequencies = (65e9, 80e9, 100e9)

        def series_network(diagnostic_inductance):
            matrices = []
            for frequency in frequencies:
                inductance = diagnostic_inductance if frequency > 80e9 else 120e-12
                z = complex(1, 2 * math.pi * frequency * inductance)
                reflection, transmission = z / (100 + z), 100 / (100 + z)
                matrices.append(((reflection, transmission), (transmission, reflection)))
            return SNetwork(frequencies, tuple(matrices), "synthetic-series-control")

        with tempfile.TemporaryDirectory(prefix="qualification-band-") as temporary:
            root = Path(temporary)
            reference, candidate = root / "reference.s2p", root / "candidate.s2p"
            for path, network in ((reference, series_network(120e-12)), (candidate, series_network(180e-12))):
                with path.open("x", encoding="ascii") as stream:
                    write_touchstone(network, stream, 50)
            result = _compare_bands(reference, candidate, {"gate_split_hz": 80e9, "comparison_profile": "mesh",
                                                          "reference_interpolation": "none", "reference_kind": "actual"}, root)
            self.assertEqual(result["application"]["control_result"], "PASS")
            self.assertEqual(result["diagnostic"]["control_result"], "FAIL")
            self.assertTrue(result["application"]["required_application_gate"])
            self.assertFalse(result["diagnostic"]["required_application_gate"])


class ExecutionFrequencyPolicyTests(unittest.TestCase):
    def prepare_fixture(self, root):
        source, suite = root / "source", root / "suite"
        source.mkdir()
        suite.mkdir()
        case = suite / "a4"
        case.mkdir()
        qualification._json(source / "afs-model-receipt.json", {"retained": True})
        (source / "dense-afs.s2p").write_text("retained derived model", encoding="ascii")
        qualification._json(case / "prepared-case.json", {"frequencies_GHz": [65, 80, 116.66666665]})
        (case / "proj.sti").write_text("original precise midpoint stimulus", encoding="ascii")
        plan = {"source_afs_case": str(source), "source_receipt": qualification._sha(source / "afs-model-receipt.json"),
                "source_model_identities": {"dense-afs.s2p": qualification._sha(source / "dense-afs.s2p")}}
        qualification._json(suite / "qualification-plan.json", plan)
        specification = {"relative_case_directory": "a4", "prepared_receipt": qualification._sha(case / "prepared-case.json"),
                         "comparison_profile": "afs", "reference_location": "source", "reference_model": "dense-afs.s2p"}
        qualification._json(suite / "qualification-suite.json", {"plan_identity": qualification._sha(suite / "qualification-plan.json"),
                            "source_afs_case": str(source), "execution_order": ["a4"], "cases": {"a4": specification}})
        return source, suite, case

    def test_opt_in_records_policy_before_solve_then_exports_and_compares(self):
        with tempfile.TemporaryDirectory(prefix="qualification-native-policy-") as temporary:
            source, suite, case = self.prepare_fixture(Path(temporary))
            originals = {path: path.read_bytes() for path in (case / "prepared-case.json", case / "proj.sti", suite / "qualification-plan.json")}
            events = []

            def solve(directory, ads_root, *, export_model):
                self.assertEqual(directory, case.resolve())
                self.assertFalse(export_model)
                policy = json.loads((case / "native-frequency-realization-policy.json").read_text())
                self.assertEqual(policy["requested_frequency_hz"], [65e9, 80e9, 116666666650.0])
                self.assertEqual(policy["planned_native_ten_digit_canonical_frequency_hz"], [65e9, 80e9, 116666666600.0])
                self.assertEqual(policy["protected_key_frequency_hz"], [65e9, 80e9])
                self.assertEqual(policy["protected_exact_frequency_hz"], [65e9, 80e9])
                self.assertEqual(policy["status"], "RECORDED_BEFORE_SOLVE_NOT_ACTUAL_FREQUENCY_EVIDENCE")
                events.append("solve")

            def export(directory, *, native_ten_digit_realization):
                self.assertTrue(native_ten_digit_realization)
                self.assertEqual(events, ["solve"])
                events.append("export")

            def compare(*args):
                self.assertEqual(events, ["solve", "export"])
                events.append("compare")
                return {"application": {"control_result": "PASS"}, "diagnostic": {"control_result": "PASS"}}

            with patch.object(qualification, "_verify_completion"), patch.object(qualification, "run_case", side_effect=solve), patch.object(qualification, "export_dataset", side_effect=export), patch.object(qualification, "_compare_bands", side_effect=compare):
                receipt = qualification.execute_controls(suite, native_ten_digit_realization=True)
            self.assertEqual(events, ["solve", "export", "compare"])
            self.assertEqual(receipt["results"][0]["status"], "ACTUAL_FULLWAVE_DATA_RETAINED")
            for path, content in originals.items():
                self.assertEqual(path.read_bytes(), content)

    def test_default_policy_uses_original_strict_export_path(self):
        with tempfile.TemporaryDirectory(prefix="qualification-strict-policy-") as temporary:
            _, suite, case = self.prepare_fixture(Path(temporary))
            with patch.object(qualification, "_verify_completion"), patch.object(qualification, "run_case") as solve, patch.object(qualification, "export_dataset") as export, patch.object(qualification, "_compare_bands", return_value={"application": {"control_result": "PASS"}, "diagnostic": {"control_result": "PASS"}}):
                receipt = qualification.execute_controls(suite)
            solve.assert_called_once_with(case.resolve(), None, export_model=True)
            export.assert_not_called()
            self.assertFalse((case / "native-frequency-realization-policy.json").exists())
            self.assertFalse(receipt["native_ten_digit_realization_opt_in_for_new_solves"])

    def test_existing_policy_is_immutable_and_old_attempts_are_not_relabelled(self):
        with tempfile.TemporaryDirectory(prefix="qualification-existing-policy-") as temporary:
            _, suite, case = self.prepare_fixture(Path(temporary))
            policy = case / "native-frequency-realization-policy.json"
            policy.write_text("retained earlier policy", encoding="utf-8")
            with patch.object(qualification, "_verify_completion"), patch.object(qualification, "run_case") as solve, patch.object(qualification, "export_dataset") as export:
                receipt = qualification.execute_controls(suite, native_ten_digit_realization=True)
                solve.assert_not_called()
                export.assert_not_called()
                self.assertEqual(receipt["results"][0]["status"], "CONTROL_OR_COMPARISON_INCOMPLETE")
                self.assertEqual(policy.read_text(), "retained earlier policy")
                (case / "execution-receipt.json").write_text("retained old solve", encoding="ascii")
                original_result = (case / "qualification-control-result.json").read_bytes()
                receipt = qualification.execute_controls(suite, native_ten_digit_realization=True)
                self.assertEqual(receipt["results"][0]["status"], "RETAINED_PREVIOUS_ATTEMPT_NOT_REEXECUTED")
                self.assertEqual((case / "qualification-control-result.json").read_bytes(), original_result)
                self.assertEqual(policy.read_text(), "retained earlier policy")
                solve.assert_not_called()
                export.assert_not_called()


if __name__ == "__main__":
    unittest.main()
