#!/usr/bin/env python3
"""Check the files Git would publish for credentials, private data and local paths.

The default scan covers tracked files plus untracked files that are not ignored,
which is exactly the working-tree set a broad ``git add`` could publish.  Use
``--staged`` in a pre-commit hook to check only the index, and ``--history`` to
scan every blob reachable from the repository's refs.

Project-specific forbidden terms belong in an ignored policy file, normally
``.local/release-policy.toml``.  Keeping those terms out of the tracked script
means the checker itself does not disclose the names it protects.

Example policy::

    [scan]
    ignore_paths = [".local/", ".mcp.json", "results/"]

    [[sensitive]]
    label = "private-pdk-kit"
    pattern = "(?i)EXAMPLE_PDK"
    severity = "high"

    [[allow]]
    path_glob = "tests/fixtures/**"
    rules = ["credential-assignment"]

Run from the repository root:

    python scripts/check_public_release.py
    python scripts/check_public_release.py --history
    python scripts/check_public_release.py --staged

Exit status is 1 when a finding at or above ``--fail-on`` (default: high,
medium) is present, otherwise 0.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Iterator, Sequence

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 and older
    tomllib = None  # type: ignore[assignment]

SEVERITIES = ("high", "medium", "low", "info")
SEVERITY_RANK = {name: rank for rank, name in enumerate(SEVERITIES)}

# Matched text from these rules is redacted in reports so a checker run does not
# copy a live credential into terminal or CI logs.
SENSITIVE_RULES = {
    "private-key",
    "aws-access-key",
    "github-token",
    "slack-token",
    "google-api-key",
    "openai-style-key",
    "url-credentials",
    "jwt",
    "bearer-token",
    "credential-assignment",
    "vendor-license",
}

BINARY_SUFFIXES = {
    ".7z",
    ".bin",
    ".bmp",
    ".bz2",
    ".db",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".ltd",
    ".oalib",
    ".oa",
    ".pdf",
    ".png",
    ".tar",
    ".tgz",
    ".zip",
}

# A file larger than this is reported once and not scanned.  Release trees are
# normally text and small; an unexpected large blob deserves a manual look.
MAX_SCAN_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True, order=True)
class Finding:
    severity: str
    rule: str
    path: str
    line: int | None
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "rule": self.rule,
            "path": self.path,
            "line": self.line,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Rule:
    name: str
    severity: str
    pattern: re.Pattern[str]
    description: str
    validator: Callable[[str, re.Match[str]], bool] | None = None


@dataclass
class Policy:
    sensitive: list["SensitiveTerm"] = field(default_factory=list)
    allow: list["AllowRule"] = field(default_factory=list)
    ignore_paths: list[str] = field(default_factory=list)
    exclude_globs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SensitiveTerm:
    label: str
    pattern: re.Pattern[str]
    severity: str = "high"


@dataclass(frozen=True)
class AllowRule:
    path_glob: str
    rules: tuple[str, ...]


def _mask(value: str) -> str:
    value = value.strip()
    if len(value) <= 8:
        return "<redacted>"
    return f"{value[:4]}...{value[-4:]}"


def _is_placeholder(match: re.Match[str]) -> bool:
    value = match.group(2).strip().strip("\"'")
    lowered = value.lower()
    if len(value) < 4:
        return True
    if lowered in {
        "none",
        "null",
        "true",
        "false",
        "secret",
        "password",
        "passwd",
        "changeme",
        "example",
        "dummy",
        "redacted",
        "required",
        "optional",
        "string",
        "str",
        "value",
    }:
        return True
    if any(
        marker in lowered
        for marker in (
            "test-only",
            "test-",
            "example",
            "placeholder",
            "your-",
            "your_",
            "replace",
            "<",
            ">",
            "${",
            "$env",
            "%(",
            "{%",
            "os.environ",
            "getenv",
            "environment",
            "process.env",
        )
    ):
        return True
    # Code expressions such as ``match.group(2)`` or ``line.strip().split()[-1]``
    # are not credentials.
    if any(character in value for character in "()[]{}"):
        return True
    if value.startswith(("r\"", "r'", "f\"", "f'")):
        return True
    return not bool(re.search(r"[A-Za-z]", value))


def _not_documentation_ip(_line: str, match: re.Match[str]) -> bool:
    value = match.group(0)
    return not value.startswith(("192.0.2.", "198.51.100.", "203.0.113.", "127.", "0."))


def _not_example_url(_line: str, match: re.Match[str]) -> bool:
    value = match.group(0)
    lowered = value.lower()
    if "example.com" in lowered:
        return False
    parts = urllib.parse.urlsplit(value)
    host = (parts.hostname or "").lower()
    password = (parts.password or "").lower()
    if host in {"host", "localhost", "example.com", "example.org", "example.net"}:
        return False
    if "." not in host and password in {"secret", "password", "passwd", "test", "token", "key"}:
        return False
    return True


def _not_example_email(_line: str, match: re.Match[str]) -> bool:
    domain = match.group(0).rsplit("@", 1)[-1].lower()
    if domain.endswith((".example", ".invalid")):
        return False
    return domain not in {
        "example.com",
        "example.org",
        "example.net",
        "localhost",
        "users.noreply.github.com",
    }


def _plausible_unc(_line: str, match: re.Match[str]) -> bool:
    parts = match.group(0).lstrip("\\").split("\\")
    if len(parts) < 2:
        return False
    host, share = parts[0], parts[1]
    if len(host) < 2 or len(share) < 2:
        return False
    if not re.search(r"[A-Za-z]", host) or host.isdigit():
        return False
    return True


def _not_placeholder_windows_path(_line: str, match: re.Match[str]) -> bool:
    lowered = match.group(0).lower()
    return not any(
        marker in lowered
        for marker in ("\\path\\to\\", "\\...\\", "<", ">", "your\\", "your_")
    )


RULES: tuple[Rule, ...] = (
    Rule(
        "private-key",
        "high",
        re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
        "PEM or OpenSSH private key block",
    ),
    Rule(
        "aws-access-key",
        "high",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "AWS access-key identifier",
    ),
    Rule(
        "github-token",
        "high",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
        "GitHub personal access token",
    ),
    Rule(
        "slack-token",
        "high",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
        "Slack token",
    ),
    Rule(
        "google-api-key",
        "high",
        re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
        "Google API key",
    ),
    Rule(
        "openai-style-key",
        "high",
        re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
        "OpenAI-style secret key",
    ),
    Rule(
        "url-credentials",
        "high",
        re.compile(r"https?://[^/\s:@]+:[^/\s@]+@[^/\s]+"),
        "credentials embedded in a URL",
        validator=_not_example_url,
    ),
    Rule(
        "jwt",
        "medium",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "JSON Web Token",
    ),
    Rule(
        "bearer-token",
        "medium",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*", re.IGNORECASE),
        "Bearer token value",
    ),
    Rule(
        "credential-assignment",
        "medium",
        re.compile(
            r"(?i)\b(api[_-]?key|apikey|client[_-]?secret|secret|password|passwd|pwd|"
            r"access[_-]?token|auth[_-]?token|refresh[_-]?token|token)\b\s*[:=]\s*[\"']?([^\s\"',;#]{4,})"
        ),
        "credential-like assignment",
        validator=lambda _line, match: not _is_placeholder(match),
    ),
    Rule(
        "vendor-license",
        "high",
        re.compile(r"(?m)^\s*(?:SERVER|VENDOR|INCREMENT|FEATURE|USE_SERVER)\b"),
        "vendor license-file line (host id or feature entitlement)",
    ),
    Rule(
        "private-ip",
        "medium",
        re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"),
        "RFC 1918 private IP address",
        validator=_not_documentation_ip,
    ),
    Rule(
        "windows-user-path",
        "medium",
        re.compile(r"\b[A-Za-z]:\\Users\\[^\\\s\"']+", re.IGNORECASE),
        "Windows user-profile path",
    ),
    Rule(
        "windows-absolute-path",
        "medium",
        re.compile(r"\b[A-Za-z]:\\(?:Program Files(?: \(x86\))?|Keysight|Users|[A-Za-z0-9_.-]+\\)[^\s\"'<>]{3,}", re.IGNORECASE),
        "Windows absolute path",
        validator=_not_placeholder_windows_path,
    ),
    Rule(
        "unix-home-path",
        "medium",
        re.compile(r"(?<![\w.])/(?:home|Users)/[A-Za-z0-9._-]+"),
        "Unix home directory path",
    ),
    Rule(
        "unc-path",
        "medium",
        re.compile(r"\\\\[A-Za-z0-9._$-]+\\[A-Za-z0-9._$-]+"),
        "Windows UNC network path",
        validator=_plausible_unc,
    ),
    Rule(
        "ssh-public-key",
        "low",
        re.compile(r"\bssh-(?:rsa|ed25519|dss) AAAA[A-Za-z0-9+/=]{20,}"),
        "SSH public key (not secret, but identifies a machine or person)",
    ),
    Rule(
        "email-address",
        "low",
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        "email address",
        validator=_not_example_email,
    ),
)


def _run(args: Sequence[str], root: Path, *, text: bool = True) -> str | bytes:
    result = subprocess.run(
        args,
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
    )
    if result.returncode != 0:
        message = result.stderr if text else result.stderr.decode("utf-8", "replace")
        raise RuntimeError(f"{' '.join(args)} failed: {message.strip()}")
    return result.stdout


def repo_root() -> Path:
    try:
        return Path(__file__).resolve().parents[1]
    except IndexError:
        return Path.cwd()


def load_policy(path: Path | None) -> Policy:
    policy = Policy()
    if path is None or not path.is_file():
        return policy
    if tomllib is None:
        raise RuntimeError("policy files require Python 3.11 or newer (tomllib)")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    scan = data.get("scan", {})
    if not isinstance(scan, dict):
        raise ValueError("[scan] must be a table")
    policy.ignore_paths = [str(item) for item in scan.get("ignore_paths", [])]
    policy.exclude_globs = [str(item) for item in scan.get("exclude_globs", [])]
    for index, item in enumerate(data.get("sensitive", []), 1):
        if not isinstance(item, dict):
            raise ValueError(f"[[sensitive]] #{index} must be a table")
        label = str(item.get("label") or f"sensitive-{index}")
        pattern = str(item.get("pattern") or "")
        if not pattern:
            raise ValueError(f"[[sensitive]] {label} needs a pattern")
        severity = str(item.get("severity", "high"))
        if severity not in SEVERITIES:
            raise ValueError(f"[[sensitive]] {label} has unknown severity {severity!r}")
        policy.sensitive.append(SensitiveTerm(label, re.compile(pattern), severity))
    for index, item in enumerate(data.get("allow", []), 1):
        if not isinstance(item, dict):
            raise ValueError(f"[[allow]] #{index} must be a table")
        glob = str(item.get("path_glob") or "")
        names = item.get("rules", [])
        if not glob or not isinstance(names, list) or not names:
            raise ValueError(f"[[allow]] #{index} needs path_glob and rules")
        policy.allow.append(AllowRule(glob, tuple(str(name) for name in names)))
    return policy


def _matches_glob(path: str, pattern: str) -> bool:
    clean = re.sub(r" \[[0-9a-f]{12}\]$", "", path)
    return PurePosixPath(clean).match(pattern)


def _allowed(policy: Policy, path: str, rule_name: str) -> bool:
    return any(
        _matches_glob(path, item.path_glob) and rule_name in item.rules for item in policy.allow
    )


def _excluded(policy: Policy, path: str) -> bool:
    return any(_matches_glob(path, pattern) for pattern in policy.exclude_globs)


def _git_paths(root: Path, staged: bool) -> list[str]:
    if staged:
        raw = _run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
            root,
            text=False,
        )
    else:
        raw = _run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            root,
            text=False,
        )
    assert isinstance(raw, bytes)
    return [item.decode("utf-8", "surrogateescape") for item in raw.split(b"\0") if item]


def _scan_line(
    line: str,
    path: str,
    line_number: int | None,
    policy: Policy,
    *,
    binary: bool = False,
    rules: Sequence[Rule] = RULES,
) -> Iterator[Finding]:
    for rule in rules:
        for match in rule.pattern.finditer(line):
            if rule.validator is not None and not rule.validator(line, match):
                continue
            if _allowed(policy, path, rule.name):
                continue
            detail = (
                _mask(match.group(0))
                if binary or rule.name in SENSITIVE_RULES
                else match.group(0).strip()
            )
            yield Finding(rule.severity, rule.name, path, line_number, detail)
    for term in policy.sensitive:
        for match in term.pattern.finditer(line):
            rule_name = f"policy:{term.label}"
            if _allowed(policy, path, rule_name):
                continue
            yield Finding(term.severity, rule_name, path, line_number, _mask(match.group(0)))


def _printable_strings(data: bytes) -> Iterator[tuple[int, str]]:
    for match in re.finditer(rb"[\x20-\x7e]{6,}", data):
        yield match.start(), match.group(0).decode("ascii", "replace")
    for match in re.finditer(rb"(?:[\x20-\x7e]\x00){6,}", data):
        yield match.start(), match.group(0).decode("utf-16le", "replace")


def scan_bytes(relative: str, data: bytes, policy: Policy) -> Iterator[Finding]:
    if _excluded(policy, relative):
        return
    size = len(data)
    if size > MAX_SCAN_BYTES:
        yield Finding(
            "info",
            "large-file",
            relative,
            None,
            f"{size} bytes; not scanned; confirm the file is intentional",
        )
        return
    binary = b"\0" in data[:8192] or Path(relative).suffix.lower() in BINARY_SUFFIXES
    if binary:
        seen: set[str] = set()
        for offset, text in _printable_strings(data):
            if text in seen:
                continue
            seen.add(text)
            for finding in _scan_line(text, relative, None, policy, binary=True):
                yield Finding(
                    finding.severity,
                    finding.rule,
                    finding.path,
                    None,
                    f"{finding.detail} @{offset}",
                )
        return
    text = data.decode("utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), 1):
        yield from _scan_line(line, relative, number, policy)


def scan_file(root: Path, relative: str, policy: Policy) -> Iterator[Finding]:
    if _excluded(policy, relative):
        return
    try:
        data = (root / relative).read_bytes()
    except OSError:
        return
    yield from scan_bytes(relative, data, policy)


def _index_entries(root: Path) -> list[tuple[str, str]]:
    raw = _run(["git", "ls-files", "-s", "-z"], root, text=False)
    assert isinstance(raw, bytes)
    entries: list[tuple[str, str]] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            meta, path = item.split(b"\t", 1)
            parts = meta.split()
        except ValueError:
            continue
        if len(parts) < 3:
            continue
        sha, stage = parts[1], parts[2]
        if stage != b"0" or not re.fullmatch(rb"[0-9a-f]{40,64}", sha):
            continue
        entries.append((path.decode("utf-8", "surrogateescape"), sha.decode("ascii")))
    return entries


def scan_index(root: Path, policy: Policy) -> Iterator[Finding]:
    entries = _index_entries(root)
    if not entries:
        return
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert process.stdin is not None and process.stdout is not None
    try:
        for relative, sha in entries:
            if _excluded(policy, relative):
                continue
            process.stdin.write(sha.encode("ascii") + b"\n")
            process.stdin.flush()
            header = process.stdout.readline()
            if not header:
                break
            parts = header.split()
            if len(parts) != 3:
                continue
            object_type, size_text = parts[1], parts[2]
            size = int(size_text)
            if object_type != b"blob":
                if size:
                    process.stdout.read(size)
                process.stdout.read(1)
                continue
            if size > MAX_SCAN_BYTES:
                process.stdout.read(size)
                process.stdout.read(1)
                yield Finding(
                    "info",
                    "large-file",
                    relative,
                    None,
                    f"{size} bytes; not scanned; confirm the file is intentional",
                )
                continue
            data = process.stdout.read(size)
            process.stdout.read(1)
            yield from scan_bytes(relative, data, policy)
    finally:
        try:
            process.stdin.close()
        except OSError:
            pass
        process.wait(timeout=30)


def _history_blobs(root: Path, *, all_refs: bool) -> dict[str, str]:
    # Branches and remote-tracking refs are what a normal push publishes.
    # refs/stash and tool-owned checkpoint refs stay local unless --all-refs is
    # requested, so the default report matches what is actually on the remote.
    refs = ["--all"] if all_refs else ["--branches", "--remotes", "HEAD"]
    raw = _run(["git", "rev-list", "--objects", *refs], root)
    assert isinstance(raw, str)
    blobs: dict[str, str] = {}
    for line in raw.splitlines():
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        sha, path = parts
        blobs.setdefault(sha, path)
    return blobs


def scan_history(
    root: Path, policy: Policy, *, max_findings: int, all_refs: bool = False
) -> Iterator[Finding]:
    blobs = _history_blobs(root, all_refs=all_refs)
    if not blobs:
        return
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert process.stdin is not None and process.stdout is not None
    emitted = 0
    try:
        for sha, path in blobs.items():
            process.stdin.write(sha.encode("ascii") + b"\n")
            process.stdin.flush()
            header = process.stdout.readline()
            if not header:
                break
            parts = header.split()
            if len(parts) != 3:
                continue
            object_type = parts[1]
            size = int(parts[2])
            data = process.stdout.read(size)
            process.stdout.read(1)
            if object_type != b"blob" or size > MAX_SCAN_BYTES:
                continue
            binary = b"\0" in data[:8192] or Path(path).suffix.lower() in BINARY_SUFFIXES
            if binary:
                seen: set[str] = set()
                for offset, text in _printable_strings(data):
                    if text in seen:
                        continue
                    seen.add(text)
                    for finding in _scan_line(text, f"{path} [{sha[:12]}]", None, policy, binary=True):
                        if finding.severity not in ("high", "medium"):
                            continue
                        yield finding
                        emitted += 1
                        if emitted >= max_findings:
                            return
            else:
                text_content = data.decode("utf-8", "replace")
                for number, line in enumerate(text_content.splitlines(), 1):
                    for finding in _scan_line(line, f"{path} [{sha[:12]}]", number, policy):
                        if finding.severity not in ("high", "medium"):
                            continue
                        yield finding
                        emitted += 1
                        if emitted >= max_findings:
                            return
    finally:
        try:
            process.stdin.close()
        except OSError:
            pass
        process.wait(timeout=30)


def check_ignores(root: Path, policy: Policy) -> Iterator[Finding]:
    for path in policy.ignore_paths:
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--", path],
            cwd=root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            yield Finding(
                "high",
                "ignore-gap",
                path,
                None,
                "expected to be ignored but is publishable",
            )


def check_local_refs(root: Path) -> Iterator[Finding]:
    raw = _run(["git", "for-each-ref", "--format=%(refname)"], root)
    assert isinstance(raw, str)
    refs = [
        ref
        for ref in raw.splitlines()
        if ref and not ref.startswith(("refs/heads/", "refs/remotes/", "refs/tags/"))
    ]
    if refs:
        categories = sorted({"/".join(ref.split("/")[:2]) for ref in refs})
        preview = ", ".join(categories[:5]) + ("..." if len(categories) > 5 else "")
        yield Finding(
            "info",
            "local-only-refs",
            "<git-refs>",
            None,
            f"{len(refs)} refs outside heads/remotes/tags ({preview}); a normal branch push does not publish them, but --mirror would",
        )


def check_forbidden_names(root: Path, policy: Policy, *, staged: bool = False) -> Iterator[Finding]:
    forbidden_suffixes = {
        ".env",
        ".jks",
        ".key",
        ".keystore",
        ".lic",
        ".p12",
        ".pem",
        ".pfx",
    }
    for relative in _git_paths(root, staged=staged):
        name = Path(relative).name.lower()
        suffix = Path(relative).suffix.lower()
        if name in {"id_rsa", "id_ed25519", "license.dat", ".env"} or suffix in forbidden_suffixes:
            yield Finding(
                "high",
                "forbidden-file",
                relative,
                None,
                "credential, private-key or vendor-license filename",
            )


def render(findings: Iterable[Finding], *, as_json: bool) -> None:
    items = sorted(set(findings), key=lambda item: (SEVERITY_RANK[item.severity], item.path, item.line or 0, item.rule))
    if as_json:
        print(json.dumps([item.as_dict() for item in items], indent=2))
        return
    if not items:
        print("No findings.")
        return
    current: str | None = None
    for item in items:
        if item.severity != current:
            current = item.severity
            print(f"\n[{current.upper()}]")
        location = item.path if item.line is None else f"{item.path}:{item.line}"
        print(f"  {item.rule}: {location}: {item.detail}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=None, help="repository root (default: this checkout)")
    parser.add_argument(
        "--policy",
        type=Path,
        default=None,
        help="ignored TOML policy with project-specific sensitive terms",
    )
    parser.add_argument("--staged", action="store_true", help="scan only files staged for commit")
    parser.add_argument(
        "--history",
        action="store_true",
        help="also scan blobs reachable from branches and remote-tracking refs",
    )
    parser.add_argument(
        "--all-refs",
        action="store_true",
        help="with --history, include local stash and tool checkpoint refs",
    )
    parser.add_argument(
        "--fail-on",
        choices=SEVERITIES,
        default="medium",
        help="lowest severity that makes the command fail (default: medium)",
    )
    parser.add_argument("--max-history-findings", type=int, default=200)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--check-ignores", action="store_true", help="verify policy ignore_paths are ignored")
    args = parser.parse_args(argv)

    root = (args.repo or repo_root()).resolve()
    policy_path = args.policy
    if policy_path is None and (root / ".local" / "release-policy.toml").is_file():
        policy_path = root / ".local" / "release-policy.toml"
    policy = load_policy(policy_path)

    findings: list[Finding] = []
    findings.extend(check_local_refs(root))
    if args.check_ignores:
        findings.extend(check_ignores(root, policy))
    if not args.staged:
        paths = _git_paths(root, staged=False)
        findings.extend(check_forbidden_names(root, policy))
        for relative in paths:
            findings.extend(scan_file(root, relative, policy))
    else:
        paths = _git_paths(root, staged=True)
        findings.extend(check_forbidden_names(root, policy, staged=True))
        findings.extend(scan_index(root, policy))
    if args.history:
        findings.extend(
            scan_history(
                root,
                policy,
                max_findings=args.max_history_findings,
                all_refs=args.all_refs,
            )
        )

    render(findings, as_json=args.json)
    threshold = SEVERITY_RANK[args.fail_on]
    failures = [item for item in findings if SEVERITY_RANK[item.severity] <= threshold]
    if not args.json:
        print(
            f"\nScanned {len(paths)} publishable file(s) from {root}"
            + (
                " plus history reachable from all local refs"
                if args.history and args.all_refs
                else " plus history reachable from branches and remote-tracking refs"
                if args.history
                else ""
            )
            + f"; {len(failures)} finding(s) at or above {args.fail_on}."
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
