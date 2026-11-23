"""Project identity and path-boundary checks for relocated engineering source."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from . import _bootstrap
except ImportError:
    import _bootstrap

import project_config


class ProjectConfigTests(unittest.TestCase):
    @contextmanager
    def project(self, *, task_id=project_config.TASK_ID, revision=1,
                schema_version=1, paths=None):
        with tempfile.TemporaryDirectory(prefix="adb-project-config-") as folder:
            root = Path(folder).resolve()
            self.assertTrue(root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
            values = {key: key for key in project_config.REQUIRED_PATHS}
            values.update({"ads": "ads/inp_lpf_nonideal_wrk",
                           "baseline": "inputs/baseline-r2",
                           "specification_snapshot": "inputs/task-spec",
                           "baseline_specification_snapshot": "inputs/baseline-r2/task-spec"})
            values.update(paths or {})
            content = [f"schema_version = {schema_version}", "", "[project]",
                       f"task_id = {json.dumps(task_id)}", f"revision = {revision}",
                       f"task_version_id = {json.dumps(task_id + '-r' + str(revision))}",
                       "", "[paths]"]
            content.extend(f"{key} = {json.dumps(value)}" for key, value in values.items())
            (root / "project.toml").write_text("\n".join(content) + "\n", encoding="utf-8")
            yield root, values

    def test_relative_paths_resolve_below_the_manifest_root(self):
        with self.project() as (root, values):
            config = project_config.load_project(root)
            self.assertEqual(config["project_root"], root)
            self.assertEqual(config["task_id"], project_config.TASK_ID)
            self.assertEqual(config["revision"], 1)
            self.assertEqual(set(config["paths"]), set(project_config.REQUIRED_PATHS))
            for key, value in values.items():
                self.assertEqual(config["paths"][key], (root / value).resolve())
                self.assertTrue(config["paths"][key].is_relative_to(root))

    def test_task_identity_revision_and_schema_mismatches_are_rejected(self):
        for change in ({"task_id": "another-task"}, {"revision": 2},
                       {"schema_version": 2}):
            with self.subTest(change=change), self.project(**change) as (root, _):
                with self.assertRaises(ValueError):
                    project_config.load_project(root)

    def test_absolute_and_traversing_paths_are_rejected(self):
        for path in ("/outside", "C:/outside", "C:outside", "../outside",
                     "ads/../../outside", ".", ""):
            with self.subTest(path=path), self.project(paths={"ads": path}) as (root, _):
                with self.assertRaises(ValueError):
                    project_config.load_project(root)

    def test_explicit_and_default_project_selection_ignore_the_current_directory(self):
        with self.project() as (root, _), self.project(task_id="wrong-cwd-task") as (other, _):
            previous = Path.cwd()
            try:
                os.chdir(other)
                explicit = project_config.load_project(root)
                with patch.object(project_config, "__file__", str(root / "tools/project_config.py")):
                    default = project_config.load_project()
            finally:
                os.chdir(previous)
            self.assertEqual(explicit["project_root"], root)
            self.assertEqual(default, explicit)


if __name__ == "__main__":
    unittest.main()
