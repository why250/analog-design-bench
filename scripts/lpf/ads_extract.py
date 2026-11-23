"""Request a missing exact PCell sample through the native ADS model flow."""

import json
from pathlib import Path
import re

from . import ads_pcell
from .search import geometry_key, validate_geometry


def _write_receipt(out, receipt):
    (out / "extraction.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8",
    )


def extract_geometry(spec, profile, workspace, device, out):
    """Return an exact, native cache entry from the run-owned ADS workspace."""
    workspace, out = Path(workspace).resolve(strict=True), Path(out).resolve()
    if workspace in out.parents or workspace.parent not in out.parents:
        raise ValueError("Extraction evidence must be beside the run-owned ADS workspace")
    kind = device["kind"]
    family = profile["devices"][kind]
    parameters = device["parameters"]
    validate_geometry(parameters, family)
    key = geometry_key(parameters)
    catalog, _ = ads_pcell._cache_index(workspace, family)
    out.mkdir(parents=True, exist_ok=False)

    suffix = re.sub(r"[^A-Za-z0-9_]", "_", out.name)
    cell = f"lpf_extract_{kind}_{suffix}"
    library = profile["layout"]["library"]
    receipt = {
        "schema_version": 1,
        "workspace": str(workspace),
        "testbench": f"{library}:{cell}:schematic",
        "model": f"{family['library']}:{family['cell']}:emModel",
        "kind": kind,
        "parameters_um": parameters,
        "status": "preparing",
    }
    if key in catalog:
        receipt.update(status="already_available", native_entry=catalog[key])
        _write_receipt(out, receipt)
        return catalog[key]

    # The PCell EM setup owns the model sweep. These circuit sweeps trigger
    # generation and check that the resulting model can serve the requested band.
    passband = spec["passband_hz"]
    last_stop = max(point["frequency_hz"] for point in spec["stopbands"])
    sweep_start = min(1e9, passband / 10)
    sweeps = ads_pcell._sweeps(spec, sweep_start, last_stop, 1301)
    receipt["fixture_sweeps"] = sweeps
    _write_receipt(out, receipt)

    fixture_ready = False
    try:
        ads_pcell.verify_em_workspace(workspace, family)
        with ads_pcell._open_workspace(workspace, profile):
            fixture = ads_pcell._build_fixture(profile, device, spec, sweeps, cell=cell)
            netlist = fixture.generate_netlist()
            ads_pcell._check_netlist(netlist, workspace, profile, [device], ground="0")
            deck, bindings = ads_pcell.bind_model_parameters(netlist, workspace, profile, [device])
            fixture_ready = True
            ads_pcell._simulate(
                deck, out / "native-attempt", sweeps, native_netlist=netlist, bindings=bindings,
            )
    except (ValueError, RuntimeError, OSError) as error:
        # Preserve the original diagnostic. Some ADS failures occur after the
        # fixture was saved and can be retried through the ADS application.
        receipt["native_error"] = str(error)

    updated, issues = ads_pcell._cache_index(workspace, family)
    entry = updated.get(key)
    if entry is not None:
        try:
            ads_pcell._range_and_notes(spec, [entry], [family])
        except ValueError as error:
            receipt.update(status="incomplete_coverage", native_entry=entry, reason=str(error))
            _write_receipt(out, receipt)
            raise
        receipt.update(status="extracted", native_entry=entry)
        _write_receipt(out, receipt)
        return entry

    receipt["cache_issues"] = issues
    diagnostic = receipt.get("native_error", "")
    for log in sorted((out / "native-attempt").glob("*.out")):
        receipt["solver_log"] = log.relative_to(out).as_posix()
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            if "gemx connection" in line.lower():
                diagnostic = line.strip()
                receipt["solver_diagnostic"] = diagnostic
                break
    if fixture_ready and ("gemx" in diagnostic.lower() or not diagnostic):
        receipt.update(status="application_extraction_pending", resume_steps=[
            "Open the recorded run-owned workspace in ADS.",
            "Open the recorded testbench and run its schematic simulation so ADS can populate the native EM model cache.",
            "Resume the same filter search with --ads-source pointing to this run-owned workspace.",
        ])
        reason = "ADS did not create the exact native EM cache entry. The application extraction can resume from"
    elif fixture_ready:
        receipt["status"] = "native_extraction_failed"
        reason = "Native ADS extraction failed without creating the exact cache entry. See"
    else:
        receipt["status"] = "fixture_failed"
        reason = "ADS did not finish the native extraction fixture. See"
    _write_receipt(out, receipt)
    detail = f" Native ADS reported: {diagnostic}" if diagnostic else ""
    raise RuntimeError(f"{reason} {out / 'extraction.json'}.{detail}")
