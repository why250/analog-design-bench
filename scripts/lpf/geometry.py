"""Propose bounded new PCell samples without creating surrogate evidence."""

from itertools import zip_longest
import math


def propose_geometries(design, profile, choices, limit):
    """Use validated model values to rank nearby, currently unsampled geometries."""
    from .search import geometry_key, validate_geometry

    proposals_by_target = []
    targets = dict.fromkeys((item["kind"], item["value"]) for item in design["elements"])
    for kind, value in targets:
        samples = choices[kind]
        family = profile["devices"][kind]
        variables = family["variables"]
        steps = family.get("proposal_steps_um", {})
        if not samples or any(steps.get(name, 0) <= 0 for name in variables):
            continue
        bounds = family.get("proposal_bounds_um") or {
            name: [min(s["parameters"][name] for s in samples), max(s["parameters"][name] for s in samples)]
            for name in variables
        }
        existing = {geometry_key(sample["parameters"]) for sample in samples}
        proposals = {}
        for sample in samples:
            estimate = sample.get("effective_value")
            if estimate is None or estimate <= 0 or not math.isfinite(estimate):
                continue
            anchor = sample["parameters"]
            changes = [(name,) for name in variables]
            if len(variables) > 1:
                changes.append(tuple(variables))
            for moved in changes:
                for direction in (-1, 1):
                    new = dict(anchor)
                    for name in moved:
                        new[name] = round(anchor[name] + direction * steps[name], 8)
                    if any(not bounds[name][0] <= new[name] <= bounds[name][1] for name in variables):
                        continue
                    try:
                        validate_geometry(new, family)
                    except ValueError:
                        continue
                    key = geometry_key(new)
                    if key in existing:
                        continue
                    # These ratios only prioritize extraction. Measured complex S is
                    # required before a geometry enters the circuit candidate search.
                    scale = math.prod(new[name] / anchor[name] for name in moved)
                    score = abs(math.log(estimate * scale / value))
                    proposal = {"kind": kind, "parameters": new}
                    if key not in proposals or score < proposals[key][0]:
                        proposals[key] = score, proposal
        proposals_by_target.append([
            proposal for _, (_, proposal) in sorted(proposals.items(), key=lambda item: (item[1][0], item[0]))
        ])

    selected, seen = [], set()
    for row in zip_longest(*proposals_by_target):
        for proposal in row:
            if proposal is None:
                continue
            key = proposal["kind"], geometry_key(proposal["parameters"])
            if key not in seen and len(selected) < limit:
                seen.add(key)
                selected.append(proposal)
        if len(selected) >= limit:
            break
    return selected
