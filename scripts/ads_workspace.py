"""Scaffold and validate standardized ADS engineering workspaces.

Supports the schema_version = 2 task-owned ADS workspace contract while
recognizing existing legacy (schema_version = 1 or pre-manifest) workspaces.
Python 3.11 or newer is required for the standard-library TOML reader.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tomllib

sys.dont_write_bytecode = True


SCHEMA_VERSION = 2
MODEL_POLICIES = ("restricted-pdk", "unrestricted-ideal")

TASK_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STAGE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
WRK_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,23}_wrk$")
AUX_WRK_NAME_RE = re.compile(r"^aux_[a-z][a-z0-9_]{0,19}_wrk$")
AUX_ROLE_RE = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# ADS library/cell naming convention (docs/ads-naming-convention.md).
BLOCK_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{0,15}$")
DUT_LIB_RE = re.compile(r"^(?P<block>[A-Z][A-Z0-9]*)_R(?P<rev>\d{2})_lib$")
LIB_ROLE_SUFFIXES = ("_lib", "_tb_lib", "_pcell_lib", "_em_lib", "_aux_lib")
SIMULATION_TOKENS = ("SP", "HB", "TRAN", "AC", "DC", "EM")
TB_CELL_RE = re.compile(
    r"^TB_(?P<dut>.+)_(?P<sim>" + "|".join(SIMULATION_TOKENS) + r")(?:_(?P<purpose>[A-Z0-9]+))?$"
)
EM_CELL_RE = re.compile(r"^EM_[A-Z][A-Z0-9_]*$")
AUX_CELL_RE = re.compile(r"^AUX_[A-Z][A-Z0-9_]*$")
AUTHORITATIVE_VIEW_NAMES = frozenset(
    {"schematic", "symbol", "layout", "emSetup", "emModel", "emModel_mw"}
)
RUN_ID_RE = re.compile(
    r"^20\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])"
    r"T(?:[01]\d|2[0-3])[0-5]\d[0-5]\dZ-[a-z0-9]+(?:-[a-z0-9]+)*$"
)
TEST_FILE_RE = re.compile(r"^(?:test_.+|.+_test)\.py$")
ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar"}

TOP_LEVEL_KEYS = {"schema_version", "project", "paths", "design", "ads_workspaces"}
FORBIDDEN_TABLES = {"planning", "execution", "evidence", "qualification", "pdk", "interface"}
PROJECT_KEYS = {"task_id", "revision", "task_version_id", "stage", "model_policy"}
REQUIRED_PATH_KEYS = {"ads", "docs", "inputs", "results"}
OPTIONAL_PATH_KEYS = {"tools", "tests", "specification_snapshot", "upstream"}
ALL_PATH_KEYS = REQUIRED_PATH_KEYS | OPTIONAL_PATH_KEYS
DESIGN_KEYS = {"dut_lib", "dut_cell", "dut_ports", "block_key", "vendored_libs"}
REQUIRED_TASK_FILES = ("task.toml", "instruction.md", "verification-plan.md", "DEVELOPMENT.md")

COMMON_GITIGNORE_RULES = (
    "__pycache__/",
    "*.py[cod]",
    "**/.ads_lock*",
    "**/*.cdslck",
    "**/*.cdslck.*",
    "**/*.lck",
    "**/saved.wrkstate",
)

POLICY_GITIGNORE_RULES = {
    "restricted-pdk": (
        "/results/",
        "/ads/",
        "/private/",
        "/inputs/pdk/",
        "/inputs/private/",
        "/inputs/upstream/",
        "/inputs/local-bindings.json",
        "*.net",
        "*.ds",
        "*.[sS][0-9]*[pP]",
        "*.[sS][nN][pP]",
        "*.zip",
    ),
    "unrestricted-ideal": (
        "/results/",
        "/private/",
        "/inputs/private/",
        "/inputs/upstream/",
        "**/*.prf",
        "**/logFile.txt",
        "**/netlist.log*",
        "**/simulation/",
        "**/data/",
    ),
}


def default_repo_root() -> Path:
    """Return the repository root derived from this module location."""
    return Path(__file__).resolve().parents[1]


def _is_link(path: Path) -> bool:
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        return True
    try:
        attrs = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    except FileNotFoundError:
        return False


def _ensure_no_links(root: Path, target: Path) -> None:
    """Verify target stays strictly inside root with no symlink or junction traversal."""
    root_abs = root.absolute()
    target_abs = target.absolute()
    try:
        rel = target_abs.relative_to(root_abs)
    except ValueError as exc:
        raise ValueError(f"Path escapes {root}: {target}") from exc
    if ".." in rel.parts:
        raise ValueError(f"Path traverses outside {root}: {target}")
    current = root_abs
    if _is_link(current):
        raise ValueError(f"Linked root is not allowed: {current}")
    for part in rel.parts:
        current = current / part
        if not current.exists() and not _is_link(current):
            break
        if _is_link(current):
            raise ValueError(f"Symlink or junction is not allowed: {current}")


def _relative_posix(value: object, label: str) -> PurePosixPath:
    """Validate and parse a normalized relative POSIX path."""
    if not isinstance(value, str) or not value or any(ord(ch) < 32 for ch in value):
        raise ValueError(f"{label} must be a nonempty path string without control characters.")
    if "\\" in value or ":" in value:
        raise ValueError(f"{label} must use forward slashes and no drive letter: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(
        part in ("", ".", "..") or part.endswith((" ", ".")) for part in path.parts
    ):
        raise ValueError(f"{label} must be a normalized relative POSIX path: {value!r}")
    return path


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _toml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _write_lf(path: Path, content: str, *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def render_gitignore(model_policy: str) -> str:
    """Render the canonical .gitignore content for a model policy."""
    if model_policy not in MODEL_POLICIES:
        raise ValueError(f"Unsupported model_policy: {model_policy!r}")
    if model_policy == "restricted-pdk":
        lines = [
            "# ADS engineering results, private bindings, and licensed PDK dependencies.",
            *POLICY_GITIGNORE_RULES[model_policy],
            "",
            "# Runtime bytecode and transient ADS locks/session state.",
            *COMMON_GITIGNORE_RULES,
            "",
        ]
    else:
        lines = [
            "# Ordinary engineering runs, private bindings, and transient ADS caches.",
            *POLICY_GITIGNORE_RULES[model_policy],
            "",
            "# Runtime bytecode and transient ADS locks/session state.",
            *COMMON_GITIGNORE_RULES,
            "",
        ]
    return "\n".join(lines)


def missing_gitignore_rules(gitignore_path: Path, model_policy: str) -> list[str]:
    """Return required .gitignore rules missing from gitignore_path."""
    required = list(POLICY_GITIGNORE_RULES[model_policy]) + list(COMMON_GITIGNORE_RULES)
    present = {
        line.strip()
        for line in gitignore_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    return [rule for rule in required if rule not in present]


def render_project_toml(
    *,
    task_id: str,
    revision: int,
    stage: str,
    model_policy: str,
    paths: dict[str, str],
    design: dict[str, object] | None = None,
    ads_workspaces: dict[str, dict[str, str]] | None = None,
) -> str:
    """Serialize a strict schema_version = 2 project.toml document."""
    lines = [
        f"schema_version = {SCHEMA_VERSION}",
        "",
        "[project]",
        f"task_id = {_toml_str(task_id)}",
        f"revision = {revision}",
        f"task_version_id = {_toml_str(f'{task_id}-r{revision}')}",
        f"stage = {_toml_str(stage)}",
        f"model_policy = {_toml_str(model_policy)}",
        "",
        "[paths]",
    ]
    ordered_keys = ("ads", "docs", "inputs", "results", "tools", "tests", "specification_snapshot", "upstream")
    for key in ordered_keys:
        if key in paths:
            lines.append(f"{key} = {_toml_str(paths[key])}")

    if design:
        clean_design = {k: v for k, v in design.items() if v is not None}
        if clean_design:
            lines.extend(["", "[design]"])
            for key in ("block_key", "dut_lib", "dut_cell", "dut_ports", "vendored_libs"):
                if key not in clean_design:
                    continue
                val = clean_design[key]
                if isinstance(val, list):
                    rendered = ", ".join(_toml_str(str(item)) for item in val)
                    lines.append(f"{key} = [{rendered}]")
                else:
                    lines.append(f"{key} = {_toml_str(str(val))}")

    if ads_workspaces:
        for role in sorted(ads_workspaces):
            entry = ads_workspaces[role]
            lines.extend([
                "",
                f"[ads_workspaces.{role}]",
                f"path = {_toml_str(entry['path'])}",
                f"purpose = {_toml_str(entry['purpose'])}",
            ])

    lines.append("")
    return "\n".join(lines)


def _render_task_toml(task_id: str, revision: int, stage: str, description: str) -> str:
    return (
        "# Engineering task contract; no registered shared-runner interface unless explicitly added.\n"
        'schema_version = "1.3"\n'
        "artifacts = []\n\n"
        "[task]\n"
        f"name = {_toml_str(f'analog-arena/{task_id}')}\n"
        f"description = {_toml_str(description)}\n"
        'keywords = ["ADS", "engineering"]\n\n'
        "[metadata]\n"
        f"task_id = {_toml_str(task_id)}\n"
        f"revision = {revision}\n"
        f"task_version_id = {_toml_str(f'{task_id}-r{revision}')}\n"
        f"stage = {_toml_str(stage)}\n"
    )


def _render_instruction_md(task_id: str, revision: int, stage: str, description: str) -> str:
    return (
        f"# {task_id} (revision {revision})\n\n"
        f"- Task ID: `{task_id}`\n"
        f"- Revision: `{revision}`\n"
        f"- Stage: `{stage}`\n"
        "- Status: `Draft` (specification pending completion)\n\n"
        "## Objective\n\n"
        f"{description}\n\n"
        "## DUT interface and ownership\n\n"
        "- Define ordered DUT terminals, reference node/plane, and what the DUT owns versus the testbench.\n\n"
        "## Acceptance criteria\n\n"
        "- List strict hard limits, exact checkpoints, and report-only observations.\n\n"
        "## Deliverables\n\n"
        f"- Editable ADS engineering source and verified evidence under `workspaces/{task_id}/`.\n"
    )


def _render_verification_plan_md(task_id: str, revision: int) -> str:
    return (
        f"# Verification plan: {task_id}-r{revision}\n\n"
        "## Authority and readiness\n\n"
        "- Engineering verification status: `Planned` (not yet executed).\n"
        "- Formal benchmark status: unregistered engineering task.\n\n"
        "## Measurements and evidence\n\n"
        "- Record simulation analyses, frequency/time/operating-point coverage, model validity checks, and cross-checks.\n\n"
        "## Replay\n\n"
        "- Regenerate netlists from a fresh copy of the saved ADS project and compare measurements before freeze.\n"
    )


def _render_development_md(task_id: str, revision: int) -> str:
    return (
        f"# Development and preflight: {task_id}-r{revision}\n\n"
        f"See [instruction.md](instruction.md), [verification-plan.md](verification-plan.md), and the\n"
        f"[engineering workspace](../../workspaces/{task_id}/README.md).\n\n"
        "## Current state\n\n"
        "- Readiness: `Draft` (awaiting finalized requirements and ADS environment preflight).\n"
        f"- Local environment binding key: `.local/ads-projects/{task_id}.json`.\n\n"
        "## Preflight checklist\n\n"
        "- [ ] Confirm ADS version, transport/MCP session, and workspace path mapping.\n"
        "- [ ] Confirm PDK/model bindings, terminal order, and valid operating domain.\n"
        "- [ ] Freeze `inputs/task-spec/` snapshot before isolated execution (`python scripts/ads_workspace.py snapshot-spec`).\n"
    )


def _render_workspace_readme(
    *,
    task_id: str,
    revision: int,
    stage: str,
    model_policy: str,
    wrk_rel: str,
    design: dict[str, object] | None,
) -> str:
    dut_line = ""
    if design and design.get("dut_cell"):
        lib = design.get("dut_lib") or "<lib>"
        cell = design["dut_cell"]
        ports = ", ".join(design.get("dut_ports", [])) if design.get("dut_ports") else "<ports>"
        dut_line = f"- Selected DUT: `{lib}:{cell}` with ordered ports `({ports})`\n"
    policy_note = (
        "Native ADS source under `ads/` contains restricted/PDK dependencies and is excluded from Git; "
        "retain reconstruction scripts in `tools/` and private archives under run `handoff/`."
        if model_policy == "restricted-pdk"
        else "Native ADS source under `ads/` uses unrestricted/ideal models and may be tracked without transient caches/locks."
    )
    return (
        f"# {task_id}\n\n"
        f"Engineering workspace for `{task_id}-r{revision}` (stage `{stage}`).\n"
        f"Authoritative task contract: [tasks/{task_id}/instruction.md](../../tasks/{task_id}/instruction.md).\n\n"
        "## Structure and design identity\n\n"
        f"- Manifest: [project.toml](project.toml) (`schema_version = {SCHEMA_VERSION}`, `model_policy = \"{model_policy}\"`)\n"
        f"- Primary ADS workspace: `{wrk_rel}`\n"
        f"{dut_line}"
        "- ADS naming: [convention](../../docs/ads-naming-convention.md)\n"
        "- Execution log: [docs/execution-record.md](docs/execution-record.md)\n"
        "- Run artifacts: `results/<YYYYMMDDTHHMMSSZ>-<slug>/` (gitignored)\n\n"
        "## Source policy\n\n"
        f"{policy_note}\n\n"
        "## Validation and run allocation\n\n"
        "```powershell\n"
        f"python scripts/ads_workspace.py validate --workspace workspaces/{task_id}\n"
        f"python scripts/ads_workspace.py new-run --workspace workspaces/{task_id} --slug nominal\n"
        "```\n"
    )


def _render_execution_record(task_id: str, revision: int, stage: str) -> str:
    return (
        f"# Execution record: {task_id}-r{revision}\n\n"
        f"- Stage: `{stage}`\n"
        f"- Task specification: [instruction.md](../../../tasks/{task_id}/instruction.md)\n"
        f"- Verification plan: [verification-plan.md](../../../tasks/{task_id}/verification-plan.md)\n\n"
        "## Retained runs\n\n"
        "| Run ID | Purpose | Outcome | Notes |\n"
        "| --- | --- | --- | --- |\n"
        "| (none yet) | | | |\n\n"
        "## Decisions and limitations\n\n"
        "- Workspace initialized; preflight and simulation pending.\n"
    )


def _check_existing_task(task_dir: Path, task_id: str, revision: int, stage: str) -> None:
    task_toml = task_dir / "task.toml"
    if not task_toml.is_file():
        raise ValueError(f"Missing task.toml in {task_dir}")
    for required in REQUIRED_TASK_FILES:
        candidate = task_dir / required
        if not candidate.is_file():
            raise ValueError(f"Task package is missing required file {candidate}")
    metadata = tomllib.loads(task_toml.read_text(encoding="utf-8")).get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError(f"Missing [metadata] table in {task_toml}")
    if metadata.get("task_id") != task_id:
        raise ValueError(f"Task ID mismatch in {task_toml}: expected {task_id!r}, got {metadata.get('task_id')!r}")
    if type(metadata.get("revision")) is not int or metadata["revision"] != revision:
        raise ValueError(f"Revision mismatch in {task_toml}: expected {revision!r}, got {metadata.get('revision')!r}")
    if "task_version_id" in metadata and metadata["task_version_id"] != f"{task_id}-r{revision}":
        raise ValueError(f"task_version_id mismatch in {task_toml}")
    if "stage" in metadata and metadata["stage"] != stage:
        raise ValueError(f"Stage mismatch in {task_toml}: expected {stage!r}, got {metadata.get('stage')!r}")


def snapshot_task_spec(repo: Path, workspace: Path) -> Path:
    """Freeze tasks/<task-id>/ specification files into workspace/inputs/task-spec/."""
    repo = Path(repo).resolve()
    workspace = Path(workspace).resolve()
    _ensure_no_links(repo, workspace)
    toml_path = workspace / "project.toml"
    doc = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    project = doc.get("project", {})
    task_id = project.get("task_id")
    revision = project.get("revision")
    if not isinstance(task_id, str) or type(revision) is not int:
        raise ValueError("Invalid [project] identity in project.toml")
    task_dir = repo / "tasks" / task_id
    _ensure_no_links(repo, task_dir)
    _check_existing_task(task_dir, task_id, revision, str(project.get("stage", "")))

    snapshot_dir = workspace / "inputs" / "task-spec"
    _ensure_no_links(workspace, snapshot_dir)
    source_files = {
        path.name: path for path in task_dir.iterdir()
        if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in (".toml", ".md")
    }
    profile_path = task_dir / "engineering.toml"
    if profile_path.exists():
        _ensure_no_links(task_dir, profile_path)
        declared_inputs = tomllib.loads(profile_path.read_text(encoding="utf-8")).get("inputs", [])
        if not isinstance(declared_inputs, list):
            raise ValueError("engineering.inputs must be a list of task-relative file paths.")
        for rel in declared_inputs:
            _relative_posix(rel, "engineering.inputs")
            source_files[rel] = task_dir / rel
    for rel, src in source_files.items():
        _ensure_no_links(task_dir, src)
        if not src.is_file() or src.stat().st_size == 0:
            raise ValueError(f"Task snapshot input is missing or empty: {rel}")
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for rel, src in sorted(source_files.items()):
        dst = snapshot_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        size, digest = _sha256_file(dst)
        records.append({"path": rel, "bytes": size, "sha256": digest})

    manifest = {
        "schema_version": 1,
        "task_id": task_id,
        "revision": revision,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": f"tasks/{task_id}",
        "files": records,
    }
    _write_lf(snapshot_dir / "manifest.json", json.dumps(manifest, indent=2) + "\n", overwrite=True)

    paths = dict(doc.get("paths", {}))
    if paths.get("specification_snapshot") != "inputs/task-spec":
        paths["specification_snapshot"] = "inputs/task-spec"
        updated = render_project_toml(
            task_id=task_id,
            revision=revision,
            stage=project["stage"],
            model_policy=project["model_policy"],
            paths=paths,
            design=doc.get("design"),
            ads_workspaces=doc.get("ads_workspaces"),
        )
        _write_lf(toml_path, updated, overwrite=True)
    return snapshot_dir


def init_workspace(
    repo: Path,
    *,
    task_id: str,
    stage: str,
    revision: int = 1,
    model_policy: str = "restricted-pdk",
    wrk_name: str = "design_wrk",
    dut_lib: str | None = None,
    dut_cell: str | None = None,
    dut_ports: list[str] | None = None,
    block_key: str | None = None,
    vendored_libs: list[str] | None = None,
    description: str | None = None,
    create_task: bool = False,
    with_tools: bool = False,
    with_tests: bool = False,
    snapshot_spec: bool = False,
) -> Path:
    """Create a standardized schema_version = 2 ADS workspace (and optionally task package)."""
    repo = Path(repo).resolve()
    if not TASK_ID_RE.fullmatch(task_id):
        raise ValueError(f"task_id must be lowercase kebab-case: {task_id!r}")
    if not STAGE_RE.fullmatch(stage):
        raise ValueError(f"stage must be lowercase kebab-case: {stage!r}")
    if type(revision) is not int or revision < 1:
        raise ValueError(f"revision must be a positive integer: {revision!r}")
    if model_policy not in MODEL_POLICIES:
        raise ValueError(f"model_policy must be one of {MODEL_POLICIES}: {model_policy!r}")
    if not WRK_NAME_RE.fullmatch(wrk_name):
        raise ValueError(
            f"wrk_name must match {WRK_NAME_RE.pattern} (short lowercase snake_case ending in _wrk): {wrk_name!r}"
        )
    if dut_ports is not None:
        cleaned_ports = [p.strip() for p in dut_ports if isinstance(p, str) and p.strip()]
        if not cleaned_ports or len(cleaned_ports) != len(dut_ports) or len(set(cleaned_ports)) != len(cleaned_ports):
            raise ValueError(f"dut_ports must be a nonempty list of unique port names: {dut_ports!r}")
        dut_ports = cleaned_ports

    if block_key is not None and (not isinstance(block_key, str) or not BLOCK_KEY_RE.fullmatch(block_key)):
        raise ValueError(f"block_key must match {BLOCK_KEY_RE.pattern}: {block_key!r}")
    if block_key is None and dut_lib:
        inferred = DUT_LIB_RE.fullmatch(dut_lib)
        if inferred:
            block_key = inferred.group("block")
    if block_key is not None and dut_lib is not None:
        expected_dut_lib = f"{block_key}_R{revision:02d}_lib"
        if dut_lib != expected_dut_lib:
            raise ValueError(
                f"dut_lib must equal {expected_dut_lib!r} for block_key {block_key!r} and revision {revision}: "
                f"got {dut_lib!r}"
            )
    if vendored_libs is not None:
        cleaned_vendored = [item.strip() for item in vendored_libs if isinstance(item, str) and item.strip()]
        if len(cleaned_vendored) != len(vendored_libs) or len(set(cleaned_vendored)) != len(cleaned_vendored):
            raise ValueError(f"vendored_libs must be a list of unique nonempty library names: {vendored_libs!r}")
        vendored_libs = cleaned_vendored

    task_dir = repo / "tasks" / task_id
    workspace = repo / "workspaces" / task_id
    _ensure_no_links(repo, task_dir)
    _ensure_no_links(repo, workspace)

    if workspace.exists():
        raise FileExistsError(f"Workspace already exists: {workspace}")

    if task_dir.exists():
        _check_existing_task(task_dir, task_id, revision, stage)
    else:
        if not create_task:
            raise FileNotFoundError(
                f"Task package {task_dir} does not exist. Author it first or pass --create-task."
            )
        desc = description or f"ADS engineering task {task_id} ({stage})."
        task_dir.mkdir(parents=True, exist_ok=True)
        _write_lf(task_dir / "task.toml", _render_task_toml(task_id, revision, stage, desc))
        _write_lf(task_dir / "instruction.md", _render_instruction_md(task_id, revision, stage, desc))
        _write_lf(task_dir / "verification-plan.md", _render_verification_plan_md(task_id, revision))
        _write_lf(task_dir / "DEVELOPMENT.md", _render_development_md(task_id, revision))

    wrk_rel = f"ads/{wrk_name}"
    paths: dict[str, str] = {
        "ads": wrk_rel,
        "docs": "docs",
        "inputs": "inputs",
        "results": "results",
    }
    if with_tools:
        paths["tools"] = "tools"
    if with_tests:
        paths["tests"] = "tests"

    design = None
    if block_key or dut_lib or dut_cell or dut_ports or vendored_libs:
        design = {
            "block_key": block_key,
            "dut_lib": dut_lib,
            "dut_cell": dut_cell,
            "dut_ports": dut_ports,
            "vendored_libs": vendored_libs,
        }

    workspace.mkdir(parents=True)
    (workspace / "docs").mkdir()
    (workspace / "inputs").mkdir()
    (workspace / "results").mkdir()
    if with_tools:
        (workspace / "tools").mkdir()
    if with_tests:
        (workspace / "tests").mkdir()

    _write_lf(workspace / ".gitignore", render_gitignore(model_policy))
    _write_lf(
        workspace / "project.toml",
        render_project_toml(
            task_id=task_id,
            revision=revision,
            stage=stage,
            model_policy=model_policy,
            paths=paths,
            design=design,
        ),
    )
    _write_lf(
        workspace / "README.md",
        _render_workspace_readme(
            task_id=task_id,
            revision=revision,
            stage=stage,
            model_policy=model_policy,
            wrk_rel=wrk_rel,
            design=design,
        ),
    )
    _write_lf(
        workspace / "docs" / "execution-record.md",
        _render_execution_record(task_id, revision, stage),
    )

    if snapshot_spec:
        snapshot_task_spec(repo, workspace)

    report = validate_workspace(repo, workspace, require_v2=True)
    if report["errors"]:
        raise ValueError("Internal scaffold validation failed: " + "; ".join(report["errors"]))
    return workspace


def allocate_run_dir(workspace: Path, slug: str, *, workflow: str | None = None,
                     kind: str | None = None, deliverables: list[str] | None = None,
                     registry: Path | None = None, repo: Path | None = None) -> Path:
    """Create a fresh UTC run directory and its draft engineering run record."""
    workspace = Path(workspace).resolve()
    if not SLUG_RE.fullmatch(slug):
        raise ValueError(f"Run slug must be lowercase kebab-case: {slug!r}")
    manifest_path = workspace / "project.toml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing project.toml in {workspace}")
    doc = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    results_rel = doc.get("paths", {}).get("results", "results")
    _relative_posix(results_rel, "paths.results")
    results_root = workspace / results_rel
    _ensure_no_links(workspace, results_root)
    results_root.mkdir(parents=True, exist_ok=True)
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{slug}"
    run_dir = results_root / run_id
    if __package__:
        from . import engineering_runs
    else:
        import engineering_runs
    task_dir, _ = engineering_runs.select_task_source(repo or workspace.parent.parent, workspace,
                                                     engineering_runs._identity(doc))
    engineering_runs.resolve_route(registry or default_repo_root() / "engineering" / "workflows.toml",
                                   task=task_dir, eda="ads", workflow=workflow, kind=kind,
                                   deliverables=deliverables)
    run_dir.mkdir(exist_ok=False)
    engineering_runs.initialize_run(run_dir, workspace, registry=registry, workflow=workflow,
                                    kind=kind, deliverables=deliverables, repo=repo)
    return run_dir


def _validate_manifest_snapshot(snapshot_dir: Path, task_id: str, revision: int, errors: list[str]) -> None:
    manifest_path = snapshot_dir / "manifest.json"
    try:
        _ensure_no_links(snapshot_dir, manifest_path)
    except ValueError as exc:
        errors.append(str(exc))
        return
    if not manifest_path.is_file():
        errors.append(f"Missing {manifest_path.name} inside {snapshot_dir.name}/.")
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Invalid task-spec manifest.json: {exc}")
        return
    if not isinstance(manifest, dict):
        errors.append("Task-spec manifest must be an object.")
        return
    if manifest.get("task_id") != task_id or type(manifest.get("revision")) is not int or manifest.get("revision") != revision:
        errors.append("inputs/task-spec/manifest.json task_id or revision does not match [project].")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        errors.append("inputs/task-spec/manifest.json must list frozen files.")
        return
    listed_paths = set()
    for entry in files:
        rel = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(rel, str):
            errors.append("Invalid file record in inputs/task-spec/manifest.json.")
            continue
        try:
            _relative_posix(rel, "manifest file path")
            _ensure_no_links(snapshot_dir, snapshot_dir / rel)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if rel == "manifest.json" or rel in listed_paths:
            errors.append("Task-spec manifest contains a duplicate or self-referencing file.")
        listed_paths.add(rel)
        target = snapshot_dir / rel
        if not target.is_file():
            errors.append(f"Frozen task-spec file missing: inputs/task-spec/{rel}")
            continue
        size, digest = _sha256_file(target)
        if size != entry.get("bytes") or digest != entry.get("sha256"):
            errors.append(f"Frozen task-spec file integrity mismatch: inputs/task-spec/{rel}")
    actual_paths = set()
    for parent, dirs, names in os.walk(snapshot_dir, followlinks=False):
        for name in list(dirs) + names:
            try:
                _ensure_no_links(snapshot_dir, Path(parent) / name)
            except ValueError as exc:
                errors.append(str(exc))
                if name in dirs:
                    dirs.remove(name)
        for name in names:
            rel = (Path(parent) / name).relative_to(snapshot_dir).as_posix()
            if rel != "manifest.json":
                actual_paths.add(rel)
    if actual_paths != listed_paths:
        errors.append("Frozen task-spec inventory differs from manifest (missing or unlisted files).")


def _validate_v2_manifest(
    repo: Path,
    workspace: Path,
    doc: dict[str, object],
    errors: list[str],
    warnings: list[str],
) -> tuple[str | None, int | None, str | None]:
    unknown_top = set(doc) - TOP_LEVEL_KEYS
    forbidden_found = sorted(unknown_top & FORBIDDEN_TABLES)
    if forbidden_found:
        errors.append(
            "project.toml must stay static; move dynamic/local tables "
            f"{forbidden_found} to docs/execution-record.md, results/, or .local/."
        )
    other_top = sorted(unknown_top - FORBIDDEN_TABLES)
    if other_top:
        errors.append(f"Unsupported top-level keys in project.toml: {other_top}")

    project = doc.get("project")
    task_id: str | None = None
    revision: int | None = None
    model_policy: str | None = None
    if not isinstance(project, dict):
        errors.append("Missing [project] table in project.toml.")
    else:
        missing_proj = sorted(PROJECT_KEYS - set(project))
        extra_proj = sorted(set(project) - PROJECT_KEYS)
        if missing_proj:
            errors.append(f"Missing required [project] keys: {missing_proj}")
        if extra_proj:
            errors.append(f"Unsupported [project] keys: {extra_proj}")
        raw_id = project.get("task_id")
        raw_rev = project.get("revision")
        raw_ver = project.get("task_version_id")
        raw_stage = project.get("stage")
        raw_policy = project.get("model_policy")
        if not isinstance(raw_id, str) or not TASK_ID_RE.fullmatch(raw_id):
            errors.append(f"project.task_id must be lowercase kebab-case: {raw_id!r}")
        else:
            task_id = raw_id
            if task_id != workspace.name:
                errors.append(f"Workspace directory name {workspace.name!r} must match project.task_id {task_id!r}.")
        if type(raw_rev) is not int or raw_rev < 1:
            errors.append(f"project.revision must be a positive integer: {raw_rev!r}")
        else:
            revision = raw_rev
        if task_id and revision is not None and raw_ver != f"{task_id}-r{revision}":
            errors.append(f"project.task_version_id must equal '{task_id}-r{revision}': got {raw_ver!r}")
        if not isinstance(raw_stage, str) or not STAGE_RE.fullmatch(raw_stage):
            errors.append(f"project.stage must be lowercase kebab-case: {raw_stage!r}")
        if raw_policy not in MODEL_POLICIES:
            errors.append(f"project.model_policy must be one of {MODEL_POLICIES}: {raw_policy!r}")
        else:
            model_policy = raw_policy

        if task_id and revision is not None:
            task_dir = repo / "tasks" / task_id
            snapshot_task = workspace / "inputs" / "task-spec" / "task.toml"
            if task_dir.exists():
                try:
                    _ensure_no_links(repo, task_dir)
                    _check_existing_task(task_dir, task_id, revision, str(raw_stage or ""))
                except ValueError as exc:
                    errors.append(str(exc))
            elif snapshot_task.is_file():
                warnings.append(f"Authoritative tasks/{task_id} not present; validated against inputs/task-spec.")
            else:
                errors.append(f"Missing authoritative task package tasks/{task_id}/ (or frozen inputs/task-spec/).")

    paths = doc.get("paths")
    declared_ads_dirs: set[str] = set()
    ads_ws_rels: list[str] = []
    if not isinstance(paths, dict):
        errors.append("Missing [paths] table in project.toml.")
        return task_id, revision, model_policy

    missing_paths = sorted(REQUIRED_PATH_KEYS - set(paths))
    extra_paths = sorted(set(paths) - ALL_PATH_KEYS)
    if missing_paths:
        errors.append(f"Missing required [paths] keys: {missing_paths}")
    if extra_paths:
        errors.append(
            f"Unsupported [paths] keys {extra_paths}; keep standard keys or declare auxiliary _wrk under [ads_workspaces.<role>]."
        )
    for key, raw_val in paths.items():
        if key not in ALL_PATH_KEYS:
            continue
        try:
            rel = _relative_posix(raw_val, f"paths.{key}")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if key == "ads":
            if len(rel.parts) != 2 or rel.parts[0] != "ads" or not WRK_NAME_RE.fullmatch(rel.parts[1]):
                errors.append(
                    f"paths.ads must match 'ads/<short_name>_wrk' ({WRK_NAME_RE.pattern}): got {raw_val!r}"
                )
            else:
                declared_ads_dirs.add(rel.parts[1])
                ads_ws_rels.append(rel.as_posix())
        elif key == "specification_snapshot":
            if raw_val != "inputs/task-spec":
                errors.append(f"paths.specification_snapshot must be 'inputs/task-spec': got {raw_val!r}")
        elif key == "upstream":
            if raw_val != "inputs/upstream":
                errors.append(f"paths.upstream must be 'inputs/upstream': got {raw_val!r}")
        elif raw_val != key:
            errors.append(f"paths.{key} must equal {key!r}: got {raw_val!r}")

    design = doc.get("design")
    if design is not None:
        if not isinstance(design, dict):
            errors.append("[design] must be a TOML table.")
        else:
            extra_design = sorted(set(design) - DESIGN_KEYS)
            if extra_design:
                errors.append(f"Unsupported keys in [design]: {extra_design}")
            for str_key in ("dut_lib", "dut_cell"):
                if str_key in design and (not isinstance(design[str_key], str) or not design[str_key].strip()):
                    errors.append(f"design.{str_key} must be a nonempty string.")
            block_key = design.get("block_key")
            if block_key is not None and (
                not isinstance(block_key, str) or not BLOCK_KEY_RE.fullmatch(block_key)
            ):
                errors.append(f"design.block_key must match {BLOCK_KEY_RE.pattern}: {block_key!r}")
            ports = design.get("dut_ports")
            if ports is not None and (
                not isinstance(ports, list)
                or not ports
                or not all(isinstance(p, str) and p.strip() for p in ports)
                or len({p.strip() for p in ports}) != len(ports)
            ):
                errors.append("design.dut_ports must be a nonempty list of unique port names.")
            elif isinstance(ports, list):
                for port in ports:
                    if not re.fullmatch(r"[a-z][a-z0-9_]*", port):
                        warnings.append(
                            f"design.dut_ports entry {port!r} is not lowercase snake_case; "
                            "use functional names such as rf_in or rf_out."
                        )
            vendored = design.get("vendored_libs")
            if vendored is not None and (
                not isinstance(vendored, list)
                or not all(isinstance(item, str) and item.strip() for item in vendored)
                or len({item.strip() for item in vendored}) != len(vendored)
            ):
                errors.append("design.vendored_libs must be a list of unique nonempty library names.")

    aux = doc.get("ads_workspaces")
    if aux is not None:
        if not isinstance(aux, dict):
            errors.append("[ads_workspaces] must be a table of named auxiliary workspaces.")
        else:
            for role, entry in aux.items():
                if not AUX_ROLE_RE.fullmatch(role) or not isinstance(entry, dict):
                    errors.append(f"Invalid auxiliary workspace entry [ads_workspaces.{role}].")
                    continue
                if set(entry) != {"path", "purpose"}:
                    errors.append(f"[ads_workspaces.{role}] must define exactly 'path' and 'purpose'.")
                    continue
                try:
                    rel = _relative_posix(entry["path"], f"ads_workspaces.{role}.path")
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                if len(rel.parts) != 2 or rel.parts[0] != "ads" or not AUX_WRK_NAME_RE.fullmatch(rel.parts[1]):
                    errors.append(
                        f"ads_workspaces.{role}.path must match 'ads/aux_<role>_wrk': got {entry['path']!r}"
                    )
                else:
                    declared_ads_dirs.add(rel.parts[1])
                    ads_ws_rels.append(rel.as_posix())

    _validate_filesystem_layout(workspace, paths, declared_ads_dirs, task_id, revision, model_policy, errors)
    _validate_ads_naming(workspace, ads_ws_rels, design, revision, errors, warnings)
    return task_id, revision, model_policy


def _validate_filesystem_layout(
    workspace: Path,
    paths: dict[str, object],
    declared_ads_dirs: set[str],
    task_id: str | None,
    revision: int | None,
    model_policy: str | None,
    errors: list[str],
) -> None:
    for required_file in ("README.md", ".gitignore", "docs/execution-record.md"):
        candidate = workspace / required_file
        if not candidate.is_file():
            errors.append(f"Missing required workspace file: {required_file}")

    gitignore = workspace / ".gitignore"
    if gitignore.is_file() and model_policy in MODEL_POLICIES:
        missing_rules = missing_gitignore_rules(gitignore, model_policy)
        if missing_rules:
            errors.append(f".gitignore is missing required {model_policy} rules: {missing_rules}")

    if not (workspace / "docs").is_dir():
        errors.append("Missing required directory: docs/")
    if not (workspace / "inputs").is_dir():
        errors.append("Missing required directory: inputs/")

    # Bidirectional check for committed optional paths vs actual folders on disk.
    optional_dir_map = {
        "tools": workspace / "tools",
        "tests": workspace / "tests",
        "specification_snapshot": workspace / "inputs" / "task-spec",
    }
    for key, target in optional_dir_map.items():
        declared = key in paths
        exists = target.exists()
        if declared and not target.is_dir():
            errors.append(f"[paths].{key} is declared, but {target.relative_to(workspace).as_posix()} is missing or not a directory.")
        elif exists and not declared:
            errors.append(f"Directory {target.relative_to(workspace).as_posix()} exists on disk, but [paths].{key} is not declared.")

    upstream_dir = workspace / "inputs" / "upstream"
    if "upstream" in paths and not upstream_dir.is_dir():
        errors.append("[paths].upstream is declared, but inputs/upstream is missing or not a directory.")

    spec_dir = optional_dir_map["specification_snapshot"]
    if spec_dir.is_dir() and task_id and revision is not None:
        _validate_manifest_snapshot(spec_dir, task_id, revision, errors)

    # Check ads/ hygiene if present on disk.
    ads_root = workspace / "ads"
    if ads_root.exists():
        if not ads_root.is_dir():
            errors.append("ads must be a directory.")
        else:
            for item in sorted(ads_root.iterdir()):
                if item.is_file():
                    if item.suffix.lower() in ARCHIVE_EXTS:
                        errors.append(f"Archives must not be stored under ads/: {item.name}")
                    else:
                        errors.append(f"Unexpected loose file directly under ads/: {item.name}")
                elif item.is_dir():
                    if item.name not in declared_ads_dirs:
                        errors.append(
                            f"Undeclared directory under ads/: {item.name} (declared: {sorted(declared_ads_dirs)})"
                        )

    # Keep runnable tools separate from unit tests.
    tools_dir = optional_dir_map["tools"]
    if tools_dir.is_dir():
        for py_file in sorted(tools_dir.rglob("*.py")):
            if TEST_FILE_RE.fullmatch(py_file.name):
                errors.append(f"Test files belong in tests/, not tools/: {py_file.relative_to(workspace).as_posix()}")

    # Enforce strict UTC run naming and prohibit loose files under results/.
    results_dir = workspace / "results"
    if results_dir.exists():
        if not results_dir.is_dir():
            errors.append("results must be a directory.")
        else:
            for item in sorted(results_dir.iterdir()):
                if item.name == ".gitkeep":
                    continue
                if item.is_file():
                    errors.append(f"Loose file is not allowed directly in results/: {item.name}")
                elif item.is_dir() and not RUN_ID_RE.fullmatch(item.name):
                    errors.append(
                        f"results/{item.name} must match '<YYYYMMDDTHHMMSSZ>-<slug>'."
                    )


def _oa_decode_name(name: str) -> str:
    """Decode OpenAccess percent-escaped cell or view directory names."""
    return re.sub(r"%(.)", r"\1", name)


def _read_lib_defs(path: Path) -> list[tuple[str, str]]:
    """Return (library, raw path) pairs from an ADS lib.defs file."""
    entries: list[tuple[str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return entries
    for line in text.splitlines():
        match = re.match(r"^\s*DEFINE\s+(\S+)\s+(.+?)\s*$", line)
        if match:
            entries.append((match.group(1), match.group(2).strip().strip('"')))
    return entries


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _validate_ads_naming(
    workspace: Path,
    ads_ws_rels: list[str],
    design: dict[str, object] | None,
    revision: int | None,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Check task-local ADS library, cell and view names against the naming convention."""
    design = design if isinstance(design, dict) else {}
    block_key = design.get("block_key")
    dut_lib = design.get("dut_lib")
    dut_cell = design.get("dut_cell")
    vendored = design.get("vendored_libs") or []
    inferred_block = False
    if block_key is None and isinstance(dut_lib, str):
        inferred = DUT_LIB_RE.fullmatch(dut_lib)
        if inferred:
            block_key = inferred.group("block")
            inferred_block = True
    if block_key is None:
        warnings.append(
            "design.block_key is not declared; ADS library/cell naming checks are skipped (grandfathered workspace)."
        )
        return
    if not isinstance(block_key, str) or not BLOCK_KEY_RE.fullmatch(block_key):
        errors.append(f"design.block_key must match {BLOCK_KEY_RE.pattern}: {block_key!r}")
        return
    if inferred_block:
        warnings.append("design.block_key was inferred from dut_lib; declare it explicitly in [design].")
    if revision is None:
        return
    root = f"{block_key}_R{revision:02d}"
    allowed_libs = {f"{root}{suffix}" for suffix in LIB_ROLE_SUFFIXES}
    dut_lib_name = f"{root}_lib"
    tb_lib_name = f"{root}_tb_lib"
    em_lib_name = f"{root}_em_lib"
    aux_lib_name = f"{root}_aux_lib"
    if isinstance(dut_lib, str) and dut_lib != dut_lib_name:
        errors.append(
            f"design.dut_lib must equal {dut_lib_name!r} for block_key {block_key!r} and revision {revision}: "
            f"got {dut_lib!r}"
        )

    found_lib_defs = False
    for rel in ads_ws_rels:
        ads_ws = workspace / rel
        if not ads_ws.is_dir():
            continue
        lib_defs_path = ads_ws / "lib.defs"
        if not lib_defs_path.is_file():
            warnings.append(f"No lib.defs under {rel}; ADS naming checks skipped until the native workspace exists.")
            continue
        found_lib_defs = True
        lib_defs = _read_lib_defs(lib_defs_path)
        local_cells: dict[str, set[str]] = {}
        lib_roots: dict[str, Path] = {}
        for lib_name, raw_path in lib_defs:
            resolved = Path(raw_path)
            if not resolved.is_absolute():
                resolved = ads_ws / resolved
            if not _is_within(resolved, workspace):
                continue
            if lib_name in vendored:
                continue
            if lib_name not in allowed_libs:
                errors.append(
                    f"Task-local ADS library {lib_name!r} under {rel} must match "
                    f"{root}_{{lib,tb_lib,pcell_lib,em_lib,aux_lib}}; "
                    "declare a byte-copied PDK library in design.vendored_libs."
                )
                continue
            if not resolved.is_dir():
                continue
            lib_roots[lib_name] = resolved
            cells: set[str] = set()
            for item in resolved.iterdir():
                if not item.is_dir() or item.name.startswith("."):
                    continue
                cell_name = _oa_decode_name(item.name)
                cells.add(cell_name)
                if lib_name == dut_lib_name:
                    if cell_name.startswith(("TB_", "EM_", "AUX_")):
                        errors.append(f"DUT library cell {cell_name!r} must not use a role prefix TB_/EM_/AUX_.")
                    elif not cell_name.startswith(f"{block_key}_"):
                        errors.append(f"DUT library cell {cell_name!r} must start with {block_key}_.")
                elif lib_name == tb_lib_name and not TB_CELL_RE.fullmatch(cell_name):
                    errors.append(
                        f"Testbench cell {cell_name!r} must match "
                        "TB_<DUT_CELL>_<SP|HB|TRAN|AC|DC|EM>[_<PURPOSE>]."
                    )
                elif lib_name == em_lib_name and not EM_CELL_RE.fullmatch(cell_name):
                    errors.append(f"EM library cell {cell_name!r} must match EM_<DEVICE>_<GEOMETRY>.")
                elif lib_name == aux_lib_name and not AUX_CELL_RE.fullmatch(cell_name):
                    errors.append(f"Auxiliary library cell {cell_name!r} must match AUX_<NAME>.")
                for view_dir in item.iterdir():
                    if not view_dir.is_dir() or view_dir.name.startswith("."):
                        continue
                    view_name = _oa_decode_name(view_dir.name)
                    if view_name not in AUTHORITATIVE_VIEW_NAMES and not view_name.startswith("x_"):
                        warnings.append(
                            f"Cell {cell_name!r} has non-standard view {view_name!r}; "
                            "use a stock view name or an x_ experimental prefix."
                        )
            local_cells[lib_name] = cells

        if isinstance(dut_lib, str) and dut_lib not in vendored and dut_lib not in lib_roots:
            errors.append(f"Declared design.dut_lib {dut_lib!r} is not a task-local library in {rel}/lib.defs.")
        elif isinstance(dut_lib, str) and isinstance(dut_cell, str) and dut_lib in lib_roots:
            cell_dirs = [
                item for item in lib_roots[dut_lib].iterdir()
                if item.is_dir() and _oa_decode_name(item.name) == dut_cell
            ]
            if not cell_dirs:
                errors.append(f"Declared design.dut_cell {dut_cell!r} is not present in {dut_lib}.")
            else:
                view_names = {
                    _oa_decode_name(item.name)
                    for item in cell_dirs[0].iterdir()
                    if item.is_dir()
                }
                for required_view in ("schematic", "symbol"):
                    if required_view not in view_names:
                        errors.append(f"Declared DUT cell {dut_cell!r} is missing the {required_view!r} view.")

        tb_cells = local_cells.get(tb_lib_name)
        dut_cells = local_cells.get(dut_lib_name, set())
        if tb_cells is not None and dut_cells:
            for tb_cell in sorted(tb_cells):
                match = TB_CELL_RE.fullmatch(tb_cell)
                if match and match.group("dut") not in dut_cells:
                    errors.append(
                        f"Testbench cell {tb_cell!r} names DUT {match.group('dut')!r}, "
                        f"which is not in {dut_lib_name}."
                    )
    if not found_lib_defs:
        warnings.append(
            "No ADS lib.defs found in the declared workspace; naming checks run after the native project is created."
        )


