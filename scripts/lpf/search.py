"""Rank exact-size PCell models without substituting ideal components."""
from __future__ import annotations

import heapq
from itertools import zip_longest
import json
import math
from pathlib import Path

import numpy as np

from .ideal import measure


DEFAULT_BUDGETS = {"paired_cases": 256, "unpaired_cases": 128, "ads_runs": 4, "new_samples": 8}
_FREQUENCY_UNITS = {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9}


def load_touchstone(path):
    """Read the Touchstone 1.x two-port format emitted by the native exporter."""
    option = None
    values = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.split("!", 1)[0].strip()
        if not line:
            continue
        if line.startswith("#"):
            option = line[1:].lower().split()
            continue
        values.extend(float(item) for item in line.split())
    if (
        option is None or len(option) != 5 or option[0] not in _FREQUENCY_UNITS
        or option[1:4] != ["s", "ri", "r"] or len(values) % 9 or len(values) < 18
    ):
        raise ValueError("Expected two-port Touchstone 1.x S RI data with real reference impedance")
    impedance = float(option[4])
    rows = np.asarray(values).reshape(-1, 9)
    frequency = rows[:, 0] * _FREQUENCY_UNITS[option[0]]
    if (
        not math.isfinite(impedance) or impedance <= 0 or not np.isfinite(rows).all()
        or frequency[0] < 0 or np.any(np.diff(frequency) <= 0)
    ):
        raise ValueError("Invalid or unordered Touchstone samples")
    complex_values = rows[:, 1::2] + 1j * rows[:, 2::2]
    s = complex_values.reshape(-1, 2, 2).transpose(0, 2, 1)
    return frequency, s, impedance


def write_touchstone(path, frequency, s, impedance):
    """Write full complex two-port data with the declared reference impedance."""
    ordered = s.transpose(0, 2, 1).reshape(-1, 4)
    rows = np.column_stack((frequency, np.stack((ordered.real, ordered.imag), axis=-1).reshape(-1, 8)))
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(f"# Hz S RI R {impedance:.17g}\n")
        np.savetxt(stream, rows, fmt="%.17g")


def geometry_key(parameters):
    return tuple(sorted(parameters.items()))


def validate_geometry(parameters, family):
    """Validate the complete parameter vector against the selected device profile."""
    fixed = family["fixed_parameters"]
    if not isinstance(parameters, dict) or set(parameters) != set(fixed) | set(family["variables"]):
        raise ValueError("Geometry must include exactly the allowed and fixed parameters")
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in parameters.values()):
        raise ValueError("Geometry parameters must be finite nonnegative numbers in micrometers")
    if any(parameters[key] != value for key, value in fixed.items()):
        raise ValueError("Geometry changes a fixed parameter")
    for variable in family["variables"]:
        limits = family.get("bounds_um", {}).get(variable, [None, None])
        lower, upper = limits
        value = parameters[variable]
        if value <= 0 or (lower is not None and value < lower) or (upper is not None and value > upper):
            raise ValueError(f"{variable} is outside the allowed search range")
    for excluded in family.get("excluded_geometries", []):
        if all(parameters.get(key) == value for key, value in excluded.items()):
            raise ValueError("Geometry is excluded by the profile's model provenance")


def _sample_models(index, profile):
    catalog = json.loads(index.read_text(encoding="utf-8"))
    if (
        not isinstance(catalog, dict) or catalog.get("schema_version") != 1
        or not isinstance(catalog.get("samples"), list)
    ):
        raise ValueError("Expected version 1 exact sample index")
    by_kind = {"L": [], "C": []}
    issues = list(catalog.get("issues", []))
    seen_ids = set()
    seen_geometries = set()
    for entry in catalog["samples"]:
        if not isinstance(entry, dict):
            issues.append({"reason": "Sample record must be an object"})
            continue
        identifier = entry.get("id")
        try:
            kind = entry["kind"]
            family = profile["devices"][kind]
            if not isinstance(identifier, str) or not identifier or identifier in seen_ids:
                raise ValueError("Missing or duplicate sample ID")
            seen_ids.add(identifier)
            parameters = entry["parameters"]
            validate_geometry(parameters, family)
            geometry = kind, geometry_key(parameters)
            if geometry in seen_geometries:
                raise ValueError("More than one sample claims the same exact device geometry")
            status = entry["model_status"]
            if status not in ("qualified", "conditional"):
                raise ValueError("Sample model status must be qualified or conditional")
            if not isinstance(entry.get("model_notes", []), list) or any(
                not isinstance(note, str) for note in entry.get("model_notes", [])
            ):
                raise ValueError("Model notes must be a list of strings")
            path = (index.parent / entry["touchstone"]).resolve()
            frequency, s, impedance = load_touchstone(path)
            note = sample_passivity_note(frequency, s)
            notes = sorted(set(entry.get("model_notes", []) + ([note] if note else [])))
            seen_geometries.add(geometry)
            by_kind[kind].append({
                **entry, "frequency": frequency, "s": s, "impedance": impedance,
                "touchstone": str(path), "model_notes": notes,
            })
        except (KeyError, ValueError, TypeError, OSError) as exc:
            issues.append({"sample_id": identifier, "reason": str(exc)})
    return by_kind, issues


