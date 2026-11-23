"""Exercise separate authored LPF tasks through the public command line."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from .workflow import load_state, main


SPEC = """schema_version = 1
impedance_ohm = 50.0
passband_hz = 65e9
s11_max_db = -20.0
s22_max_db = -20.0

[[stopbands]]
frequency_hz = 80e9
s21_max_db = -20.0

[insertion_loss]
mode = "report_only"
"""
DESIGN = {"order": 9, "elements": [{"name": "L1", "kind": "L", "value": 120e-12}]}
CELL_BYTES = b"Editable fixture cell bytes\x00\x03"
TOUCHSTONE_BYTES = b"# Hz S RI R 50\n80000000000 0 0 0.08 0 0.08 0 0 0\n"


class AuthoredTaskWorkflowTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repo = Path(directory.name)
        self.ideal = self.make_task("filter-ideal", "lpf-ideal")
        self.pcell = self.make_task("filter-pcell", "lpf-pcell")
        self.layout = self.make_task("filter-layout", "lpf-layout")
        self.spec = self.ideal / "inputs" / "electrical.toml"
        self.spec.write_text(SPEC, encoding="utf-8")
        self.profile = self.pcell / "inputs" / "profile.toml"
        self.profile.write_text('id = "offline-test"\n', encoding="utf-8")
        self.ads_source = self.pcell / "inputs" / "source_wrk"
        self.ads_source.mkdir()
        self.calls = []

        modules = patch.dict(sys.modules, {
            "scripts.lpf.ideal": SimpleNamespace(run_ideal=self.stub_ideal),
            "scripts.lpf.search": SimpleNamespace(run_search=self.stub_search),
            "scripts.lpf.ads_layout": SimpleNamespace(build_layout=self.stub_layout),
        })
        modules.start()
        self.addCleanup(modules.stop)

    def make_task(self, task_id, stage):
        contract = self.repo / "tasks" / task_id
        contract.mkdir(parents=True)
        identity = (
            f'task_id = "{task_id}"\n'
            'revision = 1\n'
            f'task_version_id = "{task_id}-r1"\n'
            f'stage = "{stage}"\n'
        )
        (contract / "task.toml").write_text(f"[metadata]\n{identity}", encoding="utf-8")
        for name in ("instruction.md", "verification-plan.md", "DEVELOPMENT.md"):
            (contract / name).write_text(f"# Offline task {task_id}\n", encoding="utf-8")
        workspace = self.repo / "workspaces" / task_id
        (workspace / "inputs").mkdir(parents=True)
        (workspace / "project.toml").write_text(
            f'schema_version = 1\n\n[project]\n{identity}'
            '\n[paths]\ninputs = "inputs"\nresults = "results"\n',
            encoding="utf-8",
        )
        return workspace

    def stub_ideal(self, spec, out, workspace):
        self.calls.append("ideal")
        self.assertTrue(out.is_relative_to(self.ideal / "results"))
        self.assertEqual(spec["passband_hz"], 65e9)
        (out / "design.json").write_text(json.dumps(DESIGN), encoding="utf-8")
        if workspace is not None:
            workspace.mkdir()
            (workspace / "lib.defs").write_text("Ideal ADS fixture\n", encoding="utf-8")
        return {"passed": True, "verification": "ads" if workspace else "analytic", "design": DESIGN}

    def stub_search(self, spec, design, profile, out, **options):
        self.calls.append("search")
        self.assertTrue(out.is_relative_to(self.pcell / "results"))
        self.assertEqual(spec["passband_hz"], 65e9)
        self.assertEqual(design, DESIGN)
        self.assertEqual(profile, {"id": "offline-test"})
        self.assertEqual(options["ads_workspace"], self.ads_source)
        verification = out / "selected" / "ads-verification"
        workspace = verification / "ads"
        workspace.mkdir(parents=True)
        (workspace / "lib.defs").write_text("Physical ADS fixture\n", encoding="utf-8")
        (workspace / "cell.oa").write_bytes(CELL_BYTES)
        (verification / "native.s2p").write_bytes(TOUCHSTONE_BYTES)
        (out / "unselected.txt").write_text("Unselected evidence\n", encoding="utf-8")
        match = {"value_db": -21.0, "limit_db": -20.0, "frequency_hz": 65e9}
        metrics = {
            "s11_worst": match, "s22_worst": match,
            "il_worst": {"value_db": 3.0, "limit_db": None, "frequency_hz": 65e9},
            "stopbands": [{**match, "frequency_hz": 80e9}],
        }
        selected = {
            "id": "selected", "passes": True, "verification": "ads", "model_status": "conditional",
            "ads_workspace": workspace.relative_to(out).as_posix(),
            "native_touchstone": (verification / "native.s2p").relative_to(out).as_posix(),
            "devices": [{"name": "L1", "kind": "L", "parameters": {"inner_diameter": 25.0}}],
            "metrics": metrics,
        }
        return {"candidates": [
            selected,
            {"id": "screen-only", "passes": True, "verification": "screen",
             "model_status": "conditional", "metrics": metrics},
        ]}

    def stub_layout(self, candidate, profile, out, *, ads_workspace):
        self.calls.append("layout")
        self.assertTrue(out.is_relative_to(self.layout / "results"))
        self.assertTrue(ads_workspace.is_relative_to(self.layout / "inputs"))
        self.assertEqual((ads_workspace / "cell.oa").read_bytes(), CELL_BYTES)
        self.assertEqual(profile, {"id": "offline-test"})
        self.assertEqual(candidate["id"], "selected")
        self.assertEqual(candidate["devices"][0]["parameters"], {"inner_diameter": 25.0})
        return {"verified": True, "candidate": candidate["id"]}

    def invoke(self, expected, *arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main([str(argument) for argument in arguments])
        self.assertEqual(exit_code, expected, stderr.getvalue())
        return stdout.getvalue(), stderr.getvalue()

    def new_ideal(self, *flags):
        stdout, _ = self.invoke(0, "ideal", "--project", self.ideal, "--spec", self.spec, *flags)
        return Path(json.loads(stdout)["run"])

    def handoff(self, run, target, *flags):
        stdout, _ = self.invoke(0, "handoff", "--run", run, "--project", target, *flags)
        return Path(json.loads(stdout)["run"])

    def search(self, run, expected=0):
        return self.invoke(expected, "search", "--run", run, "--ads-source", self.ads_source,
                           "--profile", self.profile)

    def snapshot(self, run):
        return run.parent.parent / load_state(run)["upstream"]

    def latest(self, run, stage):
        return run / load_state(run)["attempts"][stage][-1]["path"]

    def test_runs_own_distinct_results_and_copy_the_reviewed_candidate(self):
        ideal = self.new_ideal("--ads")
        ideal_checkpoint = (ideal / "checkpoint.json").read_bytes()
        self.assertEqual(load_state(ideal)["state"], "review_ideal")
        self.assertFalse((self.pcell / "results").exists())

        pcell = self.handoff(ideal, self.pcell, "--approve-ideal")
        ideal_snapshot = self.snapshot(pcell)
        self.assertEqual((ideal_snapshot / "spec.toml").read_bytes(), self.spec.read_bytes())
        self.assertEqual(
            (ideal_snapshot / "design.json").read_bytes(),
            (self.latest(ideal, "ideal") / "design.json").read_bytes(),
        )
        self.assertEqual(load_state(pcell)["state"], "search_pending")
        self.search(pcell)
        pcell_checkpoint = (pcell / "checkpoint.json").read_bytes()
        self.assertEqual(load_state(pcell)["state"], "review_pcell")

        layout = self.handoff(pcell, self.layout, "--candidate", "selected")
        layout_snapshot = self.snapshot(layout)
        frozen = json.loads((layout_snapshot / "result.json").read_bytes())
        self.assertEqual(frozen["id"], "selected")
        self.assertEqual(frozen["ads_workspace"], "ads")
        self.assertEqual((layout_snapshot / frozen["native_touchstone"]).read_bytes(), TOUCHSTONE_BYTES)
        self.assertEqual((layout_snapshot / "ads" / "cell.oa").read_bytes(), CELL_BYTES)
        self.assertFalse((layout_snapshot / "unselected.txt").exists())
        self.assertEqual((layout_snapshot / "profile.toml").read_bytes(), self.profile.read_bytes())
        self.assertEqual(load_state(layout)["state"], "layout_pending")
        self.invoke(0, "layout", "--run", layout)

        self.assertEqual(self.calls, ["ideal", "search", "layout"])
        for run, project, stage in (
            (ideal, self.ideal, "ideal"), (pcell, self.pcell, "search"), (layout, self.layout, "layout"),
        ):
            self.assertEqual(run.parent, project / "results")
            self.assertEqual(load_state(run)["task"]["task_id"], project.name)
            self.assertEqual((run / "spec.toml").read_bytes(), self.spec.read_bytes())
            for other in {"ideal", "search", "layout"} - {stage}:
                self.assertFalse((run / other).exists())
        self.assertEqual(load_state(layout)["state"], "layout_ready")
        self.assertEqual((ideal / "checkpoint.json").read_bytes(), ideal_checkpoint)
        self.assertEqual((pcell / "checkpoint.json").read_bytes(), pcell_checkpoint)
        original = self.latest(pcell, "search") / "selected" / "ads-verification" / "ads" / "cell.oa"
        self.assertEqual(original.read_bytes(), CELL_BYTES)
        self.assertEqual((layout_snapshot / "ads" / "cell.oa").read_bytes(), CELL_BYTES)

    def test_rejects_cross_role_commands_and_unapproved_handoffs(self):
        ideal = self.new_ideal("--ads")
        self.invoke(2, "handoff", "--run", ideal, "--project", self.pcell)
        self.invoke(2, "handoff", "--run", ideal, "--project", self.layout, "--approve-ideal")
        self.invoke(2, "ideal", "--project", self.pcell, "--spec", self.spec, "--ads")
        self.invoke(2, "search", "--run", ideal, "--approve-ideal", "--ads-source", self.ads_source)
        self.assertFalse((self.pcell / "results").exists())
        pcell = self.handoff(ideal, self.pcell, "--approve-ideal")
        self.invoke(2, "ideal", "--run", pcell, "--ads")
        self.search(pcell)
        self.invoke(2, "layout", "--run", pcell, "--candidate", "selected")
        self.invoke(2, "handoff", "--run", pcell, "--project", self.layout)
        self.invoke(2, "handoff", "--run", pcell, "--project", self.layout, "--candidate", "screen-only")
        self.assertFalse((self.layout / "results").exists())
        layout = self.handoff(pcell, self.layout, "--candidate", "selected")
        self.invoke(2, "layout", "--run", layout, "--candidate", "other")
        self.assertEqual(self.calls, ["ideal", "search"])

    def test_analytic_preview_cannot_be_handed_off(self):
        ideal = self.new_ideal()
        self.invoke(2, "handoff", "--run", ideal, "--project", self.pcell, "--approve-ideal")
        self.assertFalse((self.pcell / "results").exists())

    def test_rejects_tampered_frozen_ideal_result_before_search(self):
        ideal = self.new_ideal("--ads")
        pcell = self.handoff(ideal, self.pcell, "--approve-ideal")
        result = self.snapshot(pcell) / "result.json"
        result.write_bytes(result.read_bytes() + b" ")
        _, error = self.search(pcell, expected=2)
        self.assertIn("integrity", error)
        self.assertEqual(self.calls, ["ideal"])
        self.assertEqual(load_state(pcell)["state"], "search_pending")
        self.assertEqual(load_state(pcell)["attempts"]["search"], [])

    def test_rejects_tampered_native_cell_before_layout(self):
        ideal = self.new_ideal("--ads")
        pcell = self.handoff(ideal, self.pcell, "--approve-ideal")
        self.search(pcell)
        layout = self.handoff(pcell, self.layout, "--candidate", "selected")
        cell = self.snapshot(layout) / "ads" / "cell.oa"
        cell.write_bytes(CELL_BYTES + b"tampered")
        _, error = self.invoke(2, "layout", "--run", layout)
        self.assertIn("integrity", error)
        self.assertEqual(self.calls, ["ideal", "search"])
        self.assertEqual(load_state(layout)["state"], "layout_pending")
        self.assertEqual(load_state(layout)["attempts"]["layout"], [])


if __name__ == "__main__":
    unittest.main()
