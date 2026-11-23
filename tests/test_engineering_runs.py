"""Behavioral checks for engineering routing, evidence gates and sealed records."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts import ads_workspace as aw
from scripts import engineering_runs as er


class EngineeringRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.registry = self.repo / "engineering" / "workflows.toml"
        self.registry.parent.mkdir()
        self.registry.write_text(
            'schema_version = 1\n'
            '[workflows.ads-generic]\neda = "ads"\nstatus = "implemented"\nversion = "1.0"\n'
            'documents = ["docs/common.md"]\n'
            '[workflows.ads-lpf]\neda = "ads"\nstatus = "implemented"\nversion = "1.0"\n'
            'documents = ["docs/common.md"]\n'
            '[workflows.virtuoso]\neda = "virtuoso"\nstatus = "reserved"\nversion = "0.0"\n',
            encoding="utf-8",
        )
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "common.md").write_text("# Common rules\n", encoding="utf-8")
        (self.repo / "scripts").mkdir()
        for name in ("ads_workspace.py", "engineering_runs.py"):
            shutil.copyfile(REPO / "scripts" / name, self.repo / "scripts" / name)
        self.ws = aw.init_workspace(self.repo, task_id="demo-amp", stage="source-creation", create_task=True)
        self.task = self.repo / "tasks" / "demo-amp"

    def new_run(self, *, deliverables=None, kind=None):
        return aw.allocate_run_dir(self.ws, "nominal", registry=self.registry, repo=self.repo,
                                   deliverables=deliverables, kind=kind)

    def write_record(self, run, record):
        (run / "run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    def artifact(self, run, relative, text="retained observation\n"):
        path = run / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return relative

    def ready_run(self, *, deliverables=None, kind=None):
        run = self.new_run(deliverables=deliverables, kind=kind)
        er.freeze_contract(run, self.repo)
        record = er.read_json(run / "run.json")
        record["selection"]["native_design"] = "AMP_R01_lib:AMP_Main:schematic"
        record["readiness"] = dict(status="confirmed", scope="Build the declared schematic within the task budget.",
                                    brief=self.artifact(run, "delegation.md", "# Delegation\nBudget: one build. Stop after review.\n"),
                                    confirmed_by="task owner", confirmed_utc=er.utc_now())
        record["preflight"] = "preflight/observed.json"
        observed = dict(
            schema_version=1, status="ready", observed_utc=er.utc_now(), eda="ads",
            task_version_id="demo-amp-r1", native_design=record["selection"]["native_design"],
            workspace=dict(status="verified", evidence=[self.artifact(run, "preflight/workspace.txt")]),
            models=dict(status="not-applicable", reason="Source-only ideal drawing.",
                        evidence=[self.artifact(run, "preflight/models.txt")]),
        )
        er.write_json(run / record["preflight"], observed)
        self.write_record(run, record)
        return run, record

    def complete_run(self, *, deliverables=None, kind=None, electrical="not-applicable"):
        run, record = self.ready_run(deliverables=deliverables, kind=kind)
        record.update(state="completed", started_utc=er.utc_now(), ended_utc=er.utc_now())
        record["evidence"]["native_source"] = [self.artifact(run, "source/editable-source.oa")]
        report = self.artifact(run, "reports/review.json", '{"scope":"task-owned review"}\n')
        record["outcomes"] = dict(
            execution=dict(status="completed", evidence=[report]),
            electrical=dict(status=electrical, evidence=[] if electrical == "not-applicable" else [report],
                            reason="No simulation was requested."),
            models=dict(status="not-applicable", evidence=[], reason="No physical model qualification requested."),
            delivery=dict(status="complete", evidence=[report]),
        )
        if deliverables and ("simulation" in deliverables or "em" in deliverables):
            for role in ("simulator_log", "raw_data", "measurements", "check_report"):
                record["evidence"][role] = [self.artifact(run, f"evidence/{role}.txt")]
        if deliverables and "simulation" in deliverables:
            record["evidence"]["netlist"] = [self.artifact(run, "evidence/netlist.txt")]
        if deliverables and "layout" in deliverables:
            record["evidence"]["layout"] = [self.artifact(run, "source/layout.oa")]
        if deliverables and "em" in deliverables:
            record["evidence"]["em_setup"] = [self.artifact(run, "source/em-setup.txt")]
            record["evidence"]["solver_input"] = [self.artifact(run, "source/momentum-deck.txt")]
        self.write_record(run, record)
        return run, record

    def test_new_run_is_draft_and_has_no_claim_of_readiness(self):
        run = self.new_run()
        self.assertEqual(er.check_run(run)["status"], "ok")
        self.assertEqual(er.check_run(run, "ready")["status"], "error")
        record = er.read_json(run / "run.json")
        self.assertEqual(record["workflow"], dict(id="ads-generic", version="1.0"))
        self.assertEqual(record["deliverables"], ["source"])
        self.assertEqual(record["readiness"]["status"], "draft")

    def test_route_existing_task_precedes_keyword_or_explicit_override(self):
        (self.task / "engineering.toml").write_text(
            'schema_version=1\neda="ads"\nworkflow="ads-lpf"\nkind="feasibility"\n'
            'deliverables=["source","simulation"]\n', encoding="utf-8")
        route = er.resolve_route(self.registry, task=self.task, eda="ads")
        self.assertEqual(route["workflow"], "ads-lpf")
        self.assertEqual(route["selection_basis"], "task-profile")
        with self.assertRaisesRegex(ValueError, "conflicts"):
            er.resolve_route(self.registry, task=self.task, workflow="ads-generic")
        record = er.read_json(self.new_run() / "run.json")
        self.assertEqual(record["kind"], "feasibility")
        self.assertEqual(record["deliverables"], ["source", "simulation"])

    def test_reserved_route_is_draft_only(self):
        route = er.resolve_route(self.registry, eda="virtuoso")
        self.assertEqual(route["status"], "reserved")
        with self.assertRaisesRegex(ValueError, "Unknown workflow"):
            er.resolve_route(self.registry, workflow="invented-tool")
        run, record = self.ready_run()
        # A changed registry cannot turn the recorded workflow into executable support.
        frozen_registry = run / "contract" / "workflow" / "engineering" / "workflows.toml"
        frozen_registry.write_text(frozen_registry.read_text().replace('status = "implemented"', 'status = "reserved"'), encoding="utf-8")
        self.assertEqual(er.check_run(run, "ready")["status"], "error")

    def test_ready_allows_native_source_to_be_created_later(self):
        run, record = self.ready_run()
        self.assertEqual(record["evidence"]["native_source"], [])
        self.assertEqual(er.check_run(run, "ready")["status"], "ok")
        self.assertEqual(er.check_run(run, "handoff")["status"], "error")

    def test_ready_rejects_unconfirmed_scope_and_preflight_without_observation(self):
        run, record = self.ready_run()
        record["readiness"]["scope"] = ""
        self.write_record(run, record)
        self.assertEqual(er.check_run(run, "ready")["status"], "error")
        record["readiness"]["scope"] = "Create source only."
        self.write_record(run, record)
        observed = er.read_json(run / record["preflight"])
        observed["workspace"]["evidence"] = []
        (run / record["preflight"]).write_text(json.dumps(observed), encoding="utf-8")
        self.assertEqual(er.check_run(run, "ready")["status"], "error")

    def test_model_investigation_can_use_conditional_preflight_with_limits(self):
        run, record = self.ready_run(kind="feasibility")
        observed = er.read_json(run / record["preflight"])
        observed["models"]["status"] = "conditional"
        observed["models"]["reason"] = "First work package investigates the declared model domain."
        (run / record["preflight"]).write_text(json.dumps(observed), encoding="utf-8")
        self.assertEqual(er.check_run(run, "ready")["status"], "ok")
        del observed["models"]["reason"]
        (run / record["preflight"]).write_text(json.dumps(observed), encoding="utf-8")
        self.assertEqual(er.check_run(run, "ready")["status"], "error")

    def test_frozen_contract_checks_bytes_and_does_not_follow_live_changes(self):
        run, _ = self.ready_run()
        (self.task / "instruction.md").write_text("# Later task amendment\n", encoding="utf-8")
        self.assertEqual(er.check_run(run, "ready")["status"], "ok")
        frozen = run / "contract" / "task" / "instruction.md"
        frozen.write_text("# Changed frozen input\n", encoding="utf-8")
        self.assertEqual(er.check_run(run, "ready")["status"], "error")
        with self.assertRaises(ValueError):
            er.freeze_contract(run, self.repo)

    def test_frozen_identity_and_workflow_changes_before_freeze_are_rejected(self):
        run = self.new_run()
        self.registry.write_text(self.registry.read_text().replace('version = "1.0"', 'version = "2.0"'), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed"):
            er.freeze_contract(run, self.repo)
        self.assertFalse((run / "contract").exists())

    def test_optional_task_stage_and_version_must_match_before_freeze(self):
        run = self.new_run()
        task_file = self.task / "task.toml"
        original = task_file.read_text(encoding="utf-8")
        for old, new in (
            ('stage = "source-creation"', 'stage = "unrelated-stage"'),
            ('task_version_id = "demo-amp-r1"', 'task_version_id = "demo-amp-r2"'),
        ):
            task_file.write_text(original.replace(old, new), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs"):
                er.freeze_contract(run, self.repo)
            self.assertFalse((run / "contract").exists())
        task_file.write_text(original, encoding="utf-8")
        er.freeze_contract(run, self.repo)

    def test_workspace_snapshot_retains_profile_and_declared_nested_inputs(self):
        (self.task / "inputs").mkdir()
        (self.task / "inputs" / "device.json").write_text('{"model":"declared"}', encoding="utf-8")
        (self.task / "engineering.toml").write_text(
            'schema_version=1\neda="ads"\nworkflow="ads-lpf"\nkind="design"\n'
            'deliverables=["source"]\ninputs=["inputs/device.json"]\n', encoding="utf-8")
        snapshot = aw.snapshot_task_spec(self.repo, self.ws)
        route = er.resolve_route(self.registry, task=snapshot, eda="ads")
        self.assertEqual(route["workflow"], "ads-lpf")
        self.assertTrue((snapshot / "inputs/device.json").is_file())
        self.assertEqual(aw.validate_workspace(self.repo, self.ws, require_v2=True)["status"], "ok")

    def test_nested_input_traversal_is_rejected_before_writing_contract(self):
        (self.task / "engineering.toml").write_text(
            'schema_version=1\neda="ads"\nworkflow="ads-generic"\nkind="design"\n'
            'deliverables=["source"]\ninputs=["../external.txt"]\n', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.new_run()
        self.assertEqual(list((self.ws / "results").iterdir()), [])

    def test_verified_snapshot_can_route_and_freeze_on_an_isolated_host(self):
        aw.snapshot_task_spec(self.repo, self.ws)
        shutil.rmtree(self.task)
        run, _ = self.ready_run()
        self.assertEqual(er.check_run(run, "ready")["status"], "ok")
        frozen_manifest = er.read_json(run / "contract/manifest.json")
        self.assertEqual(frozen_manifest["source"]["kind"], "verified-workspace-task-snapshot")
        self.assertTrue((run / "contract/task-source-manifest.json").is_file())

    def test_unlisted_snapshot_profile_cannot_change_fallback_route(self):
        snapshot = aw.snapshot_task_spec(self.repo, self.ws)
        (snapshot / "engineering.toml").write_text(
            'schema_version=1\neda="ads"\nworkflow="ads-lpf"\nkind="design"\n'
            'deliverables=["source"]\n', encoding="utf-8")
        shutil.rmtree(self.task)
        with self.assertRaisesRegex(ValueError, "unlisted"):
            self.new_run()
        self.assertEqual(list((self.ws / "results").iterdir()), [])

    def test_frozen_helper_runs_from_another_working_directory_without_modifying_contract(self):
        run, _ = self.ready_run()
        received = self.repo / "received" / run.name
        shutil.copytree(run, received)
        before = er._inventory(received / "contract")
        helper = received / "contract/workflow/scripts/engineering_runs.py"
        result = subprocess.run([sys.executable, str(helper), "check", "--run", str(received), "--phase", "ready"],
                                cwd=received.parent, text=True, capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["status"], "ok")
        self.assertEqual(er._inventory(received / "contract"), before)
        cli_result = subprocess.run([sys.executable, str(REPO / "scripts/ads_workspace.py"), "new-run",
                                     "--workspace", str(self.ws), "--slug", "direct-cli"],
                                    cwd=self.repo, text=True, capture_output=True, encoding="utf-8")
        self.assertEqual(cli_result.returncode, 0, cli_result.stderr)

    def test_seal_metadata_must_agree_with_the_record(self):
        run, _ = self.complete_run()
        er.close_run(run)
        seal_file = run / "seal.json"
        original = er.read_json(seal_file)
        for key, bad in (("state", "failed"), ("run_id", "wrong-run"), ("schema_version", 2), ("sealed_utc", "invalid")):
            changed = dict(original)
            changed[key] = bad
            seal_file.write_text(json.dumps(changed), encoding="utf-8")
            self.assertEqual(er.check_run(run)["status"], "error")
        seal_file.write_text(json.dumps(original), encoding="utf-8")
        self.assertEqual(er.check_run(run)["status"], "ok")

    def test_failed_archive_cannot_assert_positive_results_without_evidence(self):
        run = self.new_run()
        record = er.read_json(run / "run.json")
        record.update(state="failed", ended_utc=er.utc_now())
        record["outcomes"]["execution"]["status"] = "failed"
        record["outcomes"]["delivery"]["status"] = "incomplete"
        record["outcomes"]["electrical"]["status"] = "passed"
        record["gaps"] = ["Final native delivery failed."]
        self.write_record(run, record)
        with self.assertRaisesRegex(ValueError, "nonempty"):
            er.close_run(run)

    def test_source_only_handoff_needs_no_simulation_and_seal_detects_changes(self):
        run, record = self.complete_run()
        self.assertEqual(er.check_run(run, "handoff")["status"], "ok")
        self.assertEqual(er.close_run(run)["status"], "sealed")
        self.assertEqual(er.check_run(run, "handoff")["status"], "ok")
        with self.assertRaises(FileExistsError):
            er.close_run(run)
        (run / record["evidence"]["native_source"][0]).write_text("modified\n", encoding="utf-8")
        self.assertEqual(er.check_run(run, "handoff")["status"], "error")

    def test_seal_detects_run_record_changes_and_new_files(self):
        run, record = self.complete_run()
        er.close_run(run)
        self.artifact(run, "unexpected.txt")
        self.assertEqual(er.check_run(run)["status"], "error")
        (run / "unexpected.txt").unlink()
        record["notes"].append("changed after sealing")
        self.write_record(run, record)
        self.assertEqual(er.check_run(run)["status"], "error")

    def test_completed_feasibility_study_may_have_failed_electrical_candidate(self):
        run, _ = self.complete_run(deliverables=["source", "simulation"], kind="feasibility", electrical="failed")
        self.assertEqual(er.check_run(run, "handoff")["status"], "ok")
        er.close_run(run)

    def test_missing_or_empty_raw_data_cannot_pass_completed_simulation(self):
        run, record = self.complete_run(deliverables=["source", "simulation"], electrical="passed")
        raw = run / record["evidence"]["raw_data"][0]
        raw.write_bytes(b"")
        self.assertEqual(er.check_run(run, "handoff")["status"], "error")
        with self.assertRaises(ValueError):
            er.close_run(run)

    def test_em_and_layout_have_distinct_evidence_requirements(self):
        run, record = self.complete_run(deliverables=["source", "layout", "em"], electrical="conditional")
        self.assertEqual(er.check_run(run, "handoff")["status"], "ok")
        self.assertEqual(record["evidence"]["netlist"], [])
        record["evidence"]["em_setup"] = []
        self.write_record(run, record)
        self.assertEqual(er.check_run(run, "handoff")["status"], "error")

    def test_cannot_reduce_deliverables_after_contract_freeze(self):
        run, record = self.ready_run(deliverables=["source", "simulation"])
        record["deliverables"] = ["source"]
        self.write_record(run, record)
        self.assertEqual(er.check_run(run, "ready")["status"], "error")

    def test_task_plans_and_declared_nested_inputs_are_frozen(self):
        (self.task / "model-plan.md").write_text("# Model domain\n", encoding="utf-8")
        (self.task / "inputs").mkdir()
        (self.task / "inputs" / "device.json").write_text('{"model":"declared"}', encoding="utf-8")
        (self.task / "engineering.toml").write_text(
            'schema_version=1\neda="ads"\nworkflow="ads-generic"\nkind="design"\n'
            'deliverables=["source"]\ninputs=["inputs/device.json"]\n', encoding="utf-8")
        run, _ = self.ready_run()
        self.assertTrue((run / "contract/task/model-plan.md").is_file())
        self.assertTrue((run / "contract/task/inputs/device.json").is_file())
        (run / "contract/task/inputs/device.json").write_text("changed", encoding="utf-8")
        self.assertEqual(er.check_run(run, "ready")["status"], "error")

    def test_invalid_route_does_not_allocate_an_empty_run(self):
        with self.assertRaisesRegex(ValueError, "Unknown workflow"):
            aw.allocate_run_dir(self.ws, "bad-route", workflow="missing", registry=self.registry)
        self.assertEqual(list((self.ws / "results").iterdir()), [])

    def test_owner_identity_mismatch_rejected_but_standalone_handoff_works(self):
        run, _ = self.ready_run()
        standalone = self.repo / "exports" / run.name
        shutil.copytree(run, standalone)
        self.assertEqual(er.check_run(standalone, "ready")["status"], "ok")
        other = aw.init_workspace(self.repo, task_id="other-task", stage="source-creation", create_task=True)
        wrong_owner = other / "results" / run.name
        shutil.copytree(run, wrong_owner)
        self.assertEqual(er.check_run(wrong_owner, "ready")["status"], "error")

    def test_failed_run_can_be_archived_but_never_as_complete_delivery(self):
        run = self.new_run()
        record = er.read_json(run / "run.json")
        record.update(state="failed", ended_utc=er.utc_now())
        record["outcomes"]["execution"]["status"] = "failed"
        record["outcomes"]["delivery"]["status"] = "complete"
        record["gaps"] = ["Required model was not available; no circuit simulation performed."]
        self.write_record(run, record)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            er.close_run(run)
        record["outcomes"]["delivery"]["status"] = "incomplete"
        self.write_record(run, record)
        er.close_run(run)
        self.assertEqual(er.check_run(run)["status"], "ok")
        self.assertEqual(er.check_run(run, "handoff")["status"], "error")

    def test_traversal_absolute_paths_duplicates_and_nonfinite_json_rejected(self):
        run, record = self.complete_run()
        for bad in ("../outside.txt", "C:/private.txt", "/private.txt"):
            record["evidence"]["native_source"] = [bad]
            self.write_record(run, record)
            self.assertEqual(er.check_run(run)["status"], "error")
        record["evidence"]["native_source"] = ["source/editable-source.oa"] * 2
        self.write_record(run, record)
        self.assertEqual(er.check_run(run)["status"], "error")
        (run / "run.json").write_text('{"schema_version": NaN}', encoding="utf-8")
        self.assertEqual(er.check_run(run)["status"], "error")

    def test_symlink_evidence_cannot_escape_run(self):
        run, record = self.complete_run()
        target = self.repo / "external.txt"
        target.write_text("outside\n", encoding="utf-8")
        link = run / "linked.txt"
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest("Symlink creation is unavailable.")
        record["evidence"]["native_source"] = ["linked.txt"]
        self.write_record(run, record)
        self.assertEqual(er.check_run(run)["status"], "error")


if __name__ == "__main__":
    unittest.main()
