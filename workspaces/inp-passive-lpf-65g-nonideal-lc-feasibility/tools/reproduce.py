"""Replay the three mandatory E9 cases in fresh native ADS workspaces.

Original evidence is never overwritten. Frequency lists, resolved coefficients
and native input source are compared explicitly. Portable native snapshots are
taken only after switching away from the replay workspace and checking its OA
lock files. This module makes no official benchmark acceptance claim.
"""

from __future__ import annotations

from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import uuid

import numpy as np


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n",
                          encoding="utf-8", newline="\n")


def _utc():
    return datetime.now(timezone.utc).isoformat()


def compare_netlists(original, repeated, diff_path):
    """Retain an exact textual diff and narrowly classify any byte difference."""
    original, repeated, diff_path = Path(original), Path(repeated), Path(diff_path)
    before, after = original.read_bytes(), repeated.read_bytes()
    before_text, after_text = before.decode("utf-8-sig"), after.decode("utf-8-sig")
    byte_identical = before == after
    # keepends=True retains original CRLF/LF in changed lines. The files remain
    # the authority for exact bytes; the sidecar hashes identify both inputs.
    difference = "".join(difflib.unified_diff(before_text.splitlines(keepends=True),
        after_text.splitlines(keepends=True), fromfile="original/schematic.net",
        tofile="repeated/schematic.net"))
    diff_path.write_text(difference, encoding="utf-8", newline="")
    def executable_lines(text):
        return [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith(";")]
    executable_equal = executable_lines(before_text) == executable_lines(after_text)
    if byte_identical:
        classification = "exact_bytes_identical"
        explanation = "The saved netlist bytes and SHA-256 values are identical."
    elif before_text.splitlines() == after_text.splitlines():
        classification = "line_encoding_or_line_ending_only"
        explanation = "Decoded line contents are identical; saved-byte encoding or line endings differ. Both exact hashes and the original files are retained."
    elif executable_equal:
        classification = "comment_or_blank_lines_only"
        explanation = "All executable netlist lines compare exactly after splitting line endings. Only semicolon comment or blank lines differ; the exact diff is retained. No circuit statement was normalized."
    else:
        classification = "executable_statement_difference"
        explanation = "At least one executable netlist line differs. This requires diagnosis and cannot pass automatically as a path/header difference."
    return {"original_saved_bytes_sha256": hashlib.sha256(before).hexdigest(),
            "repeated_saved_bytes_sha256": hashlib.sha256(after).hexdigest(),
            "exact_byte_identity": byte_identical, "executable_lines_identical": executable_equal,
            "difference_class": classification, "explanation": explanation,
            "exact_text_diff": diff_path.name, "acceptable_identity": byte_identical or executable_equal}


def _source_comparison(original, repeated):
    """Separate exact reconstruction-input identity from ancillary script updates."""
    original, repeated = Path(original), Path(repeated)
    names = sorted({p.name for p in original.glob("*.py")} | {p.name for p in repeated.glob("*.py")})
    files = []
    for name in names:
        before, after = original/name, repeated/name
        before_sha = _sha(before) if before.is_file() else None
        after_sha = _sha(after) if after.is_file() else None
        files.append({"name": name, "original_sha256": before_sha, "repeated_sha256": after_sha,
                      "identical": before_sha is not None and before_sha == after_sha})
    critical = ("model.py", "build_ads.py")
    if (original/"ads_support.py").exists() or (repeated/"ads_support.py").exists():
        critical += ("ads_support.py",)
    by_name = {row["name"]: row for row in files}
    return {"critical_native_input_sources": list(critical),
            "critical_native_input_sources_identical": all(by_name.get(name, {}).get("identical", False) for name in critical),
            "all_captured_python_sources_identical": bool(files) and all(row["identical"] for row in files),
            "files": files,
            "scope": "model.py, build_ads.py and the captured ads_support.py helper define native literal coefficients, terminals and connections. Legacy records without the extracted helper retain their original two-file contract. Ancillary source changes remain visible."}


