"""Compress inactive Momentum stack interfaces while proving the same model.

The task's observed EXPAND-UP preprocessing inserts background dielectric slabs
even for unused conductor masks. Their thickness must be retained when removing
those masks. This projection preserves all MATERIAL definitions, actual active
geometry, M1/M6 conductor faces and the complete expanded epsilon/mu/conductivity
profile. ADS 2027 User Guide / Material Definitions / Dielectrics requires
er_imag = -er_real * positive TanD for passive loss. This tool rejects positive
direct imaginary permittivity and compares only correctly realized passive
source/canonical stacks. Earlier wrong-sign results are not equivalent controls.
It does not qualify EM numerical equivalence or change device targets.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
from typing import Any

import plot_geometry
from validate_inputs import InputError, parse_ltd


ACTIVE_LAYERS = {7: "Metal1", 35: "Metal6"}
INPUT_FILES = ("proj.ltd", "proj_a", "proj.pin", "proj.prt", "proj.opt", "proj.sti", "proj.cfg")
Z_TOLERANCE_UM = Decimal("0.000001")
MEDIUM_KEYS = ("er", "ei", "mur", "mui", "sigma_s_per_m", "imag_sigma_s_per_m")


def _d(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InputError(f"Invalid numeric {label}") from exc
    if not result.is_finite():
        raise InputError(f"Nonfinite {label}")
    return result


def _medium(materials: dict[str, Any], name: str) -> dict[str, Decimal]:
    if name == "AIR":
        return dict(zip(MEDIUM_KEYS, map(Decimal, ("1", "0", "1", "0", "0", "0"))))
    try:
        fields = materials[name]["fields"]
    except KeyError as exc:
        raise InputError(f"Background material {name} is missing") from exc
    if "CONDUCTIVITY" in fields and "RESISTIVITY" in fields:
        raise InputError("A background material has ambiguous conductivity and resistivity")
    conductivity = _d(fields.get("CONDUCTIVITY", "0"), name + " conductivity")
    if "RESISTIVITY" in fields:
        resistivity = _d(fields["RESISTIVITY"], name + " resistivity")
        if resistivity <= 0:
            raise InputError("Finite substrate resistivity must be positive")
        conductivity = Decimal(100) / resistivity  # OHM.CM -> SIEMENS/M
    return {"er": _d(fields.get("PERMITTIVITY"), name + " relative permittivity"),
            "ei": _d(fields.get("IMAG_PERMITTIVITY", "0"), name + " imaginary permittivity"),
            "mur": _d(fields.get("PERMEABILITY", "1"), name + " relative permeability"),
            "mui": _d(fields.get("IMAG_PERMEABILITY", "0"), name + " imaginary permeability"),
            "sigma_s_per_m": conductivity,
            "imag_sigma_s_per_m": _d(fields.get("IMAG_CONDUCTIVITY", "0"), name + " imaginary conductivity")}


def _finish_profile(slabs: list[dict[str, Any]], materials: dict[str, Any] | None = None) -> dict[str, Any]:
    if not slabs:
        raise InputError("No finite dielectric slabs were found")
    if any(slab["medium"]["ei"] > 0 for slab in slabs):
        raise InputError("Positive direct imaginary permittivity represents gain in the ADS convention, not the frozen passive loss tangent")
    # The bottom finite slab is the 500 um silicon substrate; origin is its top.
    silicon = dict(zip(MEDIUM_KEYS, map(Decimal, ("11.9", "0", "1", "0", "5", "0"))))
    if slabs[-1]["medium"] != silicon:
        raise InputError("The bottom finite slab is not the frozen conductive silicon medium")
    z = -slabs[-1]["height_um"]
    intervals: list[dict[str, Any]] = []
    raw_intervals: list[dict[str, Any]] = []
    active_faces: dict[int, tuple[Decimal, Decimal]] = {}
    for slab in reversed(slabs):
        upper = z + slab["height_um"]
        row = {"lower_um": z, "upper_um": upper, "medium": slab["medium"]}
        raw_intervals.append(dict(row, flags=slab.get("flags", []), layer_index=slab.get("layer_index")))
        if slab.get("active_layer") is not None:
            layer = slab["active_layer"]
            if layer in active_faces:
                raise InputError("An active conductor has repeated expansion slabs")
            active_faces[layer] = (z, upper)
        if intervals and intervals[-1]["upper_um"] == z and intervals[-1]["medium"] == slab["medium"]:
            intervals[-1]["upper_um"] = upper
        else:
            intervals.append(row)
        z = upper
    return {"intervals": intervals, "raw_intervals": raw_intervals, "active_faces_um": active_faces,
            "top_surface_um": z, "finite_slab_count": len(slabs)}


def expanded_ltd_profile(text: str) -> dict[str, Any]:
    """Apply the observed V2 EXPAND-UP rule with exact decimal arithmetic."""
    ltd = parse_ltd(text)
    expected_units = {"DISTANCE": "METRE", "CONDUCTIVITY": "SIEMENS/M", "RESISTIVITY": "OHM.CM"}
    if any(ltd["units"].get(key) != value for key, value in expected_units.items()):
        raise InputError("Canonicalization requires METRE, SIEMENS/M and OHM.CM source units")
    stack = ltd["stack"]
    boundaries = [row for row in stack if row["kind"] in ("TOP", "BOTTOM")]
    if boundaries != [{"kind": side, "fields": {"MATERIAL": "AIR"}, "flags": ["OPEN"]} for side in ("TOP", "BOTTOM")]:
        raise InputError("The canonical research model requires OPEN AIR above and below")
    mask_names = {}
    for layer, mask in ltd["masks"].items():
        name = mask["fields"]["NAME"]
        if name in mask_names:
            raise InputError("Ambiguous mask names")
        mask_names[name] = (int(layer), mask["fields"])
    slabs: list[dict[str, Any]] = []
    above_name = "AIR"
    for row in stack:
        fields = row["fields"]
        if row["kind"] == "LAYER":
            height = _d(fields["HEIGHT"], "dielectric height") * Decimal("1e6")
            if height <= 0:
                raise InputError("Finite dielectric heights must be positive")
            above_name = fields["MATERIAL"]
            slabs.append({"height_um": height, "medium": _medium(ltd["materials"], above_name)})
        elif row["kind"] == "INTERFACE" and "MASK" in fields:
            names = fields["MASK"].strip("{}").split(",")
            if len(names) != 1 or names[0] not in mask_names:
                raise InputError("Only the observed one-mask-per-interface expansion format is supported")
            layer, mask = mask_names[names[0]]
            operation = ltd["operations"][mask["OPERATION"]]
            if operation["flags"] == ["SHEET"]:
                if layer in ACTIVE_LAYERS:
                    raise InputError("Active M1/M6 must retain finite expanded thickness")
                continue
            if operation["flags"] != ["UP"] or set(operation["fields"]) != {"EXPAND"}:
                raise InputError("Only the observed positive EXPAND-UP conductor operation is supported")
            thickness = _d(operation["fields"]["EXPAND"], "conductor expansion") * Decimal("1e6")
            if thickness <= 0:
                raise InputError("Expanded conductor thickness must be positive")
            slab = {"height_um": thickness, "medium": _medium(ltd["materials"], above_name)}
            if layer in ACTIVE_LAYERS:
                expected_thickness = {7: Decimal("0.53"), 35: Decimal("0.99")}[layer]
                if thickness != expected_thickness:
                    raise InputError("Active conductor thickness differs from the frozen model")
                conductor = ltd["materials"][mask["MATERIAL"]]["fields"]
                expected_sigma = {7: Decimal("24050900"), 35: Decimal("24050000")}[layer]
                if _d(conductor.get("CONDUCTIVITY"), "active conductivity") != expected_sigma:
                    raise InputError("Active conductor conductivity differs from the frozen model")
                slab["active_layer"] = layer
            slabs.append(slab)
    result = _finish_profile(slabs)
    if set(result["active_faces_um"]) != set(ACTIVE_LAYERS):
        raise InputError("Both and only active M1/M6 expansion faces are required")
    return result


def expanded_sub_profile(text: str) -> dict[str, Any]:
    """Independently read actual preprocessor proj.sub background and support planes."""
    layers: list[dict[str, Any]] = []
    headers: dict[str, str] = {}
    in_layers = False
    for raw in text.splitlines():
        line = raw.strip().rstrip(",;").strip()
        if not line:
            continue
        tokens = line.split()
        if line == "LAYERS":
            in_layers = True
            continue
        if not in_layers:
            if len(tokens) != 2 or tokens[0] in headers:
                raise InputError("Unsupported preprocessed SUB header")
            headers[tokens[0]] = tokens[1]
            continue
        if len(tokens) == 3 and tokens[1] == "THICKNESS":
            index = int(tokens[0])
            if index != len(layers):
                raise InputError("Noncontiguous preprocessed SUB layer numbers")
            height = None if tokens[2] == "INFINITY" else _d(tokens[2], "SUB thickness") * Decimal("1e6")
            layers.append({"height_um": height, "medium": {}, "flags": [], "layer_index": index})
        elif layers and tokens[0] == "PERMITTIVITY" and len(tokens) == 4:
            medium = layers[-1]["medium"]
            if "er" in medium:
                raise InputError("Repeated SUB permittivity")
            medium.update({"er": _d(tokens[2], "SUB er"), "imag_sigma_s_per_m": Decimal(0)})
            if tokens[1] == "VALUE":
                medium.update({"ei": _d(tokens[3], "SUB imaginary er"), "sigma_s_per_m": Decimal(0)})
            elif tokens[1] == "CONDUCTIVITY":
                medium.update({"ei": Decimal(0), "sigma_s_per_m": _d(tokens[3], "SUB conductivity")})
            else:
                raise InputError("Unsupported SUB dielectric loss model")
        elif layers and tokens[:2] == ["PERMEABILITY", "VALUE"] and len(tokens) == 4:
            layers[-1]["medium"].update({"mur": _d(tokens[2], "SUB mu"), "mui": _d(tokens[3], "SUB imaginary mu")})
        elif layers and line in ("STRIP", "VIA"):
            layers[-1]["flags"].append(line)
        else:
            raise InputError("Unsupported preprocessed SUB statement")
    if headers != {"UNITS": "METRE", "BOTTOMPLANE": "OPEN", "TOPPLANE": "OPEN"} or len(layers) < 3:
        raise InputError("SUB must have METRE units and open top/bottom planes")
    air = _medium({}, "AIR")
    if layers[0]["height_um"] is not None or layers[-1]["height_um"] is not None or layers[0]["medium"] != air or layers[-1]["medium"] != air:
        raise InputError("SUB requires infinite AIR above and below")
    for layer in layers[1:-1]:
        if layer["height_um"] is None or layer["height_um"] <= 0 or set(layer["medium"]) != set(MEDIUM_KEYS):
            raise InputError("Incomplete finite SUB layer")
    return _finish_profile(layers[1:-1])


def _same_profile(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if len(a["intervals"]) != len(b["intervals"]):
        return False
    return all(x["medium"] == y["medium"] and all(abs(x[key] - y[key]) <= Z_TOLERANCE_UM for key in ("lower_um", "upper_um"))
               for x, y in zip(a["intervals"], b["intervals"]))


def _frozen_profile() -> dict[str, Any]:
    rows = [("-500", "0", "11.9", "0", "5"), ("0", "0.35", "3.9", "-0.0195", "0"),
            ("0.35", "1.05", "4.2", "-0.021", "0"), ("1.05", "7.77", "3.76", "-0.0188", "0"),
            ("7.77", "9.76", "4.2", "-0.021", "0"), ("9.76", "10.46", "7.9", "-0.0395", "0")]
    intervals = []
    for lower, upper, er, ei, sigma in rows:
        medium = dict(zip(MEDIUM_KEYS, map(Decimal, (er, ei, "1", "0", sigma, "0"))))
        intervals.append({"lower_um": Decimal(lower), "upper_um": Decimal(upper), "medium": medium})
    return {"intervals": intervals, "active_faces_um": {7: (Decimal("1.05"), Decimal("1.58")),
                                                         35: (Decimal("7.77"), Decimal("8.76"))}}


def _same_faces(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return set(a["active_faces_um"]) == set(b["active_faces_um"]) and all(
        abs(x - y) <= Z_TOLERANCE_UM for layer in a["active_faces_um"]
        for x, y in zip(a["active_faces_um"][layer], b["active_faces_um"][layer]))


def _json_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {"z_origin": "silicon top", "z_units": "um",
            "merged_background_intervals": [{"lower_um": float(row["lower_um"]), "upper_um": float(row["upper_um"]),
                                              "medium": {key: float(value) for key, value in row["medium"].items()}}
                                             for row in profile["intervals"]],
            "active_conductor_faces_um": {str(layer): {"bottom": float(faces[0]), "top": float(faces[1])}
                                          for layer, faces in profile["active_faces_um"].items()},
            "finite_slab_count": profile.get("finite_slab_count")}


def verify_generated_sub(ltd_text: str, sub_text: str) -> dict[str, Any]:
    """Verify actual -T output, including active current-support slab faces."""
    expected = expanded_ltd_profile(ltd_text)
    observed = expanded_sub_profile(sub_text)
    if not _same_profile(expected, observed):
        raise InputError("Actual preprocessed SUB differs from the analytically expanded source profile")
    for layer, faces in expected["active_faces_um"].items():
        matching = [row for row in observed["raw_intervals"]
                    if abs(row["lower_um"] - faces[0]) <= Z_TOLERANCE_UM
                    and abs(row["upper_um"] - faces[1]) <= Z_TOLERANCE_UM and "STRIP" in row["flags"]]
        if len(matching) != 1:
            raise InputError(f"Actual SUB does not preserve active layer {layer}'s conductor support faces")
    return {"status": "SATISFIED", "scope": "actual substrate preprocessing and active face locations only",
            "profile": _json_profile(expected), "z_tolerance_um": float(Z_TOLERANCE_UM)}


CANONICAL_STACK = """BEGIN_STACK
  TOP OPEN MATERIAL=AIR
  INTERFACE Name=CanonicalTop
  LAYER Name=CanonicalPass2 HEIGHT=7e-7 MATERIAL=pass2
  INTERFACE Name=CanonicalPass1Top
  LAYER Name=CanonicalPass1 HEIGHT=1e-6 MATERIAL=pass1
  INTERFACE Name=CanonicalMetal6 MASK={Metal6}
  LAYER Name=CanonicalMixed HEIGHT=6.19e-6 MATERIAL=ox_mixed_eff
  INTERFACE Name=CanonicalMetal1 MASK={Metal1}
  LAYER Name=CanonicalOx1 HEIGHT=7e-7 MATERIAL=ResearchOx1
  INTERFACE Name=CanonicalSubTop
  LAYER Name=CanonicalSub HEIGHT=3.5e-7 MATERIAL=sub
  INTERFACE Name=CanonicalSiliconTop
  LAYER Name=CanonicalSilicon HEIGHT=5e-4 MATERIAL=Silicon
  INTERFACE Name=CanonicalBottom
  BOTTOM OPEN MATERIAL=AIR
