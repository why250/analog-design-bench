"""Offline task-profile contract checks; no Docker or model access."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import benchmark_tasks as tasks


REPO = Path(__file__).resolve().parents[1]


class TaskProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.profile = json.loads((REPO / "evaluation/tasks" / (tasks.DEFAULT_TASK + ".json")).read_text(encoding="utf-8"))
        self.profile.update(taskId="synthetic-task", revision=2, taskVersionId="synthetic-task-r2")
        self.profile_path = self.repo / "evaluation/tasks/synthetic-task.json"
        self.task_root = self.repo / "tasks/synthetic-task"
        self.write("tasks/synthetic-task/instruction.md", "Public task instruction")
        self.write("tasks/synthetic-task/task.toml", 'artifacts = ["/app/circuit.spi"]\n[metadata]\ntask_id = "synthetic-task"\nrevision = 2\n')
        self.write("tasks/synthetic-task/environment/Dockerfile", "FROM pinned-base\nCOPY starter /app\n")
        for name, content in {
            "circuit.spi": "* clean starter\n",
            "SKY130_NETLIST_GUIDE.md": "Public netlist guide",
            "testbench/tb_nominal.spi": "* Public bench\n",
            "Dockerfile": "excluded",
            ".DS_Store": "excluded",
            "._noise": "excluded",
        }.items():
            self.write("tasks/synthetic-task/environment/starter/" + name, content)
        for name in ("Dockerfile", "test.sh", "verify.py", "utils.py", "benches/point.spi"):
            self.write("tasks/synthetic-task/tests/" + name, "# original fixture\n")
        self.save_profile()

    def write(self, relative, content):
        target = self.repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def save_profile(self):
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(json.dumps(self.profile), encoding="utf-8")

    def load(self):
        return tasks.load_task(self.repo, "synthetic-task")

    def test_two_real_profiles_have_explicit_original_revision_and_sources(self):
        registered = tasks.list_tasks(REPO)
        self.assertEqual(len(registered), 2)
        expected = {tasks.DEFAULT_TASK: (1, 3), "sky130-ota-5t-gain40-pm60-noise50uv-pvt": (3, 6)}
        for task_id, (revision, files) in expected.items():
            with self.subTest(task_id=task_id):
                task = tasks.load_task(REPO, task_id)
                tasks.validate_task_sources(REPO, task)
                self.assertEqual(task["revision"], revision)
                self.assertEqual(task["taskVersionId"], f"{task_id}-r{revision}")
                self.assertEqual(len(tasks.mapped_sources(REPO, task, "development")), files)
                self.assertIn("/tests/test.sh", tasks.mapped_sources(REPO, task, "verifier"))
                self.assertEqual(task["verifier"]["checkerCommand"], ["/opt/analog-arena/check_circuit.py", "/app/circuit.spi"])
        self.assertEqual(tasks.load_task(REPO)["taskId"], tasks.DEFAULT_TASK)

    def test_registered_selection_and_explicit_profile_return_hash_identity(self):
        registered = self.load()
        explicit = tasks.load_task(self.repo, self.profile_path)
        self.assertEqual(explicit, registered)
        self.assertEqual(registered["profilePath"], "evaluation/tasks/synthetic-task.json")
        self.assertEqual(registered["profileSha256"], hashlib.sha256(self.profile_path.read_bytes()).hexdigest())
        self.assertEqual(registered["taskDirectory"], "tasks/synthetic-task")
        self.assertEqual(tasks.validate_task_sources(self.repo, registered), registered)

    def test_mapping_excludes_metadata_and_preserves_original_paths(self):
        task = self.load()
        mapping = tasks.mapped_sources(self.repo, task, "development")
        self.assertEqual(set(mapping), {"/app/circuit.spi", "/app/SKY130_NETLIST_GUIDE.md", "/app/testbench/tb_nominal.spi"})
        self.assertEqual(mapping["/app/circuit.spi"], "tasks/synthetic-task/environment/starter/circuit.spi")
        self.assertEqual(mapping, tasks.mapped_sources(self.repo, task, "solver"))
        with self.assertRaises(ValueError):
            tasks.mapped_sources(self.repo, task, "unknown")

    def test_contract_cannot_omit_or_change_revision_id_or_artifact(self):
        cases = [
            'artifacts=["/app/circuit.spi"]\n[metadata]\ntask_id="synthetic-task"\n',
            'artifacts=["/app/circuit.spi"]\n[metadata]\ntask_id="synthetic-task"\nrevision=1\n',
            'artifacts=["/app/circuit.spi"]\n[metadata]\ntask_id="another-task"\nrevision=2\n',
            'artifacts=["/app/other.spi"]\n[metadata]\ntask_id="synthetic-task"\nrevision=2\n',
            'artifacts=["/app/circuit.spi", "/app/extra.spi"]\n[metadata]\ntask_id="synthetic-task"\nrevision=2\n',
        ]
        for contract in cases:
            with self.subTest(contract=contract), self.assertRaises(ValueError):
                tasks.validate_task_sources(self.repo, self.load(), read_source=lambda _: contract)

    def test_custom_plaintext_reader_reads_the_selected_contract(self):
        paths = []
        def reader(relative):
            paths.append(relative)
            return (self.repo / relative).read_text(encoding="utf-8"), "selected-reader"
        tasks.validate_task_sources(self.repo, self.load(), reader)
        self.assertEqual(paths, ["tasks/synthetic-task/task.toml"])

    def test_bad_schema_identity_and_credentials_are_rejected(self):
        for update in ({"schemaVersion": 2}, {"revision": True}, {"revision": 0}, {"taskVersionId": "wrong-r1"},
                       {"taskId": "../other"}, {"api_key": "never-a-real-key"}):
            with self.subTest(update=update):
                original = copy.deepcopy(self.profile)
                self.profile.update(update)
                self.save_profile()
                with self.assertRaises(ValueError):
                    self.load()
                self.profile = original
        self.save_profile()

    def test_bad_relative_container_report_image_and_command_paths_are_rejected(self):
        mutations = [
            lambda p: p.update(instruction="../instruction.md"),
            lambda p: p.update(contract="/tmp/task.toml"),
            lambda p: p.update(artifact="circuit.spi"),
            lambda p: p.update(artifact="/tmp/circuit.spi"),
            lambda p: p.update(artifact="/app/../circuit.spi"),
            lambda p: p["verifier"].update(rewardPath="../../reward.json"),
            lambda p: p["verifier"].update(ctrfPath="/tmp/report.json"),
            lambda p: p["solver"].update(image="--privileged"),
            lambda p: p["solver"].update(image="https://user:secret@host/image"),
            lambda p: p["verifier"].update(command=[]),
            lambda p: p["verifier"].update(checkerCommand=["--invalid"]),
            lambda p: p["solver"].update(publicFiles=["/app/circuit.spi"]),
            lambda p: p["solver"]["sourceMappings"][0].update(target="/app/../tests"),
            lambda p: p["solver"]["sourceMappings"][0].update(source="../solution"),
        ]
        for mutate in mutations:
            original = copy.deepcopy(self.profile)
            mutate(self.profile)
            self.save_profile()
            with self.subTest(profile=self.profile), self.assertRaises(ValueError):
                self.load()
            self.profile = original
        self.save_profile()

    def test_profile_cannot_be_in_starter_or_outside_repository(self):
        self.write("tasks/synthetic-task/environment/starter/operator.json", json.dumps(self.profile))
        with self.assertRaisesRegex(ValueError, "outside solver"):
            tasks.load_task(self.repo, "tasks/synthetic-task/environment/starter/operator.json")
        with self.assertRaises(ValueError):
            tasks.load_task(self.repo, self.repo.parent / "outside.json")
        with self.assertRaises(ValueError):
            tasks.load_task(self.repo, "evaluation/tasks/../../outside.json")

    def test_unmapped_public_file_and_source_overlap_are_rejected(self):
        task = self.load()
        task["solver"]["publicFiles"].append("/app/not-present.md")
        with self.assertRaisesRegex(ValueError, "Every immutable"):
            tasks.validate_task_sources(self.repo, task)
        task = self.load()
        task["verifier"]["sourceMappings"].append({"source": "environment/starter/circuit.spi", "target": "/hidden/circuit.spi"})
        with self.assertRaisesRegex(ValueError, "disjoint"):
            tasks.validate_task_sources(self.repo, task)

    def test_solver_cannot_map_hidden_sources_even_if_public_list_is_adjusted(self):
        task = self.load()
        task["solver"]["sourceMappings"].append({"source": "tests/verify.py", "target": "/app/helper.py"})
        task["verifier"]["sourceMappings"] = [{"source": "tests/test.sh", "target": "/tests/test.sh"}]
        with self.assertRaisesRegex(ValueError, "permitted starter"):
            tasks.validate_task_sources(self.repo, task)

    def test_overlapping_targets_missing_files_and_registered_filename_mismatch(self):
        task = self.load()
        task["solver"]["sourceMappings"].append({"source": "environment/starter/circuit.spi", "target": "/app/circuit.spi"})
        with self.assertRaisesRegex(ValueError, "overlap"):
            tasks.mapped_sources(self.repo, task, "development")
        task = self.load()
        task["verifier"]["sourceMappings"][0]["source"] = "tests/missing.sh"
        with self.assertRaisesRegex(ValueError, "does not exist"):
            tasks.validate_task_sources(self.repo, task)
        self.profile["taskId"] = "other-task"
        self.profile["taskVersionId"] = "other-task-r2"
        self.save_profile()
        with self.assertRaisesRegex(ValueError, "filename"):
            self.load()

    def test_linked_source_and_profile_are_rejected_when_supported(self):
        target = self.repo / "ordinary.txt"
        target.write_text("ordinary", encoding="utf-8")
        linked = self.task_root / "environment/starter/linked.txt"
        try:
            linked.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Creating a symlink is unavailable on this host.")
        with self.assertRaisesRegex(ValueError, "linked path"):
            tasks.mapped_sources(self.repo, self.load(), "development")


if __name__ == "__main__":
    unittest.main()
