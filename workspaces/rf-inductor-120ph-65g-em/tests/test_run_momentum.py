"""Check the observed solver option canonicalization without running ADS."""

from pathlib import Path
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_momentum as runner


def options(directory):
    return f'''SPARAM_OUTPUTFORMAT SMATRIXIO;
DS_DIR {directory.as_posix()};
MAXCELLSIZE 4 UM;
EDGEMESH_BORDERWIDTH AUTO;
MESH_REDUCTION OFF;
OVERLAPEXTRACTION ON;
MATRIXSOLVER 0;
INCLUDEPORTSOLVER ON;
reusePreviousResults OFF;
MODELTYPESTRIP 3;
MODELTYPEVIA 3;
SimulationTemperature 298.15;
saveCurrentsInFile 1;
DS_NAME raw_MomMW;
SimulationMode 1;
maxThreads 4;
'''


def normalized_options(directory):
    # Text and units observed in the actual post-solve ADS2027 export.
    return f'''simulationMode 1;
simulationTemperature 298.15;
maxThreads 4;
logFile "proj.log";
mesh_reduction OFF;
edgemesh_borderwidth AUTO;
maxcellsize 4e-06 METRE;
mesh_convergence_plot OFF;
save_fields_for no frequencies;
overlapextraction ON;
gppMergeAllShapes ON;
gppMinFeatureSize 0;
modelTypeStrip 3;
modelTypeVia 3;
SAVECURRENTSINFILE 1;
SPARAM_OUTPUTFORMAT SMATRIXIO;
DS_DIR "{directory.as_posix()}";
DS_NAME "raw_MomMW";
REUSEPREVIOUSRESULTS OFF;
INCLUDEPORTSOLVER ON;
matrixSolver 0;
'''


class CanonicalizationTests(unittest.TestCase):
    def test_actual_canonicalization_preserves_frozen_core(self):
        path = Path.cwd().resolve()
        original = runner._canonical_option_values(options(path), mesh_um=4, threads=4, case_dir=path)
        canonical = runner._canonical_option_values(normalized_options(path), mesh_um=4, threads=4, case_dir=path)
        self.assertEqual(original, canonical)

    def test_wrong_mode_mesh_temperature_and_output_are_rejected(self):
        path = Path.cwd().resolve()
        baseline = normalized_options(path)
        alterations = (
            ("simulationMode 1;", "simulationMode 2;"),
            ("maxcellsize 4e-06 METRE;", "maxcellsize 8e-06 METRE;"),
            ("simulationTemperature 298.15;", "simulationTemperature 300;"),
            ('DS_NAME "raw_MomMW";', 'DS_NAME "other";'),
            ("REUSEPREVIOUSRESULTS OFF;", "REUSEPREVIOUSRESULTS ON;"),
            ("modelTypeStrip 3;", "modelTypeStrip 1;"),
        )
        for before, after in alterations:
            with self.subTest(alteration=after), self.assertRaises(runner.RunError):
                runner._canonical_option_values(baseline.replace(before, after), mesh_um=4, threads=4, case_dir=path)

    def test_legacy_recovery_requires_original_exact_byte_identity(self):
        with tempfile.TemporaryDirectory(prefix="momentum-legacy-") as temporary:
            case = Path(temporary).resolve()
            original = case / "original-export"
            original.mkdir()
            pre = options(case)
            upstream = pre.replace("MAXCELLSIZE 4 UM;", "MAXCELLSIZE 8 UM;").replace("SimulationMode 1;", "SimulationMode 2;")
            upstream = upstream.replace(f"DS_DIR {case.as_posix()};", "DS_DIR old;").replace("DS_NAME raw_MomMW;", "DS_NAME old;").replace("maxThreads 4;", "maxThreads 0;")
            # The original replacement recipe also determines the exact final
            # newline bytes. Reproduce that recipe instead of normalizing it.
            pre = upstream
            for key, value in (("MAXCELLSIZE", "4 UM"), ("SimulationMode", "1"),
                               ("DS_DIR", case.as_posix()), ("DS_NAME", "raw_MomMW"), ("maxThreads", "4")):
                pre = runner._replace_option(pre, key, value)
            (original / "proj.opt").write_text(upstream, encoding="utf-8", newline="\n")
            (case / "proj.opt").write_text(pre, encoding="utf-8", newline="\n")
            (case / "proj.ltd").write_text("MATERIAL ResearchOx1 PERMITTIVITY=4.2 IMAG_PERMITTIVITY=-0.021", encoding="utf-8")
            receipt = {"mesh_um": 4, "threads": 4, "files": {name: runner._sha(case / name) for name in ("proj.opt", "proj.ltd")}}
            runner._json(case / "prepared-case.json", receipt)
            initial_receipt = (case / "prepared-case.json").read_bytes()
            (case / "proj.opt").write_text(normalized_options(case), encoding="utf-8", newline="\n")
            runner._verify_prepared(case, postsolve=True)
            self.assertEqual((case / "prepared-inputs" / "proj.opt").read_text(), pre)
            self.assertTrue((case / "prepared-source-recovery.json").is_file())
            self.assertTrue((case / "canonical-options-receipt.json").is_file())
            self.assertEqual((case / "prepared-case.json").read_bytes(), initial_receipt)
            runner._verify_prepared(case, postsolve=True)
            (case / "proj.ltd").write_text("material changed", encoding="utf-8")
            with self.assertRaises(runner.RunError):
                runner._verify_prepared(case, postsolve=True)

    def test_legacy_recovery_refuses_unmatched_source(self):
        with tempfile.TemporaryDirectory(prefix="momentum-bad-source-") as temporary:
            case = Path(temporary).resolve()
            (case / "original-export").mkdir()
            (case / "original-export" / "proj.opt").write_text(options(case), encoding="utf-8", newline="\n")
            (case / "prepared-case.json").write_text("{}", encoding="utf-8")
            receipt = {"mesh_um": 4, "threads": 4, "files": {"proj.opt": {"bytes": 1, "sha256": "incorrect"}}}
            with self.assertRaisesRegex(runner.RunError, "exact recorded byte"):
                runner._prepared_options(case, receipt)
            self.assertFalse((case / "prepared-inputs").exists())


