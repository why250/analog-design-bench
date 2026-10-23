"""Offline tests for accounting, verification evidence and producer exports."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evaluation_evidence import (estimate_cost, evaluate_verifier, export_evidence,
                                 summarize_usage)


def report(statuses):
    return {"results": {
        "summary": {"tests": len(statuses), "passed": statuses.count("passed"),
                    "failed": statuses.count("failed")},
        "tests": [{"name": f"check-{i}", "status": status, "message": "measured"}
                  for i, status in enumerate(statuses)],
    }}


class UsageTests(unittest.TestCase):
    def test_cached_input_and_thinking_are_subsets(self):
        usage = summarize_usage([{"prompt_tokens": 100, "completion_tokens": 20,
                                  "total_tokens": 120,
                                  "prompt_tokens_details": {"cached_tokens": 60},
                                  "completion_tokens_details": {"reasoning_tokens": 12}}])
        self.assertEqual((usage["input"], usage["cacheRead"], usage["output"], usage["thinking"], usage["total"]),
                         (40, 60, 20, 12, 120))
        self.assertIsNone(usage["cacheWrite"])

    def test_prompt_detail_cache_write_tokens_are_separate(self):
        usage = summarize_usage([{"prompt_tokens": 100, "completion_tokens": 20,
                                  "prompt_tokens_details": {"cached_tokens": 60, "cache_write_tokens": 15},
                                  "completion_tokens_details": {"reasoning_tokens": 12}}])
        self.assertEqual((usage["input"], usage["cacheRead"], usage["cacheWrite"], usage["output"], usage["thinking"], usage["total"]),
                         (25, 60, 15, 20, 12, 120))

    def test_matching_cache_write_counters_are_not_double_counted(self):
        usage = summarize_usage([{"prompt_tokens": 100, "completion_tokens": 20,
                                  "cache_creation_input_tokens": 15,
                                  "prompt_tokens_details": {"cached_tokens": 60, "cache_write_tokens": 15}}])
        self.assertEqual((usage["input"], usage["cacheWrite"], usage["total"]), (25, 15, 120))

    def test_conflicting_cache_write_counters_are_unknown(self):
        usage = summarize_usage([{"prompt_tokens": 100, "completion_tokens": 20,
                                  "cache_creation_input_tokens": 25,
                                  "prompt_tokens_details": {"cached_tokens": 60, "cache_write_tokens": 15}}])
        self.assertIsNone(usage["input"])
        self.assertIsNone(usage["cacheWrite"])
        self.assertEqual(usage["cacheRead"], 60)
        self.assertFalse(usage["raw"]["unreportedCacheWriteIncludedInInput"])
        self.assertTrue(any("Conflicting cache-write" in value for value in usage["warnings"]))

    def test_invalid_explicit_cache_write_is_not_replaced_by_another_counter(self):
        usage = summarize_usage([{"prompt_tokens": 100, "completion_tokens": 20,
                                  "cache_creation_input_tokens": 25,
                                  "prompt_tokens_details": {"cached_tokens": 60, "cache_write_tokens": -1}}])
        self.assertIsNone(usage["input"])
        self.assertIsNone(usage["cacheWrite"])

    def test_unknown_response_makes_totals_unknown(self):
        usage = summarize_usage([{"prompt_tokens": 100, "completion_tokens": 20,
                                  "prompt_cache_hit_tokens": 0}, None])
        self.assertIsNone(usage["input"])
        self.assertIsNone(usage["total"])
        self.assertEqual(len(usage["raw"]["records"]), 2)
        self.assertTrue(usage["warnings"])

    def test_empty_counters_are_unknown(self):
        usage = summarize_usage([])
        self.assertTrue(all(usage[key] is None for key in ("input", "cacheRead", "cacheWrite", "output", "thinking", "total")))

    def test_deepseek_hit_miss_fields(self):
        usage = summarize_usage([{"prompt_tokens": 100, "prompt_cache_hit_tokens": 75,
                                  "prompt_cache_miss_tokens": 25, "completion_tokens": 12}])
        self.assertEqual((usage["input"], usage["cacheRead"], usage["total"]), (25, 75, 112))

    def test_deepseek_conflicting_miss_is_unknown(self):
        usage = summarize_usage([{"prompt_tokens": 100, "prompt_cache_hit_tokens": 75,
                                  "prompt_cache_miss_tokens": 35, "completion_tokens": 12}])
        self.assertIsNone(usage["input"])
        self.assertIsNone(usage["cacheRead"])
        self.assertTrue(any("disagree" in value for value in usage["warnings"]))

    def test_inconsistent_cached_counters_are_not_chosen(self):
        usage = summarize_usage([{"prompt_tokens": 100, "completion_tokens": 12,
                                  "prompt_cache_hit_tokens": 70,
                                  "prompt_tokens_details": {"cached_tokens": 60}}])
        self.assertIsNone(usage["input"])
        self.assertIsNone(usage["cacheRead"])

    def test_prompt_total_without_split_stays_unknown_input(self):
        usage = summarize_usage([{"prompt_tokens": 100, "completion_tokens": 12}])
        self.assertIsNone(usage["input"])
        self.assertIsNone(usage["cacheRead"])
        self.assertEqual(usage["total"], 112)

    def test_separate_anthropic_cache_categories(self):
        usage = summarize_usage([{"input_tokens": 30, "cache_read_input_tokens": 70,
                                  "cache_creation_input_tokens": 10, "output_tokens": 20}])
        self.assertEqual((usage["input"], usage["cacheRead"], usage["cacheWrite"], usage["total"]), (30, 70, 10, 130))
        self.assertIsNone(usage["thinking"])

    def test_partial_anthropic_counters_do_not_become_zero(self):
        usage = summarize_usage([{"input_tokens": 30, "output_tokens": 20}])
        self.assertEqual(usage["input"], 30)
        self.assertIsNone(usage["cacheRead"])
        self.assertIsNone(usage["total"])

    def test_reported_total_conflict_is_unknown(self):
        usage = summarize_usage([{"prompt_tokens": 100, "completion_tokens": 20,
                                  "total_tokens": 101, "prompt_cache_hit_tokens": 0}])
        self.assertIsNone(usage["total"])

    def test_invalid_and_excessive_thinking_not_accepted(self):
        usage = summarize_usage([{"prompt_tokens": -1, "completion_tokens": 20,
                                  "completion_tokens_details": {"reasoning_tokens": 50}}])
        self.assertIsNone(usage["input"])
        self.assertIsNone(usage["thinking"])

    def test_unrepresentable_counter_is_unknown(self):
        usage = summarize_usage([{"prompt_tokens": 10 ** 1000, "completion_tokens": 2}])
        self.assertIsNone(usage["input"])
        self.assertIsNone(usage["total"])

    def test_independent_records_are_summed_once(self):
        record = {"prompt_tokens": 100, "completion_tokens": 20, "prompt_cache_hit_tokens": 60}
        usage = summarize_usage([record, {"usage": record}])
        self.assertEqual(usage["total"], 240)
        self.assertEqual(usage["raw"]["recordCount"], 2)


class CostTests(unittest.TestCase):
    def setUp(self):
        self.pricing = {"currency": "USD", "date": "2026-10-21", "modelId": "example-model",
                        "rates": {"input": 2, "cacheRead": 0.2, "output": 10}}

    def test_explicit_rates_estimate_without_recharging_thinking(self):
        cost = estimate_cost({"input": 100, "cacheRead": 300, "output": 20,
                              "thinking": 15, "cacheWrite": None,
                              "raw": {"unreportedCacheWriteIncludedInInput": True}}, self.pricing)
        self.assertAlmostEqual(cost["estimatedUsd"], 0.00046)
        self.assertIsNone(cost["actualUsd"])
        self.assertEqual(cost["pricingDate"], "2026-10-21")

    def test_missing_price_is_unknown(self):
        cost = estimate_cost({"input": 100, "output": 20}, None)
        self.assertIsNone(cost["estimatedUsd"])
        self.assertIsNone(cost["ratesPerMillion"])

    def test_price_source_and_notes_are_retained(self):
        self.pricing["source"] = "https://example.com/dated-price-evidence"
        self.pricing["notes"] = ["Standard service tier.", "Context under stated threshold."]
        cost = estimate_cost({"input": 100, "cacheRead": 300, "cacheWrite": 0, "output": 20}, self.pricing)
        self.assertEqual(cost["source"], self.pricing["source"])
        self.assertTrue(all(note in cost["notes"] for note in self.pricing["notes"]))
        self.pricing["notes"] = "Single supplied assumption."
        self.assertIn(self.pricing["notes"], estimate_cost({}, self.pricing)["notes"])

    def test_explicit_prompt_cache_write_cost_is_counted_once(self):
        usage = summarize_usage([{"prompt_tokens": 100, "completion_tokens": 20,
                                  "prompt_tokens_details": {"cached_tokens": 60, "cache_write_tokens": 15},
                                  "completion_tokens_details": {"reasoning_tokens": 12}}])
        self.pricing["rates"]["cacheWrite"] = 3
        self.assertAlmostEqual(estimate_cost(usage, self.pricing)["estimatedUsd"], 0.000307)

    def test_missing_priced_counter_keeps_cost_unknown(self):
        cost = estimate_cost({"input": 100, "cacheRead": None, "output": 20}, self.pricing)
        self.assertIsNone(cost["estimatedUsd"])

    def test_unreported_writes_are_not_invented(self):
        self.pricing["rates"]["cacheWrite"] = 3
        cost = estimate_cost({"input": 100, "cacheRead": 300, "output": 20,
                              "cacheWrite": None}, self.pricing)
        self.assertIsNone(cost["estimatedUsd"])

    def test_separate_write_tokens_require_a_rate(self):
        for value in (None, 50):
            with self.subTest(cacheWrite=value):
                cost = estimate_cost({"input": 100, "cacheRead": 300, "output": 20,
                                      "cacheWrite": value}, self.pricing)
                self.assertIsNone(cost["estimatedUsd"])

    def test_zero_price_does_not_require_usage_for_that_category(self):
        self.pricing["rates"]["cacheWrite"] = 0
        cost = estimate_cost({"input": 100, "cacheRead": 300, "output": 20}, self.pricing)
        self.assertAlmostEqual(cost["estimatedUsd"], 0.00046)

    def test_undated_or_extra_reasoning_price_is_rejected(self):
        for field, value in (("date", "2026-99-10"), ("modelId", ""), ("currency", "EUR")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                estimate_cost({}, {**self.pricing, field: value})
        self.pricing["rates"]["thinking"] = 5
        with self.assertRaises(ValueError):
            estimate_cost({}, self.pricing)


class VerifierTests(unittest.TestCase):
    def test_complete_pass(self):
        result = evaluate_verifier({"reward": 1, "tests_total": 2, "tests_passed": 2}, report(["passed", "passed"]))
        self.assertEqual((result["outcome"], result["evidenceComplete"]), ("passed", True))

    def test_zero_reward_with_reports_is_complete_failure(self):
        result = evaluate_verifier({"reward": 0, "tests_total": 2, "tests_passed": 1, "partial": 0.5}, report(["passed", "failed"]))
        self.assertEqual((result["outcome"], result["reward"], result["evidenceComplete"]), ("failed", 0, True))

    def test_partial_reward_is_not_complete_pass(self):
        result = evaluate_verifier({"reward": 0.5}, report(["passed", "failed"]))
        self.assertEqual(result["outcome"], "failed")
        self.assertTrue(result["evidenceComplete"])

    def test_reward_without_check_evidence_is_incomplete(self):
        result = evaluate_verifier({"reward": 0}, None)
        self.assertEqual(result["outcome"], "incomplete")
        self.assertIs(result["evidenceComplete"], False)

    def test_exit_code_is_not_acceptance(self):
        result = evaluate_verifier({"reward": 0, "exit_code": 0}, report(["failed"]))
        self.assertEqual(result["outcome"], "failed")

    def test_inconsistent_summary_and_reward_counts_are_incomplete(self):
        ctrf = report(["passed", "failed"])
        ctrf["results"]["summary"]["passed"] = 2
        result = evaluate_verifier({"reward": 1, "tests_total": 3}, ctrf)
        self.assertEqual(result["outcome"], "incomplete")
        self.assertGreaterEqual(len(result["warnings"]), 3)

    def test_unknown_or_skipped_check_is_incomplete(self):
        self.assertFalse(evaluate_verifier({"reward": 0}, report(["skipped"]))["evidenceComplete"])


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.run = self.base / "run"
        (self.run / "record").mkdir(parents=True)
        (self.run / "verifier/verifier").mkdir(parents=True)
        self.circuit = b"* frozen circuit\n.end\n"
        (self.run / "record/submitted-circuit.spi").write_bytes(self.circuit)
        self.write_json("record/run.json", {"runId": "model-ldo-attempt-1"})
        self.write_json("record/result.json", {"candidate_sha256": hashlib.sha256(self.circuit).hexdigest(),
                                               "usage": []})
        self.write_json("record/initial-input.json", {"messages": [{"role": "user", "content": "Design the task."}]})
        self.write_json("verifier/verifier/reward.json", {"reward": 0, "tests_total": 1, "tests_passed": 0})
        self.write_json("verifier/verifier/new-ctrf.json", report(["failed"]))
        (self.run / "record/trajectory.jsonl").write_text('{"response":{"message":{"content":"Done"}}}\n', encoding="utf-8")
        (self.run / "record/response-001.jsonl").write_text('{"private":"raw stream"}\n', encoding="utf-8")
        (self.run / ".env").write_text("API_KEY=secret", encoding="utf-8")
        self.out = self.base / "run.evidence.zip"

    def write_json(self, relative, value):
        (self.run / relative).write_text(json.dumps(value), encoding="utf-8")

    def test_export_preserves_bytes_and_excludes_raw_streams_and_environment(self):
        manifest = export_evidence(self.run, self.out)
        self.assertTrue(manifest["reviewRequired"])
        self.assertEqual(manifest["kind"], "evaluation-evidence")
        self.assertEqual(manifest["verification"]["outcome"], "failed")
        with zipfile.ZipFile(self.out) as archive:
            names = set(archive.namelist())
            self.assertNotIn("record/response-001.jsonl", names)
            self.assertNotIn(".env", names)
            self.assertEqual(archive.read("record/submitted-circuit.spi"), self.circuit)
            for item in manifest["files"]:
                self.assertEqual(hashlib.sha256(archive.read(item["path"])).hexdigest(), item["sha256"])
            self.assertIsNone(json.loads(archive.read("record/cost.json"))["estimatedUsd"])

    def test_existing_archive_is_not_overwritten(self):
        self.out.write_bytes(b"retain these bytes")
        with self.assertRaises(FileExistsError):
            export_evidence(self.run, self.out)
        self.assertEqual(self.out.read_bytes(), b"retain these bytes")

    def test_assistant_reasoning_is_omitted_with_audit_without_changing_originals(self):
        source = self.run / "record/trajectory.jsonl"
        event = {"response": {"message": {"role": "assistant", "content": "Visible answer",
                 "reasoning_content": "private-text-placeholder", "reasoning": "private-alias-placeholder",
                 "reasoning_details": [{"type": "reasoning.encrypted", "data": "opaque-placeholder"}]}}}
        source.write_text(json.dumps(event) + "\n", encoding="utf-8")
        original = source.read_bytes()
        manifest = export_evidence(self.run, self.out)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(manifest["generatedReviewFiles"], ["reasoning-redactions.json"])
        with zipfile.ZipFile(self.out) as archive:
            public = archive.read("record/trajectory.jsonl")
            message = json.loads(public)["response"]["message"]
            self.assertEqual(message, {"role": "assistant", "content": "Visible answer"})
            for withheld in (b"private-text-placeholder", b"private-alias-placeholder", b"opaque-placeholder"):
                self.assertNotIn(withheld, b"".join(archive.read(name) for name in archive.namelist()))
            audit = json.loads(archive.read("reasoning-redactions.json"))["files"][0]
            self.assertEqual(audit["sourceSha256"], hashlib.sha256(original).hexdigest())
            self.assertEqual(audit["exportSha256"], hashlib.sha256(public).hexdigest())
            self.assertEqual(len(audit["removedFields"]), 3)

    def test_profile_report_locations_are_preserved_and_used_for_archive_verdict(self):
        (self.run / "verifier/custom").mkdir()
        self.write_json("record/task-profile.json", {"verifier": {
            "rewardPath": "custom/score.json", "ctrfPath": "custom/checks.json"}})
        self.write_json("verifier/custom/score.json", {"reward": 1})
        self.write_json("verifier/custom/checks.json", report(["passed"]))
        manifest = export_evidence(self.run, self.out)
        self.assertEqual(manifest["verification"]["outcome"], "passed")
        with zipfile.ZipFile(self.out) as archive:
            self.assertEqual(archive.read("verifier/custom/score.json"),
                             (self.run / "verifier/custom/score.json").read_bytes())
            self.assertIn("verifier/custom/checks.json", archive.namelist())

    def test_profile_report_paths_cannot_escape_the_attempt(self):
        self.write_json("record/task-profile.json", {"verifier": {
            "rewardPath": "../../outside.json", "ctrfPath": "verifier/new-ctrf.json"}})
        with self.assertRaisesRegex(ValueError, "escapes"):
            export_evidence(self.run, self.out)
        self.assertFalse(self.out.exists())

    def test_profile_cannot_export_private_requests_as_verifier_reports(self):
        (self.run / "record/requests").mkdir()
        self.write_json("record/requests/private.json", {"private": "must remain private"})
        self.write_json("record/task-profile.json", {"verifier": {
            "rewardPath": "../record/requests/private.json", "ctrfPath": "verifier/new-ctrf.json"}})
        with self.assertRaisesRegex(ValueError, "escapes"):
            export_evidence(self.run, self.out)
        self.assertFalse(self.out.exists())

    def test_credential_echo_blocks_export_without_mutating_originals(self):
        secret = "test-only-credential-abc123"
        source = self.run / "record/trajectory.jsonl"
        source.write_text(json.dumps({"response": {"message": {"content": secret}}}) + "\n", encoding="utf-8")
        original = source.read_bytes()
        with self.assertRaises(ValueError) as error:
            export_evidence(self.run, self.out, forbidden_values=[secret])
        self.assertNotIn(secret, str(error.exception))
        self.assertFalse(self.out.exists())
        self.assertEqual(source.read_bytes(), original)

    def test_json_escaped_credentials_are_also_blocked(self):
        secret = 'test-token-"quoted"\\value'
        self.write_json("record/initial-input.json", {"captureComplete": True, "request": {"content": secret}})
        with self.assertRaisesRegex(ValueError, "forbidden credential"):
            export_evidence(self.run, self.out, forbidden_values=[secret])
        self.assertFalse(self.out.exists())

    def test_manifest_bytes_are_checked_before_archive_creation(self):
        with self.assertRaisesRegex(ValueError, "forbidden credential"):
            export_evidence(self.run, self.out, forbidden_values=[b"evaluation-evidence"])
        self.assertFalse(self.out.exists())

    def test_private_unselected_records_are_not_scanned(self):
        secret = "test-only-credential-abc123"
        (self.run / "record/response-001.jsonl").write_text(secret, encoding="utf-8")
        (self.run / ".env").write_text(secret, encoding="utf-8")
        manifest = export_evidence(self.run, self.out, forbidden_values=[secret])
        self.assertTrue(manifest["reviewRequired"])
        self.assertTrue(self.out.is_file())

    def test_missing_initial_capture_is_rejected(self):
        (self.run / "record/initial-input.json").unlink()
        with self.assertRaisesRegex(ValueError, "initial-input"):
            export_evidence(self.run, self.out)
        self.assertFalse(self.out.exists())

    def test_legacy_capture_gaps_remain_explicit(self):
        self.write_json("record/initial-input.json", {"captureComplete": False, "messages": None,
                                                     "limitations": ["Historical actual input is unavailable."]})
        self.write_json("record/run.json", {"runId": "legacy-attempt", "importLimitations": ["Capture was imported after execution."]})
        manifest = export_evidence(self.run, self.out)
        self.assertIs(manifest["initialInputCaptureComplete"], False)
        self.assertIn("Historical actual input is unavailable.", manifest["warnings"])
        self.assertIn("Capture was imported after execution.", manifest["warnings"])

    def test_corrupt_submission_is_rejected(self):
        (self.run / "record/submitted-circuit.spi").write_bytes(b"changed bytes")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            export_evidence(self.run, self.out)

    def test_normalized_ndjson_is_supported(self):
        (self.run / "record/trajectory.jsonl").unlink()
        (self.run / "record/trajectory.ndjson").write_text('{"type":"raw"}\n', encoding="utf-8")
        manifest = export_evidence(self.run, self.out)
        self.assertIn("record/trajectory.ndjson", [entry["path"] for entry in manifest["files"]])

    def test_full_tool_logs_and_capture_audit_are_included(self):
        (self.run / "record/tool-output").mkdir()
        (self.run / "record/tool-output/0001.log").write_bytes(b"complete tool output\n")
        (self.run / "record/tool-output/credentials.txt").write_text("not a log", encoding="utf-8")
        self.write_json("record/source-manifest.json", {"files": []})
        self.write_json("record/capture-report.json", {"complete": True})
        manifest = export_evidence(self.run, self.out)
        paths = [item["path"] for item in manifest["files"]]
        self.assertIn("record/tool-output/0001.log", paths)
        self.assertIn("record/source-manifest.json", paths)
        self.assertIn("record/capture-report.json", paths)
        self.assertNotIn("record/tool-output/credentials.txt", paths)

    def test_link_detection_rejects_selected_evidence(self):
        with mock.patch.object(Path, "is_symlink", lambda path: path.name == "submitted-circuit.spi"):
            with self.assertRaisesRegex(ValueError, "Linked"):
                export_evidence(self.run, self.out)

    def test_symlink_evidence_cannot_escape_allowlist(self):
        source = self.run / "record/submitted-circuit.spi"
        outside = self.base / "private.spi"
        outside.write_bytes(self.circuit)
        source.unlink()
        try:
            source.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"Creating a symlink is unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "Linked"):
            export_evidence(self.run, self.out)

    def test_bad_json_is_rejected(self):
        (self.run / "record/run.json").write_text("broken JSON", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "JSON"):
            export_evidence(self.run, self.out)


if __name__ == "__main__":
    unittest.main()
