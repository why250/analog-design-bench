"""Portable Virtuoso workspace ownership, input integrity and EDA boundaries."""
from pathlib import Path
import json
import sys
import tempfile
import tomllib
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts import virtuoso_workspace as vw


class VirtuosoWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        task = self.repo / "tasks/demo-lpf"
        (task / "inputs").mkdir(parents=True)
        (task / "task.toml").write_text('[metadata]\ntask_id="demo-lpf"\nrevision=1\nstage="ideal"\n', encoding="utf-8")
        for name in ("instruction.md", "verification-plan.md", "DEVELOPMENT.md"):
            (task / name).write_text("# Authored contract\n", encoding="utf-8")
        (task / "engineering.toml").write_text(
            'schema_version=1\neda="virtuoso"\nworkflow="virtuoso"\nkind="reproduction"\n'
            'deliverables=["source","simulation"]\ninputs=["inputs/values.json"]\n', encoding="utf-8")
        (task / "inputs/values.json").write_text('{"L":1e-10}\n', encoding="utf-8")

    def init(self):
        return vw.init_workspace(self.repo, task_id="demo-lpf", revision=1, stage="ideal",
                                 block_key="LPF", dut_lib="LPF_R01_lib", dut_cell="LPF_Main",
                                 dut_ports=["rfin", "rfout", "gnd"], model_policy="unrestricted-ideal")

    def test_native_layout_and_snapshot_remain_virtuoso(self):
        workspace = self.init()
        doc = tomllib.loads((workspace / "project.toml").read_text(encoding="utf-8"))
        self.assertEqual(doc["eda"], "virtuoso")
        self.assertEqual(doc["paths"]["virtuoso"], "virtuoso")
        self.assertNotIn("ads", doc["paths"])
        self.assertTrue((workspace / "inputs/task-spec/inputs/values.json").is_file())
        self.assertEqual(vw.validate_workspace(self.repo, workspace)["status"], "ok")
        with self.assertRaises(FileExistsError):
            self.init()

    def test_snapshot_drift_and_wrong_eda_are_rejected(self):
        workspace = self.init()
        snapshot = workspace / "inputs/task-spec/inputs/values.json"
        snapshot.write_text("changed\n", encoding="utf-8")
        self.assertEqual(vw.validate_workspace(self.repo, workspace)["status"], "error")
        manifest = workspace / "project.toml"
        manifest.write_text(manifest.read_text().replace('eda = "virtuoso"', 'eda = "ads"'), encoding="utf-8")
        self.assertIn("eda = virtuoso", " ".join(vw.validate_workspace(self.repo, workspace)["errors"]))

    def test_path_escape_and_missing_ignore_rule_are_rejected(self):
        workspace = self.init()
        manifest = workspace / "project.toml"
        original = manifest.read_text()
        manifest.write_text(original.replace('virtuoso = "virtuoso"', 'virtuoso = "../outside"'), encoding="utf-8")
        self.assertEqual(vw.validate_workspace(self.repo, workspace)["status"], "error")
        manifest.write_text(original, encoding="utf-8")
        ignore = workspace / ".gitignore"
        ignore.write_text(ignore.read_text().replace("/results/\n", ""), encoding="utf-8")
        self.assertEqual(vw.validate_workspace(self.repo, workspace)["status"], "error")

    def test_invalid_route_does_not_allocate_run(self):
        workspace = self.init()
        registry = self.repo / "engineering/workflows.toml"
        registry.parent.mkdir()
        registry.write_text('schema_version=1\n[workflows.virtuoso]\neda="virtuoso"\nstatus="reserved"\nversion="0.0"\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "conflicts"):
            vw.allocate_run_dir(workspace, "test", repo=self.repo, registry=registry, workflow="ads-generic")
        self.assertEqual(list((workspace / "results").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
