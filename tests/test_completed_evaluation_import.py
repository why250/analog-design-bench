import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from import_completed_evaluation import import_completed_evaluation


class CompletedEvidenceImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "input"
        self.source.mkdir()
        self.circuit = self.source / "circuit.spi"
        self.circuit.write_bytes(b"* frozen\nR1 out 0 1000\n.end\n")
        self.reward = self.write("reward.json", {"reward": 1, "tests_total": 1, "tests_passed": 1})
        self.ctrf = self.write("ctrf.json", {"results": {
            "summary": {"tests": 1, "passed": 1, "failed": 0},
            "tests": [{"name": "electrical", "status": "passed"}]}})
        self.metadata_value = {
            "id": "existing-run-1", "taskVersionId": "nmos-r1",
            "modelConfigId": "exact-model-ultra", "protocolId": "official-2h-3",
            "attempt": 1, "mode": "blind",
            "startedAt": "2026-10-20T08:00:00Z", "endedAt": "2026-10-20T08:10:00Z",
            "provenance": {"requestedModel": "exact-model", "rootEffort": "ultra"},
            "circuitSha256": hashlib.sha256(self.circuit.read_bytes()).hexdigest(),
        }
        self.metadata = self.write("metadata.json", self.metadata_value)
        self.output = self.root / "imported"

    def write(self, name, value):
        path = self.source / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def call(self, **kwargs):
        values = dict(circuit=self.circuit, reward=self.reward, ctrf=self.ctrf,
                      metadata=self.metadata, out_directory=self.output)
        values.update(kwargs)
        return import_completed_evaluation(**values)

    def test_import_preserves_original_identity_bytes_and_missing_capture(self):
        trajectory = self.source / "trajectory.ndjson"
        trajectory.write_bytes(b'{"type":"raw","content":"public"}\r\n')
        usage = self.write("usage.json", {"input": 12, "cachedInput": 30, "output": 8})
        cost = self.write("cost.json", {"estimatedUsd": 0.0001, "actualUsd": None})
        result = self.call(trajectory=trajectory, usage=usage, cost=cost)
        run = json.loads((self.output / "record/run.json").read_text())
        self.assertEqual(run["id"], self.metadata_value["id"])
        self.assertEqual(run["attempt"], 1)
        self.assertEqual(run["startedAt"], self.metadata_value["startedAt"])
        self.assertTrue(run["importedFromCompletedEvidence"])
        self.assertEqual(run["provenance"], self.metadata_value["provenance"])
        for supplied, relative in [(self.circuit, "record/submitted-circuit.spi"),
                                   (self.reward, "verifier/verifier/reward.json"),
                                   (self.ctrf, "verifier/verifier/new-ctrf.json"),
                                   (trajectory, "record/trajectory.ndjson"),
                                   (usage, "record/usage.json"), (cost, "record/cost.json")]:
            self.assertEqual(supplied.read_bytes(), (self.output / relative).read_bytes())
        capture = json.loads((self.output / "record/initial-input.json").read_text())
        self.assertFalse(capture["captureComplete"])
        self.assertIsNone(capture["messages"])
        self.assertEqual(result["outcome"], "passed")

    def test_accepts_published_manifest_and_preserves_explicit_initial_input(self):
        self.metadata = self.write("manifest.json", {"schemaVersion": 1, "kind": "runs", "data": self.metadata_value})
        initial = self.write("initial.json", {"captureComplete": True, "messages": [{"role": "user", "content": "original"}]})
        self.call(initial_input=initial)
        self.assertEqual(initial.read_bytes(), (self.output / "record/initial-input.json").read_bytes())

    def test_missing_accounting_remains_unknown(self):
        self.call()
        usage = json.loads((self.output / "record/usage.json").read_text())
        cost = json.loads((self.output / "record/cost.json").read_text())
        self.assertIsNone(usage["input"])
        self.assertIsNone(cost["estimatedUsd"])
        self.assertIsNone(cost["actualUsd"])

    def test_no_model_identity_or_attempt_is_guessed(self):
        for key in ("id", "taskVersionId", "modelConfigId", "protocolId", "attempt", "mode", "startedAt", "provenance"):
            metadata = dict(self.metadata_value)
            del metadata[key]
            path = self.write(f"missing-{key}.json", metadata)
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.call(metadata=path)
        self.assertFalse(self.output.exists())

    def test_hash_mismatch_rejected_before_writing(self):
        metadata = dict(self.metadata_value, circuitSha256="a" * 64)
        with self.assertRaisesRegex(ValueError, "hash differs"):
            self.call(metadata=self.write("wrong-hash.json", metadata))
        self.assertFalse(self.output.exists())

    def test_existing_outputs_and_input_output_collisions_are_rejected(self):
        self.output.mkdir()
        (self.output / "keep.txt").write_text("keep")
        with self.assertRaisesRegex(ValueError, "empty"):
            self.call()
        self.assertEqual((self.output / "keep.txt").read_text(), "keep")
        with self.assertRaises(ValueError):
            self.call(out_directory=self.source)

    def test_invalid_or_reversed_timestamps_rejected(self):
        for start, end in [("2026-10-20T10:00:00", "2026-10-20T10:01:00Z"),
                           ("2026-10-20T10:00:00Z", "2026-10-20T09:00:00Z")]:
            value = dict(self.metadata_value, startedAt=start, endedAt=end)
            with self.assertRaises(ValueError):
                self.call(metadata=self.write("time.json", value))

    def test_symlink_input_rejected(self):
        linked = self.source / "linked.spi"
        try:
            linked.symlink_to(self.circuit)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable")
        with self.assertRaisesRegex(ValueError, "Linked"):
            self.call(circuit=linked)

    def test_export_archive_is_outside_input_and_never_overwritten(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            self.call(out_zip=self.output / "result.zip")
        archive = self.root / "existing.zip"
        archive.write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.call(out_zip=archive)
        self.assertEqual(archive.read_bytes(), b"keep")

    def test_export_preserves_bytes_and_does_not_include_unselected_sources(self):
        archive = self.root / "evidence.zip"
        (self.source / "private-session.jsonl").write_text("never select this")
        result = self.call(out_zip=archive)
        self.assertEqual(result["manifest"]["runId"], self.metadata_value["id"])
        with zipfile.ZipFile(archive) as bundle:
            manifest = json.loads(bundle.read("manifest.json"))
            self.assertEqual(manifest["kind"], "evaluation-evidence")
            self.assertTrue(manifest["reviewRequired"])
            self.assertEqual(bundle.read("record/submitted-circuit.spi"), self.circuit.read_bytes())
            self.assertEqual(bundle.read("verifier/verifier/reward.json"), self.reward.read_bytes())
            self.assertFalse(any("private-session" in name for name in bundle.namelist()))
            for item in manifest["files"]:
                payload = bundle.read(item["path"])
                self.assertEqual(hashlib.sha256(payload).hexdigest(), item["sha256"])
                self.assertEqual(len(payload), item["size"])

    def test_existing_cost_and_usage_are_never_renormalized(self):
        usage = self.write("usage.json", {"raw": {"threadScope": "root+child"}, "input": 0})
        cost = self.write("cost.json", {"estimatedUsd": 0, "actualUsd": 0, "notes": "measured"})
        with patch("evaluation_evidence.summarize_usage", side_effect=AssertionError("must preserve")), \
             patch("evaluation_evidence.estimate_cost", side_effect=AssertionError("must preserve")):
            self.call(usage=usage, cost=cost)
        self.assertEqual(cost.read_bytes(), (self.output / "record/cost.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
