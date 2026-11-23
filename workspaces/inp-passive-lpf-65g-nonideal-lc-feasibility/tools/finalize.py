"""Audit and document a completed untuned study; optionally package its evidence.

This entrypoint needs NumPy and the retained files, not an active ADS session.
The original simulator evidence and initial summaries remain unchanged.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

try:
    from . import handoff, reporting, project_config
except ImportError:
    import handoff, reporting, project_config


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8", newline="\n")


def finish(project, root, *, package=False):
    config = project_config.load_project(project)
    project, root = config["project_root"], Path(root).resolve()
    if not root.is_relative_to(config["paths"]["results"]):
        raise ValueError("The run must belong to this task's configured results directory")
    aggregate_path = root / "aggregate.json"
    existing = json.loads(aggregate_path.read_text(encoding="utf-8")) if aggregate_path.exists() else {}
    readonly = existing.get("study_state") == "COMPLETE"
    original_audit = root / "handoff-audit.json"
    completed_utc = (json.loads(original_audit.read_text(encoding="utf-8")).get("created_utc")
                     if readonly and original_audit.exists() else None)
    requests=json.loads((root/"requests.json").read_text(encoding="utf-8"))["requests"]
    combined=[r for r in requests if r["family"] in {"E6","E8"}]
    states={r["case_id"]:json.loads((root/"cases"/r["case_id"]/"summary.json").read_text(encoding="utf-8"))["state"] for r in combined}
    if not readonly and combined and all(value=="FAIL" for value in states.values()):
        n6=sum(r["family"]=="E6" for r in combined);n8=sum(r["family"]=="E8" for r in combined)
        write_json(root/"stage-decision.json", {
            "decision":"TOPOLOGY REVIEW REQUIRED",
            "recorded_utc":datetime.now(timezone.utc).isoformat(),
            "rationale":f"All {n6} combined-coefficient E6 requests and all {n8} E8 slice samples fail the unchanged specification. Passing loss-only cases establish useful partial bounds, but no explored joint loss/parasitic sample establishes an envelope suitable for direct PDK mapping. This engineering judgment therefore requires reviewing the fixed nominal design before mapping, while PDK data acquisition can proceed.",
            "evidence_case_ids":sorted(states),
            "scope":"Untuned fixed nine-arm nominal ladder and the declared synthetic ranges only. Optional same-topology retuning was not executed. No global topology impossibility, process capability or authorization for a new topology is inferred."})
    if readonly:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        audit=handoff.audit(root, output_dir=root/"handoff"/stamp/"revalidation")
    else:
        reporting.aggregate(root)
        audit=handoff.audit(root)
    if not audit["ok"]:
        return {"complete":False,"audit_ok":False,"issues":audit["issues"]}
    final=existing if readonly else reporting.aggregate(root)
    if final["study_state"]!="COMPLETE":
        return {"complete":False,"audit_ok":True,"issues":final["completion_issues"]}
    units=json.loads((root/"unit-summary.json").read_text(encoding="utf-8"))
    repeat=json.loads((root/"reproduction.json").read_text(encoding="utf-8"))
    boundary=json.loads((root/"boundary-search.json").read_text(encoding="utf-8"))
    max_error=max(r["complex_crosscheck_error"] for r in audit["cases"])
    e6_states={}
    for row in requests:
        if row["family"]=="E6":e6_states[states[row["case_id"]]]=e6_states.get(states[row["case_id"]],0)+1
    completion_date = (datetime.fromisoformat(completed_utc.replace("Z", "+00:00")).date().isoformat()
                       if completed_utc else datetime.now(timezone.utc).date().isoformat())
    run_href=Path(os.path.relpath(root,config["paths"]["docs"])).as_posix()
    lines=["# Stage 2 execution record", "",
        f"Completed in UTC on {completion_date}; run `{root.name}`.", "",
        f"Study: **{final['study_state']}**. Primary stage decision: **{final['pdk_readiness']}**.", "",
        f"Retained {final['request_mapping_count']} filter request mappings and {final['unique_case_count']} unique physical circuits; candidate states: {json.dumps(final['case_state_counts'],sort_keys=True)}. E9 adds three fresh-workspace repetitions. E1 retains {units['valid_count']}/{units['scheduled_count']} valid isolated-device runs.", "",
        f"E6 combined-case request states: {json.dumps(e6_states,sort_keys=True)}. E8 retained {boundary['additional_requests_retained']} additional parameter requests over its 20 seeds. Every sampled interval and unsearched interior remains explicit.", "",
        f"The maximum absolute ADS/independent complex-S disagreement over the unique filter cases is {max_error:.12g} (limit 1e-6). All cases passed full-matrix passivity, reciprocity, exact checkpoint, dense-grid, actual-model extrema and tracked local-refinement checks. The ideal recovery additionally passed unitarity.", "",
        f"Fresh-workspace repetitions passed {repeat['passed_count']}/{repeat['scheduled_count']} comparisons, with frozen sweeps, source/settings comparisons, exact saved-netlist diffs and OA snapshots taken after lock release.", "",
        "The necessary DC common-Q bound of approximately 35.59 is weaker than RF requirements: loss-only Q=60 fails insertion loss, whereas Q=100 and Q=200 pass. The complete measured conditional envelope and individual failures are retained in the report; these two points do not establish a universal Q threshold.", "",
        "The criterion-based readiness and the documented engineering judgment are both retained. Single-effect passing samples do not establish feasibility of the explored joint nonideal circuits. Same-topology retuning remains an optional follow-up after this untuned study.", "",
        f"Read the [full report]({run_href}/report.md), [learning record]({run_href}/learning.md), [audit]({run_href}/handoff-audit.json), and [reproduction evidence]({run_href}/reproduction.json).", "",
        "The specification-stage task documents are preserved as the frozen research contract. This execution record supersedes their historical 'not executed' status only for this retained study. No official benchmark score or SPICE submission was produced. All coefficients are synthetic; no InP process, layout/EM, temperature-range, corner or yield claim follows.", ""]
    config["paths"]["docs"].mkdir(parents=True,exist_ok=True)
    (config["paths"]["docs"]/"execution-record.md").write_text("\n".join(lines),encoding="utf-8",newline="\n")
    result={"complete":True,"audit_ok":True,"study_state":final["study_state"],"pdk_readiness":final["pdk_readiness"],
            "case_state_counts":final["case_state_counts"],"unique_cases":final["unique_case_count"],
            "requests":final["request_mapping_count"],"max_complex_error":max_error,
            "completed_evidence_read_only":readonly}
    if package:result["handoff"]=handoff.package(project,root)
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project",type=Path,required=True)
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--package",action="store_true")
    args=parser.parse_args()
    result=finish(args.project,args.run,package=args.package)
    if result.get("handoff",{}).get("receipt"):
        destination=Path(result["handoff"]["receipt"]).parent
    else:
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:8]
        destination=args.run/"handoff"/stamp
        destination.mkdir(parents=True,exist_ok=False)
    write_json(destination/"finalization.json",result)
    print(json.dumps(result,indent=2,allow_nan=False))
    raise SystemExit(0 if result["complete"] else 1)
