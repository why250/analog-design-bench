"""Prove inactive-layer compression preserves background and active faces."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import canonicalize_stack as canonical
from validate_inputs import InputError, parse_ltd


def original_ltd():
    materials = [
        f"MATERIAL Metal{n} CONDUCTIVITY={'2.405e7' if n >= 5 else '2.40509e7'} IMAG_CONDUCTIVITY=0 PERMEABILITY=1"
        for n in range(1, 7)] + [
        "MATERIAL Poly CONDUCTIVITY=625000 PERMEABILITY=1",
        "MATERIAL Via CONDUCTIVITY=4e6 PERMEABILITY=1",
        "MATERIAL Silicon PERMITTIVITY=11.9 PERMEABILITY=1 IMAG_PERMEABILITY=0 RESISTIVITY=20 DOPING=ptype",
        "MATERIAL sub PERMITTIVITY=3.9 IMAG_PERMITTIVITY=-0.0195 PERMEABILITY=1 IMAG_PERMEABILITY=0",
        "MATERIAL ResearchOx1 PERMITTIVITY=4.2 IMAG_PERMITTIVITY=-0.021 PERMEABILITY=1 IMAG_PERMEABILITY=0",
        "MATERIAL ox_mixed_eff PERMITTIVITY=3.76 IMAG_PERMITTIVITY=-0.0188 PERMEABILITY=1 IMAG_PERMEABILITY=0",
        "MATERIAL pass1 PERMITTIVITY=4.2 IMAG_PERMITTIVITY=-0.021 PERMEABILITY=1 IMAG_PERMEABILITY=0",
        "MATERIAL pass2 PERMITTIVITY=7.9 IMAG_PERMITTIVITY=-0.0395 PERMEABILITY=1 IMAG_PERMEABILITY=0"]
    thicknesses = ["5.3e-7", "5.3e-7", "5.3e-7", "5.3e-7", "6e-7", "9.9e-7"]
    operations = [f"OPERATION ThicknessMetal{n} EXPAND={t} UP" for n, t in enumerate(thicknesses, 1)]
    operations += ["OPERATION ThicknessPoly EXPAND=2e-7 UP", "OPERATION ViaDrill DRILL"]
    masks = [f"MASK {layer} Name=Metal{n} MATERIAL=Metal{n} OPERATION=ThicknessMetal{n}"
             for n, layer in enumerate([7, 9, 11, 31, 33, 35], 1)]
    masks += ["MASK 3 Name=Poly MATERIAL=Poly OPERATION=ThicknessPoly", "MASK 34 Name=Via5 MATERIAL=Via OPERATION=ViaDrill"]
    stack = """TOP OPEN MATERIAL=AIR
