"""Offline acceptance tests for provider streaming and completion semantics."""

import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import chat_completions as adapter


class Stream(io.BytesIO):
    headers = {"Content-Type": "text/event-stream; charset=utf-8"}


def event(value):
    return ("data: " + json.dumps(value) + "\n\n").encode()


def choice(delta=None, finish=None, **extra):
    return {"choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish, **extra}]}


DONE = b"data: [DONE]\n\n"


class AdapterTests(unittest.TestCase):
    body = {"model": "requested", "reasoning_effort": "max", "stream": True,
            "messages": [{"role": "user", "content": "Test"}]}

    def run_stream(self, raw, **kwargs):
        with mock.patch.object(adapter.urllib.request, "urlopen", return_value=Stream(raw)):
            return adapter.complete(copy.deepcopy(self.body), base_url="https://relay.invalid/v1",
                                    key="not-a-real-key", **kwargs)

    def test_normal_final_and_exact_request_capture(self):
        captured, requests = [], []
        raw = event({"id": "r1", "model": "returned", "provider": "provider", **choice({"content": "Done"}, "stop", native_finish_reason="stop")}) + DONE
        result = self.run_stream(raw, on_chunk=captured.append, on_request=requests.append)
        self.assertEqual(result["message"]["content"], "Done")
        self.assertEqual(result["response_model"], "returned")
        self.assertEqual(result["provider"], "provider")
        self.assertEqual(result["response_id"], "r1")
        self.assertEqual(result["native_finish_reason"], "stop")
        self.assertTrue(result["transport"]["doneReceived"])
        self.assertFalse(result["transport"]["eofReceived"])
        self.assertEqual(captured[-1]["_capture"]["type"], "sse_done")
        self.assertEqual(requests, [self.body])
        self.assertNotIn("Authorization", json.dumps(requests))

    def test_observed_reasoning_only_done_without_finish_is_protocol_error(self):
        captured = []
        raw = event(choice({"reasoning": "synthetic reasoning", "content": None,
                            "reasoning_details": [{"type": "reasoning.text", "text": "synthetic reasoning"}]})) + event({"choices": [], "usage": {"completion_tokens": 20}}) + DONE
        with self.assertRaises(adapter.AdapterError) as caught:
            self.run_stream(raw, on_chunk=captured.append)
        error = caught.exception
        self.assertEqual(error.kind, "protocol_error")
        self.assertIsNone(error.response["finish_reason"])
        self.assertEqual(error.response["usage"], {"completion_tokens": 20})
        self.assertTrue(error.response["transport"]["doneReceived"])
        self.assertEqual(error.response["message"]["reasoning_content"], "synthetic reasoning")
        self.assertIsNone(error.response["message"]["content"])
        self.assertEqual(captured[-1]["_capture"]["type"], "sse_done")

    def test_empty_stop_cannot_be_normal_completion(self):
        for content in (None, "", "   "):
            with self.subTest(content=content), self.assertRaises(adapter.AdapterError) as caught:
                self.run_stream(event(choice({"content": content, "reasoning_content": "thinking"}, "stop")) + DONE)
            self.assertEqual(caught.exception.kind, "protocol_error")

    def test_truncated_without_done_or_finish_retains_partial_response(self):
        raw = event(choice({"content": "partial"}))
        with self.assertRaisesRegex(adapter.AdapterError, "Incomplete API stream") as caught:
            self.run_stream(raw)
        self.assertTrue(caught.exception.response["transport"]["eofReceived"])
        self.assertFalse(caught.exception.response["transport"]["doneReceived"])
        self.assertEqual(caught.exception.response["message"]["content"], "partial")

    def test_explicit_finish_at_eof_is_distinct_from_done_marker(self):
        result = self.run_stream(event(choice({"content": "Done"}, "stop")))
        self.assertTrue(result["transport"]["eofReceived"])
        self.assertFalse(result["transport"]["doneReceived"])

    def test_tool_calls_reassemble_and_keep_one_trailing_usage(self):
        raw = b"".join([
            event(choice({"tool_calls": [{"index": 0, "id": "call-1", "type": "function",
                                          "function": {"name": "she", "arguments": '{"command":'}}]})),
            event(choice({"tool_calls": [{"index": 0, "function": {"name": "ll", "arguments": '"true"}'}}]}, "tool_calls")),
            event({"choices": [], "usage": {"prompt_tokens": 20, "completion_tokens": 5}}), DONE])
        result = self.run_stream(raw)
        self.assertEqual(result["usage"], {"prompt_tokens": 20, "completion_tokens": 5})
        self.assertEqual(result["message"]["tool_calls"], [{"id": "call-1", "type": "function",
                         "function": {"name": "shell", "arguments": '{"command":"true"}'}}])
        self.assertEqual(result["transport"]["eventCount"], 3)

    def test_repeated_finish_in_accounting_frame_is_not_a_second_response(self):
        raw = event(choice({"content": "Done"}, "stop")) + event({"usage": {"total_tokens": 12}, **choice({}, "stop")}) + DONE
        result = self.run_stream(raw)
        self.assertEqual(result["message"]["content"], "Done")
        self.assertEqual(result["usage"]["total_tokens"], 12)

    def test_length_stop_retains_incomplete_tool_arguments_without_execution(self):
        raw = event(choice({"tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "shell", "arguments": '{"command":'}}]}, "length")) + DONE
        result = self.run_stream(raw)
        self.assertEqual(result["finish_reason"], "length")
        self.assertEqual(result["message"]["tool_calls"][0]["function"]["arguments"], '{"command":')

    def test_invalid_tool_arguments_and_inconsistent_finishes_are_rejected(self):
        cases = [
            ("tool_calls", []),
            ("tool_calls", [{"id": "c", "type": "function", "function": {"name": "shell", "arguments": "[]"}}]),
            ("tool_calls", [{"id": "c", "type": "function", "function": {"name": "shell", "arguments": "{"}}]),
            ("tool_calls", [{"id": "", "type": "function", "function": {"name": "shell", "arguments": "{}"}}]),
            ("stop", [{"id": "c", "type": "function", "function": {"name": "shell", "arguments": "{}"}}]),
        ]
        for finish, calls in cases:
            with self.subTest(finish=finish, calls=calls), self.assertRaises(adapter.AdapterError):
                adapter.validate_response({"finish_reason": finish, "message": {"content": "Done", "tool_calls": calls}})

    def test_duplicate_tool_ids_and_changed_stream_id_are_rejected(self):
        calls = [{"id": "c", "type": "function", "function": {"name": "shell", "arguments": "{}"}}] * 2
        with self.assertRaises(adapter.AdapterError):
            adapter.validate_response({"finish_reason": "tool_calls", "message": {"tool_calls": calls}})
        raw = event(choice({"tool_calls": [{"index": 0, "id": "first"}]})) + event(choice({"tool_calls": [{"index": 0, "id": "different"}]}))
        with self.assertRaisesRegex(adapter.AdapterError, "identifier changed"):
            self.run_stream(raw)

    def test_reasoning_aliases_use_precedence_instead_of_double_counting(self):
        details = [{"type": "reasoning.text", "text": "detail copy", "index": 0},
                   {"type": "reasoning.encrypted", "data": "opaque-test-payload", "index": 1}]
        raw = event(choice({"reasoning_content": "preferred", "reasoning": "alias copy", "reasoning_details": details})) + event(choice({"content": "Done"}, "stop")) + DONE
        result = self.run_stream(raw)
        self.assertEqual(result["message"]["reasoning_content"], "preferred")
        self.assertEqual(result["reasoning_source"], "reasoning_content")
        self.assertEqual(result["message"]["reasoning_details"], details)

    def test_alternate_reasoning_and_text_details_are_captured_separately(self):
        for delta, source in [({"reasoning": "thought"}, "reasoning"),
                              ({"reasoning_details": [{"type": "reasoning.text", "text": "thought"}]}, "reasoning_details.text")]:
            with self.subTest(source=source):
                result = self.run_stream(event(choice(delta)) + event(choice({"content": "Done"}, "stop")) + DONE)
                self.assertEqual(result["reasoning_source"], source)
                self.assertEqual(result["message"]["reasoning_content"], "thought")
                self.assertEqual(result["message"]["content"], "Done")

    def test_encrypted_details_remain_opaque_and_are_not_reasoning_text(self):
        details = [{"type": "reasoning.encrypted", "data": "opaque-test-payload"}]
        result = self.run_stream(event(choice({"reasoning_details": details})) + event(choice({"content": "Done"}, "stop")) + DONE)
        self.assertEqual(result["message"]["reasoning_content"], "")
        self.assertEqual(result["message"]["reasoning_details"], details)
        self.assertNotIn("reasoning_source", result)

    def test_midstream_error_event_is_captured_before_failure_with_usage(self):
        captured = []
        raw = event({"model": "actual", "usage": {"completion_tokens": 3},
                     "error": {"code": 503, "message": "synthetic failure"}, **choice({}, "error")})
        with self.assertRaises(adapter.AdapterError) as caught:
            self.run_stream(raw, on_chunk=captured.append)
        self.assertEqual(caught.exception.kind, "api_error")
        self.assertEqual(caught.exception.response["usage"], {"completion_tokens": 3})
        self.assertEqual(caught.exception.response["finish_reason"], "error")
        self.assertTrue(caught.exception.response["transport"]["errorEventReceived"])
        self.assertEqual(captured[0]["error"]["code"], 503)

    def test_error_finish_without_error_body_is_not_success(self):
        for finish in ("error", "content_filter"):
            with self.subTest(finish=finish), self.assertRaises(adapter.AdapterError) as caught:
                self.run_stream(event(choice({}, finish)) + DONE)
            self.assertEqual(caught.exception.kind, "api_error")

    def test_malformed_json_is_retained_as_namespaced_capture_record(self):
        captured = []
        with self.assertRaises(adapter.AdapterError):
            self.run_stream(b"data: {broken\n\n", on_chunk=captured.append)
        self.assertEqual(captured[0]["_capture"]["type"], "invalid_sse_data")
        self.assertEqual(captured[0]["_capture"]["data"], "{broken")

    def test_multiline_data_comments_and_final_payload_without_blank_line(self):
        raw = b': heartbeat\n\ndata: {"choices":\ndata: [{"index":0,"delta":{"content":"Done"},"finish_reason":"stop"}]}\n'
        result = self.run_stream(raw)
        self.assertEqual(result["message"]["content"], "Done")
        self.assertTrue(result["transport"]["eofReceived"])

    def test_conflicting_terminal_reasons_are_protocol_error(self):
        raw = event(choice({"content": "Done"}, "stop")) + event(choice({}, "length")) + DONE
        with self.assertRaisesRegex(adapter.AdapterError, "changed its terminal"):
            self.run_stream(raw)

    def test_http_and_socket_errors_are_classified_and_secrets_redacted(self):
        failure = urllib.error.HTTPError("https://relay.invalid", 401, "no", {}, io.BytesIO(b"not-a-real-key"))
        with mock.patch.object(adapter.urllib.request, "urlopen", side_effect=failure):
            with self.assertRaises(adapter.AdapterError) as caught:
                adapter.complete(self.body, base_url="https://relay.invalid", key="not-a-real-key")
        self.assertEqual(caught.exception.kind, "api_error")
        self.assertNotIn("not-a-real-key", str(caught.exception))
        with mock.patch.object(adapter.urllib.request, "urlopen", side_effect=TimeoutError("synthetic timeout")):
            with self.assertRaises(adapter.AdapterError) as caught:
                adapter.complete(self.body, base_url="https://relay.invalid", key="not-a-real-key")
        self.assertEqual(caught.exception.response["transport"]["readError"], "TimeoutError")

    def test_fixture_validation_does_not_require_http_transport_metadata(self):
        result = {"finish_reason": "stop", "message": {"role": "assistant", "content": "Done"}}
        self.assertIs(adapter.validate_response(result), result)

    def test_read_error_keeps_already_reported_usage(self):
        class Interrupted(Stream):
            def __iter__(self):
                yield from Stream(event({"usage": {"completion_tokens": 7}, "choices": []}))
                raise OSError("synthetic read failure")
        with mock.patch.object(adapter.urllib.request, "urlopen", return_value=Interrupted(b"")):
            with self.assertRaises(adapter.AdapterError) as caught:
                adapter.complete(self.body, base_url="https://relay.invalid", key="not-a-real-key")
        self.assertEqual(caught.exception.kind, "api_error")
        self.assertEqual(caught.exception.response["usage"], {"completion_tokens": 7})
        self.assertEqual(caught.exception.response["transport"]["readError"], "OSError")

    def test_capture_write_failure_is_not_reclassified_as_provider_error(self):
        def failed_capture(_event):
            raise OSError("synthetic local capture failure")
        with self.assertRaisesRegex(OSError, "local capture"):
            self.run_stream(event(choice({"content": "Done"}, "stop")) + DONE, on_chunk=failed_capture)

    def test_malformed_utf8_is_protocol_error(self):
        with self.assertRaises(adapter.AdapterError) as caught:
            self.run_stream(b"data: \xff\n\n")
        self.assertEqual(caught.exception.kind, "protocol_error")


if __name__ == "__main__":
    unittest.main()
