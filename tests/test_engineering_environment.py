"""Task preparation and closeout checks with a local planner protocol fixture."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts import ads_workspace as aw
from scripts import engineering_environment as ee
from scripts import engineering_runs as er


class EngineeringEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.task = self.repo / "tasks/demo-amp"
        self.ws = aw.init_workspace(self.repo, task_id="demo-amp", stage="source-creation", create_task=True,
                                    block_key="AMP", dut_lib="AMP_R01_lib", dut_cell="AMP_Main")
        (self.repo / "engineering").mkdir()
        (self.repo / "engineering/workflows.toml").write_text(
            'schema_version = 1\n[workflows.ads-generic]\neda = "ads"\nstatus = "implemented"\nversion = "1.1"\ndocuments = []\n', encoding="utf-8")
        (self.repo / "scripts").mkdir()
        for name in ("ads_workspace.py", "engineering_runs.py"):
            shutil.copyfile(REPO / "scripts" / name, self.repo / "scripts" / name)
        (self.repo / ".local").mkdir()
        (self.repo / ".local/eda-lab.json").write_text(json.dumps({
            "schema_version": 2, "lab_root": str(self.repo / "lab"),
            "clients": {"claude": {"interfaces": {"ads2027-win": {"mcp_name": "ads2027"}}},
                        "codex": {"interfaces": {"ads2027-win": {"mcp_name": "ads2027"}}}}},
        ), encoding="utf-8")
        self.plan = dict(status="planned", task="ads", selected_host="win", platform="windows",
                         required_tools={"ads": "2027"}, requested_resources={},
                         planning_ceiling=dict(logical_cpus=64, memory_gib=376, enforcement="planning_only"),
                         workspace_root="D:/owned/project/workspaces/demo-amp", pending_checks=["Actual workspace check remains pending"],
                         project_binding=dict(mcp_name="ads2027"))

    def invoke_planner(self, command, **kwargs):
        self.command = command
        self.request = json.loads(kwargs["input"])
        return subprocess.CompletedProcess(command, 0, json.dumps(self.plan), "")

    def prepare(self, **kwargs):
        with patch.object(ee.subprocess, "run", side_effect=self.invoke_planner):
            return ee.prepare_task(self.repo, self.task, slug="nominal", **kwargs)

    def test_preview_invokes_lab_without_creating_a_run(self):
        with patch.object(ee.subprocess, "run", side_effect=self.invoke_planner):
            result = ee.environment_plan(self.repo, self.task, cpus=8, memory_gib=16)
        self.assertEqual(self.request["resources"], dict(logical_cpus=8, memory_gib=16))
        self.assertIn("--project", self.command)
        self.assertEqual(result["status"], "planned")
        self.assertEqual(list((self.ws / "results").iterdir()), [])

    def test_prepare_retains_private_mapping_and_freezes_portable_plan(self):
        result = self.prepare()
        run = self.repo / result["run"]
        record = er.read_json(run / "run.json")
        summary = er.read_json(run / "environment-plan.json")
        self.assertEqual(record["readiness"]["status"], "draft")
        self.assertEqual(record["selection"]["native_design"], "AMP_R01_lib:AMP_Main:schematic")
        self.assertTrue((run / "contract/execution/environment-plan.json").exists())
        self.assertNotIn("D:/owned", json.dumps(summary))
        self.assertNotIn("lab_root", summary)
        self.assertTrue((self.repo / result["private_receipt"]).exists())
        self.assertEqual(er.check_run(run, "scaffold")["status"], "ok")
        self.assertEqual(er.check_run(run, "ready")["status"], "error")

    def test_environment_tampering_is_rejected(self):
        result = self.prepare()
        run = self.repo / result["run"]
        path = run / "environment-plan.json"
        path.write_text(path.read_text().replace('"win"', '"sz16"'), encoding="utf-8")
        self.assertEqual(er.check_run(run, "scaffold")["status"], "error")

    def test_blocked_plan_creates_no_run(self):
        self.plan["status"] = "blocked"
        result = self.prepare()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(list((self.ws / "results").iterdir()), [])

    def test_existing_task_binding_is_preserved_and_sent_as_constraint(self):
        path = self.repo / ".local/ads-projects/demo-amp.json"
        path.parent.mkdir()
        original = json.dumps(dict(task_id="demo-amp", revision=1, ssh_alias="owned-host", remote_project="D:/existing/demo"))
        path.write_text(original, encoding="utf-8")
        self.prepare()
        self.assertEqual(self.request["ssh_alias"], "owned-host")
        self.assertEqual(self.request["workspace_root"], "D:/existing/demo")
        self.assertEqual(path.read_text(), original)

    def test_missing_binding_does_not_guess(self):
        (self.repo / ".local/eda-lab.json").unlink()
        with self.assertRaisesRegex(ValueError, "bind-project"):
            ee.environment_plan(self.repo, self.task)

    def test_plan_forwards_the_calling_client(self):
        with patch.object(ee.subprocess, "run", side_effect=self.invoke_planner):
            ee.environment_plan(self.repo, self.task, client="claude")
        self.assertEqual(self.command[self.command.index("--client") + 1], "claude")

    def test_legacy_schema_one_binding_remains_accepted(self):
        (self.repo / ".local/eda-lab.json").write_text(
            json.dumps({"schema_version": 1, "lab_root": str(self.repo / "lab")}), encoding="utf-8")
        with patch.object(ee.subprocess, "run", side_effect=self.invoke_planner):
            result = ee.environment_plan(self.repo, self.task)
        self.assertEqual(result["status"], "planned")

    def test_unsupported_binding_schema_is_rejected(self):
        (self.repo / ".local/eda-lab.json").write_text(
            json.dumps({"schema_version": 3, "lab_root": str(self.repo / "lab")}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unsupported lab project binding"):
            ee.environment_plan(self.repo, self.task)

    def test_cli_forwards_the_calling_client(self):
        captured = {}

        def fake_plan(repo, task, **kwargs):
            captured.update(kwargs)
            return {"status": "planned"}

        with patch.object(ee, "environment_plan", side_effect=fake_plan):
            with contextlib.redirect_stdout(io.StringIO()):
                code = er.main(["environment", "--repo", str(self.repo), "--task", str(self.task), "--client", "claude"])
        self.assertEqual(code, 0)
        self.assertEqual(captured["client"], "claude")

    def test_prepare_can_initialize_a_new_standard_workspace(self):
        self.assertTrue(self.ws.resolve().is_relative_to(self.repo.resolve()))
        shutil.rmtree(self.ws)
        self.prepare(block_key="AMP", dut_cell="AMP_Main", model_policy="unrestricted-ideal")
        self.assertEqual(aw.validate_workspace(self.repo, self.ws, require_v2=True)["status"], "ok")

    def test_failed_closeout_updates_entrypoint_without_rewriting_run(self):
        result = self.prepare()
        run = self.repo / result["run"]
        record = er.read_json(run / "run.json")
        record.update(state="interrupted", ended_utc=er.utc_now(), gaps=["Stopped before native execution"])
        record["outcomes"]["execution"]["status"] = "interrupted"
        record["outcomes"]["delivery"]["status"] = "incomplete"
        (run / "run.json").write_text(json.dumps(record), encoding="utf-8")
        readme_before = (self.ws / "README.md").read_text()
        er.close_run(run)
        readme = (self.ws / "README.md").read_text()
        self.assertTrue(readme.startswith(readme_before.rstrip()))
        self.assertIn("interrupted", readme)
        self.assertIn(run.name, readme)
        self.assertEqual(er.check_run(run, "scaffold")["status"], "ok")


if __name__ == "__main__":
    unittest.main()