class PassiveMaterialTests(unittest.TestCase):
    def test_negative_passive_oxide_values_are_accepted(self):
        for er, imaginary, changed in ((4, -0.02, True), (4.2, -0.021, False)):
            with self.subTest(er=er):
                source = f"MATERIAL ResearchOx1 PERMITTIVITY={er} IMAG_PERMITTIVITY={imaginary} PERMEABILITY=1\n"
                corrected, receipt = runner._reconcile_oxide(source)
                self.assertIn("PERMITTIVITY=4.2 IMAG_PERMITTIVITY=-0.021", corrected)
                self.assertEqual(receipt["after"]["imaginary_er"], -0.021)
                self.assertEqual(receipt["changed"], changed)
                self.assertEqual(receipt["before"]["imaginary_er"], imaginary)

    def test_positive_gain_is_rejected_for_any_material_without_sign_flip(self):
        passive = "MATERIAL ResearchOx1 PERMITTIVITY=4.2 IMAG_PERMITTIVITY=-0.021\n"
        for invalid in (
            passive.replace("-0.021", "0.021"),
            passive + "MATERIAL pass1 PERMITTIVITY=4.2 IMAG_PERMITTIVITY=0.021\n",
            passive + "MATERIAL another PERMITTIVITY=3.9\n IMAG_PERMITTIVITY=0.0195\n",
        ):
            with self.subTest(source=invalid), self.assertRaisesRegex(runner.RunError, "positive IMAG_PERMITTIVITY realizes gain"):
                runner._reconcile_oxide(invalid)

    def test_all_negative_dielectrics_and_lossless_conductor_are_accepted(self):
        source = """BEGIN_MATERIAL
MATERIAL Metal6 CONDUCTIVITY=24050000
MATERIAL ResearchOx1 PERMITTIVITY=4.2 IMAG_PERMITTIVITY=-0.021
MATERIAL pass2 PERMITTIVITY=7.9 IMAG_PERMITTIVITY=-0.0395
MATERIAL air PERMITTIVITY=1 IMAG_PERMITTIVITY=0
END_MATERIAL
"""
        values = runner._guard_passive_permittivity(source)
        self.assertEqual(len(values), 3)
        self.assertTrue(all(item["imaginary_er"] <= 0 for item in values))

    def test_nonfinite_material_values_are_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaisesRegex(runner.RunError, "must be finite"):
                runner._guard_passive_permittivity(f"MATERIAL pass1 PERMITTIVITY=4.2 IMAG_PERMITTIVITY={value}\n")

    def test_positive_source_is_rejected_before_preparation_allocates_a_case(self):
        with tempfile.TemporaryDirectory(prefix="momentum-positive-source-") as temporary:
            root = Path(temporary).resolve()
            source, native, installation, output = root / "source", root / "native", root / "ads", root / "new-case"
            source.mkdir()
            native.mkdir()
            (installation / "bin").mkdir(parents=True)
            (installation / "bin" / "adsMomWrapper.bat").write_text("", encoding="utf-8")
            for name in runner.REQUIRED_INPUTS:
                (source / name).write_text("source", encoding="utf-8")
            material = "MATERIAL ResearchOx1 PERMITTIVITY=4.2 IMAG_PERMITTIVITY=0.021\n"
            (source / "proj.ltd").write_text(material, encoding="utf-8")
            with self.assertRaisesRegex(runner.RunError, "positive IMAG_PERMITTIVITY realizes gain"):
                runner.prepare_case(source, output, 4, [65, 80], installation, native_workspace=native)
            self.assertFalse(output.exists())
            self.assertEqual((source / "proj.ltd").read_text(), material)

    def test_legacy_positive_input_cannot_be_verified_or_reexported(self):
        with tempfile.TemporaryDirectory(prefix="momentum-positive-legacy-") as temporary:
            case = Path(temporary).resolve()
            material = "MATERIAL ResearchOx1 PERMITTIVITY=4.2 IMAG_PERMITTIVITY=0.021\n"
            (case / "proj.ltd").write_text(material, encoding="utf-8")
            receipt = {"files": {"proj.ltd": runner._sha(case / "proj.ltd")}}
            runner._json(case / "prepared-case.json", receipt)
            old_receipt = (case / "prepared-case.json").read_bytes()
            for operation in (runner._verify_prepared, runner._verify_completion, runner.run_case, runner.export_dataset):
                with self.subTest(operation=operation.__name__), self.assertRaisesRegex(runner.RunError, "positive IMAG_PERMITTIVITY realizes gain"):
                    operation(case)
            self.assertEqual((case / "proj.ltd").read_text(), material)
            self.assertEqual((case / "prepared-case.json").read_bytes(), old_receipt)
            self.assertFalse((case / "canonical-options-receipt.json").exists())