def compare_frozen_settings(original, repeated):
    """Keep raw settings while recognizing one documented wording-only change."""
    keys = ("task_version", "baseline_commit", "testbench", "ordered_ports",
            "reference_impedance_ohm", "temperature_deg_c", "temperature_law", "sweeps")
    absent_law_wordings = {
        "none; bookkeeping",
        "none; metadata only; no native temperature sweep or physical temperature claim",
    }
    result = {}
    for key in keys:
        before, after = original.get(key), repeated.get(key)
        identical = before == after
        equivalent = (not identical and key == "temperature_law"
                      and isinstance(before, str) and isinstance(after, str)
                      and before in absent_law_wordings and after in absent_law_wordings)
        result[key] = {"original": before, "repeated": after, "identical": identical,
                       "metadata_equivalent": equivalent, "acceptable": identical or equivalent}
        if equivalent:
            result[key].update({"equivalence": "declared_absent_coefficient_temperature_law_wording_only",
                "reason": "These two exact retained metadata strings both declare no coefficient temperature law. The newer wording clarifies that 25 degC is bookkeeping metadata, with no native temperature sweep or physical-temperature claim. temperature_deg_c is compared separately and exactly; no circuit setting or physical coefficient is normalized."})
    return result


def compare_evidence(original, repeated):
    """Compare retained original/replay files without running ADS."""
    try:
        from . import analysis, model
    except ImportError:
        import analysis
        import model
    original, repeated = Path(original), Path(repeated)
    original_manifest = _read(original/"manifest.json")
    repeated_manifest = _read(repeated/"manifest.json")
    original_settings = _read(original/"settings.json")
    repeated_settings = _read(repeated/"settings.json")
    original_summary = _read(original/"summary.json")
    repeated_summary = _read(repeated/"summary.json")
    f0, s0 = analysis.read_csv(original/"ads_sparameters.csv")
    f1, s1 = analysis.read_csv(repeated/"ads_sparameters.csv")
    same_count = len(f0) == len(f1)
    maximum_frequency_error = float(np.max(abs(f1-f0))) if same_count else None
    maximum_s_error = float(np.max(abs(s1-s0))) if same_count else None
    frequency_ok = bool(same_count and maximum_frequency_error <= 1.)
    complex_ok = bool(same_count and maximum_s_error <= 1e-6)
    native_input_sources = _source_comparison(original/"source-inputs", repeated/"source-inputs")
    netlists = compare_netlists(original/"schematic.net", repeated/"schematic.net", repeated/"netlist-exact.diff")
    frozen_settings = compare_frozen_settings(original_settings, repeated_settings)
    changed_settings = {key: {"original": original_settings.get(key), "repeated": repeated_settings.get(key)}
        for key in sorted(set(original_settings) | set(repeated_settings))
        if original_settings.get(key) != repeated_settings.get(key)}
    _write(repeated/"settings-exact-differences.json", changed_settings)
    original_hash_valid = original_settings.get("netlist_saved_bytes_sha256") == netlists["original_saved_bytes_sha256"]
    repeated_hash_valid = repeated_settings.get("netlist_saved_bytes_sha256") == netlists["repeated_saved_bytes_sha256"]
    original_physical = model.physical_hash(original_manifest)
    repeated_physical = model.physical_hash(repeated_manifest)
    checks = {"resolved_coefficients_identical": original_physical == repeated_physical,
              "frozen_settings_compatible": all(row["acceptable"] for row in frozen_settings.values()),
              "critical_native_input_sources_identical": native_input_sources["critical_native_input_sources_identical"],
              "frequency_list_within_1hz": frequency_ok,
              "all_complex_s_within_1e_minus6": complex_ok,
              "generated_netlist_identity": netlists["acceptable_identity"],
              "original_saved_netlist_hash_valid": original_hash_valid,
              "repeated_saved_netlist_hash_valid": repeated_hash_valid,
              "original_numerically_valid": original_summary.get("state") in ("PASS", "FAIL"),
              "repeated_numerically_valid": repeated_summary.get("state") in ("PASS", "FAIL"),
              "electrical_state_reproduced": original_summary.get("state") == repeated_summary.get("state")}
    return {"compared_utc": _utc(), "checks": checks,
            "comparison_passed_before_portable_snapshot": all(checks.values()),
            "frequency_count_original": len(f0), "frequency_count_repeated": len(f1),
            "maximum_frequency_difference_hz": maximum_frequency_error,
            "maximum_complex_s_difference": maximum_s_error,
            "frequency_tolerance_hz": 1., "complex_s_tolerance": 1e-6,
            "original_state": original_summary.get("state"), "repeated_state": repeated_summary.get("state"),
            "original_physical_sha256": original_physical, "repeated_physical_sha256": repeated_physical,
            "netlist": netlists, "source": native_input_sources,
            "frozen_settings": frozen_settings,
            "all_frozen_settings_identical": all(row["identical"] for row in frozen_settings.values()),
            "all_settings_differences": "settings-exact-differences.json"}


