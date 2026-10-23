"""Strict, task-independent Chat Completions SSE transport.

Provider responses and opaque reasoning details remain private capture. This
module does not retry requests, choose model settings, or interpret task scores.
"""

import copy
import datetime as dt
import json
import time
import urllib.error
import urllib.request


ADAPTER_VERSION = "chat-completions-sse-v1"


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class AdapterError(RuntimeError):
    """A transport/protocol failure with the captured partial response attached."""

    def __init__(self, message, *, kind="protocol_error", response=None):
        super().__init__(message)
        self.kind = kind
        self.response = copy.deepcopy(response or {})


def validate_response(record):
    """Reject incomplete responses, including fixture responses bypassing HTTP.

    A transport sentinel is not a model completion reason. Length stops retain
    partial output so the caller can classify its declared response token limit.
    """
    def fail(message, kind="protocol_error"):
        raise AdapterError(message, kind=kind, response=record)

    if not isinstance(record, dict):
        raise AdapterError("API response must be an object.")
    finish = record.get("finish_reason")
    if not finish:
        fail("Incomplete API stream; no terminal finish_reason was received.")
    message = record.get("message")
    if not isinstance(message, dict):
        fail("API response has no valid assistant message.")
    if finish == "length":
        return record
    if finish in ("error", "content_filter"):
        fail("Provider terminated the response with finish_reason=" + finish + ".", "api_error")
    if finish not in ("stop", "tool_calls"):
        fail("Unsupported terminal finish_reason: " + str(finish))
    calls = message.get("tool_calls")
    if calls is None:
        calls = []
    if not isinstance(calls, list):
        fail("API tool_calls must be an array.")
    if finish == "stop":
        if calls:
            fail("API finish_reason=stop conflicts with returned tool calls.")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            fail("API finish_reason=stop has no visible final response.")
        return record
    if not calls:
        fail("API finish_reason=tool_calls has no tool calls.")
    identifiers = set()
    for call in calls:
        if not isinstance(call, dict) or call.get("type") != "function":
            fail("API tool call is not a function call.")
        identifier = call.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in identifiers:
            fail("API tool call has a missing or repeated identifier.")
        identifiers.add(identifier)
        function = call.get("function")
        if not isinstance(function, dict) or not isinstance(function.get("name"), str) or not function["name"].strip():
            fail("API tool call has no function name.")
        try:
            arguments = json.loads(function["arguments"])
        except (KeyError, TypeError, ValueError):
            fail("API tool call arguments are not complete JSON.")
        if not isinstance(arguments, dict):
            fail("API tool call arguments must be a JSON object.")
    return record


class _StreamReadError(Exception):
    def __init__(self, error):
        super().__init__(str(error))
        self.error = error


def _sse_data(response, deadline):
    """Yield SSE data payloads, retaining multiline data and an EOF payload."""
    lines = []
    iterator = iter(response)
    while True:
        try:
            raw_line = next(iterator)
        except StopIteration:
            break
        except OSError as error:
            raise _StreamReadError(error) from error
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("Solver time limit reached during API generation.")
        line = raw_line.decode("utf-8").rstrip("\r\n")
        if not line:
            if lines:
                yield "\n".join(lines)
                lines = []
        elif line.startswith("data:"):
            value = line[5:]
            lines.append(value[1:] if value.startswith(" ") else value)
        # SSE comments, event names and retry fields contain no response body.
    if lines:
        yield "\n".join(lines)