def _renormalize(s, old_reference, new_reference):
    if old_reference == new_reference:
        return s
    shift = (new_reference - old_reference) / (new_reference + old_reference)
    identity = np.eye(2, dtype=complex)
    return np.linalg.solve(identity - shift * s, s - shift * identity)


def _interpolate(sample, frequency, impedance):
    stored_frequency = sample["frequency"]
    if frequency[0] < stored_frequency[0] or frequency[-1] > stored_frequency[-1]:
        raise ValueError("Frequency outside the exact geometry model's export range")
    data = sample["s"]
    result = np.empty((len(frequency), 2, 2), dtype=complex)
    for out, incoming in ((0, 0), (0, 1), (1, 0), (1, 1)):
        result[:, out, incoming] = np.interp(frequency, stored_frequency, data[:, out, incoming])
    return _renormalize(result, sample["impedance"], impedance)


def _cascade(left, right):
    denominator = 1 - left[:, 1, 1] * right[:, 0, 0]
    if np.any(np.abs(denominator) < 1e-14):
        raise ValueError("Singular two-port connection")
    result = np.empty_like(left)
    result[:, 0, 0] = left[:, 0, 0] + left[:, 0, 1] * right[:, 0, 0] * left[:, 1, 0] / denominator
    result[:, 0, 1] = left[:, 0, 1] * right[:, 0, 1] / denominator
    result[:, 1, 0] = right[:, 1, 0] * left[:, 1, 0] / denominator
    result[:, 1, 1] = right[:, 1, 1] + right[:, 1, 0] * left[:, 1, 1] * right[:, 0, 1] / denominator
    return result


def _diagnostics(s):
    return {
        "passivity_max_sv": float(np.linalg.svd(s, compute_uv=False).max()),
        "reciprocity_max_abs": float(np.max(np.abs(s[:, 0, 1] - s[:, 1, 0]))),
    }


def sample_passivity_note(frequency, s):
    """Reject substantial nonpassivity and qualify small solver overshoots."""
    if not np.isfinite(s).all():
        raise ValueError("The device sample contains nonfinite S-parameters")
    singular = np.linalg.svd(s, compute_uv=False)[:, 0]
    peak = int(np.argmax(singular))
    if singular[peak] > 1.0001:
        raise ValueError("Two-port model violates the passive-network check")
    if singular[peak] > 1.00001:
        return (
            f"Device model has a small passivity overshoot "
            f"(maximum singular value {singular[peak]:.8g} at {frequency[peak]:.8g} Hz)"
        )
    return None


def _effective_value(sample, frequency, impedance):
    s = _interpolate(sample, np.array([frequency]), impedance)[0]
    s11, s12 = s[0]
    s21, s22 = s[1]
    if abs(s21) < 1e-12:
        return None
    if sample["kind"] == "L":
        series_z = impedance * ((1 + s11) * (1 + s22) - s12 * s21) / (2 * s21)
        return series_z.imag / (2 * np.pi * frequency)
    shunt_y = ((1 - s11) * (1 - s22) - s12 * s21) / (2 * impedance * s21)
    return shunt_y.imag / (2 * np.pi * frequency)


