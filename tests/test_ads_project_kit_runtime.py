"""Offline tests for ads-project-kit runtime loading, preflight, creation, and validation."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts import ads_project_kit_runtime as runtime  # noqa: E402
from scripts import engineering_runs as er  # noqa: E402
from scripts import virtuoso_workspace as vw  # noqa: E402
from scripts.lpf import ads_ideal  # noqa: E402


@dataclass(frozen=True)
class _FakeCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class _FakeReport:
    path: Path
    static: tuple[_FakeCheck, ...]
    native: tuple[_FakeCheck, ...]


def _fake_keysight_module(*, workspace_open: bool = False, active_path: Path | None = None):
    keysight = ModuleType("keysight")
    keysight.__path__ = []
    ads = ModuleType("keysight.ads")
    ads.__path__ = []
    de = SimpleNamespace(
        version=lambda: 650,
        product_version=lambda: "ADS 2027",
        hpeesof_path=lambda: Path("C:/ADS2027_SIM"),
        is_pde_app=lambda: False,
        running_automation=lambda: True,
        workspace_is_open=Mock(return_value=workspace_open),
        active_workspace=Mock(return_value=SimpleNamespace(path=active_path)),
        close_workspace=Mock(),
        create_workspace=Mock(),
    )
    ads.de = de
    keysight.ads = ads
    return {"keysight": keysight, "keysight.ads": ads}, de


def _write_minimal_kit(root: Path, *, version: str = "0.1.0", include_create: bool = True) -> Path:
    pkg = root / "src" / "ads_project_kit"
    pkg.mkdir(parents=True)
    create_fn = (
        "def create_project(path, name, libraries=(), *, setup_schematic_tech=True):\n"
        "    return {'path': str(path), 'name': name, 'libraries': tuple(libraries), 'tech': setup_schematic_tech}\n"
        if include_create
        else ""
    )
    (pkg / "__init__.py").write_text(
        f'__version__ = "{version}"\n'
        + create_fn
        + "def validate_project(path, *, native=True):\n"
        + "    return None\n",
        encoding="utf-8",
    )
    (pkg / "naming.py").write_text(
        "STANDARD_VIEWS = frozenset({'schematic', 'symbol', 'layout', 'emSetup', 'emModel', 'emModel_mw'})\n"
        "def is_valid_workspace_name(name): return isinstance(name, str) and name.endswith('_wrk')\n",
        encoding="utf-8",
    )
    return root


class AdsProjectKitRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_missing_dependency_fails_clearly_without_silent_fallback(self):
        with patch.dict(sys.modules, {"ads_project_kit": None}), patch.dict(os.environ, {}, clear=False):
            os.environ.pop(runtime.ADS_PROJECT_KIT_ENV_VAR, None)
            with self.assertRaises(runtime.AdsProjectKitError) as ctx:
                runtime.load_ads_project_kit()
        message = str(ctx.exception)
        self.assertIn("Unable to import ads_project_kit", message)
        self.assertIn(runtime.ADS_PROJECT_KIT_PINNED_COMMIT, message)

    def test_runtime_loading_failures_are_rejected(self):
        missing = self.root / "does-not-exist"
        with self.assertRaisesRegex(runtime.AdsProjectKitError, "does not exist"):
            runtime.load_ads_project_kit(src_path=missing)

        empty_dir = self.root / "empty"
        empty_dir.mkdir()
        with self.assertRaisesRegex(runtime.AdsProjectKitError, "does not contain"):
            runtime.load_ads_project_kit(src_path=empty_dir)

        old_kit = _write_minimal_kit(self.root / "old_kit", version="0.0.1", include_create=True)
        with patch.dict(sys.modules):
            sys.modules.pop("ads_project_kit", None)
            sys.modules.pop("ads_project_kit.naming", None)
            with self.assertRaisesRegex(runtime.AdsProjectKitError, "older than required"):
                runtime.load_ads_project_kit(src_path=old_kit)

        broken_kit = _write_minimal_kit(self.root / "broken_kit", version="0.1.0", include_create=False)
        with patch.dict(sys.modules):
            sys.modules.pop("ads_project_kit", None)
            sys.modules.pop("ads_project_kit.naming", None)
            with self.assertRaisesRegex(runtime.AdsProjectKitError, "missing required APIs"):
                runtime.load_ads_project_kit(src_path=broken_kit)

    def test_load_via_src_path_and_env_records_provenance(self):
        kit_root = _write_minimal_kit(self.root / "deployed_kit", version="0.1.0")
        (kit_root / "ads-project-kit-commit.txt").write_text(
            runtime.ADS_PROJECT_KIT_PINNED_COMMIT + "\n", encoding="utf-8"
        )
        with patch.dict(sys.modules), patch.dict(os.environ, {runtime.ADS_PROJECT_KIT_ENV_VAR: str(kit_root)}):
            sys.modules.pop("ads_project_kit", None)
            sys.modules.pop("ads_project_kit.naming", None)
            mod, info = runtime.load_ads_project_kit()
            self.assertEqual(info["load_mode"], f"env:{runtime.ADS_PROJECT_KIT_ENV_VAR}")
            self.assertEqual(info["package_version"], "0.1.0")
            self.assertEqual(info["deployed_commit"], runtime.ADS_PROJECT_KIT_PINNED_COMMIT)
            self.assertIsNone(info["source_kind"])
            self.assertTrue(Path(info["package_path"]).is_file())
            self.assertIsNotNone(mod)

    def test_load_uses_package_info_when_available(self):
        fake_kit = ModuleType("ads_project_kit")
        fake_kit.__version__ = "0.1.0"
        fake_kit.__file__ = str(self.root / "site-packages" / "ads_project_kit" / "__init__.py")
        fake_kit.create_project = lambda *args, **kwargs: None
        fake_kit.validate_project = lambda *args, **kwargs: None
        fake_kit.package_info = lambda: {
            "name": "ads-project-kit",
            "version": "0.1.0",
            "package_path": fake_kit.__file__,
            "commit": "6f7a361000000000000000000000000000000000",
            "source_kind": "vcs",
        }
        with patch.dict(sys.modules, {"ads_project_kit": fake_kit}), patch.dict(os.environ, {}, clear=False):
            os.environ.pop(runtime.ADS_PROJECT_KIT_ENV_VAR, None)
            _mod, info = runtime.load_ads_project_kit()
        self.assertEqual(info["deployed_commit"], "6f7a361000000000000000000000000000000000")
        self.assertEqual(info["source_kind"], "vcs")
        self.assertEqual(info["package_version"], "0.1.0")

    def test_preflight_requires_ads_runtime_when_requested(self):
        kit_root = _write_minimal_kit(self.root / "kit")
        wrk = self.root / "LPF_wrk"
        with patch.dict(sys.modules, {"keysight": None, "keysight.ads": None}):
            sys.modules.pop("ads_project_kit", None)
            sys.modules.pop("ads_project_kit.naming", None)
            failed = runtime.preflight_ads_runtime(wrk, require_ads=True, src_path=kit_root)
            self.assertEqual(failed["status"], "FAIL")
            self.assertEqual(failed["ads_runtime"]["status"], "FAIL")

            not_run = runtime.preflight_ads_runtime(wrk, require_ads=False, src_path=kit_root)
            self.assertEqual(not_run["status"], "NOT RUN")
            self.assertEqual(not_run["ads_runtime"]["status"], "NOT RUN")

    def test_create_ads_project_calls_api_and_validates_natively(self):
        keysight_mods, de = _fake_keysight_module(workspace_open=False)
        wrk = self.root / "Demo_LPF_wrk"

        fake_kit = ModuleType("ads_project_kit")
        fake_kit.__version__ = "0.1.0"
        fake_kit.__file__ = str(self.root / "fake_kit" / "__init__.py")
        fake_naming = ModuleType("ads_project_kit.naming")
        fake_naming.is_valid_workspace_name = lambda name: name.endswith("_wrk")

        def fake_create(path, name, libraries=(), *, setup_schematic_tech=True):
            self.assertEqual(Path(path), wrk)
            self.assertEqual(name, "Demo_LPF")
            self.assertEqual(tuple(libraries), ("LPF_R01_lib", "LPF_R01_tb_lib"))
            self.assertFalse(setup_schematic_tech)
            wrk.mkdir(parents=True)
            return SimpleNamespace(path=wrk, name=name, libraries=tuple(libraries))

        def fake_validate(path, *, native=True):
            self.assertTrue(native)
            return _FakeReport(
                path=Path(path),
                static=(_FakeCheck("workspace_name", "PASS", wrk.name),),
                native=(
                    _FakeCheck("ads_workspace", "PASS", "Opened with the ADS API"),
                    _FakeCheck("ads_library:LPF_R01_lib", "PASS", "Registered"),
                ),
            )

        fake_kit.create_project = Mock(side_effect=fake_create)
        fake_kit.validate_project = Mock(side_effect=fake_validate)

        with patch.dict(
            sys.modules,
            {**keysight_mods, "ads_project_kit": fake_kit, "ads_project_kit.naming": fake_naming},
        ):
            result = runtime.create_ads_project(
                wrk,
                "Demo_LPF",
                ("LPF_R01_lib", "LPF_R01_tb_lib"),
                setup_schematic_tech=False,
            )

        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["validation"]["native_validated"])
        self.assertEqual(result["project"]["libraries"], ["LPF_R01_lib", "LPF_R01_tb_lib"])
        de.create_workspace.assert_not_called()
        fake_kit.create_project.assert_called_once()
        fake_kit.validate_project.assert_called_once()

    def test_validation_distinguishes_pass_fail_and_not_run(self):
        wrk = self.root / "Demo_wrk"
        wrk.mkdir()

        not_run_report = _FakeReport(
            path=wrk,
            static=(_FakeCheck("workspace_name", "PASS", "Demo_wrk"),),
            native=(_FakeCheck("ads_workspace", "NOT RUN", "ADS Python API is unavailable"),),
        )
        formatted_not_run = runtime.format_validation_report(not_run_report, native_requested=True)
        self.assertEqual(formatted_not_run["overall_status"], "NOT RUN")
        self.assertTrue(formatted_not_run["static_passed"])
        self.assertFalse(formatted_not_run["native_validated"])

        fail_report = _FakeReport(
            path=wrk,
            static=(_FakeCheck("workspace_name", "PASS", "Demo_wrk"),),
            native=(_FakeCheck("ads_workspace", "FAIL", "Unrecognized"),),
        )
        formatted_fail = runtime.format_validation_report(fail_report, native_requested=True)
        self.assertEqual(formatted_fail["overall_status"], "FAIL")
        self.assertFalse(formatted_fail["native_validated"])

        pass_report = _FakeReport(
            path=wrk,
            static=(_FakeCheck("workspace_name", "PASS", "Demo_wrk"),),
            native=(_FakeCheck("ads_workspace", "PASS", "Opened"),),
        )
        formatted_pass = runtime.format_validation_report(pass_report, native_requested=True)
        self.assertEqual(formatted_pass["overall_status"], "PASS")
        self.assertTrue(formatted_pass["native_validated"])

    def test_existing_project_and_open_workspace_are_protected(self):
        existing_wrk = self.root / "Existing_wrk"
        existing_wrk.mkdir()
        sentinel = existing_wrk / "keep.txt"
        sentinel.write_text("preserve\n", encoding="utf-8")

        keysight_mods, de = _fake_keysight_module(workspace_open=False)
        fake_kit = ModuleType("ads_project_kit")
        fake_kit.__version__ = "0.1.0"
        fake_kit.create_project = Mock()
        fake_kit.validate_project = Mock()
        fake_naming = ModuleType("ads_project_kit.naming")
        fake_naming.is_valid_workspace_name = lambda name: name.endswith("_wrk")

        with patch.dict(
            sys.modules,
            {**keysight_mods, "ads_project_kit": fake_kit, "ads_project_kit.naming": fake_naming},
        ):
            with self.assertRaisesRegex(runtime.AdsProjectKitError, "already exists"):
                runtime.create_ads_project(existing_wrk, "Existing", ("LPF_R01_lib",))
            fake_kit.create_project.assert_not_called()
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve\n")

        other_wrk = self.root / "Other_wrk"
        other_wrk.mkdir()
        fresh_wrk = self.root / "Fresh_wrk"
        open_mods, open_de = _fake_keysight_module(workspace_open=True, active_path=other_wrk)
        with patch.dict(
            sys.modules,
            {**open_mods, "ads_project_kit": fake_kit, "ads_project_kit.naming": fake_naming},
        ):
            with self.assertRaisesRegex(runtime.AdsProjectKitError, "already open"):
                runtime.create_ads_project(fresh_wrk, "Fresh", ("LPF_R01_lib",))
            open_de.close_workspace.assert_not_called()
            fake_kit.create_project.assert_not_called()
            self.assertFalse(fresh_wrk.exists())

    def test_lpf_ideal_adapter_fails_without_silent_fallback_when_kit_missing(self):
        keysight = ModuleType("keysight")
        keysight.__path__ = []
        ads = ModuleType("keysight.ads")
        ads.__path__ = []
        de = SimpleNamespace(workspace_is_open=Mock(return_value=False), create_workspace=Mock())
        ads.de = de
        ads.dataset = SimpleNamespace()
        ads.de.db_uu = SimpleNamespace()
        exp = ModuleType("keysight.ads.de.experimental")
        exp.DesignBuilder = SimpleNamespace()
        sym = ModuleType("keysight.ads.de.experimental.generate_symbol")
        sym.SymbolGenerator = SimpleNamespace()
        edatoolbox = ModuleType("keysight.edatoolbox")
        edatoolbox.__path__ = []
        edatoolbox_ads = ModuleType("keysight.edatoolbox.ads")
        edatoolbox_ads.CircuitSimulator = SimpleNamespace()
        edatoolbox.ads = edatoolbox_ads

        spec = {
            "impedance_ohm": 50.0,
            "passband_hz": 65e9,
            "s11_max_db": -20.0,
            "s22_max_db": -20.0,
            "stopbands": [{"frequency_hz": 80e9, "s21_max_db": -20.0}],
            "insertion_loss_max_db": None,
        }
        design = {"order": 3, "elements": []}
        sweeps = [("SP_broad", 1e6, 90e9, 10)]

        with patch.dict(
            sys.modules,
            {
                "keysight": keysight,
                "keysight.ads": ads,
                "keysight.ads.de": de,
                "keysight.ads.de.experimental": exp,
                "keysight.ads.de.experimental.generate_symbol": sym,
                "keysight.edatoolbox": edatoolbox,
                "keysight.edatoolbox.ads": edatoolbox_ads,
                "ads_project_kit": None,
            },
        ), patch.dict(os.environ, {}, clear=False):
            os.environ.pop(runtime.ADS_PROJECT_KIT_ENV_VAR, None)
            with self.assertRaises(runtime.AdsProjectKitError):
                ads_ideal.simulate_ideal(spec, design, sweeps, self.root / "ideal_wrk", self.root / "out")
        de.create_workspace.assert_not_called()

    def test_non_ads_virtuoso_workflow_unaffected_without_ads_project_kit(self):
        repo = self.root / "virtuoso-repo"
        task = repo / "tasks" / "demo-v"
        task.mkdir(parents=True)
        (repo / "workspaces").mkdir()
        (repo / "engineering").mkdir()
        (repo / "scripts").mkdir()
        for name in ("ads_workspace.py", "engineering_runs.py", "virtuoso_workspace.py"):
            shutil.copyfile(REPO / "scripts" / name, repo / "scripts" / name)
        (repo / "docs").mkdir()
        (repo / "docs" / "common.md").write_text("# common\n", encoding="utf-8")
        (repo / "engineering" / "workflows.toml").write_text(
            'schema_version = 1\n[workflows.virtuoso]\neda = "virtuoso"\nstatus = "implemented"\nversion = "0.1"\n'
            'documents = ["docs/common.md"]\n',
            encoding="utf-8",
        )
        (task / "task.toml").write_text('[metadata]\ntask_id="demo-v"\nrevision=1\nstage="ideal"\n', encoding="utf-8")
        for name in ("instruction.md", "verification-plan.md", "DEVELOPMENT.md"):
            (task / name).write_text("# Virtuoso task\n", encoding="utf-8")
        (task / "engineering.toml").write_text(
            'schema_version = 1\neda = "virtuoso"\nworkflow = "virtuoso"\nkind = "design"\n'
            'deliverables = ["source"]\n',
            encoding="utf-8",
        )

        with patch.dict(sys.modules, {"ads_project_kit": None, "ads_project_kit.naming": None}):
            ws = vw.init_workspace(
                repo,
                task_id="demo-v",
                stage="ideal",
                block_key="VLPF",
                dut_lib="VLPF_R01_lib",
                dut_cell="VLPF_Main",
                dut_ports=["rfin", "rfout", "gnd"],
                model_policy="unrestricted-ideal",
            )
            self.assertEqual(vw.validate_workspace(repo, ws)["status"], "ok")
            run = vw.allocate_run_dir(ws, "smoke", registry=repo / "engineering/workflows.toml", repo=repo)
            er.freeze_contract(run, repo)
            self.assertEqual(er.check_run(run, "scaffold")["status"], "ok")


if __name__ == "__main__":
    unittest.main()