class NativeFrequencyRealizationTests(unittest.TestCase):
    def test_observed_three_native_half_even_realizations_require_explicit_opt_in(self):
        requested = [65e9, 80e9, 116666666650.0, 141666666650.0, 166666666650.0]
        actual = [65e9, 80e9, 116666666600.0, 141666666600.0, 166666666600.0]
        with self.assertRaisesRegex(runner.RunError, "requested explicit list"):
            runner._frequency_realization(requested, actual)
        result = runner._frequency_realization(requested, actual, native_ten_digit_realization=True)
        self.assertEqual(result["native_ten_digit_canonical_frequency_hz"], actual)
        self.assertEqual(result["actual_minus_requested_hz"], [0, 0, -50, -50, -50])
        self.assertEqual(result["changed_point_count"], 3)
        self.assertEqual([point["status"] for point in result["points"][:2]], ["UNCHANGED_EXACT"] * 2)
        self.assertFalse(result["raw_frequency_coordinates_modified"])
        self.assertFalse(result["electrical_acceptance_thresholds_modified"])

    def test_other_realizations_key_changes_collisions_and_nonfinite_are_rejected(self):
        invalid = (
            ([65e9, 80e9, 116666666650.0], [65e9, 80e9, 116666666700.0]),
            ([65e9, 80e9], [65e9 - 0.01, 80e9]),
            ([65e9, 80e9], [65e9, 80e9 + 0.01]),
            ([65e9, 100e9], [65e9, 100e9 + 1]),
            ([116666666650.0, 116666666651.0], [116666666600.0] * 2),
            ([65e9, float("nan")], [65e9, 80e9]),
        )
        for requested, actual in invalid:
            with self.subTest(requested=requested, actual=actual), self.assertRaises(runner.RunError):
                runner._frequency_realization(requested, actual, native_ten_digit_realization=True)
        # Retain the pre-existing default policy, including its original tiny
        # representation tolerance; the opt-in policy is exact instead.
        runner._frequency_realization([65e9, 80e9], [65e9, 80e9 + 0.01])

    def test_export_preserves_source_and_writes_immutable_realization_amendment(self):
        requested = [65e9, 80e9, 116666666650.0, 141666666650.0, 166666666650.0]
        actual = [float(format(value, ".10g")) for value in requested]

        class Frame:
            def __init__(self, rows):
                self.rows = rows
                self.columns = list(rows[0])

            def to_dataframe(self):
                return self

            def reset_index(self):
                return self

            def __len__(self):
                return len(self.rows)

            def __getitem__(self, key):
                return [row[key] for row in self.rows]

            def iterrows(self):
                return enumerate(self.rows)

        table = Frame([{"freq": f, "S[1,1]": 0.1 + 0.2j, "S[1,2]": 0.7 - 0.3j,
                        "S[2,1]": 0.7 - 0.3j, "S[2,2]": 0.15 + 0.25j,
                        "PORTZ[1]": 50 + 0j, "PORTZ[2]": 50 + 0j} for f in actual])
        ports = Frame([{"Ports": f"P{i}", "PlusPins": f"P{i} ", "MinusPins": "P4 "} for i in (1, 2)])
        ads = types.ModuleType("keysight.ads")
        ads.dataset = types.SimpleNamespace(open=lambda _: {"data": table, "ports": ports})
        with tempfile.TemporaryDirectory(prefix="momentum-native-frequency-") as temporary:
            case = Path(temporary).resolve()
            prepared = {"ports": [{}, {}], "frequencies_GHz": [f / 1e9 for f in requested]}
            for name, content in (("prepared-case.json", json.dumps(prepared)), ("execution-receipt.json", "{}"),
                                  ("proj.sti", "original explicit stimulus"), ("raw_MomMW.ds", "retained native dataset"),
                                  ("proj.sio", "retained solver network")):
                (case / name).write_text(content, encoding="utf-8")
            original_sources = {name: (case / name).read_bytes() for name in ("prepared-case.json", "proj.sti", "raw_MomMW.ds", "proj.sio")}
            with patch.dict(sys.modules, {"keysight": types.ModuleType("keysight"), "keysight.ads": ads}), patch.object(runner, "_verify_completion", return_value=prepared):
                with self.assertRaises(runner.RunError):
                    runner.export_dataset(case)
                self.assertFalse((case / "native-frequency-realization.json").exists())
                self.assertFalse((case / "raw.s2p").exists())
                receipt = runner.export_dataset(case, native_ten_digit_realization=True)
                amendment_path = case / "native-frequency-realization.json"
                amendment_bytes = amendment_path.read_bytes()
                amendment = json.loads(amendment_bytes)
                self.assertEqual(amendment["requested_frequency_hz"], requested)
                self.assertEqual(amendment["actual_frequency_hz"], actual)
                self.assertEqual(amendment["prepared_case_receipt"], runner._sha(case / "prepared-case.json"))
                self.assertEqual(amendment["source_dataset"]["sha256"], runner._sha(case / "raw_MomMW.ds")["sha256"])
                self.assertEqual(receipt["frequency_realization_amendment"], {"path": amendment_path.name, **runner._sha(amendment_path)})
                self.assertEqual(receipt["requested_frequency_hz"], requested)
                self.assertEqual(receipt["actual_frequency_hz"], actual)
                csv_rows = (case / "raw-complex-s.csv").read_text().splitlines()[1:]
                self.assertEqual([float(row.split(",")[0]) for row in csv_rows], actual)
                with self.assertRaisesRegex(runner.RunError, "export already exists"):
                    runner.export_dataset(case, native_ten_digit_realization=True)
                self.assertEqual(amendment_path.read_bytes(), amendment_bytes)
            for name, content in original_sources.items():
                self.assertEqual((case / name).read_bytes(), content)


