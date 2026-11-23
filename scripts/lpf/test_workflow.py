"""Exercise stage boundaries without acquiring an ADS license."""

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from .geometry import propose_geometries
from .specification import load_spec
from .workflow import DEFAULT_PROJECT, load_state, main


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.project = Path(directory.name)
        self.spec = DEFAULT_PROJECT / "inputs" / "lpf-65-80.toml"
        self.profile = self.project / "profile.toml"
        self.profile.write_text("schema_version = 1\n", encoding="utf-8")
        self.calls = []

        def ideal(spec, out, workspace):
            self.calls.append("ideal")
            return {"passed": True, "verification": "ads" if workspace else "analytic",
                    "design": {"order": 9, "elements": []}}

        def search(spec, design, profile, out, **kwargs):
            self.calls.append("search")
            workspace = out / "candidate_wrk"
            workspace.mkdir()
            point = {"value_db": -21.0, "limit_db": -20.0, "frequency_hz": 65e9}
            metrics = {"s11_worst": point, "s22_worst": point, "il_worst": {
                "value_db": 3.0, "limit_db": None, "frequency_hz": 65e9,
            }, "stopbands": [point]}
            return {"candidates": [
                {"id": "selected", "passes": True, "verification": "ads",
                 "ads_workspace": workspace.name, "model_status": "conditional", "metrics": metrics},
                {"id": "near-miss", "passes": False, "verification": "ads",
                 "ads_workspace": workspace.name, "model_status": "qualified", "metrics": metrics},
                {"id": "incomplete", "passes": True, "verification": "ads",
                 "ads_workspace": workspace.name, "model_status": "incomplete", "metrics": metrics},
            ]}

        def layout(candidate, profile, out, *, ads_workspace):
            self.calls.append("layout")
            self.assertTrue(ads_workspace.is_dir())
            return {"verified": True, "candidate": candidate["id"]}

        stubs = {
            "scripts.lpf.ideal": SimpleNamespace(run_ideal=ideal),
            "scripts.lpf.search": SimpleNamespace(run_search=search),
            "scripts.lpf.ads_layout": SimpleNamespace(build_layout=layout),
        }
        modules = patch.dict(sys.modules, stubs)
        modules.start()
        self.addCleanup(modules.stop)

    def invoke(self, *arguments):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return main([str(argument) for argument in arguments])

    def new_run(self, *flags):
        self.assertEqual(self.invoke("ideal", "--project", self.project, "--spec", self.spec, *flags), 0)
        return next((self.project / "results").iterdir())

    def search(self, run, *flags):
        return self.invoke("search", "--run", run, "--profile", self.profile,
                           "--ads-source", self.project, *flags)

    def test_both_reviews_are_explicit_and_recoverable(self):
        run = self.new_run("--ads")
        self.assertEqual(load_state(run)["state"], "review_ideal")
        self.assertEqual(self.calls, ["ideal"])
        self.assertEqual(self.search(run), 2)
        self.assertEqual(self.invoke("layout", "--run", run, "--candidate", "selected"), 2)
        self.assertEqual(self.search(run, "--approve-ideal"), 0)
        self.assertEqual(load_state(run)["state"], "review_pcell")
        search_path = load_state(run)["attempts"]["search"][-1]["path"]
        self.assertIn("Report only", (run / search_path / "review.md").read_text(encoding="utf-8"))
        self.assertEqual(self.calls, ["ideal", "search"])
        self.assertEqual(self.search(run), 0)
        self.assertEqual(self.invoke("layout", "--run", run, "--candidate", "selected"), 0)
        self.assertEqual(load_state(run)["state"], "layout_ready")
        self.assertEqual(self.calls, ["ideal", "search", "search", "layout"])

    def test_analytic_preview_does_not_unlock_search(self):
        run = self.new_run()
        self.assertEqual(load_state(run)["state"], "ideal_pending")
        self.assertEqual(self.search(run, "--approve-ideal"), 2)
        self.assertEqual(self.invoke("ideal", "--run", run, "--ads"), 0)
        self.assertEqual(load_state(run)["state"], "review_ideal")
        self.assertEqual(len(load_state(run)["attempts"]["ideal"]), 2)

    def test_near_miss_requires_selection_and_incomplete_is_rejected(self):
        run = self.new_run("--ads")
        self.assertEqual(self.search(run, "--approve-ideal"), 0)
        layout = ("layout", "--run", run, "--candidate")
        self.assertEqual(self.invoke(*layout, "incomplete", "--accept-near-miss"), 2)
        self.assertEqual(self.invoke(*layout, "near-miss"), 2)
        self.assertEqual(self.invoke(*layout, "near-miss", "--accept-near-miss"), 0)
        self.assertTrue(load_state(run)["layout_selection"]["accepted_near_miss"])

    def test_frozen_spec_cannot_be_edited_in_place(self):
        run = self.new_run("--ads")
        frozen = run / "spec.toml"
        frozen.write_bytes(frozen.read_bytes() + b"\n# amended\n")
        self.assertEqual(self.search(run, "--approve-ideal"), 2)
        self.assertEqual(load_state(run)["state"], "review_ideal")

    def test_layout_requires_the_profile_used_by_search(self):
        run = self.new_run("--ads")
        self.assertEqual(self.search(run, "--approve-ideal"), 0)
        attempt = load_state(run)["attempts"]["search"][-1]["path"]
        frozen = run / attempt / "profile.toml"
        frozen.write_bytes(frozen.read_bytes() + b"\n# amended\n")
        self.assertEqual(self.invoke("layout", "--run", run, "--candidate", "selected"), 2)
        self.assertEqual(load_state(run)["state"], "review_pcell")

    def test_revision_keeps_previous_run_and_revalidates_ideal(self):
        run = self.new_run("--ads")
        other = DEFAULT_PROJECT / "inputs" / "lpf-50-75.toml"
        self.assertEqual(self.invoke("ideal", "--spec", other, "--project", self.project,
                                     "--revise", run), 0)
        revised, = set((self.project / "results").iterdir()) - {run}
        self.assertEqual(load_state(revised)["previous_run"], str(run))
        self.assertEqual(load_state(revised)["state"], "ideal_pending")
        self.assertEqual(load_state(run)["state"], "review_ideal")