def _locks(workspace):
    return [str(path.relative_to(workspace)).replace("\\", "/") for path in Path(workspace).rglob("*")
            if path.is_file() and (".cdslck" in path.name.lower() or path.suffix.lower() == ".lck"
                                   or path.name.startswith(".ads_lock"))]


def _portable_snapshot(workspace, idle, destination, build_ads, runner, de):
    """Release through the existing unsaved-design guard before reading OA files."""
    workspace, idle, destination = Path(workspace).resolve(), Path(idle).resolve(), Path(destination)
    if destination.exists():
        manifest_path = destination.parent/"portable-native-manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("Preserved portable snapshot has no integrity manifest")
        saved = _read(manifest_path)
        saved["current_snapshot_hashes_valid"] = all((destination/row["path"]).is_file() and
            (destination/row["path"]).stat().st_size == row["bytes"] and
            _sha(destination/row["path"]) == row["sha256"] for row in saved["files"])
        return saved
    # This helper checks unsaved app designs and refuses to switch until clean.
    build_ads._support._switch_workspace(idle)
    build_ads._last_build = None
    active = Path(de.active_workspace().path).resolve() if de.workspace_is_open() else None
    if active == workspace:
        raise RuntimeError("Replay workspace remains active; portable snapshot is unsafe")
    remaining_locks = _locks(workspace)
    if remaining_locks:
        raise RuntimeError("OA lock files remain after switching away: "+", ".join(remaining_locks))
    runner._native_snapshot(workspace, destination)
    files = [{"path": str(path.relative_to(destination)).replace("\\", "/"),
              "bytes": path.stat().st_size, "sha256": _sha(path)}
             for path in sorted(destination.rglob("*")) if path.is_file()]
    if not files or not any(row["path"].endswith(".oalib") for row in files):
        raise RuntimeError("Portable native source is missing OA library metadata")
    result = {"created_utc": _utc(), "snapshot_after_workspace_release": True,
              "release_method": "Task-owned ADS support checked unsaved designs and closed the replay workspace before snapshot",
              "remaining_oa_lock_files": remaining_locks, "current_snapshot_hashes_valid": True,
              "files": files}
    _write(destination.parent/"portable-native-manifest.json", result)
    return result


def _aggregate(root, requests):
    root = Path(root)
    comparisons = []
    for row in requests:
        path = root/"reproductions"/row["request_id"]/"comparison.json"
        if path.exists():
            value = _read(path)
            comparisons.append({"request_id": row["request_id"], "case_id": row["case_id"],
                "comparison_passed": value.get("comparison_passed", False),
                "maximum_frequency_difference_hz": value.get("maximum_frequency_difference_hz"),
                "maximum_complex_s_difference": value.get("maximum_complex_s_difference"),
                "netlist_exact_byte_identity": value.get("netlist", {}).get("exact_byte_identity"),
                "portable_native_manifest": f"reproductions/{row['request_id']}/portable-native-manifest.json"})
    result = {"updated_utc": _utc(), "scheduled_count": len(requests), "completed_count": len(comparisons),
              "passed_count": sum(row["comparison_passed"] for row in comparisons),
              "e9_complete": len(comparisons) == 3 and all(row["comparison_passed"] for row in comparisons),
              "comparisons": comparisons,
              "scope": "Fresh native-workspace replay of E0, anchor B and the mandatory near-resonance case; no official benchmark acceptance claim"}
    _write(root/"reproduction.json", result)
    checks_path = root/"study_checks.json"
    if checks_path.exists():
        checks = _read(checks_path)
        checks["e9_complete"] = result["e9_complete"]
        _write(checks_path, checks)
    return result


