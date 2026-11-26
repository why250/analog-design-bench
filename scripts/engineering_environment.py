"""Select an environment with an external lab planner, then prepare a task-owned run.

Only local scaffolding and records are written. No EDA session, SSH command,
simulation or remote directory is created by this module.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

if __package__:
    from . import ads_workspace as aw
    from . import engineering_runs as er
else:
    import ads_workspace as aw
    import engineering_runs as er


def task_context(repo, task, workspace=None):
    repo, task = Path(repo).resolve(), Path(task).resolve()
    aw._ensure_no_links(repo, task)
    if task.parent != repo / "tasks":
        raise ValueError("Select an authoritative task directly below this repository's tasks directory.")
    doc = tomllib.loads((task / "task.toml").read_text(encoding="utf-8"))
    metadata = doc["metadata"]
    task_id = metadata["task_id"]
    if task.name != task_id or not aw.TASK_ID_RE.fullmatch(task_id):
        raise ValueError("Task identity does not match its directory.")
    profile_path = task / "engineering.toml"
    aw._ensure_no_links(task, profile_path)
    eda = tomllib.loads(profile_path.read_text(encoding="utf-8")).get("eda", "ads") if profile_path.exists() else "ads"
    er.workspace_module(eda)
    if workspace is None:
        matches = []
        for path in (repo / "workspaces").glob("*/project.toml"):
            aw._ensure_no_links(repo, path)
            project = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {})
            if project.get("task_id") == task_id:
                matches.append(path.parent)
        if len(matches) > 1:
            raise ValueError("Multiple existing workspaces match; explicitly select the intended workspace.")
        workspace = matches[0] if matches else repo / "workspaces" / task_id
    workspace = Path(workspace).resolve()
    aw._ensure_no_links(repo, workspace)
    if workspace.parent != repo / "workspaces":
        raise ValueError("Workspace must be directly below the repository workspaces directory.")
    if workspace.exists():
        project = tomllib.loads((workspace / "project.toml").read_text(encoding="utf-8"))
        identity = er._identity(project)
        er._task_identity(doc, identity)
        if er.workspace_eda(project) != eda:
            raise ValueError("Existing workspace EDA conflicts with the task profile.")
    else:
        identity = er._identity({"project": metadata})
    binding_path = repo / ".local" / (eda + "-projects") / (task_id + ".json")
    aw._ensure_no_links(repo, binding_path)
    binding = er.read_json(binding_path) if binding_path.exists() else {}
    if binding.get("task_id", task_id) != task_id or binding.get("revision", identity["revision"]) != identity["revision"]:
        raise ValueError("Existing private task binding has a different identity or revision; reconcile it before preparing a new run.")
    return repo, task, workspace, identity, binding


def environment_plan(repo, task, *, workspace=None, workflow=None, kind=None, deliverables=None,
                     host=None, platform=None, cpus=None, memory_gib=None, client=None):
    repo, task, workspace, identity, task_binding = task_context(repo, task, workspace)
    route = er.resolve_route(repo / "engineering/workflows.toml", task=task,
                             eda=None if (task / "engineering.toml").exists() else "ads",
                             workflow=workflow, kind=kind, deliverables=deliverables)
    if route["status"] != "implemented" or route["eda"] not in ("ads", "virtuoso"):
        raise ValueError("This engineering execution branch is reserved or not implemented.")
    binding_path = repo / ".local/eda-lab.json"
    aw._ensure_no_links(repo, binding_path)
    if not binding_path.exists():
        raise ValueError("Connect this project with the lab register_project/bind-project command first; "
                         "no execution environment was guessed.")
    binding = er.read_json(binding_path)
    if binding.get("schema_version") not in (1, 2):
        raise ValueError("Unsupported lab project binding.")
    lab_root = Path(binding["lab_root"])
    request = {"schema_version": 1, "project": identity["task_id"],
               "task": "virtuoso" if route["eda"] == "virtuoso" else ("em" if "em" in route["deliverables"] else "ads"),
               "resources": {}}
    if route["eda"] == "virtuoso":
        selected_tools = task_binding.get("required_tools", {})
        if (not isinstance(selected_tools, dict) or any(not isinstance(selected_tools.get(key), str)
                or not selected_tools[key].strip() for key in ("virtuoso", "spectre"))):
            raise ValueError("Record the lab-selected Virtuoso and Spectre versions in the private task binding required_tools before preparation.")
        request["required_tools"] = {key: selected_tools[key] for key in ("virtuoso", "spectre")}
    for key, value in (("host", host), ("platform", platform), ("ssh_alias", task_binding.get("ssh_alias"))):
        if value is not None:
            request[key] = value
    for key, value in (("logical_cpus", cpus), ("memory_gib", memory_gib)):
        if value is not None:
            request["resources"][key] = value
    # These fields name a task workspace, not its nested native project.
    remote_workspace = task_binding.get("remote_project") or task_binding.get("planned_remote_workspace")
    if remote_workspace:
        request["workspace_root"] = remote_workspace
    command = [binding.get("python_executable") or sys.executable, str(lab_root / "scripts/lab.py"),
               "plan", "-", "--project", str(repo), "--workspace-suffix", workspace.relative_to(repo).as_posix()]
    if client:
        command.extend(["--client", client])
    try:
        child_env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        done = subprocess.run(command, input=json.dumps(request, allow_nan=False), encoding="utf-8", env=child_env,
                              capture_output=True, timeout=45, cwd=repo)
        plan = json.loads(done.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ValueError("Lab planning failed before returning a valid plan: " + type(exc).__name__) from None
    if done.returncode not in (0, 2) or plan.get("status") not in ("planned", "blocked"):
        raise ValueError("Lab planner returned an unexpected result; no native work was started.")
    if plan["status"] == "planned" and task_binding.get("mcp_server"):
        if task_binding["mcp_server"] != plan["project_binding"]["mcp_name"]:
            raise ValueError("Existing task MCP binding conflicts with the selected project interface.")
    if plan["status"] == "planned" and route["eda"] == "virtuoso":
        if plan.get("task") != "virtuoso" or plan.get("project_binding", {}).get("status") != "configured":
            raise ValueError("Virtuoso planning requires the configured calling-client product binding.")
        if any(plan.get("required_tools", {}).get(key) != version for key, version in request["required_tools"].items()):
            raise ValueError("Lab plan does not retain both selected Virtuoso and Spectre versions.")
    return dict(schema_version=1, status=plan["status"], task=identity, workflow=route,
                workspace=workspace.relative_to(repo).as_posix(), lab_request=request, lab_plan=plan,
                execution=dict(submitted=False, ready=False, remote_writes=False))


def prepare_task(repo, task, *, slug, workspace=None, model_policy="restricted-pdk", block_key=None,
                 dut_cell=None, dut_ports=None, **constraints):
    # Route and validate the actual consumer MCP entry before creating local scaffolding.
    result = environment_plan(repo, task, workspace=workspace, **constraints)
    if result["status"] == "blocked":
        return result
    repo, task, workspace, identity, _ = task_context(repo, task, workspace)
    if not aw.SLUG_RE.fullmatch(slug):
        raise ValueError("Run slug must use lowercase kebab-case.")
    if not workspace.exists():
        if not block_key:
            raise ValueError("Choose a block key for the new task before preparing its native workspace.")
        module = er.workspace_module(result["workflow"]["eda"])
        options = dict(task_id=identity["task_id"], stage=identity["stage"], revision=identity["revision"],
                       model_policy=model_policy, block_key=block_key,
                       dut_lib=f"{block_key}_R{identity['revision']:02d}_lib",
                       dut_cell=dut_cell or f"{block_key}_Main", dut_ports=dut_ports)
        if result["workflow"]["eda"] == "ads":
            options["with_tools"] = True
        workspace = module.init_workspace(repo, **options)
    module = er.workspace_module(result["workflow"]["eda"])
    validation = module.validate_workspace(repo, workspace, require_v2=False)
    if validation["errors"]:
        raise ValueError("Workspace validation failed: " + "; ".join(validation["errors"]))
    route = result["workflow"]
    run = module.allocate_run_dir(workspace, slug, registry=repo / "engineering/workflows.toml", repo=repo,
                              workflow=route["workflow"], kind=route["kind"], deliverables=route["deliverables"])
    project = tomllib.loads((workspace / "project.toml").read_text(encoding="utf-8"))
    paths = project["paths"]
    native_key = route["eda"]
    native_rel = aw._relative_posix(paths[native_key], "paths." + native_key).as_posix()
    run_rel = run.relative_to(workspace).as_posix()
    private_ref = f"engineering-runs/{identity['task_id']}/{run.name}/environment.json"
    private_path = repo / ".local" / private_ref
    aw._ensure_no_links(repo, private_path)
    plan = result["lab_plan"]
    remote_workspace = plan.get("workspace_root")
    private = {**result, "run_id": run.name, "paths": {
        "local_workspace": str(workspace), "local_run": str(run),
        "remote_workspace": remote_workspace,
        "remote_native": remote_workspace.rstrip("/\\") + "/" + native_rel if remote_workspace else None,
        "remote_" + native_key: remote_workspace.rstrip("/\\") + "/" + native_rel if remote_workspace else None,
        "remote_run": remote_workspace.rstrip("/\\") + "/" + run_rel if remote_workspace else None,
    }}
    private_path.parent.mkdir(parents=True, exist_ok=True)
    er.write_json(private_path, private)
    summary = dict(schema_version=1, status="planned", task=identity, run_id=run.name,
                   workflow=dict(id=route["workflow"], version=route["version"]),
                   route=plan["task"], host=plan["selected_host"], platform=plan["platform"],
                   required_tools=plan["required_tools"], requested_resources=plan["requested_resources"],
                   planning_ceiling=plan["planning_ceiling"], private_binding_ref=private_ref,
                   paths={"workspace": result["workspace"], "native": native_rel, native_key: native_rel, "results": run_rel},
                   pending_checks=plan["pending_checks"], execution=result["execution"])
    er.write_json(run / "environment-plan.json", summary)
    record = er.read_json(run / "run.json")
    record["environment"] = dict(plan="environment-plan.json", sha256=aw._sha256_file(run / "environment-plan.json")[1])
    design = project.get("design", {})
    if design.get("dut_lib") and design.get("dut_cell"):
        record["selection"]["native_design"] = f"{design['dut_lib']}:{design['dut_cell']}:schematic"
    brief = ("# Prepared engineering execution brief\n\n"
             f"Task: {identity['task_version_id']}\nWorkflow: {route['workflow']} {route['version']}\n"
             f"Workspace: {result['workspace']}\nNative source: {native_rel}\nRun: {run_rel}\n"
             f"Environment plan: environment-plan.json\nPrivate binding reference: {private_ref}\n\n"
             "Read the frozen task and verification plan under contract/task/. "
             "Use the private receipt to select the actual host, MCP entry and output paths. "
             "Keep one writer on the primary native workspace. Keep this run's logs, "
             "input snapshots and results together.\n\n"
             "Scope and existing authorization: pending review against the user's request. "
             "Populate the budget, stop rules, required evidence and deferred work using "
             "the frozen delegation template before marking readiness confirmed. "
             "This scaffold does not start EDA, authorize a new license or approve GUI work.\n\n"
             "Return actual native source and the requested simulation/layout/EM evidence. "
             "Record execution completion, electrical acceptance, model applicability and "
             "delivery completeness independently in run.json. The main agent reviews the "
             "returned files before handoff checking and closeout.\n")
    aw._write_lf(run / "delegation.md", brief)
    record["readiness"]["brief"] = "delegation.md"
    aw._write_lf(run / "run.json", json.dumps(record, indent=2, allow_nan=False) + "\n", overwrite=True)
    er.freeze_contract(run, repo)
    check = er.check_run(run, "scaffold")
    if check["status"] != "ok":
        raise ValueError("Prepared run failed scaffold checks: " + "; ".join(check["errors"]))
    return dict(status="prepared", workspace=result["workspace"], run=run.relative_to(repo).as_posix(),
                native_design=record["selection"]["native_design"], environment_plan="environment-plan.json",
                private_receipt=".local/" + private_ref, workflow=route,
                scaffold=check, execution=result["execution"],
                next_action="Review the prepared brief and actual environment, then perform the existing ready and handoff checks.")
