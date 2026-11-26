"""Record and check task-owned engineering runs; never execute an EDA tool.

Python 3.11+ and the bundled ads_workspace module are the only dependencies.
Checks establish recorded identity, evidence presence and byte integrity, not
electrical correctness or the truth of a tool observation supplied by an operator.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tomllib

sys.dont_write_bytecode = True

if __package__:
    from . import ads_workspace as aw
else:
    import ads_workspace as aw

KINDS = ("design", "reproduction", "feasibility")
DELIVERABLES = ("source", "simulation", "layout", "em")
ROLES = ("native_source", "netlist", "solver_input", "simulator_log", "raw_data", "measurements", "check_report", "layout", "em_setup")
TERMINAL = ("completed", "failed", "interrupted")
FACETS = {
    "execution": ("pending", "running", "completed", "failed", "interrupted"),
    "electrical": ("pending", "passed", "failed", "conditional", "not-applicable"),
    "models": ("pending", "verified", "failed", "conditional", "not-applicable"),
    "delivery": ("pending", "complete", "incomplete"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> dict:
    def invalid(value):
        raise ValueError(f"Non-finite JSON number in {path.name}: {value}")
    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")
    return value


def write_json(path: Path, value: dict) -> None:
    aw._write_lf(path, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def _text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError(f"{label} must be a nonempty single-line string.")
    return value


def _timestamp(value, label: str) -> None:
    _text(value, label)
    try:
        stamp = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(f"{label} must be a UTC timestamp ending in Z.") from exc
    if stamp.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError(f"Invalid {label}.")


def _inside(root: Path, value, label: str, *, nonempty=True) -> Path:
    rel = aw._relative_posix(value, label)
    target = root / rel
    aw._ensure_no_links(root, target)
    if not target.is_file() or (nonempty and target.stat().st_size == 0):
        raise ValueError(f"{label} must reference an existing nonempty file: {value}")
    return target


def _paths(root: Path, values, label: str, *, required=False) -> list[Path]:
    if not isinstance(values, list) or (required and not values):
        raise ValueError(f"{label} must be {'a nonempty' if required else 'a'} list of file paths.")
    if any(not isinstance(v, str) for v in values) or len(set(values)) != len(values):
        raise ValueError(f"{label} must contain unique path strings.")
    return [_inside(root, value, label) for value in values]


def _identity(doc: dict) -> dict:
    project = doc.get("project", {})
    if not isinstance(project, dict):
        raise ValueError("project must be a table.")
    task_id = _text(project.get("task_id"), "project.task_id")
    if not aw.TASK_ID_RE.fullmatch(task_id):
        raise ValueError("Invalid task ID.")
    revision = project.get("revision")
    if type(revision) is not int or revision < 1:
        raise ValueError("project.revision must be a positive integer.")
    task_version = f"{task_id}-r{revision}"
    if project.get("task_version_id", task_version) != task_version:
        raise ValueError("project.task_version_id does not match task identity.")
    return dict(task_id=task_id, revision=revision, task_version_id=task_version,
                stage=_text(project.get("stage", "unspecified"), "project.stage"))


def _task_identity(task_doc: dict, identity: dict) -> None:
    metadata = task_doc.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Task metadata table is required.")
    if metadata.get("task_id") != identity["task_id"] or type(metadata.get("revision")) is not int or metadata.get("revision") != identity["revision"]:
        raise ValueError("Task package identity differs from run identity.")
    for key in ("stage", "task_version_id"):
        if key in metadata and metadata[key] != identity[key]:
            raise ValueError(f"Task metadata.{key} differs from run identity.")


def workspace_eda(project: dict) -> str:
    """Old manifests are ADS; new EDA manifests declare their product explicitly."""
    eda = project.get("eda", "ads")
    if eda not in ("ads", "virtuoso"):
        raise ValueError("Unsupported workspace EDA.")
    return eda


def workspace_module(eda: str):
    if eda == "ads":
        return aw
    if eda == "virtuoso":
        if __package__:
            from . import virtuoso_workspace
        else:
            import virtuoso_workspace
        return virtuoso_workspace
    raise ValueError("Unsupported workspace EDA.")


def load_registry(path: Path) -> dict:
    registry = tomllib.loads(path.read_text(encoding="utf-8"))
    if registry.get("schema_version") != 1 or not isinstance(registry.get("workflows"), dict):
        raise ValueError("Workflow registry requires schema_version = 1 and workflows tables.")
    return registry


def select_task_source(repo: Path, workspace: Path, identity: dict) -> tuple[Path, str]:
    """Use the authoritative package or an exactly verified isolated-host snapshot."""
    task = repo / "tasks" / identity["task_id"]
    aw._ensure_no_links(repo, task)
    if task.exists():
        return task, "authoritative-task-package"
    snapshot = workspace / "inputs" / "task-spec"
    aw._ensure_no_links(workspace, snapshot)
    errors = []
    aw._validate_manifest_snapshot(snapshot, identity["task_id"], identity["revision"], errors)
    if errors:
        raise ValueError("Task snapshot is not verified: " + "; ".join(errors))
    return snapshot, "verified-workspace-task-snapshot"


def resolve_route(registry: Path, *, task: Path | None = None, workflow: str | None = None,
                  eda: str | None = None, kind: str | None = None,
                  deliverables: list[str] | None = None) -> dict:
    """An existing task profile takes precedence; conflicting explicit overrides fail."""
    profile = {}
    if task is not None and (task / "engineering.toml").exists():
        aw._ensure_no_links(task, task / "engineering.toml")
        profile = tomllib.loads((task / "engineering.toml").read_text(encoding="utf-8"))
        allowed = {"schema_version", "eda", "workflow", "kind", "deliverables", "inputs"}
        if profile.get("schema_version") != 1 or set(profile) - allowed:
            raise ValueError("engineering.toml has an unsupported schema or field.")
        for key in ("eda", "workflow", "kind", "deliverables"):
            if key not in profile:
                raise ValueError(f"engineering.toml requires {key}.")
        _paths(task, profile.get("inputs", []), "engineering.inputs")
    supplied = dict(eda=eda, workflow=workflow, kind=kind, deliverables=deliverables)
    for key, value in supplied.items():
        if key in profile and value is not None and value != profile[key]:
            raise ValueError(f"Explicit {key} conflicts with the existing task engineering.toml.")
    chosen_eda = profile.get("eda", eda)
    chosen_workflow = profile.get("workflow", workflow)
    if chosen_workflow is None:
        chosen_workflow = {"ads": "ads-generic", "virtuoso": "virtuoso"}.get(chosen_eda)
    entry = load_registry(registry)["workflows"].get(chosen_workflow)
    if not isinstance(entry, dict):
        raise ValueError(f"Unknown workflow {chosen_workflow!r}; select an available workflow explicitly.")
    actual_eda = _text(entry.get("eda"), "workflow.eda")
    if chosen_eda is not None and chosen_eda != actual_eda:
        raise ValueError("Selected EDA and workflow disagree.")
    status = entry.get("status")
    if status not in ("implemented", "reserved"):
        raise ValueError("Workflow status must be implemented or reserved.")
    chosen_kind = profile.get("kind", kind or "design")
    groups = profile.get("deliverables", deliverables if deliverables is not None else ["source"])
    if chosen_kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}.")
    if not isinstance(groups, list) or not groups or any(g not in DELIVERABLES for g in groups) or len(set(groups)) != len(groups):
        raise ValueError(f"deliverables must be unique values from {DELIVERABLES}.")
    if actual_eda == "virtuoso" and status == "implemented" and set(groups) - {"source", "simulation"}:
        raise ValueError("The implemented Virtuoso workflow supports source and simulation only.")
    return dict(eda=actual_eda, workflow=chosen_workflow, version=_text(entry.get("version"), "workflow.version"),
                status=status, kind=chosen_kind, deliverables=groups,
                selection_basis="task-profile" if profile else "explicit-or-default")


def initialize_run(run: Path, workspace: Path, *, registry: Path | None = None,
                   workflow: str | None = None, kind: str | None = None,
                   deliverables: list[str] | None = None, repo: Path | None = None) -> dict:
    workspace = workspace.resolve()
    aw._ensure_no_links(workspace, run)
    project = tomllib.loads((workspace / "project.toml").read_text(encoding="utf-8"))
    identity = _identity(project)
    repo = repo or workspace.parent.parent
    task, _ = select_task_source(repo, workspace, identity)
    registry = registry or aw.default_repo_root() / "engineering" / "workflows.toml"
    route = resolve_route(registry, task=task, eda=workspace_eda(project), workflow=workflow,
                          kind=kind, deliverables=deliverables)
    record = dict(
        schema_version=1, task=identity, run_id=run.name, created_utc=utc_now(), started_utc=None, ended_utc=None,
        eda=route["eda"], workflow=dict(id=route["workflow"], version=route["version"]),
        kind=route["kind"], deliverables=route["deliverables"], state="planned",
        selection=dict(candidate=None, native_design=None),
        readiness=dict(status="draft", scope="", brief=None, confirmed_by="", confirmed_utc=None), preflight=None,
        outcomes={key: dict(status="pending", evidence=[]) for key in FACETS},
        evidence={key: [] for key in ROLES}, gaps=[], notes=[], contract=None,
    )
    write_json(run / "run.json", record)
    return record


def _inventory(root: Path, *, exclude=()) -> list[dict]:
    files = []
    for parent, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            aw._ensure_no_links(root, Path(parent) / name)
        for name in sorted(names):
            path = Path(parent) / name
            rel = path.relative_to(root).as_posix()
            if rel in exclude:
                continue
            size, digest = aw._sha256_file(path)
            files.append(dict(path=rel, bytes=size, sha256=digest))
    return sorted(files, key=lambda item: item["path"])


def _execution_plan(record):
    plan = {key: record[key] for key in ("eda", "kind", "deliverables")}
    if "environment" in record:
        plan["environment"] = record["environment"]
    return plan


def _check_environment(run, record):
    if "environment" not in record:
        return
    reference = record["environment"]
    if not isinstance(reference, dict) or reference.get("plan") != "environment-plan.json":
        raise ValueError("Invalid environment plan reference.")
    path = _inside(run, reference["plan"], "environment plan")
    if aw._sha256_file(path)[1] != reference.get("sha256"):
        raise ValueError("Environment plan integrity mismatch.")
    plan = read_json(path)
    if plan.get("schema_version") != 1 or plan.get("status") != "planned":
        raise ValueError("Environment selection was not successfully planned.")
    for key in ("task", "workflow", "run_id"):
        if plan.get(key) != record.get(key):
            raise ValueError("Environment plan differs from the run: " + key)


def _verify_inventory(root: Path, manifest: dict, *, exclude=()) -> None:
    listed = manifest.get("files")
    if not isinstance(listed, list) or not listed:
        raise ValueError("Integrity manifest must list files.")
    for item in listed:
        if not isinstance(item, dict):
            raise ValueError("Invalid integrity file record.")
        _inside(root, item.get("path"), "integrity file", nonempty=False)
    if _inventory(root, exclude=exclude) != listed:
        raise ValueError("Frozen inventory integrity mismatch (missing, changed, or additional files).")


def _load_run(run: Path) -> dict:
    if aw._is_link(run) or aw._is_link(run.parent):
        raise ValueError("A run directory cannot be linked.")
    aw._ensure_no_links(run, run / "run.json")
    return read_json(run / "run.json")


def freeze_contract(run: Path, repo: Path) -> dict:
    """Create once-only task, workflow and helper snapshots before execution."""
    record = _load_run(run)
    if record.get("state") != "planned" or record.get("contract") is not None or (run / "seal.json").exists():
        raise ValueError("Only an unfrozen planned run may freeze its contract.")
    if (run / "contract").exists():
        raise FileExistsError("contract/ already exists; preserve it and allocate a fresh run.")
    task_id = record.get("task", {}).get("task_id")
    _text(task_id, "task.task_id")
    if not aw.TASK_ID_RE.fullmatch(task_id):
        raise ValueError("Invalid task ID.")
    task, source_kind = select_task_source(repo, run.parent.parent, record["task"])
    task_doc = tomllib.loads(_inside(task, "task.toml", "task metadata").read_text(encoding="utf-8"))
    _task_identity(task_doc, record["task"])
    registry_path = repo / "engineering" / "workflows.toml"
    route = resolve_route(registry_path, task=task, workflow=record["workflow"]["id"], eda=record["eda"],
                          kind=record["kind"], deliverables=record["deliverables"])
    if route["version"] != record["workflow"]["version"]:
        raise ValueError("Workflow changed since run allocation; allocate a fresh run.")
    registry = load_registry(registry_path)
    entry = registry["workflows"][route["workflow"]]
    resources = entry.get("documents", [])
    if not isinstance(resources, list) or any(not isinstance(p, str) for p in resources):
        raise ValueError("workflow.documents must be a list of repository-relative file paths.")
    for name in ("task.toml", "instruction.md", "verification-plan.md"):
        _inside(task, name, "required task file")
    selected_files = {path.name for path in task.iterdir()
                      if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in (".md", ".toml")}
    if (task / "engineering.toml").exists():
        task_profile = tomllib.loads((task / "engineering.toml").read_text(encoding="utf-8"))
        selected_files.update(task_profile.get("inputs", []))
    copies = [(_inside(task, rel, "task input"), f"task/{rel}") for rel in sorted(selected_files)]
    source_provenance = dict(kind=source_kind)
    if source_kind == "verified-workspace-task-snapshot":
        copies.append((task / "manifest.json", "task-source-manifest.json"))
        source_provenance["receipt"] = "task-source-manifest.json"
    helpers = ["scripts/virtuoso_workspace.py"] if record["eda"] == "virtuoso" else []
    for rel in dict.fromkeys(["engineering/workflows.toml", "scripts/ads_workspace.py", "scripts/engineering_runs.py", *helpers, *resources]):
        copies.append((_inside(repo, rel, "workflow resource"), f"workflow/{rel}"))
    if "environment" in record:
        _check_environment(run, record)
        copies.append((_inside(run, record["environment"]["plan"], "environment plan"), "execution/environment-plan.json"))
    # Read all inputs before writing so a missing resource leaves no partial snapshot.
    payloads = []
    for source, rel in copies:
        source_root = task if source.is_relative_to(task) else repo
        aw._ensure_no_links(source_root, source)
        data = source.read_bytes()
        if not data:
            raise ValueError(f"Empty contract input: {source.name}")
        payloads.append((rel, data))
    contract = run / "contract"
    aw._ensure_no_links(run, contract)
    contract.mkdir()
    for rel, data in payloads:
        target = contract / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    plan = _execution_plan(record)
    manifest = dict(schema_version=1, task=record["task"], workflow=record["workflow"], execution_plan=plan,
                    source=source_provenance, frozen_utc=utc_now(), files=_inventory(contract))
    write_json(contract / "manifest.json", manifest)
    record["contract"] = dict(path="contract/manifest.json", sha256=aw._sha256_file(contract / "manifest.json")[1])
    aw._write_lf(run / "run.json", json.dumps(record, indent=2, allow_nan=False) + "\n", overwrite=True)
    return manifest


def _check_contract(run: Path, record: dict) -> dict:
    contract = record.get("contract")
    if not isinstance(contract, dict) or contract.get("path") != "contract/manifest.json":
        raise ValueError("Freeze the task and workflow contract before execution.")
    path = _inside(run, contract["path"], "contract manifest")
    if aw._sha256_file(path)[1] != contract.get("sha256"):
        raise ValueError("Contract manifest integrity mismatch.")
    manifest = read_json(path)
    if manifest.get("task") != record.get("task") or manifest.get("workflow") != record.get("workflow"):
        raise ValueError("Frozen contract identity differs from the run.")
    if manifest.get("execution_plan") != _execution_plan(record):
        raise ValueError("Frozen execution plan differs from the run; do not change EDA, kind or deliverables after freezing.")
    _verify_inventory(path.parent, manifest, exclude=("manifest.json",))
    task = path.parent / "task"
    task_doc = tomllib.loads((task / "task.toml").read_text(encoding="utf-8"))
    _task_identity(task_doc, record["task"])
    registry = path.parent / "workflow" / "engineering" / "workflows.toml"
    route = resolve_route(registry, task=task, workflow=record["workflow"]["id"], eda=record["eda"],
                          kind=record["kind"], deliverables=record["deliverables"])
    if route["version"] != record["workflow"]["version"] or route["status"] != "implemented":
        raise ValueError("Selected workflow is reserved, changed, or unavailable for execution.")
    return route


def _check_preflight(run: Path, record: dict) -> None:
    path = _inside(run, record.get("preflight"), "preflight")
    observed = read_json(path)
    if observed.get("schema_version") != 1 or observed.get("status") != "ready":
        raise ValueError("Preflight requires schema_version = 1 and status = ready.")
    _timestamp(observed.get("observed_utc"), "preflight.observed_utc")
    for key, expected in (("eda", record["eda"]), ("task_version_id", record["task"]["task_version_id"]),
                          ("native_design", record["selection"]["native_design"])):
        if observed.get(key) != expected:
            raise ValueError(f"Preflight {key} differs from the selected run.")
    for key in ("workspace", "models"):
        item = observed.get(key)
        allowed = ("verified",) if key == "workspace" else ("verified", "conditional", "not-applicable")
        if not isinstance(item, dict) or item.get("status") not in allowed:
            raise ValueError(f"Preflight {key} status is not ready for this run.")
        _paths(run, item.get("evidence"), f"preflight.{key}.evidence", required=True)
        if item.get("status") != "verified":
            _text(item.get("reason"), f"preflight.{key}.reason")
    # The evidence must be actual retained tool observations; this checker cannot
    # infer live host/model readiness merely from files or operator assertions.


def _check_record(run: Path, record: dict, phase: str) -> None:
    _check_environment(run, record)
    if type(record.get("schema_version")) is not int or record.get("schema_version") != 1:
        raise ValueError("run.json requires schema_version = 1.")
    if not aw.RUN_ID_RE.fullmatch(run.name) or record.get("run_id") != run.name:
        raise ValueError("run_id must match the UTC-named run directory.")
    identity = _identity({"project": record.get("task")})
    if identity != record.get("task"):
        raise ValueError("Invalid task identity fields.")
    # A run copied under another declared workspace must not inherit that
    # workspace's identity accidentally. Standalone run handoffs remain usable.
    owner_manifest = run.parent.parent / "project.toml"
    if owner_manifest.is_file():
        aw._ensure_no_links(run.parent.parent, owner_manifest)
        owner_doc = tomllib.loads(owner_manifest.read_text(encoding="utf-8"))
        owner = _identity(owner_doc)
        if owner != identity:
            raise ValueError("Run task identity differs from its owning workspace project.toml.")
        if workspace_eda(owner_doc) != record.get("eda"):
            raise ValueError("Run EDA differs from its owning workspace project.toml.")
    _timestamp(record.get("created_utc"), "created_utc")
    for name in ("started_utc", "ended_utc"):
        if record.get(name) is not None:
            _timestamp(record[name], name)
    if record.get("state") not in ("planned", "running", *TERMINAL):
        raise ValueError("Invalid run state.")
    if record.get("kind") not in KINDS:
        raise ValueError("Invalid task kind.")
    _text(record.get("eda"), "eda")
    workflow = record.get("workflow")
    if not isinstance(workflow, dict):
        raise ValueError("workflow must identify its id and version.")
    for key in ("id", "version"):
        _text(workflow.get(key), f"workflow.{key}")
    groups = record.get("deliverables")
    if not isinstance(groups, list) or not groups or any(g not in DELIVERABLES for g in groups) or len(set(groups)) != len(groups):
        raise ValueError("deliverables must contain unique supported groups.")
    for field in ("gaps", "notes"):
        items = record.get(field)
        if not isinstance(items, list):
            raise ValueError(f"{field} must be a list.")
        for value in items:
            _text(value, field)
    evidence = record.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != set(ROLES):
        raise ValueError("evidence must contain exactly the supported evidence roles.")
    for role in ROLES:
        _paths(run, evidence[role], f"evidence.{role}")
    outcomes = record.get("outcomes")
    if not isinstance(outcomes, dict) or set(outcomes) != set(FACETS):
        raise ValueError("outcomes must contain the four independent facets.")
    for key, statuses in FACETS.items():
        facet = outcomes[key]
        if not isinstance(facet, dict) or facet.get("status") not in statuses:
            raise ValueError(f"Invalid outcomes.{key}.status.")
        _paths(run, facet.get("evidence"), f"outcomes.{key}.evidence")
    selection = record.get("selection")
    if not isinstance(selection, dict):
        raise ValueError("selection must identify candidate and native_design.")
    for key in ("candidate", "native_design"):
        if selection.get(key) is not None:
            _text(selection[key], f"selection.{key}")
    if phase == "scaffold":
        return
    _check_contract(run, record)
    readiness = record.get("readiness")
    if not isinstance(readiness, dict) or readiness.get("status") != "confirmed":
        raise ValueError("Task readiness and authorized scope must be explicitly confirmed.")
    for key in ("scope", "confirmed_by"):
        _text(readiness.get(key), f"readiness.{key}")
    _inside(run, readiness.get("brief"), "readiness.brief")
    _timestamp(readiness.get("confirmed_utc"), "readiness.confirmed_utc")
    _text(selection.get("native_design"), "selection.native_design")
    _check_preflight(run, record)
    if phase == "ready":
        return
    if record.get("state") != "completed":
        raise ValueError("A successful handoff requires state = completed; archive failures with explicit gaps.")
    _timestamp(record.get("started_utc"), "started_utc")
    _timestamp(record.get("ended_utc"), "ended_utc")
    if record["ended_utc"] < record["started_utc"]:
        raise ValueError("ended_utc cannot precede started_utc.")
    if record["gaps"]:
        raise ValueError("Successful delivery cannot have unresolved gaps.")
    if outcomes["execution"]["status"] != "completed" or outcomes["delivery"]["status"] != "complete":
        raise ValueError("Successful handoff requires execution completed and delivery complete.")
    for key, facet in outcomes.items():
        if facet["status"] in ("pending", "running", "incomplete"):
            raise ValueError(f"outcomes.{key} has not reached a reportable conclusion.")
        if facet["status"] == "not-applicable":
            _text(facet.get("reason"), f"outcomes.{key}.reason")
        else:
            _paths(run, facet["evidence"], f"outcomes.{key}.evidence", required=True)
    required = {"native_source"}
    if "layout" in groups:
        required.add("layout")
    if "simulation" in groups or "em" in groups:
        required.update(("simulator_log", "raw_data", "measurements", "check_report"))
        if outcomes["electrical"]["status"] == "not-applicable":
            raise ValueError("Simulation/EM delivery requires an electrical result, including a failure if observed.")
    if "simulation" in groups:
        required.add("netlist")
    if "em" in groups:
        required.update(("em_setup", "solver_input"))
    for role in required:
        _paths(run, evidence[role], f"evidence.{role}", required=True)


def check_run(run: Path, phase: str = "scaffold") -> dict:
    errors = []
    try:
        if phase not in ("scaffold", "ready", "handoff"):
            raise ValueError("Unknown check phase.")
        record = _load_run(run)
        _check_record(run, record, phase)
        if (run / "seal.json").exists():
            manifest = read_json(_inside(run, "seal.json", "seal"))
            if type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != 1:
                raise ValueError("Invalid seal schema version.")
            if manifest.get("run_id") != record["run_id"] or manifest.get("state") != record["state"]:
                raise ValueError("Seal identity/state differs from the run record.")
            _timestamp(manifest.get("sealed_utc"), "seal.sealed_utc")
            _verify_inventory(run, manifest, exclude=("seal.json",))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return dict(status="error" if errors else "ok", phase=phase, errors=errors,
                scope="Recorded identity, evidence presence and integrity only; electrical conclusions require task-specific review.")


def close_run(run: Path) -> dict:
    if (run / "seal.json").exists():
        raise FileExistsError("This run is already sealed; preserve it and record amendments in a fresh run.")
    record = _load_run(run)
    state = record.get("state")
    if state not in TERMINAL:
        raise ValueError("Set a terminal run state before closing.")
    _check_record(run, record, "handoff" if state == "completed" else "scaffold")
    if state != "completed":
        if not record["gaps"] or record["outcomes"]["delivery"]["status"] != "incomplete":
            raise ValueError("Failed/interrupted runs require explicit gaps and delivery = incomplete.")
        if record["outcomes"]["execution"]["status"] != state:
            raise ValueError("Execution outcome must match the failed/interrupted state.")
        _timestamp(record.get("ended_utc"), "ended_utc")
        for key in ("electrical", "models"):
            facet = record["outcomes"][key]
            if facet["status"] not in ("pending", "not-applicable"):
                _paths(run, facet["evidence"], f"outcomes.{key}.evidence", required=True)
            elif facet["status"] == "not-applicable":
                _text(facet.get("reason"), f"outcomes.{key}.reason")
        if record.get("contract") is not None:
            # Reserved/draft routes can be archived without claiming execution
            # readiness, but frozen bytes must still match their receipt.
            path = _inside(run, record["contract"]["path"], "contract manifest")
            if aw._sha256_file(path)[1] != record["contract"].get("sha256"):
                raise ValueError("Contract manifest integrity mismatch.")
            _verify_inventory(path.parent, read_json(path), exclude=("manifest.json",))
    manifest = dict(schema_version=1, run_id=run.name, sealed_utc=utc_now(), state=state,
                    files=_inventory(run))
    write_json(run / "seal.json", manifest)
    if "environment" in record:
        _update_run_entrypoint(run, record)
    return dict(status="sealed", run_id=run.name, state=state)


def _update_run_entrypoint(run: Path, record: dict) -> None:
    """Link a closed prepared run without changing any retained evidence."""
    workspace = run.parent.parent
    if not (workspace / "project.toml").is_file():
        return
    target = workspace / "README.md"
    aw._ensure_no_links(workspace, target)
    existing = target.read_text(encoding="utf-8") if target.exists() else "# Engineering workspace\n"
    start, end = "<!-- engineering-run-index:start -->", "<!-- engineering-run-index:end -->"
    relative = run.relative_to(workspace).as_posix()
    lines = [start, "## Latest retained engineering run", "",
             f"Run: [{run.name}]({relative}/run.json).",
             f"Selected native design: `{record['selection'].get('native_design') or 'not selected'}`.", "",
             "| Facet | Recorded outcome |", "|---|---|"]
    lines.extend(f"| {key} | {value['status']} |" for key, value in record["outcomes"].items())
    for role in ("native_source", "check_report"):
        for index, path in enumerate(record["evidence"][role], 1):
            lines.extend(["", f"[{role} {index}]({relative}/{path})"])
    lines.extend(["", "This index describes the retained run; electrical acceptance follows its actual task reports.", end])
    block = "\n".join(lines)
    if start in existing and end in existing:
        before, remainder = existing.split(start, 1)
        _, after = remainder.split(end, 1)
        updated = before + block + after
    else:
        updated = existing.rstrip() + "\n\n" + block + "\n"
    aw._write_lf(target, updated, overwrite=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    route = sub.add_parser("route", help="Resolve a task profile or explicit workflow without starting tools")
    route.add_argument("--registry", type=Path, default=aw.default_repo_root() / "engineering" / "workflows.toml")
    route.add_argument("--task", type=Path)
    route.add_argument("--workflow")
    route.add_argument("--eda")
    route.add_argument("--kind", choices=KINDS)
    route.add_argument("--deliverables", help="Comma-separated deliverable groups")
    for command in ("environment", "prepare"):
        entry = sub.add_parser(command, help="Select the lab environment" if command == "environment" else "Prepare a local workspace, run and delegation package after lab environment selection")
        entry.add_argument("--repo", type=Path, default=aw.default_repo_root())
        entry.add_argument("--task", required=True, type=Path)
        entry.add_argument("--workspace", type=Path)
        entry.add_argument("--workflow")
        entry.add_argument("--kind", choices=KINDS)
        entry.add_argument("--deliverables")
        entry.add_argument("--host")
        entry.add_argument("--platform", choices=("windows", "linux"))
        entry.add_argument("--cpus", type=int)
        entry.add_argument("--memory-gib", type=float)
        entry.add_argument("--client", help="Calling lab client whose MCP binding is verified; required when several clients are registered")
        if command == "prepare":
            entry.add_argument("--slug", required=True)
            entry.add_argument("--model-policy", choices=aw.MODEL_POLICIES, default="restricted-pdk")
            entry.add_argument("--block-key")
            entry.add_argument("--dut-cell")
            entry.add_argument("--dut-ports")
    freeze = sub.add_parser("freeze", help="Freeze the exact task, workflow and helper input before execution")
    freeze.add_argument("--run", required=True, type=Path)
    freeze.add_argument("--repo", type=Path, default=aw.default_repo_root())
    check = sub.add_parser("check", help="Check scaffold, recorded readiness, or completed handoff")
    check.add_argument("--run", required=True, type=Path)
    check.add_argument("--phase", choices=("scaffold", "ready", "handoff"), default="scaffold")
    close = sub.add_parser("close", help="Seal an explicitly concluded run without changing its evidence")
    close.add_argument("--run", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "route":
            result = resolve_route(args.registry, task=args.task, workflow=args.workflow, eda=args.eda,
                                   kind=args.kind, deliverables=args.deliverables.split(",") if args.deliverables else None)
        elif args.command in ("environment", "prepare"):
            if __package__:
                from . import engineering_environment as environment
            else:
                import engineering_environment as environment
            options = dict(workspace=args.workspace, workflow=args.workflow, kind=args.kind,
                           deliverables=args.deliverables.split(",") if args.deliverables else None,
                           host=args.host, platform=args.platform, cpus=args.cpus, memory_gib=args.memory_gib,
                           client=args.client)
            if args.command == "prepare":
                options.update(slug=args.slug, model_policy=args.model_policy, block_key=args.block_key,
                               dut_cell=args.dut_cell, dut_ports=args.dut_ports.split(",") if args.dut_ports else None)
            function = environment.prepare_task if args.command == "prepare" else environment.environment_plan
            result = function(args.repo, args.task, **options)
        elif args.command == "freeze":
            freeze_contract(args.run, args.repo)
            result = dict(status="frozen", run_id=args.run.name)
        elif args.command == "check":
            result = check_run(args.run, args.phase)
        else:
            result = close_run(args.run)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") == "blocked" else (1 if result.get("status") == "error" else 0)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"engineering_runs: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
