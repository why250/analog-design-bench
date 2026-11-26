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
        for name in ("ads_workspace.py", "engineering_runs.py", "virtuoso_workspace.py"):
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

    def virtuoso_task(self):
        task = self.repo / "tasks/demo-lpf"
        task.mkdir()
        (task / "task.toml").write_text('[metadata]\ntask_id="demo-lpf"\nrevision=1\nstage="ideal"\n', encoding="utf-8")
        for name in ("instruction.md", "verification-plan.md", "DEVELOPMENT.md"):
            (task / name).write_text("# Contract\n", encoding="utf-8")
        (task / "engineering.toml").write_text(
            'schema_version=1\neda="virtuoso"\nworkflow="virtuoso"\nkind="reproduction"\n'
            'deliverables=["source","simulation"]\n', encoding="utf-8")
        registry = self.repo / "engineering/workflows.toml"
        registry.write_text(registry.read_text() + '\n[workflows.virtuoso]\neda="virtuoso"\nstatus="implemented"\nversion="1.0"\ndocuments=[]\n', encoding="utf-8")
        binding = self.repo / ".local/virtuoso-projects/demo-lpf.json"
        binding.parent.mkdir()
        binding.write_text(json.dumps(dict(task_id="demo-lpf", revision=1, mcp_server="virt-tools",
            remote_project="/owned/demo-lpf", required_tools={"virtuoso":"IC-custom", "spectre":"S-custom"})), encoding="utf-8")
        self.plan.update(task="virtuoso", selected_host="linux", platform="linux", workspace_root="/owned/demo-lpf",
                         required_tools={"virtuoso":"IC-custom", "spectre":"S-custom"},
                         project_binding={"mcp_name":"virt-tools", "status":"configured"})
        return task, binding

    def test_virtuoso_prepare_uses_selected_tools_and_native_paths(self):
        task, binding = self.virtuoso_task()
        original = binding.read_bytes()
        with patch.object(ee.subprocess, "run", side_effect=self.invoke_planner):
            result = ee.prepare_task(self.repo, task, slug="smoke", block_key="VLPF",
                                     dut_cell="VLPF_Main", dut_ports=["rfin","rfout","gnd"], client="codex")
        self.assertEqual(self.request["task"], "virtuoso")
        self.assertEqual(self.request["required_tools"], {"virtuoso":"IC-custom", "spectre":"S-custom"})
        private = er.read_json(self.repo / result["private_receipt"])
        self.assertEqual(private["paths"]["remote_native"], "/owned/demo-lpf/virtuoso")
        self.assertEqual(private["paths"]["remote_virtuoso"], private["paths"]["remote_native"])
        self.assertNotIn("remote_ads", private["paths"])
        run = self.repo / result["run"]
        portable = er.read_json(run / "environment-plan.json")
        self.assertEqual(portable["paths"]["virtuoso"], "virtuoso")
        self.assertNotIn("/owned/", json.dumps(portable))
        self.assertTrue((run / "contract/workflow/scripts/virtuoso_workspace.py").is_file())
        self.assertEqual(er.read_json(run / "run.json")["eda"], "virtuoso")
        self.assertEqual(binding.read_bytes(), original)

    def test_virtuoso_missing_solver_selection_or_unconfigured_binding_creates_no_run(self):
        task, binding = self.virtuoso_task()
        data = er.read_json(binding)
        del data["required_tools"]["spectre"]
        binding.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Virtuoso and Spectre"):
            ee.environment_plan(self.repo, task)
        data["required_tools"]["spectre"] = "S-custom"
        binding.write_text(json.dumps(data), encoding="utf-8")
        self.plan["project_binding"]["status"] = "not-configured"
        with patch.object(ee.subprocess, "run", side_effect=self.invoke_planner):
            with self.assertRaisesRegex(ValueError, "configured calling-client"):
                ee.prepare_task(self.repo, task, slug="smoke", block_key="VLPF")
        self.assertFalse((self.repo / "workspaces/demo-lpf").exists())

    def test_reserved_virtuoso_environment_is_not_bypassed(self):
        task, _ = self.virtuoso_task()
        registry = self.repo / "engineering/workflows.toml"
        registry.write_text(registry.read_text().replace('status="implemented"', 'status="reserved"'), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "reserved"):
            ee.environment_plan(self.repo, task)

    def test_existing_workspace_wrong_eda_is_rejected(self):
        (self.task / "engineering.toml").write_text(
            'schema_version=1\neda="virtuoso"\nworkflow="virtuoso"\nkind="design"\ndeliverables=["source"]\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "workspace EDA"):
            ee.task_context(self.repo, self.task)


if __name__ == "__main__":
    unittest.main()