END_STACK
"""


def canonical_ltd_text(original: str) -> str:
    """Project to active masks while retaining every original MATERIAL byte."""
    ltd = parse_ltd(original)
    operations = {ltd["masks"][str(layer)]["fields"]["OPERATION"] for layer in ACTIVE_LAYERS}
    newline = "\r\n" if "\r\n" in original else "\n"
    output: list[str] = []
    section = ""
    for line in original.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == "BEGIN_STACK":
            output.append(CANONICAL_STACK.replace("\n", newline))
            section = "stack"
        elif section == "stack":
            if stripped == "END_STACK":
                section = ""
        elif stripped in ("BEGIN_MASK", "BEGIN_OPERATION"):
            section = stripped
            output.append(line)
        elif stripped in ("END_MASK", "END_OPERATION"):
            section = ""
            output.append(line)
        elif section == "BEGIN_MASK" and stripped:
            tokens = shlex.split(stripped)
            if tokens[0] == "MASK" and int(tokens[1]) in ACTIVE_LAYERS:
                output.append(line)
        elif section == "BEGIN_OPERATION" and stripped:
            tokens = shlex.split(stripped)
            if tokens[0] == "OPERATION" and tokens[1] in operations:
                output.append(line)
        else:
            output.append(line)
    canonical = "".join(output)
    source_material = re.search(r"(?ms)^BEGIN_MATERIAL\s*\r?\n.*?^END_MATERIAL[^\r\n]*(?:\r?\n|$)", original)
    final_material = re.search(r"(?ms)^BEGIN_MATERIAL\s*\r?\n.*?^END_MATERIAL[^\r\n]*(?:\r?\n|$)", canonical)
    if source_material is None or final_material is None or source_material.group() != final_material.group():
        raise InputError("Canonicalization changed the original MATERIAL definition bytes")
    return canonical


def prove_equivalent(original_ltd: str, canonical_ltd: str, original_sub: str) -> dict[str, Any]:
    old = expanded_ltd_profile(original_ltd)
    new = expanded_ltd_profile(canonical_ltd)
    reference = _frozen_profile()
    if not _same_profile(old, reference) or not _same_faces(old, reference):
        raise InputError("Source effective stack or active faces differ from the frozen observed research model")
    observed_preprocessor = verify_generated_sub(original_ltd, original_sub)
    if not _same_profile(old, new) or not _same_faces(old, new):
        raise InputError("Canonical candidate changes the expanded physical profile or active conductor faces")
    if parse_ltd(original_ltd)["materials"] != parse_ltd(canonical_ltd)["materials"]:
        raise InputError("Material definitions changed")
    if set(parse_ltd(canonical_ltd)["masks"]) != {"7", "35"}:
        raise InputError("Canonical candidate retains unexpected masks or loses an active mask")
    return {"status": "SATISFIED", "scope": "analytical physical model equivalence; EM numerical reproduction remains required",
            "original_effective_profile": _json_profile(old), "canonical_effective_profile": _json_profile(new),
            "original_preprocessor_profile": observed_preprocessor,
            "all_material_definitions_unchanged": True, "z_tolerance_um": float(Z_TOLERANCE_UM),
            "dielectric_loss_convention": {
                "source": "ADS 2027 User Guide / Material Definitions / Dielectrics",
                "source_document": "usrguide/Material_Definitions.html",
                "realization": "direct er_imag = -er_real * positive TanD",
                "comparison": "correctly realized negative-imaginary source versus negative-imaginary canonical stack only"},
            "numerical_EM_equivalence": "NOT EVALUATED",
            "inactive_geometry_assumption": "actual proj_a contains only Metal1 and Metal6; no via or other conductor geometry"}


def canonicalize(source: str | Path, output: str | Path, reference_sub: str | Path | None = None) -> dict[str, Any]:
    """Prove before writing a fresh, complete solver-input projection."""
    source, output = Path(source).resolve(strict=True), Path(output).resolve()
    if output.exists():
        raise FileExistsError("Use a fresh output directory; source and earlier evidence are retained")
    if output.is_relative_to(source):
        raise InputError("The canonical projection must be outside its source input directory")
    for name in INPUT_FILES:
        if not (source / name).is_file():
            raise InputError(f"Source solver input {name} is missing")
    polygons = plot_geometry.parse_egs((source / "proj_a").read_text(encoding="utf-8-sig"))
    if {polygon.layer for polygon in polygons} != set(ACTIVE_LAYERS):
        raise InputError("Only actual Metal1/Metal6 geometry may use this projection; via or inactive-mask geometry is present")
    baseline_sub = Path(reference_sub).resolve(strict=True) if reference_sub else source / "proj.sub"
    if not baseline_sub.is_file():
        raise InputError("Retained source proj.sub is required to verify actual preprocessing")
    original_bytes = (source / "proj.ltd").read_bytes()
    original_text = original_bytes.decode("utf-8")
    candidate = canonical_ltd_text(original_text)
    proof = prove_equivalent(original_text, candidate, baseline_sub.read_text(encoding="utf-8-sig"))
    # No filesystem output is created before every proof above succeeds.
    output.mkdir(parents=True, exist_ok=False)
    retained = output / "original"
    retained.mkdir()
    (retained / "proj.ltd").write_bytes(original_bytes)
    shutil.copyfile(baseline_sub, retained / "proj.sub")
    for name in INPUT_FILES:
        if name != "proj.ltd":
            shutil.copyfile(source / name, output / name)
    (output / "proj.ltd").write_bytes(candidate.encode("utf-8"))
    proof.update({"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
                  "task_version_id": "rf-inductor-120ph-65g-em-r1",
                  "projection": "remove inactive interfaces while retaining all expanded dielectric thickness",
                  "source_files": [{"name": name, "size_bytes": (source / name).stat().st_size,
                                    "sha256": hashlib.sha256((source / name).read_bytes()).hexdigest()} for name in INPUT_FILES],
                  "source_sub_sha256": hashlib.sha256(baseline_sub.read_bytes()).hexdigest(),
                  "canonical_ltd_sha256": hashlib.sha256((output / "proj.ltd").read_bytes()).hexdigest(),
                  "next_checks": ["Run substrate preprocessing and verify_generated_sub on canonical proj.sub",
                                  "Independently compare exact 65/80 GHz complex S under the frozen tolerance"]})
    (output / "stack-equivalence-proof.json").write_text(json.dumps(proof, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return proof


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Original retained solver-input directory")
    parser.add_argument("--output", type=Path, required=True, help="Fresh canonical solver-input directory outside source")
    parser.add_argument("--reference-sub", type=Path, help="Retained original preprocessor SUB; default source/proj.sub")
    args = parser.parse_args()
    proof = canonicalize(args.source, args.output, args.reference_sub)
    old = proof["original_effective_profile"]["finite_slab_count"]
    new = proof["canonical_effective_profile"]["finite_slab_count"]
    print(f"Physical profile proof: {proof['status']}; expanded slabs {old} to {new}")
    print("Actual canonical preprocessing and exact-frequency EM reproduction remain required.")


if __name__ == "__main__":
    main()
