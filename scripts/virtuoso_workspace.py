"""Create and validate portable Virtuoso engineering workspaces; never start EDA.

Python 3.11+ is required. Native libraries and runtime bindings are supplied
separately. Shared path, snapshot and integrity primitives live in ads_workspace.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tomllib

if __package__:
    from . import ads_workspace as aw
else:
    import ads_workspace as aw

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
PATHS = {"virtuoso": "virtuoso", "docs": "docs", "inputs": "inputs",
         "results": "results", "specification_snapshot": "inputs/task-spec", "tools": "tools"}
IGNORE = ("/results/", "/private/", "/inputs/private/", "__pycache__/", "*.py[cod]",
          "**/*.cdslck", "**/*.cdslck.*", "**/*.lck", "**/CDS.log*", "**/si.log",
          "**/simulation/", "**/psf/", "**/netlist/", "**/spectre.out")


def init_workspace(repo: Path, *, task_id: str, stage: str, revision: int = 1,
                   model_policy: str = "restricted-pdk", block_key: str,
                   dut_lib: str, dut_cell: str, dut_ports: list[str] | None = None) -> Path:
    """Scaffold one authored task; no native database or remote files are created."""
    repo = Path(repo).resolve()
    if not aw.TASK_ID_RE.fullmatch(task_id) or not aw.STAGE_RE.fullmatch(stage):
        raise ValueError("Task ID and stage must use lowercase kebab-case.")
    if type(revision) is not int or revision < 1 or model_policy not in aw.MODEL_POLICIES:
        raise ValueError("A positive revision and supported model policy are required.")
    for name, value in (("block_key", block_key), ("dut_lib", dut_lib), ("dut_cell", dut_cell)):
        if not isinstance(value, str) or not NAME_RE.fullmatch(value):
            raise ValueError(f"{name} must be a portable native identifier.")
    ports = [] if dut_ports is None else dut_ports
    if (not isinstance(ports, list) or any(not isinstance(p, str) or not NAME_RE.fullmatch(p) for p in ports)
            or len(set(ports)) != len(ports)):
        raise ValueError("dut_ports must contain unique portable native identifiers.")
    task, workspace = repo / "tasks" / task_id, repo / "workspaces" / task_id
    aw._ensure_no_links(repo, task)
    aw._ensure_no_links(repo, workspace)
    aw._check_existing_task(task, task_id, revision, stage)
    if workspace.exists():
        raise FileExistsError(f"Workspace already exists: {workspace}")
    lines = ["schema_version = 2", 'eda = "virtuoso"', "", "[project]",
             f"task_id = {aw._toml_str(task_id)}", f"revision = {revision}",
             f"task_version_id = {aw._toml_str(f'{task_id}-r{revision}')}",
             f"stage = {aw._toml_str(stage)}", f"model_policy = {aw._toml_str(model_policy)}", "", "[paths]"]
    lines += [f"{key} = {aw._toml_str(value)}" for key, value in PATHS.items()]
    lines += ["", "[design]", f"block_key = {aw._toml_str(block_key)}",
              f"dut_lib = {aw._toml_str(dut_lib)}", f"dut_cell = {aw._toml_str(dut_cell)}",
              "dut_ports = [" + ", ".join(aw._toml_str(p) for p in ports) + "]", ""]
    for path in PATHS.values():
        (workspace / path).mkdir(parents=True, exist_ok=True)
    aw._write_lf(workspace / "project.toml", "\n".join(lines))
    ignores = ["# Engineering results, private dependencies and Virtuoso runtime state.", *IGNORE]
    if model_policy == "restricted-pdk":
        ignores += ["/virtuoso/", "/inputs/pdk/", "*.zip"]
    aw._write_lf(workspace / ".gitignore", "\n".join(ignores) + "\n")
    aw._write_lf(workspace / "README.md",
                 f"# {task_id} engineering workspace\n\nTask revision: {revision}. Stage: {stage}.\n\n"
                 f"Native source: `virtuoso/`; selected design: `{dut_lib}:{dut_cell}:schematic`.\n"
                 "The manifest declares identity and paths only. Read retained run reports for outcomes.\n")
    aw._write_lf(workspace / "docs/execution-record.md", "# Execution record\n\nNo native execution has been performed.\n")
    # The snapshot path is predeclared, so the common snapshot routine preserves
    # this EDA-specific manifest rather than rendering an ADS manifest.
    aw.snapshot_task_spec(repo, workspace)
    report = validate_workspace(repo, workspace)
    if report["errors"]:
        raise ValueError("Internal Virtuoso scaffold validation failed: " + "; ".join(report["errors"]))
    return workspace


def validate_workspace(repo: Path, workspace: Path, *, require_v2: bool = True) -> dict:
    """Validate declared paths, identity and frozen inputs, not native readiness."""
    repo, workspace = Path(repo).resolve(), Path(workspace).resolve()
    errors = []
    identity = {}
    try:
        aw._ensure_no_links(repo / "workspaces", workspace)
        doc = tomllib.loads((workspace / "project.toml").read_text(encoding="utf-8"))
        if doc.get("schema_version") != 2 or doc.get("eda") != "virtuoso":
            raise ValueError("Virtuoso workspace requires schema_version = 2 and eda = virtuoso.")
        if set(doc) - {"schema_version", "eda", "project", "paths", "design"}:
            raise ValueError("Unsupported Virtuoso manifest table or field.")
        project = doc.get("project", {})
        if set(project) - aw.PROJECT_KEYS:
            raise ValueError("Unsupported project field.")
        task_id, revision, stage = project.get("task_id"), project.get("revision"), project.get("stage")
        if not isinstance(task_id, str) or not aw.TASK_ID_RE.fullmatch(task_id) or workspace.name != task_id:
            raise ValueError("Workspace directory and task identity must agree.")
        if type(revision) is not int or revision < 1 or project.get("task_version_id") != f"{task_id}-r{revision}":
            raise ValueError("Invalid Virtuoso task revision or version identity.")
        if not isinstance(stage, str) or not aw.STAGE_RE.fullmatch(stage) or project.get("model_policy") not in aw.MODEL_POLICIES:
            raise ValueError("Invalid stage or model policy.")
        identity = project
        paths = doc.get("paths", {})
        if paths != PATHS:
            raise ValueError("Virtuoso paths must use the declared portable workspace layout.")
        for key, rel in paths.items():
            aw._relative_posix(rel, "paths." + key)
            aw._ensure_no_links(workspace, workspace / rel)
            if not (workspace / rel).is_dir():
                raise ValueError("Missing workspace directory: " + rel)
        design = doc.get("design", {})
        if set(design) != {"block_key", "dut_lib", "dut_cell", "dut_ports"}:
            raise ValueError("Virtuoso design must declare block_key, dut_lib, dut_cell and dut_ports.")
        for key in ("block_key", "dut_lib", "dut_cell"):
            if not isinstance(design[key], str) or not NAME_RE.fullmatch(design[key]):
                raise ValueError("Invalid native identifier: " + key)
        ports = design["dut_ports"]
        if not isinstance(ports, list) or any(not isinstance(p, str) or not NAME_RE.fullmatch(p) for p in ports) or len(set(ports)) != len(ports):
            raise ValueError("Invalid ordered DUT ports.")
        for name in ("README.md", "docs/execution-record.md", ".gitignore"):
            aw._ensure_no_links(workspace, workspace / name)
            if not (workspace / name).is_file():
                raise ValueError("Missing workspace file: " + name)
        rules = set((workspace / ".gitignore").read_text(encoding="utf-8").splitlines())
        expected = set(IGNORE) | ({"/virtuoso/", "/inputs/pdk/", "*.zip"} if project["model_policy"] == "restricted-pdk" else set())
        if not expected <= rules:
            raise ValueError("Missing Virtuoso ignore rules.")
        source_task = repo / "tasks" / task_id
        if source_task.exists():
            aw._ensure_no_links(repo, source_task)
            aw._check_existing_task(source_task, task_id, revision, stage)
        aw._validate_manifest_snapshot(workspace / "inputs/task-spec", task_id, revision, errors)
        for parent, dirs, files in os.walk(workspace, followlinks=False):
            for name in dirs + files:
                aw._ensure_no_links(workspace, Path(parent) / name)
            if Path(parent) == workspace / "results":
                dirs.clear()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return dict(workspace=workspace.name, task_id=identity.get("task_id"), revision=identity.get("revision"),
                schema_version=2, status="error" if errors else "ok", errors=errors, warnings=[])


def allocate_run_dir(workspace: Path, slug: str, *, workflow=None, kind=None,
                     deliverables=None, registry=None, repo=None) -> Path:
    """Allocate an EDA-aware draft record after validating the selected route."""
    if __package__:
        from . import engineering_runs as er
    else:
        import engineering_runs as er
    workspace = Path(workspace).resolve()
    repo = Path(repo or workspace.parent.parent).resolve()
    if not aw.SLUG_RE.fullmatch(slug):
        raise ValueError("Run slug must use lowercase kebab-case.")
    validation = validate_workspace(repo, workspace)
    if validation["errors"]:
        raise ValueError("Workspace validation failed: " + "; ".join(validation["errors"]))
    doc = tomllib.loads((workspace / "project.toml").read_text(encoding="utf-8"))
    task, _ = er.select_task_source(repo, workspace, er._identity(doc))
    er.resolve_route(registry or repo / "engineering/workflows.toml", task=task, eda="virtuoso",
                     workflow=workflow, kind=kind, deliverables=deliverables)
    run = workspace / "results" / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{slug}"
    aw._ensure_no_links(workspace, run)
    run.mkdir(exist_ok=False)
    er.initialize_run(run, workspace, registry=registry, workflow=workflow, kind=kind,
                      deliverables=deliverables, repo=repo)
    return run


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    entry = sub.add_parser("validate")
    entry.add_argument("--repo", type=Path, default=aw.default_repo_root())
    entry.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args(argv)
    result = validate_workspace(args.repo, args.workspace)
    print(json.dumps(result, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