INTERFACE Name=i10
LAYER Name=s10 HEIGHT=7e-7 MATERIAL=pass2
INTERFACE Name=i9
LAYER Name=s9 HEIGHT=1e-6 MATERIAL=pass1
INTERFACE Name=i8 MASK={Metal6}
LAYER Name=s8 MASK={Via5} HEIGHT=8e-7 MATERIAL=ox_mixed_eff
INTERFACE Name=i7 MASK={Metal5}
LAYER Name=s7 HEIGHT=8e-7 MATERIAL=ox_mixed_eff
INTERFACE Name=i6 MASK={Metal4}
LAYER Name=s6 HEIGHT=8e-7 MATERIAL=ox_mixed_eff
INTERFACE Name=i5 MASK={Metal3}
LAYER Name=s5 HEIGHT=8e-7 MATERIAL=ox_mixed_eff
INTERFACE Name=i4 MASK={Metal2}
LAYER Name=s4 HEIGHT=8e-7 MATERIAL=ox_mixed_eff
INTERFACE Name=i3 MASK={Metal1}
LAYER Name=s3 HEIGHT=5e-7 MATERIAL=ResearchOx1
INTERFACE Name=i2 MASK={Poly}
LAYER Name=s2 HEIGHT=3.5e-7 MATERIAL=sub
INTERFACE Name=i1
LAYER Name=s1 HEIGHT=5e-4 MATERIAL=Silicon
INTERFACE Name=i0
BOTTOM OPEN MATERIAL=AIR"""
    sections = [("MATERIAL", "\n".join(materials)), ("OPERATION", "\n".join(operations)),
                ("MASK", "\n".join(masks)), ("STACK", stack)]
    header = "TECHFORMAT=V2\nUNITS\nDISTANCE=METRE\nCONDUCTIVITY=SIEMENS/M\nRESISTIVITY=OHM.CM\nEND_UNITS\n"
    return header + "".join(f"BEGIN_{name}\n{body}\nEND_{name}\n" for name, body in sections)


ORIGINAL = original_ltd()
# An independent transcription of the observed preprocessor output, in um.
ORIGINAL_SUB_ROWS = [
    ("0.7", "7.9", "-0.0395", False), ("1", "4.2", "-0.021", False),
    ("0.99", "4.2", "-0.021", True),
    ("0.8", "3.76", "-0.0188", True), ("0.6", "3.76", "-0.0188", True),
    ("0.8", "3.76", "-0.0188", True), ("0.53", "3.76", "-0.0188", True),
    ("0.8", "3.76", "-0.0188", True), ("0.53", "3.76", "-0.0188", True),
    ("0.8", "3.76", "-0.0188", True), ("0.53", "3.76", "-0.0188", True),
    ("0.8", "3.76", "-0.0188", True), ("0.53", "3.76", "-0.0188", True),
    ("0.5", "4.2", "-0.021", True), ("0.2", "4.2", "-0.021", True),
    ("0.35", "3.9", "-0.0195", True), ("500", "11.9", "conductivity:5", False)]
CANONICAL_SUB_ROWS = [ORIGINAL_SUB_ROWS[0], ORIGINAL_SUB_ROWS[1], ORIGINAL_SUB_ROWS[2],
                      ("6.19", "3.76", "-0.0188", True), ("0.53", "3.76", "-0.0188", True),
                      ("0.7", "4.2", "-0.021", True), ORIGINAL_SUB_ROWS[-2], ORIGINAL_SUB_ROWS[-1]]


def sub_text(rows):
    lines = ["UNITS METRE", "BOTTOMPLANE OPEN", "TOPPLANE OPEN", "LAYERS",
             "0 THICKNESS INFINITY", "PERMITTIVITY VALUE 1 0", "PERMEABILITY VALUE 1 0,"]
    for number, (height_um, er, loss, strip) in enumerate(rows, 1):
        lines.append(f"{number} THICKNESS {Decimal(height_um) * Decimal('1e-6')}")
        if loss.startswith("conductivity:"):
            lines.append(f"PERMITTIVITY CONDUCTIVITY {er} {loss.split(':')[1]}")
        else:
            lines.append(f"PERMITTIVITY VALUE {er} {loss}")
        lines.append("PERMEABILITY VALUE 1 0")
        if strip:
            lines.extend(["STRIP", "VIA"])
    lines.extend([f"{len(rows)+1} THICKNESS INFINITY", "PERMITTIVITY VALUE 1 0", "PERMEABILITY VALUE 1 0;"])
    return "\n".join(lines) + "\n"


class StackProjectionTests(unittest.TestCase):
    def test_original_effective_profile_and_faces_match_observed_expansion(self):
        profile = canonical.expanded_ltd_profile(ORIGINAL)
        self.assertEqual(profile["finite_slab_count"], 17)
        self.assertEqual(profile["active_faces_um"][7], (Decimal("1.05"), Decimal("1.58")))
        self.assertEqual(profile["active_faces_um"][35], (Decimal("7.77"), Decimal("8.76")))
        self.assertEqual(profile["top_surface_um"], Decimal("10.46"))
        self.assertTrue(canonical._same_profile(profile, canonical.expanded_sub_profile(sub_text(ORIGINAL_SUB_ROWS))))

    def test_canonical_projection_preserves_all_materials_and_active_faces(self):
        candidate = canonical.canonical_ltd_text(ORIGINAL)
        proof = canonical.prove_equivalent(ORIGINAL, candidate, sub_text(ORIGINAL_SUB_ROWS))
        self.assertEqual(proof["status"], "SATISFIED")
        self.assertEqual(proof["canonical_effective_profile"]["finite_slab_count"], 8)
        self.assertEqual(parse_ltd(ORIGINAL)["materials"], parse_ltd(candidate)["materials"])
        self.assertEqual(set(parse_ltd(candidate)["masks"]), {"7", "35"})
        self.assertEqual(len(parse_ltd(candidate)["operations"]), 2)
        self.assertEqual(canonical.verify_generated_sub(candidate, sub_text(CANONICAL_SUB_ROWS))["status"], "SATISFIED")
        self.assertTrue(all(row["medium"]["ei"] <= 0 for row in canonical.expanded_ltd_profile(candidate)["intervals"]))

    def test_positive_direct_imaginary_gain_is_rejected_in_source_and_sub(self):
        wrong_source = ORIGINAL.replace("IMAG_PERMITTIVITY=-0.0188", "IMAG_PERMITTIVITY=0.0188")
        with self.assertRaisesRegex(InputError, "represents gain"):
            canonical.expanded_ltd_profile(wrong_source)
        wrong_sub = sub_text(ORIGINAL_SUB_ROWS).replace("VALUE 3.76 -0.0188", "VALUE 3.76 0.0188", 1)
        with self.assertRaisesRegex(InputError, "represents gain"):
            canonical.verify_generated_sub(ORIGINAL, wrong_sub)

    def test_candidate_thickness_and_active_face_errors_are_rejected(self):
        candidate = canonical.canonical_ltd_text(ORIGINAL)
        for changed in (candidate.replace("HEIGHT=6.19e-6", "HEIGHT=6.18e-6"),
                        candidate.replace("HEIGHT=5e-4", "HEIGHT=4.99e-4"),
                        candidate.replace("EXPAND=9.9e-7", "EXPAND=1e-6")):
            with self.subTest(changed=changed[-150:]), self.assertRaises(InputError):
                canonical.prove_equivalent(ORIGINAL, changed, sub_text(ORIGINAL_SUB_ROWS))

    def test_same_epsilon_profile_with_wrong_current_support_faces_is_rejected(self):
        candidate = canonical.canonical_ltd_text(ORIGINAL)
        shifted = list(CANONICAL_SUB_ROWS)
        shifted[3] = ("6.18", "3.76", "-0.0188", True)
        shifted[4] = ("0.54", "3.76", "-0.0188", True)
        self.assertTrue(canonical._same_profile(canonical.expanded_ltd_profile(candidate), canonical.expanded_sub_profile(sub_text(shifted))))
        with self.assertRaisesRegex(InputError, "conductor support faces"):
            canonical.verify_generated_sub(candidate, sub_text(shifted))

    def test_changed_inactive_material_definition_is_rejected(self):
        candidate = canonical.canonical_ltd_text(ORIGINAL).replace("Metal2 CONDUCTIVITY=2.40509e7", "Metal2 CONDUCTIVITY=1e6")
        with self.assertRaisesRegex(InputError, "Material definitions changed"):
            canonical.prove_equivalent(ORIGINAL, candidate, sub_text(ORIGINAL_SUB_ROWS))

    def test_actual_preprocessed_loss_change_is_rejected(self):
        wrong = sub_text(ORIGINAL_SUB_ROWS).replace("VALUE 3.76 -0.0188", "VALUE 3.76 -0.0187", 1)
        with self.assertRaisesRegex(InputError, "preprocessed SUB differs"):
            canonical.verify_generated_sub(ORIGINAL, wrong)

    def source_directory(self, root):
        source = root / "source"
        source.mkdir()
        for name in canonical.INPUT_FILES:
            (source / name).write_bytes(b"unchanged input\r\n")
        (source / "proj.ltd").write_bytes(ORIGINAL.replace("\n", "\r\n").encode())
        (source / "proj.sub").write_text(sub_text(ORIGINAL_SUB_ROWS))
        (source / "proj_a").write_text("UNITS UM,2000; EDIT proj; ADD P7 :W0 0,0 1,0 0,1; ADD P35 :W0 2,2 3,2 2,3; SAVE;")
        return source

    def test_fresh_projection_retains_original_bytes_and_untouched_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.source_directory(root)
            before = {p.name: p.read_bytes() for p in source.iterdir()}
            output = root / "canonical"
            result = canonical.canonicalize(source, output)
            self.assertEqual(result["status"], "SATISFIED")
            self.assertEqual({p.name: p.read_bytes() for p in source.iterdir()}, before)
            self.assertEqual((output / "original" / "proj.ltd").read_bytes(), before["proj.ltd"])
            self.assertEqual((output / "original" / "proj.sub").read_bytes(), before["proj.sub"])
            for name in canonical.INPUT_FILES:
                if name != "proj.ltd":
                    self.assertEqual((output / name).read_bytes(), before[name])

    def test_via_geometry_rejects_before_any_output_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.source_directory(root)
            (source / "proj_a").write_text((source / "proj_a").read_text().replace("SAVE;", "ADD P34 :W0 4,4 5,4 4,5; SAVE;"))
            output = root / "canonical"
            with self.assertRaisesRegex(InputError, "via or inactive-mask geometry"):
                canonical.canonicalize(source, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
