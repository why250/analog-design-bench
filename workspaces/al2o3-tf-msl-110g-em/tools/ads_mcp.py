#!/usr/bin/env python3
"""Minimal MCP stdio client for the ADS 2027 MCP server over SSH.

Claude Code sessions on this repository do not register the ADS MCP server
directly. This client speaks newline-delimited JSON-RPC to ``ads-mcp.exe``
launched on the ADS host through the SSH alias in ``ADS_MCP_SSH_ALIAS``, so
task execution can use the same ADS session and Python automation route.

Examples
--------
    python tools/ads_mcp.py list-sessions
    python tools/ads_mcp.py --session 58724 summary
    python tools/ads_mcp.py --session 58724 exec --file probe.py
    python tools/ads_mcp.py --local exec --code "print('hello')"
    python tools/ads_mcp.py docs --path api/keysight.ads.de

The ``--session`` and ``--local`` options attach before the requested tool call
in the same client process. Each invocation starts a fresh MCP server process;
write scripts that are self-contained rather than relying on REPL state across
invocations. For long solver runs, launch a background process on the ADS host
and poll its log/status files with separate ``exec`` calls.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

DEFAULT_SSH = os.environ.get("ADS_MCP_SSH", "ssh")
DEFAULT_ALIAS = os.environ.get("ADS_MCP_SSH_ALIAS", "")
DEFAULT_REMOTE = os.environ.get(
    "ADS_MCP_REMOTE",
    "$env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'; & 'ads-mcp.exe'",
)
PROTOCOL_VERSION = "2024-11-05"


class McpError(RuntimeError):
    """Protocol, timeout or ADS MCP tool failure."""


class McpClient:
    def __init__(self, ssh: str, alias: str, remote: str, timeout: float) -> None:
        self.timeout = timeout
        self.proc = subprocess.Popen(
            [ssh, "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12", alias, remote],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._messages: "queue.Queue[str | None]" = queue.Queue()
        self._next_id = 0
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self._handshake()

    def _read_stdout(self) -> None:
        assert self.proc.stdout is not None
        for raw in self.proc.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                self._messages.put(line)
        self._messages.put(None)

    def _read_stderr(self) -> None:
        assert self.proc.stderr is not None
        for raw in self.proc.stderr:
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                print(f"[ads-mcp] {line}", file=sys.stderr)

    def _send(self, message: dict) -> None:
        assert self.proc.stdin is not None
        payload = json.dumps(message, ensure_ascii=False) + "\n"
        self.proc.stdin.write(payload.encode("utf-8"))
        self.proc.stdin.flush()

    def _request(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict:
        self._next_id += 1
        request_id = self._next_id
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)
        return self._wait(request_id, timeout or self.timeout)

    def _wait(self, request_id: int, timeout: float) -> dict:
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise McpError(f"Timed out waiting for response id={request_id}")
            try:
                line = self._messages.get(timeout=remaining)
            except queue.Empty:
                raise McpError(f"Timed out waiting for response id={request_id}") from None
            if line is None:
                raise McpError("ADS MCP server closed stdout")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                print(f"[ads-mcp] non-JSON output: {line[:300]}", file=sys.stderr)
                continue
            if message.get("id") == request_id:
                if "error" in message:
                    raise McpError(json.dumps(message["error"], ensure_ascii=False))
                return message.get("result", {})
            if "method" in message and "id" in message:
                self._send({
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "error": {"code": -32601, "message": "unsupported client request"},
                })
            # Other notifications are intentionally ignored.

    def _handshake(self) -> None:
        result = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "ads-mcp-cli", "version": "0.1.0"},
        })
        self.server_info = result.get("serverInfo", {})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def call_tool(self, name: str, arguments: dict | None = None, timeout: float | None = None) -> dict:
        return self._request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            timeout,
        )

    def close(self) -> None:
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


def _tool_text(result: dict) -> str:
    parts = []
    for item in result.get("content", []) if isinstance(result, dict) else []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item.get("text", ""))
        else:
            parts.append(json.dumps(item, ensure_ascii=False))
    if not parts:
        parts.append(json.dumps(result, ensure_ascii=False, indent=2))
    return "\n".join(parts)


def _emit(result: dict) -> None:
    print(_tool_text(result))
    if result.get("isError"):
        raise SystemExit(2)


def _require_ok(result: dict, label: str) -> None:
    if result.get("isError"):
        print(f"{label} failed: {_tool_text(result)}", file=sys.stderr)
        raise SystemExit(2)
    print(f"{label}: ok", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ssh", default=DEFAULT_SSH, help="local OpenSSH executable")
    parser.add_argument("--alias", default=DEFAULT_ALIAS, help="SSH alias for the ADS host")
    parser.add_argument("--remote", default=DEFAULT_REMOTE, help="remote ADS MCP launch command")
    parser.add_argument("--timeout", type=float, default=900.0, help="tool-call timeout in seconds")
    connection = parser.add_mutually_exclusive_group()
    connection.add_argument("--session", type=int, help="connect to this ADS UI session first")
    connection.add_argument("--local", action="store_true", help="start a headless local ADS session first")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-sessions", help="list running ADS UI sessions")
    sub.add_parser("summary", help="show the active ADS workspace summary")
    docs = sub.add_parser("docs", help="browse ADS Python API documentation")
    docs.add_argument("--path", default="")
    search = sub.add_parser("search", help="search ADS Python API documentation")
    search.add_argument("--query", required=True)
    execute = sub.add_parser("exec", help="execute Python in the attached ADS session")
    source = execute.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="local Python file to send; '-' reads stdin")
    source.add_argument("--code", help="inline Python code")
    call = sub.add_parser("call", help="call any advertised MCP tool")
    call.add_argument("--tool", required=True)
    call.add_argument("--args-json", default="{}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.alias:
        parser.error("set ADS_MCP_SSH_ALIAS or pass --alias")

    code = None
    if args.command == "exec":
        if args.file is not None:
            code = sys.stdin.read() if str(args.file) == "-" else args.file.read_text(encoding="utf-8")
        else:
            code = args.code

    client = McpClient(args.ssh, args.alias, args.remote, args.timeout)
    try:
        if args.session is not None:
            _require_ok(client.call_tool("connect_session", {"session_id": args.session}), "connect_session")
        elif args.local:
            _require_ok(client.call_tool("start_local_session", {}), "start_local_session")

        if args.command == "list-sessions":
            _emit(client.call_tool("list_sessions", {}))
        elif args.command == "summary":
            _emit(client.call_tool("workspace_summary", {}))
        elif args.command == "docs":
            _emit(client.call_tool("get_docs", {"path": args.path}))
        elif args.command == "search":
            _emit(client.call_tool("search_docs", {"query": args.query}))
        elif args.command == "exec":
            _emit(client.call_tool("execute_python", {"code": code}, timeout=args.timeout))
        elif args.command == "call":
            _emit(client.call_tool(args.tool, json.loads(args.args_json)))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