def validate_workspace(repo: Path, workspace: Path, *, require_v2: bool = True) -> dict[str, object]:
    """Validate an ADS engineering workspace against the repository contract."""
    repo = Path(repo).resolve()
    workspace = Path(workspace).resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not workspace.is_dir():
        return {
            "workspace": str(workspace),
            "task_id": None,
            "revision": None,
            "schema_version": None,
            "status": "error",
            "errors": [f"Workspace directory does not exist: {workspace}"],
            "warnings": warnings,
        }

    try:
        _ensure_no_links(repo / "workspaces", workspace)
        for root, dirs, files in os.walk(workspace, followlinks=False):
            root_path = Path(root)
            for name in (*dirs, *files):
                if _is_link(root_path / name):
                    errors.append(f"Symlink or junction is not allowed inside workspace: {(root_path / name)}")
            # Avoid scanning massive simulation datasets inside results/<run-id>/.
            if root_path == workspace / "results":
                dirs.clear()
    except ValueError as exc:
        errors.append(str(exc))

    toml_path = workspace / "project.toml"
    if not toml_path.is_file():
        status = "error" if require_v2 else "legacy"
        if require_v2:
            errors.append("Missing project.toml.")
        else:
            warnings.append("Pre-manifest legacy workspace (no project.toml).")
        return {
            "workspace": workspace.name,
            "task_id": None,
            "revision": None,
            "schema_version": None,
            "status": status,
            "errors": errors,
            "warnings": warnings,
        }

    try:
        doc = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {
            "workspace": workspace.name,
            "task_id": None,
            "revision": None,
            "schema_version": None,
            "status": "error",
            "errors": [f"Failed to parse project.toml: {exc}"],
            "warnings": warnings,
        }

    schema_version = doc.get("schema_version")
    if schema_version == 1 and not require_v2:
        proj = doc.get("project", {}) if isinstance(doc.get("project"), dict) else {}
        return {
            "workspace": workspace.name,
            "task_id": proj.get("task_id"),
            "revision": proj.get("revision"),
            "schema_version": 1,
            "status": "legacy-v1",
            "errors": errors,
            "warnings": ["Legacy schema_version = 1 workspace (grandfathered)."],
        }

    if schema_version != SCHEMA_VERSION:
        errors.append(f"Expected schema_version = {SCHEMA_VERSION}, got {schema_version!r}.")
        return {
            "workspace": workspace.name,
            "task_id": None,
            "revision": None,
            "schema_version": schema_version,
            "status": "error",
            "errors": errors,
            "warnings": warnings,
        }

    task_id, revision, _ = _validate_v2_manifest(repo, workspace, doc, errors, warnings)
    return {
        "workspace": workspace.name,
        "task_id": task_id,
        "revision": revision,
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if not errors else "error",
        "errors": errors,
        "warnings": warnings,
    }