def run(root, workspace_parent=None, limit=1):
    """Replay up to ``limit`` pending E9 selections, with a fresh workspace each.

    Execute in ADS Python. Completed simulation directories can resume the
    comparison/snapshot step, but an unfinished simulation is never overwritten.
    A study-owned idle workspace releases OA locks between selected replays.
    """
    try:
        from . import build_ads, cases, run_study as runner
    except ImportError:
        import build_ads
        import cases
        import run_study as runner
    from keysight.ads import de
    root = Path(root).resolve()
    work_root = root / "work"
    workspace_parent = (work_root / "reproductions" if workspace_parent is None
                        else Path(workspace_parent)).resolve()
    if not root.is_dir() or limit < 1:
        raise ValueError("Expected an existing study root and a positive limit")
    if not workspace_parent.is_relative_to(work_root):
        raise ValueError("Fresh E9 workspaces belong under the run's work directory")
    workspace_parent.mkdir(parents=True, exist_ok=True)
    frozen = _read(root/"requests.json")
    requests = frozen.get("e9_repetitions") or cases.repetition_requests(frozen["requests"])
    if len(requests) != 3 or any(row["family"] != "E9" for row in requests):
        raise ValueError("Expected the three frozen mandatory E9 repetition requests")
    journal_path = root/"reproduction-workspaces.json"
    journal = _read(journal_path) if journal_path.exists() else {"created_utc": _utc(), "allocations": {}}
    idle = workspace_parent/"idle_wrk"
    new_results = []
    for selection_index, row in enumerate(requests, 1):
        original = root/"cases"/row["case_id"]
        destination = root/"reproductions"/row["request_id"]
        if (destination/"comparison.json").exists():
            continue
        if not (original/"summary.json").exists():
            raise RuntimeError(f"Original E9 selection has no completed evidence: {row['case_id']}")
        settings = _read(original/"settings.json")
        sweeps = [(r["analysis"], r["start_hz"], r["stop_hz"], r["points"]) for r in settings["sweeps"]]
        if destination.exists():
            if not (destination/"summary.json").exists():
                raise RuntimeError(f"Preserved unfinished E9 attempt requires diagnosis: {row['request_id']}")
            if row["request_id"] not in journal["allocations"]:
                raise RuntimeError("Completed E9 evidence has no fresh-workspace allocation record")
            fresh = Path(journal["allocations"][row["request_id"]]["workspace"])
        else:
            fresh = workspace_parent/f"replay-{selection_index:02d}-{uuid.uuid4().hex[:8]}_wrk"
            if fresh.exists():
                raise RuntimeError("Fresh E9 workspace unexpectedly exists")
            journal["allocations"][row["request_id"]] = {"allocated_utc": _utc(),
                "workspace": str(fresh), "required_new_workspace": True,
                "selection_index": selection_index,
                "original_case_id": row["case_id"], "original_saved_netlist_sha256": settings["netlist_saved_bytes_sha256"]}
            _write(journal_path, journal)
            try:
                runner.run_case(root, row, fresh, frozen_sweeps=sweeps, case_folder="reproductions")
            except Exception:
                _aggregate(root, requests)
                raise
        comparison = compare_evidence(original, destination)
        portable = _portable_snapshot(fresh, idle, destination/"portable-native", build_ads, runner, de)
        comparison["portable_native"] = {"snapshot_after_workspace_release": portable["snapshot_after_workspace_release"],
            "lock_files_absent": not portable["remaining_oa_lock_files"],
            "hashes_valid": portable["current_snapshot_hashes_valid"], "manifest": "portable-native-manifest.json"}
        comparison["checks"]["portable_native_after_lock_release"] = bool(
            portable["snapshot_after_workspace_release"] and not portable["remaining_oa_lock_files"]
            and portable["current_snapshot_hashes_valid"])
        comparison["comparison_passed"] = all(comparison["checks"].values())
        comparison.update({"request_id": row["request_id"], "case_id": row["case_id"],
                           "reproduces_request_id": row["reproduces_request_id"]})
        _write(destination/"comparison.json", comparison)
        new_results.append({"request_id": row["request_id"], "comparison_passed": comparison["comparison_passed"],
            "maximum_frequency_difference_hz": comparison["maximum_frequency_difference_hz"],
            "maximum_complex_s_difference": comparison["maximum_complex_s_difference"],
            "netlist_exact_byte_identity": comparison["netlist"]["exact_byte_identity"]})
        _aggregate(root, requests)
        if len(new_results) >= limit:
            break
    summary = _aggregate(root, requests)
    return {"new_results": new_results, "completed": summary["completed_count"],
            "passed": summary["passed_count"], "scheduled": 3, "e9_complete": summary["e9_complete"]}