class SpecificationTests(unittest.TestCase):
    def test_stop_checkpoint_must_be_above_edge(self):
        with TemporaryDirectory() as directory:
            source = DEFAULT_PROJECT / "inputs" / "lpf-65-80.toml"
            bad = Path(directory) / "bad.toml"
            bad.write_text(source.read_text().replace("80e9", "65e9"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "above the passband edge"):
                load_spec(bad)

    def test_il_policy_is_explicit(self):
        with TemporaryDirectory() as directory:
            source = DEFAULT_PROJECT / "inputs" / "lpf-65-80.toml"
            self.assertIsNone(load_spec(source)["insertion_loss_max_db"])
            limited = Path(directory) / "limited.toml"
            text = source.read_text().replace('mode = "report_only"', 'mode = "limit"\nmax_db = 1.0')
            limited.write_text(text, encoding="utf-8")
            self.assertEqual(load_spec(limited)["insertion_loss_max_db"], 1.0)

    def test_extraction_proposals_preserve_fixed_geometry_and_skip_cached_sizes(self):
        profile = {"devices": {"L": {
            "variables": ["diameter"], "fixed_parameters": {"gap": 10.0},
            "proposal_steps_um": {"diameter": 1.0},
            "proposal_bounds_um": {"diameter": [15.0, 30.0]},
        }}}
        design = {"elements": [{"kind": "L", "value": 110e-12}]}
        choices = {"L": [
            {"parameters": {"diameter": 20.0, "gap": 10.0}, "effective_value": 100e-12},
            {"parameters": {"diameter": 21.0, "gap": 10.0}, "effective_value": 105e-12},
        ]}
        proposed = propose_geometries(design, profile, choices, 1)
        self.assertEqual(proposed, [{"kind": "L", "parameters": {"diameter": 22.0, "gap": 10.0}}])


if __name__ == "__main__":
    unittest.main()