def _groups(elements, paired):
    if not paired:
        return [(position,) for position in range(len(elements))]
    result = []
    for position in range((len(elements) + 1) // 2):
        opposite = len(elements) - 1 - position
        if elements[position]["kind"] != elements[opposite]["kind"]:
            raise ValueError("Mirror pairing requires matching device kinds across the center")
        result.append((position,) if position == opposite else (position, opposite))
    return result


def _candidate_assignments(elements, choices, paired, *, prototype_scale=1.0):
    groups = _groups(elements, paired)
    ranked = []
    for positions in groups:
        element = elements[positions[0]]
        target = prototype_scale * sum(elements[position]["value"] for position in positions) / len(positions)
        by_distance = []
        for sample in choices[element["kind"]]:
            value = sample["effective_value"]
            distance = abs(math.log(value / target)) if value is not None and value > 0 else 100.0
            by_distance.append((distance, sample["id"], sample))
        if not by_distance:
            return
        ranked.append(sorted(by_distance, key=lambda item: item[:2]))

    # Enumerate the most promising vectors first without allocating the Cartesian product.
    origin = (0,) * len(groups)
    queue = [(sum(items[0][0] for items in ranked), origin)]
    visited = {origin}
    while queue:
        _, indices = heapq.heappop(queue)
        assignment = [None] * len(elements)
        for positions, items, index in zip(groups, ranked, indices):
            for position in positions:
                assignment[position] = items[index][2]
        yield assignment
        for axis, items in enumerate(ranked):
            if indices[axis] + 1 == len(items):
                continue
            neighbor = indices[:axis] + (indices[axis] + 1,) + indices[axis + 1:]
            if neighbor not in visited:
                visited.add(neighbor)
                cost = sum(items[index][0] for items, index in zip(ranked, neighbor))
                heapq.heappush(queue, (cost, neighbor))


def _paired_assignments(spec, elements, choices):
    """Interleave nominal and frequency-scaled ideal priors before screening."""
    nearest_stop = min(item["frequency_hz"] for item in spec["stopbands"])
    transition_ratio = spec["passband_hz"] / nearest_stop
    # Scaling all L/C values shifts the ideal response in frequency. The
    # transition width supplies two offsets each way to accommodate PCell
    # parasitics while preserving the original prior as the first stream.
    scales = [transition_ratio**power for power in (0, 0.5, 1, -0.5, -1)]
    streams = [
        _candidate_assignments(elements, choices, paired=True, prototype_scale=scale)
        for scale in scales
    ]
    seen = set()
    for batch in zip_longest(*streams):
        for assignment in batch:
            if assignment is None:
                continue
            key = tuple(sample["id"] for sample in assignment)
            if key not in seen:
                seen.add(key)
                yield assignment


def _metrics_rank(result):
    metrics = result["metrics"]
    scored = [metrics["s11_worst"], metrics["s22_worst"], *metrics["stopbands"]]
    if metrics["il_worst"]["limit_db"] is not None:
        scored.append(metrics["il_worst"])
    misses = [
        max(0.0, item["value_db"] - item["limit_db"]) if item["value_db"] is not None else math.inf
        for item in scored
    ]
    insertion_loss = metrics["il_worst"]["value_db"]
    return (
        not result["passes"], max(misses), sum(misses),
        insertion_loss if insertion_loss is not None else math.inf, result["id"],
    )


def _screen(spec, elements, assignment, identifier, stage):
    start = max(1e6, *(sample["frequency"][0] for sample in assignment))
    edge = spec["passband_hz"]
    stops = [item["frequency_hz"] for item in spec["stopbands"]]
    if start >= edge or min(sample["frequency"][-1] for sample in assignment) < max(stops):
        raise ValueError("Device samples do not jointly cover the passband edge and all stop checkpoints")
    band = np.linspace(start, edge, 1301)
    frequency = np.unique(np.concatenate((band, stops)))
    impedance = spec["impedance_ohm"]
    chain = _interpolate(assignment[0], frequency, impedance)
    for sample in assignment[1:]:
        chain = _cascade(chain, _interpolate(sample, frequency, impedance))
    diagnostics = _diagnostics(chain)
    if diagnostics["passivity_max_sv"] > 1.00001 or diagnostics["reciprocity_max_abs"] > 1e-4:
        raise ValueError("Assembled model failed the passive or reciprocal network check")
    notes = sorted({note for sample in assignment for note in sample.get("model_notes", [])})
    if start > 1e6:
        notes.append(f"Common source-model coverage begins at {start:g} Hz")
    result = {
        "id": identifier,
        "search_stage": stage,
        "devices": [
            {
                "name": element["name"], "kind": element["kind"], "parameters": sample["parameters"],
                "sample_id": sample["id"], "native_sample": sample.get("native_sample"),
                "native_sio_sha256": sample.get("native_sio_sha256"),
            }
            for element, sample in zip(elements, assignment)
        ],
        **measure(spec, frequency, chain),
        "diagnostics": diagnostics,
        "verification": "screen",
        "model_status": "conditional" if notes or any(
            sample["model_status"] == "conditional" for sample in assignment
        ) else "qualified",
        "model_notes": notes,
    }
    return result, frequency, chain


def run_search(spec, design, profile, out, *, sample_index=None, ads_workspace=None, budgets=None):
    """Search mirrored combinations first and verify survivors in native ADS when available."""
    limits = DEFAULT_BUDGETS | (budgets or {})
    if any(key not in DEFAULT_BUDGETS or type(value) is not int or value < 0 for key, value in limits.items()):
        raise ValueError("Search budgets must be nonnegative integer counts")
    if limits["paired_cases"] < 1:
        raise ValueError("The paired search needs at least one evaluation")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out / "search.json").exists():
        raise ValueError("The output already contains a completed PCell search")
    report = {
        "budgets": limits, "candidates": [], "issues": [], "recommendations": [],
        "search_counts": {"paired": 0, "unpaired": 0, "ads_runs": 0},
    }
    native_source = None
    if ads_workspace is not None:
        from . import ads_pcell

        native_source = ads_pcell.copy_workspace(Path(ads_workspace), out / "ads-source")
    if sample_index is None:
        if native_source is None:
            raise ValueError("Supply a sample index or an ADS source workspace")
        sample_index = ads_pcell.export_samples(spec, design, profile, native_source, out / "samples")
    sample_index = Path(sample_index)
    resolved_index = sample_index.resolve()
    report["sample_index"] = (
        resolved_index.relative_to(out).as_posix() if resolved_index.is_relative_to(out) else str(resolved_index)
    )
    choices, issues = _sample_models(sample_index, profile)
    report["issues"].extend(issues)
    def rank_samples(kind, samples):
        for sample in samples:
            low, high = sample["frequency"][[0, -1]]
            reference = min(max(spec["passband_hz"] / 2, low), high)
            sample["effective_value"] = _effective_value(sample, reference, spec["impedance_ohm"])
            threshold = profile["devices"][kind].get("unqualified_above_hz")
            if threshold is not None and max(item["frequency_hz"] for item in spec["stopbands"]) > threshold:
                note = f"Device-model applicability above {threshold:g} Hz is conditional"
                sample["model_notes"] = sorted(set(sample.get("model_notes", []) + [note]))

    for kind, samples in choices.items():
        rank_samples(kind, samples)
        if not samples and any(item["kind"] == kind for item in design["elements"]):
            report["issues"].append({"kind": kind, "reason": "No usable exact sample models"})

    elements = design["elements"]
    seen = set()

    def verify(candidates, cap):
        for candidate in sorted(candidates, key=_metrics_rank):
            if native_source is None or report["search_counts"]["ads_runs"] >= cap:
                break
            report["search_counts"]["ads_runs"] += 1
            try:
                native = ads_pcell.verify_candidate(
                    spec, profile, candidate, native_source, out / candidate["id"] / "ads-verification",
                )
            except (ValueError, RuntimeError, OSError, ImportError) as exc:
                candidate["native_error"] = str(exc)
                report["issues"].append({"candidate_id": candidate["id"], "reason": str(exc)})
                continue
            for key in ("ads_workspace", "native_touchstone"):
                native[key] = Path(native[key]).resolve().relative_to(out).as_posix()
            candidate["screen_metrics"] = candidate["metrics"]
            candidate.update(native)

    def screen_stage(stage, cap):
        candidates = []
        assignments = (
            _paired_assignments(spec, elements, choices)
            if stage == "paired" else _candidate_assignments(elements, choices, paired=False)
        )
        for assignment in assignments:
            if report["search_counts"][stage] >= cap:
                break
            key = tuple(sample["id"] for sample in assignment)
            if key in seen:
                continue
            seen.add(key)
            report["search_counts"][stage] += 1
            identifier = f"{stage}-{report['search_counts'][stage]:04d}"
            try:
                result, frequency, chain = _screen(spec, elements, assignment, identifier, stage)
            except (ValueError, np.linalg.LinAlgError) as exc:
                report["issues"].append({"candidate_id": identifier, "sample_ids": key, "reason": str(exc)})
                continue
            candidates.append(result)
            if result["passes"]:
                target = out / identifier
                target.mkdir()
                write_touchstone(target / "screen.s2p", frequency, chain, spec["impedance_ohm"])
                result["screen_touchstone"] = (target / "screen.s2p").relative_to(out).as_posix()
        report["candidates"].extend(candidates)
        return candidates

    def passing(candidates):
        return any(
            candidate["passes"] and (native_source is None or candidate["verification"] == "ads")
            for candidate in candidates
        )

    paired_cap = limits["paired_cases"]
    if native_source is not None and limits["new_samples"]:
        paired_cap = max(1, paired_cap // 2)
    native_pair_cap = limits["ads_runs"]
    if native_pair_cap > 1 and limits["unpaired_cases"]:
        native_pair_cap -= 1
    paired = screen_stage("paired", paired_cap)
    verify([candidate for candidate in paired if candidate["passes"]], native_pair_cap)

    if not passing(paired) and limits["new_samples"]:
        from .geometry import propose_geometries

        requests = propose_geometries(design, profile, choices, limits["new_samples"])
        report["extraction_requests"] = requests
        if requests:
            extraction = out / "extraction"
            extraction.mkdir()
            extra_samples = []
            for index, device in enumerate(requests, 1):
                if native_source is None:
                    device["status"] = "pending_ads"
                    continue
                target = extraction / f"request-{index:03d}"
                try:
                    from .ads_extract import extract_geometry

                    fixture = {**device, "name": "Device"}
                    extract_geometry(spec, profile, native_source, fixture, target)
                    exported = ads_pcell.export_geometry(
                        spec, profile, native_source, fixture, extraction,
                    )
                    exported["touchstone"] = Path(exported["touchstone"]).relative_to(extraction).as_posix()
                    extra_samples.append(exported)
                    device["status"] = "exact_sample_exported"
                except (ValueError, RuntimeError, OSError, ImportError) as exc:
                    device.update(status="pending_ads", reason=str(exc))
            (extraction / "extraction-requests.json").write_text(
                json.dumps(requests, indent=2) + "\n", encoding="utf-8",
            )
            if extra_samples:
                added = extraction / "sample-index.json"
                added.write_text(json.dumps({"schema_version": 1, "samples": extra_samples}) + "\n",
                                 encoding="utf-8")
                extra_choices, extra_issues = _sample_models(added, profile)
                report["issues"].extend(extra_issues)
                for kind, samples in extra_choices.items():
                    rank_samples(kind, samples)
                    choices[kind].extend(samples)
    if not passing(paired) and paired_cap < limits["paired_cases"]:
        more = screen_stage("paired", limits["paired_cases"])
        verify([candidate for candidate in more if candidate["passes"]], native_pair_cap)
        paired.extend(more)
    if not passing(paired):
        unpaired = screen_stage("unpaired", limits["unpaired_cases"])
        verify([candidate for candidate in unpaired if candidate["passes"]], limits["ads_runs"])

    candidates = report["candidates"]
    if not any(candidate["verification"] == "ads" for candidate in candidates):
        remaining = [candidate for candidate in candidates if "native_error" not in candidate]
        verify(sorted(remaining, key=_metrics_rank)[:1], limits["ads_runs"])
    native_passes = [item for item in candidates if item["passes"] and item["verification"] == "ads"]
    qualified = [item for item in native_passes if item["model_status"] == "qualified"]
    native = [item for item in candidates if item["verification"] == "ads"]
    best_pool = qualified or native_passes or native or candidates
    report["best_candidate_id"] = min(best_pool, key=_metrics_rank)["id"] if best_pool else None
    near_misses = [candidate for candidate in candidates if not candidate["passes"]]
    report["best_near_miss_id"] = min(near_misses, key=_metrics_rank)["id"] if near_misses else None
    native_misses = [candidate for candidate in near_misses if candidate["verification"] == "ads"]
    report["best_native_near_miss_id"] = min(native_misses, key=_metrics_rank)["id"] if native_misses else None
    if not qualified:
        report["recommendations"].append(
            "A finite search without a qualified ADS pass does not establish physical infeasibility."
        )
    if any(item["passes"] and item["verification"] == "screen" for item in candidates):
        report["recommendations"].append("Screen-only results need a native ADS rerun before acceptance.")
    (out / "search.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report
