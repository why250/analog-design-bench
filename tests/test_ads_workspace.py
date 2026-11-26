"""Tests for ADS engineering workspace scaffolding and schema_version = 2 validation."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import re
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))

import ads_workspace as aw  # noqa: E402
from scripts.lpf import task_handoff  # noqa: E402


def _ensure_apk_naming_modules():
    """Load real sibling ads_project_kit.naming when present, or a minimal test stub."""
    sibling_src = REPO.parent / "ads-project-kit" / "src"
    if (sibling_src / "ads_project_kit" / "naming.py").is_file():
        if str(sibling_src) not in sys.path:
            sys.path.insert(0, str(sibling_src))
        import ads_project_kit
        import ads_project_kit.naming

        return {"ads_project_kit": ads_project_kit, "ads_project_kit.naming": ads_project_kit.naming}

    ident = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z", re.ASCII)
    tb = re.compile(r"TB_(?P<dut>[A-Za-z_][A-Za-z0-9_]*)_(?:SP|HB|TRAN|AC|DC|EM)(?:_[A-Z][A-Z0-9]*)?\Z", re.ASCII)
    standard = frozenset({"schematic", "symbol", "layout", "emSetup", "emModel", "emModel_mw"})
    kit = ModuleType("ads_project_kit")
    naming = ModuleType("ads_project_kit.naming")
    naming.STANDARD_VIEWS = standard
    naming.is_valid_workspace_name = lambda n: isinstance(n, str) and n.endswith("_wrk") and bool(ident.fullmatch(n[:-4]))
    naming.is_valid_library_name = lambda n: isinstance(n, str) and bool(ident.fullmatch(n))
    naming.is_valid_dut_cell_name = lambda n: isinstance(n, str) and bool(ident.fullmatch(n)) and not n.upper().startswith("TB_")
    naming.is_valid_testbench_cell_name = lambda n: isinstance(n, str) and bool(tb.fullmatch(n)) and not tb.fullmatch(n).group("dut").upper().startswith("TB_")
    naming.is_valid_view_name = lambda n: isinstance(n, str) and (n in standard or (n.startswith("x_") and len(n) > 2 and bool(ident.fullmatch(n))))
    kit.naming = naming
    return {"ads_project_kit": kit, "ads_project_kit.naming": naming}


class AdsWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / "tasks").mkdir()
        (self.repo / "workspaces").mkdir()

    def test_init_create_task_and_validate_both_policies(self):
        ws_pdk = aw.init_workspace(
            self.repo,
            task_id="inp-lna-65g-nominal",
            stage="nominal-schematic",
            model_policy="restricted-pdk",
            dut_lib="inp_lna_lib",
            dut_cell="LNA_65G",
            dut_ports=["RFIN", "RFOUT", "VCC", "GND"],
            create_task=True,
            with_tools=True,
            with_tests=True,
            snapshot_spec=True,
        )
        self.assertTrue((self.repo / "tasks" / "inp-lna-65g-nominal" / "task.toml").is_file())
        self.assertTrue((ws_pdk / "inputs" / "task-spec" / "manifest.json").is_file())
        self.assertIn("/ads/", (ws_pdk / ".gitignore").read_text(encoding="utf-8"))
        report_pdk = aw.validate_workspace(self.repo, ws_pdk, require_v2=True)
        self.assertEqual(report_pdk["status"], "ok", report_pdk["errors"])

        ws_ideal = aw.init_workspace(
            self.repo,
            task_id="ideal-bpf-50ohm-r1",
            stage="ideal-verification",
            model_policy="unrestricted-ideal",
            wrk_name="bpf_ideal_wrk",
            create_task=True,
        )
        self.assertNotIn("/ads/", (ws_ideal / ".gitignore").read_text(encoding="utf-8"))
        self.assertIn("**/simulation/", (ws_ideal / ".gitignore").read_text(encoding="utf-8"))
        report_ideal = aw.validate_workspace(self.repo, ws_ideal, require_v2=True)
        self.assertEqual(report_ideal["status"], "ok", report_ideal["errors"])

    def test_init_requires_task_package_unless_create_task_set(self):
        with self.assertRaises(FileNotFoundError):
            aw.init_workspace(self.repo, task_id="missing-task", stage="nominal-schematic")

    def test_init_rejects_mismatched_existing_task_metadata(self):
        task_dir = self.repo / "tasks" / "demo-task"
        task_dir.mkdir(parents=True)
        for name in ("instruction.md", "verification-plan.md", "DEVELOPMENT.md"):
            (task_dir / name).write_text("# demo\n", encoding="utf-8")
        (task_dir / "task.toml").write_text(
            '[metadata]\ntask_id = "demo-task"\nrevision = 2\n', encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "Revision mismatch"):
            aw.init_workspace(self.repo, task_id="demo-task", revision=1, stage="nominal-schematic")

    def test_lpf_task_handoff_is_compatible_with_v2_workspace(self):
        ws_ideal = aw.init_workspace(
            self.repo,
            task_id="lpf-demo-ideal",
            stage="lpf-ideal",
            model_policy="unrestricted-ideal",
            create_task=True,
        )
        ws_pcell = aw.init_workspace(
            self.repo,
            task_id="lpf-demo-pcell",
            stage="lpf-pcell",
            model_policy="restricted-pdk",
            create_task=True,
        )
        loaded_ideal = task_handoff.load_task(ws_ideal)
        loaded_pcell = task_handoff.load_task(ws_pcell)
        self.assertEqual(loaded_ideal["identity"]["stage"], "lpf-ideal")
        self.assertEqual(loaded_pcell["identity"]["stage"], "lpf-pcell")
        # Simulating handoff creating gitignored inputs/upstream/ dynamically must not break v2 validation.
        (ws_pcell / "inputs" / "upstream" / "ideal").mkdir(parents=True)
        report = aw.validate_workspace(self.repo, ws_pcell, require_v2=True)
        self.assertEqual(report["status"], "ok", report["errors"])

    def test_rejects_forbidden_tables_and_custom_paths(self):
        ws = aw.init_workspace(self.repo, task_id="demo-v2", stage="nominal-schematic", create_task=True)
        toml_path = ws / "project.toml"
        original = toml_path.read_text(encoding="utf-8")
        toml_path.write_text(original + '\n[planning]\nstate = "draft"\n', encoding="utf-8")
        report = aw.validate_workspace(self.repo, ws, require_v2=True)
        self.assertEqual(report["status"], "error")
        self.assertTrue(any("must stay static" in err for err in report["errors"]))

        toml_path.write_text(original.replace('results = "results"', 'results = "results"\ngeometry_ads = "ads/em_wrk"'), encoding="utf-8")
        report = aw.validate_workspace(self.repo, ws, require_v2=True)
        self.assertEqual(report["status"], "error")
        self.assertTrue(any("Unsupported [paths] keys" in err for err in report["errors"]))

    def test_rejects_ads_archives_undeclared_wrk_tools_tests_and_bad_results(self):
        ws = aw.init_workspace(
            self.repo,
            task_id="hygiene-demo",
            stage="nominal-schematic",
            create_task=True,
            with_tools=True,
            with_tests=True,
        )
        (ws / "ads" / "design_wrk").mkdir(parents=True)
        (ws / "ads" / "design_wrk-20261112.zip").write_bytes(b"PK")
        (ws / "ads" / "backup_wrk").mkdir()
        (ws / "tools" / "test_helper.py").write_text("assert True\n", encoding="utf-8")
        (ws / "results" / "ad-hoc-folder").mkdir()
        (ws / "results" / "loose.png").write_bytes(b"png")

        report = aw.validate_workspace(self.repo, ws, require_v2=True)
        self.assertEqual(report["status"], "error")
        joined = "\n".join(report["errors"])
        self.assertIn("Archives must not be stored under ads/", joined)
        self.assertIn("Undeclared directory under ads/: backup_wrk", joined)
        self.assertIn("Test files belong in tests/, not tools/", joined)
        self.assertIn("results/ad-hoc-folder", joined)
        self.assertIn("Loose file is not allowed directly in results/", joined)

    def test_rejects_tampered_task_spec_snapshot_and_undeclared_tools(self):
        ws = aw.init_workspace(
            self.repo,
            task_id="snapshot-demo",
            stage="nominal-schematic",
            create_task=True,
            snapshot_spec=True,
        )
        instr = ws / "inputs" / "task-spec" / "instruction.md"
        instr.write_text(instr.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
        (ws / "tools").mkdir()
        report = aw.validate_workspace(self.repo, ws, require_v2=True)
        self.assertEqual(report["status"], "error")
        joined = "\n".join(report["errors"])
        self.assertIn("integrity mismatch", joined)
        self.assertIn("tools exists on disk", joined)

    def test_allocate_run_dir_and_cli_roundtrip(self):
        buf = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(err):
            code = aw.main([
                "init",
                "--repo", str(self.repo),
                "--task-id", "cli-demo",
                "--stage", "nominal-schematic",
                "--create-task",
                "--with-tools",
            ])
        self.assertEqual(code, 0, err.getvalue())
        ws = self.repo / "workspaces" / "cli-demo"
        run_dir = aw.allocate_run_dir(ws, "nominal-check")
        self.assertRegex(run_dir.name, aw.RUN_ID_RE)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            val_code = aw.main(["validate", "--repo", str(self.repo), "--all-v2"])
        self.assertEqual(val_code, 0)

    def test_auxiliary_ads_workspace_and_symlink_rejection(self):
        ws = aw.init_workspace(self.repo, task_id="aux-demo", stage="em-and-circuit", create_task=True)
        (ws / "ads" / "design_wrk").mkdir(parents=True)
        (ws / "ads" / "aux_em_wrk").mkdir()
        toml_path = ws / "project.toml"
        toml_path.write_text(
            toml_path.read_text(encoding="utf-8")
            + '\n[ads_workspaces.em_fixture]\npath = "ads/aux_em_wrk"\npurpose = "Device EM extraction fixture"\n',
            encoding="utf-8",
        )
        report = aw.validate_workspace(self.repo, ws, require_v2=True)
        self.assertEqual(report["status"], "ok", report["errors"])

        target = self.repo / "external.txt"
        target.write_text("external\n", encoding="utf-8")
        try:
            (ws / "docs" / "linked.txt").symlink_to(target)
        except (OSError, NotImplementedError):
            return
        report_link = aw.validate_workspace(self.repo, ws, require_v2=True)
        self.assertEqual(report_link["status"], "error")
        self.assertTrue(any("Symlink or junction" in err for err in report_link["errors"]))

    def test_repository_audit_handles_legacy_workspaces_cleanly(self):
        reports = aw.audit_workspaces(REPO, v2_only=False)
        self.assertGreater(len(reports), 0)
        errors = [r for r in reports if r["status"] == "error"]
        self.assertEqual(errors, [], f"Unexpected errors in repository audit: {errors}")

    def test_mixed_eda_audit_scopes_ads_without_hiding_unknown_eda(self):
        from scripts import virtuoso_workspace as vw
        ads = aw.init_workspace(self.repo, task_id="ads-demo", stage="ideal", create_task=True)
        task = self.repo / "tasks/virtuoso-demo"
        task.mkdir()
        (task / "task.toml").write_text('[metadata]\ntask_id="virtuoso-demo"\nrevision=1\nstage="ideal"\n', encoding="utf-8")
        for name in ("instruction.md", "verification-plan.md", "DEVELOPMENT.md"):
            (task / name).write_text("# Contract\n", encoding="utf-8")
        native = vw.init_workspace(self.repo, task_id="virtuoso-demo", stage="ideal", block_key="LPF",
                                   dut_lib="LPF_R01_lib", dut_cell="LPF_Main", dut_ports=["rfin","rfout","gnd"])
        v2_reports = aw.audit_workspaces(self.repo, v2_only=True)
        self.assertEqual([(r["workspace"],r["status"]) for r in v2_reports], [(ads.name,"ok")])
        normal = {r["workspace"]:r for r in aw.audit_workspaces(self.repo)}
        self.assertEqual(normal[native.name]["status"],"non-ads")
        self.assertIn("outside ADS audit coverage",normal[native.name]["warnings"][0])
        manifest = native / "project.toml"
        manifest.write_text(manifest.read_text().replace('eda = "virtuoso"','eda = "virtouso"'),encoding="utf-8")
        self.assertEqual(aw.audit_workspaces(self.repo,v2_only=True)[1]["status"],"error")
        manifest.write_text('schema_version = [broken',encoding="utf-8")
        self.assertEqual(aw.audit_workspaces(self.repo,v2_only=True)[1]["status"],"error")

    def _init_named_workspace(self, **kwargs):
        defaults = dict(
            task_id="lpf-naming-demo",
            stage="pcell-loss-match-optimization",
            block_key="LPF",
            dut_lib="LPF_R01_lib",
            dut_cell="LPF_Series_First",
            dut_ports=["P1", "P2"],
            create_task=True,
        )
        defaults.update(kwargs)
        return aw.init_workspace(self.repo, **defaults)

    def _write_lib_defs(self, ws, entries):
        ads_ws = ws / "ads" / "design_wrk"
        ads_ws.mkdir(parents=True, exist_ok=True)
        lines = ["INCLUDE $HPEESOF_DIR/oalibs/analog_rf.defs"]
        for name, path in entries:
            lines.append(f"DEFINE {name} {path}")
            lines.append(f"ASSIGN {name} libMode shared")
        (ads_ws / "lib.defs").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return ads_ws

    def test_init_writes_block_key_and_enforces_dut_lib(self):
        ws = self._init_named_workspace()
        doc = (ws / "project.toml").read_text(encoding="utf-8")
        self.assertIn('block_key = "LPF"', doc)
        with self.assertRaisesRegex(ValueError, "dut_lib must equal"):
            aw.init_workspace(
                self.repo,
                task_id="lpf-naming-bad",
                stage="pcell-loss-match-optimization",
                block_key="LPF",
                dut_lib="lpf_lib",
                create_task=True,
            )

    def test_naming_validation_accepts_conforming_workspace(self):
        ws = self._init_named_workspace()
        ads_ws = self._write_lib_defs(
            ws,
            [
                ("LPF_R01_lib", "LPF_R01_lib"),
                ("LPF_R01_tb_lib", "LPF_R01_tb_lib"),
                ("EXAMPLE_PDK", "D:/pdk/EXAMPLE_PDK"),
            ],
        )
        for view in ("schematic", "symbol"):
            (ads_ws / "LPF_R01_lib" / "LPF_Series_First" / view).mkdir(parents=True)
        (ads_ws / "LPF_R01_lib" / "LPF_Series_First_C01" / "schematic").mkdir(parents=True)
        (ads_ws / "LPF_R01_tb_lib" / "TB_LPF_Series_First_SP" / "schematic").mkdir(parents=True)
        with patch.dict(sys.modules, _ensure_apk_naming_modules()):
            report = aw.validate_workspace(self.repo, ws, require_v2=True)
        self.assertEqual(report["status"], "ok", report["errors"])

    def test_naming_validation_rejects_bad_library_and_tb(self):
        ws = self._init_named_workspace()
        ads_ws = self._write_lib_defs(
            ws,
            [
                ("lpf_lib", "lpf_lib"),
                ("LPF_R01_lib", "LPF_R01_lib"),
                ("LPF_R01_tb_lib", "LPF_R01_tb_lib"),
            ],
        )
        for view in ("schematic", "symbol"):
            (ads_ws / "LPF_R01_lib" / "LPF_Series_First" / view).mkdir(parents=True)
        (ads_ws / "lpf_lib" / "LPF_Series_First" / "schematic").mkdir(parents=True)
        (ads_ws / "LPF_R01_tb_lib" / "TB_Unknown_SP" / "schematic").mkdir(parents=True)
        (ads_ws / "LPF_R01_tb_lib" / "InvalidTBName" / "schematic").mkdir(parents=True)
        with patch.dict(sys.modules, _ensure_apk_naming_modules()):
            report = aw.validate_workspace(self.repo, ws, require_v2=True)
        self.assertEqual(report["status"], "error")
        joined = "\n".join(report["errors"])
        self.assertIn("Task-local ADS library 'lpf_lib'", joined)
        self.assertIn("names DUT 'Unknown'", joined)
        self.assertIn("InvalidTBName", joined)

    def test_naming_validation_warns_not_run_when_ads_project_kit_missing(self):
        ws = self._init_named_workspace()
        ads_ws = self._write_lib_defs(
            ws,
            [
                ("LPF_R01_lib", "LPF_R01_lib"),
                ("LPF_R01_tb_lib", "LPF_R01_tb_lib"),
            ],
        )
        for view in ("schematic", "symbol"):
            (ads_ws / "LPF_R01_lib" / "LPF_Series_First" / view).mkdir(parents=True)
        (ads_ws / "LPF_R01_tb_lib" / "TB_LPF_Series_First_SP" / "schematic").mkdir(parents=True)
        with patch.dict(sys.modules, {"ads_project_kit": None, "ads_project_kit.naming": None}):
            report = aw.validate_workspace(self.repo, ws, require_v2=True)
        self.assertEqual(report["status"], "ok", report["errors"])
        self.assertTrue(any("NOT RUN" in warning for warning in report["warnings"]))

    def test_naming_validation_skips_without_block_key(self):
        ws = aw.init_workspace(
            self.repo,
            task_id="lpf-legacy-demo",
            stage="nominal-schematic",
            dut_lib="lpf_lib",
            create_task=True,
        )
        ads_ws = self._write_lib_defs(ws, [("lpf_lib", "lpf_lib")])
        (ads_ws / "lpf_lib" / "LPF_Legacy" / "schematic").mkdir(parents=True)
        report = aw.validate_workspace(self.repo, ws, require_v2=True)
        self.assertEqual(report["status"], "ok", report["errors"])
        self.assertTrue(any("block_key is not declared" in warning for warning in report["warnings"]))

    def test_naming_validation_accepts_vendored_library(self):
        ws = self._init_named_workspace(
            task_id="lpf-vendored-demo",
            vendored_libs=["example_pcells_lib"],
        )
        ads_ws = self._write_lib_defs(
            ws,
            [
                ("LPF_R01_lib", "LPF_R01_lib"),
                ("example_pcells_lib", "example_pcells_lib"),
            ],
        )
        for view in ("schematic", "symbol"):
            (ads_ws / "LPF_R01_lib" / "LPF_Series_First" / view).mkdir(parents=True)
        (ads_ws / "example_pcells_lib" / "example_device" / "layout").mkdir(parents=True)
        with patch.dict(sys.modules, _ensure_apk_naming_modules()):
            report = aw.validate_workspace(self.repo, ws, require_v2=True)
        self.assertEqual(report["status"], "ok", report["errors"])


if __name__ == "__main__":
    unittest.main()
