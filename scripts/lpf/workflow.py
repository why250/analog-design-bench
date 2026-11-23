"""Run one LPF design stage at a time and retain its review checkpoint."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tomllib
from uuid import uuid4

from .specification import normalize_spec


REPO = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT = REPO / "workspaces" / "inp-passive-lpf-parametric"
# Real device bindings stay in ignored local configuration; the committed
# profile is a neutral example of the same schema.
_LOCAL_PROFILE = REPO / ".local" / "profiles" / "private-inp.toml"
DEFAULT_PROFILE = _LOCAL_PROFILE if _LOCAL_PROFILE.exists() else Path(__file__).resolve().parent / "profiles" / "example-inp.toml"
STAGES = ("ideal", "search", "layout")


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id():
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(data, output, indent=2, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def lock_run(run):
    """Release the run lock on process exit, including interrupted stages."""
    with (run / ".lock").open("a+b") as lock:
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError(f"Another stage is active for {run}") from error
        yield


def load_state(run):
    state = read_json(run / "checkpoint.json")
    if state.get("schema_version") != 1:
        raise ValueError("Unsupported run checkpoint version")
    return state


def load_frozen_spec(run, state):
    source = (run / "spec.toml").read_bytes()
    if sha256(source).hexdigest() != state["spec_sha256"]:
        raise ValueError("The frozen specification changed. Start a revision from a new spec file.")
    return normalize_spec(tomllib.loads(source.decode("utf-8")))


def create_run(project, spec_path, parent=None, *, source=None, task=None, upstream=None):
    if source is None:
        source = spec_path.read_bytes()
    spec = normalize_spec(tomllib.loads(source.decode("utf-8")))
    if parent is not None:
        load_frozen_spec(parent, load_state(parent))
    results = task["results"] if task else project / "results"
    run = results / new_id()
    run.mkdir(parents=True)
    (run / "spec.toml").write_bytes(source)
    write_json(run / "spec.json", spec)
    state = {
        "schema_version": 1,
        "created_at": timestamp(),
        "spec_sha256": sha256(source).hexdigest(),
        "previous_run": str(parent) if parent else None,
        "state": {"lpf-pcell": "search_pending", "lpf-layout": "layout_pending"}.get(
            task["identity"]["stage"] if task else None, "ideal_pending",
        ),
        "ideal_approval": None,
        "layout_selection": None,
        "attempts": {stage: [] for stage in STAGES},
    }
    if task:
        state["task"] = task["identity"]
        state["task_project"] = Path(os.path.relpath(project, run)).as_posix()
        if upstream is not None:
            state["upstream"] = upstream.relative_to(project).as_posix()
            if task["identity"]["stage"] == "lpf-pcell":
                state["ideal_approval"] = {"attempt": state["upstream"], "approved_at": timestamp()}
        frozen = run / "task-spec"
        frozen.mkdir()
        for name in ("task.toml", "instruction.md", "verification-plan.md", "DEVELOPMENT.md"):
            (frozen / name).write_bytes((task["task_dir"] / name).read_bytes())
    write_json(run / "checkpoint.json", state)
    return run


def current_task(run, state):
    if "task" not in state:
        return None
    from .task_handoff import load_task

    task = load_task((run / state["task_project"]).resolve())
    if task is None or task["identity"] != state["task"] or run.parent != task["results"]:
        raise ValueError("The run does not match the current task and workspace revision")
    return task


def upstream_result(run, state, stage):
    from .task_handoff import load_handoff

    task = current_task(run, state)
    snapshot = (task["project"] / state["upstream"]).resolve()
    if not snapshot.is_relative_to(task["inputs"]):
        raise ValueError("The upstream handoff must be under the task's inputs directory")
    result, source = load_handoff(snapshot, task, stage)
    if source != (run / "spec.toml").read_bytes():
        raise ValueError("The run and upstream handoff specifications disagree")
    return result, snapshot


def start_attempt(run, state, stage):
    out = run / stage / uuid4().hex[:8]
    out.mkdir(parents=True)
    record = {"path": out.relative_to(run).as_posix(), "status": "running", "started_at": timestamp()}
    for previous in state["attempts"][stage]:
        if previous["status"] == "running":
            previous.update(status="interrupted", ended_at=timestamp())
    state["attempts"][stage].append(record)
    write_json(run / "checkpoint.json", state)
    return out, record


def run_attempt(run, state, stage, action):
    out, record = start_attempt(run, state, stage)
    try:
        result, next_state = action(out)
        write_json(out / "result.json", result)
    except Exception as error:
        record.update(status="failed", ended_at=timestamp(), error=str(error))
        write_json(run / "checkpoint.json", state)
        print(f"{stage} failed: {error}", file=sys.stderr)
        return 1
    record.update(status="completed", ended_at=timestamp())
    state["state"] = next_state
    write_json(run / "checkpoint.json", state)
    return 0


def ideal_stage(args, run, state, spec):
    if state["state"] not in {"ideal_pending", "review_ideal"}:
        raise ValueError("The ideal stage is already frozen. Create a revision to change it.")

    def action(out):
        from .ideal import run_ideal

        workspace = out / "ads" / "ideal_wrk" if args.ads else None
        if workspace is not None:
            workspace.parent.mkdir()
        result = run_ideal(spec, out, workspace)
        ready = result.get("passed") is True and result.get("verification") == "ads"
        return result, "review_ideal" if ready else "ideal_pending"

    return run_attempt(run, state, "ideal", action)


def latest_completed(state, stage):
    for attempt in reversed(state["attempts"][stage]):
        if attempt["status"] == "completed":
            return attempt["path"]
    raise ValueError(f"No completed {stage} attempt is available")


def search_stage(args, run, state, spec):
    if state.get("task", {}).get("stage") == "lpf-pcell":
        if state["state"] not in {"search_pending", "review_pcell"}:
            raise ValueError("The PCell task needs an approved ideal handoff")
        ideal_result, _ = upstream_result(run, state, "ideal")
        ideal = state["upstream"]
    elif state["state"] == "review_ideal":
        if not args.approve_ideal:
            raise ValueError("Review the ideal results and pass --approve-ideal to begin PCell search")
        ideal = latest_completed(state, "ideal")
        ideal_result = read_json(run / ideal / "result.json")
    elif state["state"] in {"search_pending", "review_pcell"}:
        ideal = state["ideal_approval"]["attempt"]
        ideal_result = read_json(run / ideal / "result.json")
    else:
        raise ValueError("Complete and review the native ADS ideal stage before PCell search")
    if args.sample_index is None and args.ads_source is None:
        raise ValueError("Provide --sample-index or an ADS source workspace with --ads-source")

    profile_source = args.profile.read_bytes()
    profile = tomllib.loads(profile_source.decode("utf-8"))
    if ideal_result.get("passed") is not True or ideal_result.get("verification") != "ads":
        raise ValueError("The reviewed attempt no longer has passing native ideal verification")
    design = ideal_result["design"]
    budgets = {
        "paired_cases": args.paired_cases, "unpaired_cases": args.unpaired_cases,
        "ads_runs": args.ads_runs, "new_samples": args.new_samples,
    }
    if state["ideal_approval"] is None:
        state["ideal_approval"] = {"attempt": ideal, "approved_at": timestamp()}
        state["state"] = "search_pending"

    def action(out):
        from .review import write_pcell_review
        from .search import run_search

        (out / "profile.toml").write_bytes(profile_source)
        write_json(out / "search-inputs.json", {
            "ideal_attempt": ideal,
            "profile_sha256": sha256(profile_source).hexdigest(),
            "sample_index": str(args.sample_index) if args.sample_index else None,
            "ads_source": str(args.ads_source) if args.ads_source else None,
            "budgets": budgets,
        })
        result = run_search(
            spec, design, profile, out, sample_index=args.sample_index,
            ads_workspace=args.ads_source, budgets=budgets,
        )
        write_pcell_review(out / "review.md", result)
        return result, "review_pcell"

    return run_attempt(run, state, "search", action)


def select_candidate(args, run, state):
    if not args.candidate:
        raise ValueError("Select a candidate ID with --candidate")
    search_path = latest_completed(state, "search")
    if args.search_attempt:
        search_path = f"search/{args.search_attempt}"
        if not any(record["path"] == search_path and record["status"] == "completed"
                   for record in state["attempts"]["search"]):
            raise ValueError("The requested PCell search attempt is unavailable")
    search_out = run / search_path
    search = read_json(search_out / "result.json")
    matches = [entry for entry in search.get("candidates", []) if entry["id"] == args.candidate]
    if len(matches) != 1:
        raise ValueError("Select a candidate ID from the specified PCell search result")
    candidate = matches[0]
    if (candidate.get("verification") != "ads" or not candidate.get("ads_workspace")
            or candidate.get("model_status") not in {"qualified", "conditional"}):
        raise ValueError("Layout needs a native ADS candidate with complete, applicable model evidence")
    if candidate.get("passes") is not True and not args.accept_near_miss:
        raise ValueError("The candidate missed the specification. Use --accept-near-miss only after review.")

    workspace = (search_out / candidate["ads_workspace"]).resolve(strict=True)
    if not workspace.is_dir() or not workspace.is_relative_to(search_out.resolve()):
        raise ValueError("The selected native workspace must be retained in the search attempt")
    profile_source = (search_out / "profile.toml").read_bytes()
    search_inputs = read_json(search_out / "search-inputs.json")
    if sha256(profile_source).hexdigest() != search_inputs["profile_sha256"]:
        raise ValueError("The selected candidate's device profile changed. Run a new PCell search.")
    return candidate, search_path, search_out, workspace, profile_source


def layout_stage(args, run, state):
    if state["state"] not in {"review_pcell", "layout_pending", "layout_ready"}:
        raise ValueError("Complete and review a PCell search before building a layout")
    if state.get("task", {}).get("stage") == "lpf-layout":
        candidate, snapshot = upstream_result(run, state, "search")
        search_path = state["upstream"]
        if args.search_attempt or (args.candidate and args.candidate != candidate["id"]):
            raise ValueError("The layout task uses the candidate selected in its frozen handoff")
        profile_source = (snapshot / "profile.toml").read_bytes()
        workspace = snapshot / "ads"
    else:
        candidate, search_path, _, workspace, profile_source = select_candidate(args, run, state)
    profile = tomllib.loads(profile_source.decode("utf-8"))
    state["layout_selection"] = {
        "candidate": candidate["id"], "search_attempt": search_path,
        "selected_at": timestamp(), "accepted_near_miss": candidate.get("passes") is not True,
    }
    state["state"] = "layout_pending" if state.get("task") else "review_pcell"

    def action(out):
        from .ads_layout import build_layout

        write_json(out / "selected-candidate.json", candidate)
        result = build_layout(candidate, profile, out, ads_workspace=workspace)
        return result, "layout_ready" if result.get("verified") is True else state["state"]

    return run_attempt(run, state, "layout", action)


def handoff_stage(args, run, state, source_task):
    from .task_handoff import freeze_handoff, load_task

    target_task = load_task(args.project)
    if source_task is None or target_task is None:
        raise ValueError("Handoff requires separately authored source and destination LPF tasks")
    source_role = source_task["identity"]["stage"]
    target_role = target_task["identity"]["stage"]
    if source_role == "lpf-ideal" and target_role == "lpf-pcell":
        if (state["state"] != "review_ideal" or not args.approve_ideal or args.candidate
                or args.search_attempt or args.accept_near_miss):
            raise ValueError("Review the native ideal result and select --approve-ideal for the PCell handoff")
        stage = "ideal"
        attempt = run / latest_completed(state, stage)
        result = read_json(attempt / "result.json")
        if result.get("passed") is not True or result.get("verification") != "ads":
            raise ValueError("The ideal handoff needs passing native ADS verification")
        evidence = {path.name: path for path in attempt.iterdir() if path.name != "result.json"}
    elif source_role == "lpf-pcell" and target_role == "lpf-layout":
        if state["state"] != "review_pcell" or args.approve_ideal:
            raise ValueError("Review a completed PCell search and select its native candidate for layout")
        stage = "search"
        result, _, attempt, workspace, _ = select_candidate(args, run, state)
        result = {
            **result, "ads_workspace": "ads",
            "accepted_near_miss": result.get("passes") is not True,
        }
        evidence = {"ads": workspace, "profile.toml": attempt / "profile.toml"}
        for name in ("review.md", "search-inputs.json"):
            if (attempt / name).is_file():
                evidence[name] = attempt / name
        for path in workspace.parent.iterdir():
            if path != workspace:
                evidence[f"verification/{path.name}"] = path
        if result.get("native_touchstone"):
            result["native_touchstone"] = "verification/native.s2p"
        result.pop("screen_touchstone", None)
    else:
        raise ValueError("Handoff order is ideal synthesis, PCell search, then editable layout")

    source = (run / "spec.toml").read_bytes()
    snapshot = freeze_handoff(
        args.project, source_task, target_task, stage=stage, spec_bytes=source,
        result=result, evidence=evidence, source_run=run.name, source_attempt=attempt.relative_to(run).as_posix(),
    )
    destination = create_run(args.project, None, source=source, task=target_task, upstream=snapshot)
    print(json.dumps(status(destination, load_state(destination)), indent=2))
    return 0


def status(run, state):
    review = {
        "ideal_pending": "Complete native ADS ideal verification.",
        "review_ideal": "Review the ideal result before approving PCell search.",
        "search_pending": "Resume the approved PCell search.",
        "review_pcell": "Review candidate loss, margin and model validity before selecting a layout candidate.",
        "layout_pending": "Build the editable layout from the approved native candidate handoff.",
        "layout_ready": "Review the editable layout. Coupled full-wave validation is a separate stage.",
    }
    if state.get("task"):
        review["review_ideal"] = "Review and hand off the ideal result to the authored PCell task."
        review["review_pcell"] = "Review and hand off a selected native candidate to the authored layout task."
    return {
        "run": str(run), "state": state["state"], "next_decision": review[state["state"]],
        "previous_run": state["previous_run"], "layout_selection": state["layout_selection"],
        "task": state.get("task"), "upstream": state.get("upstream"),
        "attempts": state["attempts"],
    }


def count(value):
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("expected a nonnegative integer")
    return parsed


def absolute(value):
    return Path(value).expanduser().resolve()


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="stage", required=True)
    ideal = sub.add_parser("ideal", help="Synthesize, verify and stop for ideal review")
    inputs = ideal.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--spec", type=absolute)
    inputs.add_argument("--run", type=absolute, help="Retry an existing ideal stage")
    ideal.add_argument("--project", type=absolute, default=DEFAULT_PROJECT)
    ideal.add_argument("--revise", type=absolute, help="Record the prior run for a changed specification")
    ideal.add_argument("--ads", action="store_true", help="Build and verify in an ADS-capable Python environment")

    search = sub.add_parser("search", help="Search PCell sizes and stop before layout")
    search.add_argument("--run", required=True, type=absolute)
    search.add_argument("--approve-ideal", action="store_true")
    search.add_argument("--profile", type=absolute, default=DEFAULT_PROFILE)
    search.add_argument("--sample-index", type=absolute)
    search.add_argument("--ads-source", type=absolute, help="Existing ADS workspace with licensed PCells and EM caches")
    search.add_argument("--paired-cases", type=count, default=3000)
    search.add_argument("--unpaired-cases", type=count, default=1000)
    search.add_argument("--ads-runs", type=count, default=5)
    search.add_argument("--new-samples", type=count, default=8)

    layout = sub.add_parser("layout", help="Generate editable layout for a reviewed native candidate")
    layout.add_argument("--run", required=True, type=absolute)
    layout.add_argument("--candidate", help="Candidate ID for a single-run workflow")
    layout.add_argument("--search-attempt")
    layout.add_argument("--accept-near-miss", action="store_true", help="Retain the electrical failure on an explicitly selected candidate")

    handoff = sub.add_parser("handoff", help="Freeze a reviewed result for a separate downstream task")
    handoff.add_argument("--run", required=True, type=absolute)
    handoff.add_argument("--project", required=True, type=absolute, help="Authored downstream task workspace")
    handoff.add_argument("--approve-ideal", action="store_true")
    handoff.add_argument("--candidate")
    handoff.add_argument("--search-attempt")
    handoff.add_argument("--accept-near-miss", action="store_true")

    inspect = sub.add_parser("status", help="Read the saved progress and pending decision")
    inspect.add_argument("--run", required=True, type=absolute)
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        run = args.run
        if args.stage == "ideal":
            if args.revise and run:
                raise ValueError("--revise needs a new --spec")
            if run is None:
                from .task_handoff import load_task

                task = load_task(args.project)
                if task and task["identity"]["stage"] != "lpf-ideal":
                    raise ValueError("Start this task from an approved upstream handoff")
                run = create_run(args.project, args.spec, args.revise, task=task)
        state = load_state(run)
        if args.stage == "status":
            print(json.dumps(status(run, state), indent=2))
            return 0
        with lock_run(run):
            state = load_state(run)
            spec = load_frozen_spec(run, state)
            task = current_task(run, state)
            if args.stage == "handoff":
                return handoff_stage(args, run, state, task)
            expected_stage = {"ideal": "lpf-ideal", "search": "lpf-pcell", "layout": "lpf-layout"}
            if task and task["identity"]["stage"] != expected_stage[args.stage]:
                raise ValueError("This action belongs to a different task. Use an approved handoff.")
            if args.stage == "ideal":
                code = ideal_stage(args, run, state, spec)
            elif args.stage == "search":
                code = search_stage(args, run, state, spec)
            else:
                code = layout_stage(args, run, state)
            print(json.dumps(status(run, state), indent=2))
            return code
    except (OSError, ValueError) as error:
        print(f"LPF workflow: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