class MatrixSolverSelectionTests(unittest.TestCase):
    def fixture(self, root, code):
        source, native, installation = root / "export", root / "native", root / "ads"
        source.mkdir()
        native.mkdir()
        (installation / "bin").mkdir(parents=True)
        (installation / "bin" / "adsMomWrapper.bat").write_text("", encoding="ascii")
        for name in runner.REQUIRED_INPUTS:
            (source / name).write_text("retained source", encoding="utf-8")
        (source / "proj.opt").write_text(options(source).replace("MATRIXSOLVER 0;", f"MATRIXSOLVER {code};"), encoding="utf-8", newline="\n")
        (source / "proj.ltd").write_text("MATERIAL ResearchOx1 PERMITTIVITY=4.2 IMAG_PERMITTIVITY=-0.021\n", encoding="ascii")
        (source / "proj.cfg").write_text("user = original_native\n", encoding="ascii")
        (source / "proj.prt").write_text("<port_setup><port_list>" + "".join(f"<port id='{i}'><name>P{i}</name><plus_pin>P{i}</plus_pin><minus_pin>P4</minus_pin><impedance><real>50</real><imag>0</imag></impedance></port>" for i in (1, 2)) + "</port_list></port_setup>", encoding="ascii")
        return source, native, installation

    def test_native_code_one_is_preserved_and_drives_pre_and_postsolve_validation(self):
        with tempfile.TemporaryDirectory(prefix="momentum-matrix-one-") as temporary:
            root = Path(temporary).resolve()
            source, native, installation = self.fixture(root, 1)
            original_sources = {name: (source / name).read_bytes() for name in runner.REQUIRED_INPUTS}
            case = root / "case"
            receipt = runner.prepare_case(source, case, 4, [65, 80], installation,
                                          native_workspace=native, matrix_solver_code=1)
            self.assertEqual(receipt["matrix_solver_code"], 1)
            self.assertEqual(receipt["native_export_matrix_solver_code"], 1)
            self.assertEqual(receipt["matrix_solver_name"], "UNCLASSIFIED")
            self.assertEqual(receipt["matrix_solver_classification_status"], "PENDING_RUNTIME_LOG")
            runner._verify_prepared(case)
            self.assertEqual((case / "original-export/proj.opt").read_bytes(), original_sources["proj.opt"])
            (case / "proj.opt").write_text(normalized_options(case).replace("matrixSolver 0;", "matrixSolver 1;"), encoding="utf-8", newline="\n")
            runner._verify_prepared(case, postsolve=True)
            canonical = json.loads((case / "canonical-options-receipt.json").read_text())
            self.assertEqual(canonical["core_settings"]["matrix_solver"], 1)
            (case / "proj.opt").write_text(normalized_options(case), encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(runner.RunError, "MATRIXSOLVER differs"):
                runner._verify_prepared(case, postsolve=True)
            for name, content in original_sources.items():
                self.assertEqual((source / name).read_bytes(), content)

    def test_code_one_requires_native_one_and_unknown_codes_never_allocate_case(self):
        with tempfile.TemporaryDirectory(prefix="momentum-matrix-refusal-") as temporary:
            root = Path(temporary).resolve()
            source, native, installation = self.fixture(root, 0)
            case = root / "case"
            with self.assertRaisesRegex(runner.RunError, "already match the original native"):
                runner.prepare_case(source, case, 4, [65, 80], installation,
                                    native_workspace=native, matrix_solver_code=1)
            for code in (2, -1, True, 1.0, "1"):
                with self.subTest(code=code), self.assertRaisesRegex(runner.RunError, "integer 0 or 1"):
                    runner.prepare_case(source, case, 4, [65, 80], installation,
                                        native_workspace=native, matrix_solver_code=code)
            self.assertFalse(case.exists())

    def test_legacy_receipt_without_matrix_code_remains_code_zero(self):
        with tempfile.TemporaryDirectory(prefix="momentum-matrix-legacy-") as temporary:
            root = Path(temporary).resolve()
            source, native, installation = self.fixture(root, 0)
            case = root / "case"
            receipt = runner.prepare_case(source, case, 4, [65, 80], installation, native_workspace=native)
            for key in ("matrix_solver_code", "native_export_matrix_solver_code", "matrix_solver_name", "matrix_solver_classification_status"):
                del receipt[key]
            (case / "prepared-case.json").write_text(json.dumps(receipt), encoding="utf-8")
            runner._verify_prepared(case)
            (case / "proj.opt").write_text(normalized_options(case), encoding="utf-8", newline="\n")
            runner._verify_prepared(case, postsolve=True)
            self.assertEqual(json.loads((case / "canonical-options-receipt.json").read_text())["core_settings"]["matrix_solver"], 0)
            with self.assertRaisesRegex(runner.RunError, "MATRIXSOLVER differs"):
                runner._canonical_option_values(normalized_options(case).replace("matrixSolver 0;", "matrixSolver 1;"),
                                                mesh_um=4, threads=4, case_dir=case)


if __name__ == "__main__":
    unittest.main()