def complete(body, *, base_url, key, deadline=None, on_chunk=None, on_request=None):
    """Send one request and retain exact JSON events plus transport sentinels.

    ``on_chunk`` receives original parsed JSON events before interpretation.
    Namespaced ``_capture`` records distinguish DONE/EOF and malformed payloads
    from provider events. Error responses keep reported usage in AdapterError.
    """
    requested_at = _now()
    record = {"request_model": body.get("model"),
              "requested_effort": body.get("reasoning_effort"),
              "requested_at": requested_at, "usage": None, "finish_reason": None,
              "transport": {"adapterVersion": ADAPTER_VERSION, "doneReceived": False,
                            "eofReceived": False, "eventCount": 0}}
    assistant = {"role": "assistant", "content": "", "reasoning_content": ""}
    calls = {}
    reasoning = {"reasoning_content": [], "reasoning": [], "reasoning_details.text": []}
    details = []

    def assemble():
        for field, fragments in reasoning.items():
            if fragments:
                assistant["reasoning_content"] = "".join(fragments)
                record["reasoning_source"] = field
                break
        if details:
            assistant["reasoning_details"] = copy.deepcopy(details)
        if calls:
            assistant["tool_calls"] = [calls[index] for index in sorted(calls)]
        assistant["content"] = assistant["content"] or None
        record["message"] = assistant
        record["completed_at"] = _now()

    def fail(message, kind="protocol_error"):
        assemble()
        raise AdapterError(message.replace(key, "[REDACTED]") if key else message,
                           kind=kind, response=record)

    def captured(value):
        if on_chunk:
            on_chunk(value)

    if on_request:
        on_request(copy.deepcopy(body))
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions",
                                    data=json.dumps(body).encode("utf-8"),
                                    headers={"Authorization": "Bearer " + key,
                                             "Content-Type": "application/json"})
    try:
        remaining = deadline - time.monotonic() if deadline is not None else 120
        if remaining <= 0:
            raise TimeoutError("Solver time limit reached before API generation.")
        with urllib.request.urlopen(request, timeout=min(120, remaining)) as response:
            if "text/event-stream" not in response.headers.get("Content-Type", "").lower():
                fail("Relay did not return the requested SSE stream.")
            for data in _sse_data(response, deadline):
                if data.strip() == "[DONE]":
                    record["transport"]["doneReceived"] = True
                    captured({"_capture": {"type": "sse_done", "at": _now()}})
                    break
                try:
                    event = json.loads(data)
                except ValueError:
                    captured({"_capture": {"type": "invalid_sse_data", "data": data, "at": _now()}})
                    fail("Relay returned malformed SSE JSON.")
                captured(event)
                record["transport"]["eventCount"] += 1
                if not isinstance(event, dict):
                    fail("Relay SSE event must be a JSON object.")
                for source, target in (("model", "response_model"), ("id", "response_id"),
                                       ("provider", "provider"), ("service_tier", "service_tier")):
                    if event.get(source):
                        record[target] = event[source]
                if event.get("usage") is not None:
                    record["usage"] = copy.deepcopy(event["usage"])
                if "error" in event:
                    record["transport"]["errorEventReceived"] = True
                    for choice in event.get("choices", []) if isinstance(event.get("choices"), list) else []:
                        if isinstance(choice, dict) and choice.get("index", 0) == 0:
                            for field in ("finish_reason", "native_finish_reason"):
                                if choice.get(field) is not None:
                                    record[field] = choice[field]
                    fail("Relay stream error: " + json.dumps(event["error"])[:1500], "api_error")
                choices = event.get("choices", [])
                if not isinstance(choices, list):
                    fail("Relay SSE choices must be an array.")
                for choice in choices:
                    if not isinstance(choice, dict):
                        fail("Relay SSE choice must be an object.")
                    if choice.get("index", 0) != 0:
                        continue
                    delta = choice.get("delta") or {}
                    if not isinstance(delta, dict):
                        fail("Relay SSE delta must be an object.")
                    content = delta.get("content")
                    if content is not None:
                        if not isinstance(content, str):
                            fail("Relay SSE content must be text or null.")
                        assistant["content"] += content
                    for field in ("reasoning_content", "reasoning"):
                        if delta.get(field) is not None:
                            if not isinstance(delta[field], str):
                                fail("Relay SSE reasoning text must be text or null.")
                            if delta[field]:
                                reasoning[field].append(delta[field])
                    if delta.get("reasoning_details") is not None:
                        if not isinstance(delta["reasoning_details"], list):
                            fail("Relay SSE reasoning_details must be an array.")
                        for detail in delta["reasoning_details"]:
                            if not isinstance(detail, dict):
                                fail("Relay SSE reasoning detail must be an object.")
                            details.append(copy.deepcopy(detail))
                            if detail.get("type") == "reasoning.text" and isinstance(detail.get("text"), str) and detail["text"]:
                                reasoning["reasoning_details.text"].append(detail["text"])
                    fragments = delta.get("tool_calls") or []
                    if not isinstance(fragments, list):
                        fail("Relay SSE tool_calls must be an array.")
                    for fragment in fragments:
                        if not isinstance(fragment, dict):
                            fail("Relay SSE tool call must be an object.")
                        index = fragment.get("index")
                        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                            fail("Relay SSE tool call has an invalid index.")
                        current = calls.setdefault(index, {"id": "", "type": "function",
                                                            "function": {"name": "", "arguments": ""}})
                        if fragment.get("type") not in (None, "function"):
                            fail("Relay SSE tool call has an unsupported type.")
                        if fragment.get("id"):
                            if not isinstance(fragment["id"], str):
                                fail("Relay SSE tool call identifier must be text.")
                            if current["id"] and current["id"] != fragment["id"]:
                                fail("Relay SSE tool call identifier changed during streaming.")
                            current["id"] = fragment["id"]
                        function = fragment.get("function") or {}
                        if not isinstance(function, dict):
                            fail("Relay SSE tool function must be an object.")
                        for field in ("name", "arguments"):
                            if function.get(field) is not None:
                                if not isinstance(function[field], str):
                                    fail("Relay SSE function fields must be text.")
                                current["function"][field] += function[field]
                    if choice.get("native_finish_reason") is not None:
                        record["native_finish_reason"] = choice["native_finish_reason"]
                    if choice.get("finish_reason") is not None:
                        finish = choice["finish_reason"]
                        if not isinstance(finish, str) or not finish:
                            fail("Relay finish_reason must be nonempty text.")
                        if record["finish_reason"] and record["finish_reason"] != finish:
                            fail("Relay changed its terminal finish_reason.")
                        record["finish_reason"] = finish
            else:
                record["transport"]["eofReceived"] = True
                captured({"_capture": {"type": "sse_eof", "at": _now()}})
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        fail(f"Relay HTTP {error.code}: {detail[:1500]}", "api_error")
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        record["transport"]["readError"] = type(error).__name__
        fail("Relay request failed: " + str(error), "api_error")
    except _StreamReadError as error:
        record["transport"]["readError"] = type(error.error).__name__
        fail("Relay stream read failed: " + str(error), "api_error")
    except UnicodeError:
        fail("Relay SSE payload is not valid UTF-8.")
    assemble()
    return validate_response(record)