def audit_workspaces(repo: Path, *, v2_only: bool = False) -> list[dict[str, object]]:
    """Inspect all workspaces under repo/workspaces/ and return validation summaries."""
    repo = Path(repo).resolve()
    root = repo / "workspaces"
    if not root.is_dir():
        return []
    reports = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if (entry / "circuit.spi").exists() and not (entry / "project.toml").exists():
            if not v2_only:
                reports.append({
                    "workspace": entry.name,
                    "task_id": entry.name,
                    "revision": None,
                    "schema_version": None,
                    "status": "non-ads",
                    "errors": [],
                    "warnings": ["Non-ADS workspace (KiCad/SPICE)."],
                })
            continue
        toml_path = entry / "project.toml"
        is_v2 = False
        if toml_path.is_file():
            try:
                _ensure_no_links(root, entry)
                _ensure_no_links(entry, toml_path)
                doc = tomllib.loads(toml_path.read_text(encoding="utf-8"))
                is_v2 = doc.get("schema_version") == SCHEMA_VERSION
                declared_eda = doc.get("eda", "ads")
                if declared_eda == "virtuoso" and is_v2:
                    if not v2_only:
                        project = doc.get("project", {})
                        reports.append({
                            "workspace": entry.name,
                            "task_id": project.get("task_id") if isinstance(project, dict) else None,
                            "revision": project.get("revision") if isinstance(project, dict) else None,
                            "schema_version": SCHEMA_VERSION,
                            "status": "non-ads", "errors": [],
                            "warnings": ["Virtuoso workspace is outside ADS audit coverage; validate it with scripts/virtuoso_workspace.py."],
                        })
                    continue
                if declared_eda != "ads":
                    reports.append({
                        "workspace": entry.name, "task_id": None, "revision": None,
                        "schema_version": doc.get("schema_version"), "status": "error",
                        "errors": ["Unsupported workspace EDA or schema declaration."], "warnings": [],
                    })
                    continue
            except (OSError, ValueError):
                is_v2 = True
        if v2_only and not is_v2:
            continue
        reports.append(validate_workspace(repo, entry, require_v2=is_v2))
    return reports


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("init", help="Initialize a standardized schema_version = 2 ADS workspace")
    init_cmd.add_argument("--repo", type=Path, default=default_repo_root())
    init_cmd.add_argument("--task-id", required=True)
    init_cmd.add_argument("--stage", required=True)
    init_cmd.add_argument("--revision", type=int, default=1)
    init_cmd.add_argument("--model-policy", choices=MODEL_POLICIES, default="restricted-pdk")
    init_cmd.add_argument("--wrk-name", default="design_wrk")
    init_cmd.add_argument("--block-key", help="Uppercase block key for ADS library/cell naming, e.g. LPF")
    init_cmd.add_argument("--dut-lib")
    init_cmd.add_argument("--dut-cell")
    init_cmd.add_argument("--dut-ports", help="Comma-separated ordered DUT port names")
    init_cmd.add_argument(
        "--vendored-libs",
        help="Comma-separated byte-copied PDK library names exempt from task naming rules",
    )
    init_cmd.add_argument("--description")
    init_cmd.add_argument("--create-task", action="store_true", help="Create starter files in tasks/<task-id>/ if absent")
    init_cmd.add_argument("--with-tools", action="store_true", help="Create tools/ and declare it in project.toml")
    init_cmd.add_argument("--with-tests", action="store_true", help="Create tests/ and declare it in project.toml")
    init_cmd.add_argument("--snapshot-spec", action="store_true", help="Freeze tasks/<task-id>/ into inputs/task-spec/")

    val_cmd = sub.add_parser("validate", help="Validate an ADS workspace against schema_version = 2")
    val_cmd.add_argument("--repo", type=Path, default=default_repo_root())
    group = val_cmd.add_mutually_exclusive_group(required=True)
    group.add_argument("--workspace", type=Path)
    group.add_argument("--all-v2", action="store_true", help="Validate all schema_version = 2 workspaces")
    val_cmd.add_argument("--allow-legacy", action="store_true", help="Do not fail when targeting a legacy workspace")

    audit_cmd = sub.add_parser("audit", help="Report schema/layout status across all workspaces/")
    audit_cmd.add_argument("--repo", type=Path, default=default_repo_root())

    snap_cmd = sub.add_parser("snapshot-spec", help="Freeze tasks/<task-id>/ into inputs/task-spec/")
    snap_cmd.add_argument("--repo", type=Path, default=default_repo_root())
    snap_cmd.add_argument("--workspace", required=True, type=Path)

    run_cmd = sub.add_parser("new-run", help="Allocate a UTC-named results/<YYYYMMDDTHHMMSSZ>-<slug>/ folder")
    run_cmd.add_argument("--workspace", required=True, type=Path)
    run_cmd.add_argument("--slug", required=True)
    run_cmd.add_argument("--workflow", help="Workflow ID; existing task engineering.toml takes precedence")
    run_cmd.add_argument("--kind", choices=("design", "reproduction", "feasibility"))
    run_cmd.add_argument("--deliverables", help="Comma-separated groups: source,simulation,layout,em")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for ADS workspace scaffolding and validation."""
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "init":
            ports = [p.strip() for p in args.dut_ports.split(",") if p.strip()] if args.dut_ports else None
            vendored = [p.strip() for p in args.vendored_libs.split(",") if p.strip()] if args.vendored_libs else None
            workspace = init_workspace(
                args.repo,
                task_id=args.task_id,
                stage=args.stage,
                revision=args.revision,
                model_policy=args.model_policy,
                wrk_name=args.wrk_name,
                dut_lib=args.dut_lib,
                dut_cell=args.dut_cell,
                dut_ports=ports,
                block_key=args.block_key,
                vendored_libs=vendored,
                description=args.description,
                create_task=args.create_task,
                with_tools=args.with_tools,
                with_tests=args.with_tests,
                snapshot_spec=args.snapshot_spec,
            )
            print(json.dumps({"status": "created", "workspace": str(workspace)}, indent=2))
            return 0

        if args.command == "validate":
            if args.all_v2:
                reports = audit_workspaces(args.repo, v2_only=True)
                failed = [r for r in reports if r["status"] == "error"]
                print(json.dumps({"checked": len(reports), "failed": len(failed), "reports": reports}, indent=2))
                return 1 if failed else 0
            report = validate_workspace(args.repo, args.workspace, require_v2=not args.allow_legacy)
            print(json.dumps(report, indent=2))
            return 1 if report["status"] == "error" else 0

        if args.command == "audit":
            reports = audit_workspaces(args.repo, v2_only=False)
            print(json.dumps({"total": len(reports), "reports": reports}, indent=2))
            return 1 if any(r["status"] == "error" for r in reports) else 0

        if args.command == "snapshot-spec":
            dest = snapshot_task_spec(args.repo, args.workspace)
            print(json.dumps({"status": "snapshotted", "path": str(dest)}, indent=2))
            return 0

        if args.command == "new-run":
            run_dir = allocate_run_dir(args.workspace, args.slug, workflow=args.workflow, kind=args.kind,
                                       deliverables=args.deliverables.split(",") if args.deliverables else None)
            print(json.dumps({"status": "allocated", "run_dir": str(run_dir)}, indent=2))
            return 0
    except (OSError, ValueError) as exc:
        print(f"ads_workspace: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
