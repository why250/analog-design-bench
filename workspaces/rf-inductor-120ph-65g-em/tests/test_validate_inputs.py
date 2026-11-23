"""Reject changed physical stacks, hidden references and off-metal terminals."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import validate_inputs as validator


LTD = """TECHFORMAT=V2
UNITS
DISTANCE=METRE
CONDUCTIVITY=SIEMENS/M
RESISTIVITY=OHM.CM
PERMITTIVITY=RELATIVETOVACUUM
PERMEABILITY=RELATIVETOVACUUM
END_UNITS
BEGIN_MATERIAL
MATERIAL Metal1 CONDUCTIVITY=2.40509e7 IMAG_CONDUCTIVITY=0 PERMEABILITY=1
MATERIAL Metal6 CONDUCTIVITY=2.405e7 IMAG_CONDUCTIVITY=0 PERMEABILITY=1
MATERIAL Silicon PERMITTIVITY=11.9 PERMEABILITY=1 IMAG_PERMEABILITY=0 RESISTIVITY=20 DOPING=ptype
MATERIAL sub PERMITTIVITY=3.9 IMAG_PERMITTIVITY=-0.0195 PERMEABILITY=1 IMAG_PERMEABILITY=0
MATERIAL ResearchOx1 PERMITTIVITY=4.2 IMAG_PERMITTIVITY=-0.021 PERMEABILITY=1 IMAG_PERMEABILITY=0
MATERIAL ox_mixed_eff PERMITTIVITY=3.76 IMAG_PERMITTIVITY=-0.0188 PERMEABILITY=1 IMAG_PERMEABILITY=0
MATERIAL pass1 PERMITTIVITY=4.2 IMAG_PERMITTIVITY=-0.021 PERMEABILITY=1 IMAG_PERMEABILITY=0
MATERIAL pass2 PERMITTIVITY=7.9 IMAG_PERMITTIVITY=-0.0395 PERMEABILITY=1 IMAG_PERMEABILITY=0
END_MATERIAL
BEGIN_OPERATION
OPERATION OperationThickness_Metal1 EXPAND=5.3e-7 UP
OPERATION OperationThickness_Metal6 EXPAND=9.9e-7 UP
END_OPERATION
BEGIN_MASK
MASK 7 Name=Metal1 MATERIAL=Metal1 OPERATION=OperationThickness_Metal1
MASK 35 Name=Metal6 MATERIAL=Metal6 OPERATION=OperationThickness_Metal6
END_MASK
BEGIN_STACK
TOP OPEN MATERIAL=AIR
INTERFACE Name=i10
LAYER Name=s10 HEIGHT=7e-7 MATERIAL=pass2
INTERFACE Name=i9
LAYER Name=s9 HEIGHT=1e-6 MATERIAL=pass1
INTERFACE Name=i8 MASK={Metal6}
LAYER Name=s8 HEIGHT=8e-7 MATERIAL=ox_mixed_eff
INTERFACE Name=i7
LAYER Name=s7 HEIGHT=8e-7 MATERIAL=ox_mixed_eff
INTERFACE Name=i6
LAYER Name=s6 HEIGHT=8e-7 MATERIAL=ox_mixed_eff
INTERFACE Name=i5
LAYER Name=s5 HEIGHT=8e-7 MATERIAL=ox_mixed_eff
INTERFACE Name=i4
LAYER Name=s4 HEIGHT=8e-7 MATERIAL=ox_mixed_eff
INTERFACE Name=i3 MASK={Metal1}
LAYER Name=s3 HEIGHT=5e-7 MATERIAL=ResearchOx1
INTERFACE Name=i2
LAYER Name=s2 HEIGHT=3.5e-7 MATERIAL=sub
INTERFACE Name=i1
LAYER Name=s1 HEIGHT=5e-4 MATERIAL=Silicon
INTERFACE Name=i0
BOTTOM OPEN MATERIAL=AIR
END_STACK
"""


def egs(frame_factor=1.8):
    lo, hi = 20 - 20 * frame_factor, 20 + 20 * frame_factor
    return f"""UNITS UM,2000;
EDIT proj;
ADD P35 :W0 0,0 9,0 9,-5 19,-5 19,4 4,4 4,36 36,36 36,4 21,4 21,-5 31,-5 31,0 40,0 40,40 0,40;
ADD P7 :W0 {lo-20},{lo-20} {lo},{lo-20} {lo},{hi+20} {lo-20},{hi+20};
ADD P7 :W0 {hi},{lo-20} {hi+20},{lo-20} {hi+20},{hi+20} {hi},{hi+20};
ADD P7 :W0 {lo},{lo-20} {hi},{lo-20} {hi},{lo} {lo},{lo};
ADD P7 :W0 {lo},{hi} {hi},{hi} {hi},{hi+20} {lo},{hi+20};
SAVE;
"""


def pin_xml(frame_factor=1.8):
    rows = [("P1", 35, "14e-6", "-5e-6"), ("P2", 35, "26e-6", "-5e-6"),
            ("P4", 7, "20e-6", str((20 - 20 * frame_factor - 10) * 1e-6))]
    return "<pin_list>" + "".join(
        f"<pin><name>{name}</name><net>{name}</net><layout><shape><layer>{layer}</layer>"
        f"<purpose>-1</purpose><point><x>{x}</x><y>{y}</y></point></shape></layout></pin>"
        for name, layer, x, y in rows) + "</pin_list>"


PORTS = "<port_setup><port_list>" + "".join(
    f'<port id="{n}"><name>P{n}</name><plus_pin>P{n}</plus_pin><minus_pin>P4</minus_pin>'
    '<impedance><real>50</real><imag>0</imag></impedance></port>' for n in (1, 2)
) + "</port_list></port_setup>"


class PhysicalInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "inputs").mkdir()
        self.input_dir = self.root / "case"
        self.input_dir.mkdir()
        (self.root / "project.toml").write_text(
            '[project]\ntask_id="rf-inductor-120ph-65g-em"\nrevision=1\n'
            'task_version_id="rf-inductor-120ph-65g-em-r1"\n[paths]\ninputs="inputs"\n')
        shutil.copyfile(ROOT / "inputs" / "research-contract-r1.json",
                        self.root / "inputs" / "research-contract-r1.json")
        for name, text in (("proj.ltd", LTD), ("proj_a", egs()), ("proj.pin", pin_xml()), ("proj.prt", PORTS)):
            (self.input_dir / name).write_text(text)

    def validate(self, **kwargs):
        result = validator.validate_inputs(self.root, self.input_dir, **kwargs)
        json.dumps(result, allow_nan=False)
        return result

    def assert_invalid_check(self, result, name):
        self.assertEqual(result["status"], "INVALID")
        self.assertTrue(any(row["check"] == name and row["status"] == "VIOLATION" for row in result["checks"]), result)

    def test_complete_nominal_stack_and_physical_geometry(self):
        receipt = self.root / "construction.json"
        receipt.write_text(json.dumps({"geometry": {"D_um": 40, "w_um": 4, "s_um": 2, "frame_factor": 1.8}}))
        result = self.validate(geometry_receipt=receipt)
        self.assertEqual(result["status"], "SATISFIED", result)
        self.assertEqual(result["geometry"]["derived_top_linewidth_um"], 4)
        self.assertEqual(result["geometry"]["frame"]["side_widths_um"], [20] * 4)
        self.assertEqual(len(result["stack"]["dielectric_layers_top_to_bottom"]), 10)
        self.assertTrue(all(float(result["stack"]["materials"][name]["fields"]["IMAG_PERMITTIVITY"]) < 0
                            for name in ("sub", "ResearchOx1", "ox_mixed_eff", "pass1", "pass2")))

    def test_positive_direct_imaginary_gain_is_rejected(self):
        (self.input_dir / "proj.ltd").write_text(LTD.replace("IMAG_PERMITTIVITY=-0.0188", "IMAG_PERMITTIVITY=0.0188"))
        self.assert_invalid_check(self.validate(), "ox_mixed_eff_passive_direct_imaginary_sign")

    def test_wrong_oxide_permittivity_and_malformed_metal_are_rejected(self):
        changed = LTD.replace("ResearchOx1 PERMITTIVITY=4.2", "ResearchOx1 PERMITTIVITY=4")
        (self.input_dir / "proj.ltd").write_text(changed)
        self.assert_invalid_check(self.validate(), "ResearchOx1_relative_permittivity")
        malformed = LTD.replace("Metal6 CONDUCTIVITY=2.405e7", "Metal6 CONDUCTIVITY=not-a-number")
        (self.input_dir / "proj.ltd").write_text(malformed)
        self.assert_invalid_check(self.validate(), "complete_supported_input_parse")

    def test_perfect_backside_is_rejected(self):
        (self.input_dir / "proj.ltd").write_text(LTD.replace("BOTTOM OPEN MATERIAL=AIR", "BOTTOM CLOSED MATERIAL=PEC"))
        self.assert_invalid_check(self.validate(), "open_air_top_and_bottom")

    def test_wrong_physical_return_is_rejected(self):
        (self.input_dir / "proj.prt").write_text(PORTS.replace("<minus_pin>P4</minus_pin>", "<minus_pin>P1</minus_pin>", 1))
        self.assert_invalid_check(self.validate(), "actual_two_port_physical_return_mapping")

    def test_pin_off_metal_is_rejected(self):
        (self.input_dir / "proj.pin").write_text(pin_xml().replace("<x>14e-6</x>", "<x>0.001</x>"))
        self.assert_invalid_check(self.validate(), "P1_on_exported_metal")

    def test_unexpected_via_geometry_is_rejected(self):
        (self.input_dir / "proj_a").write_text(egs().replace("SAVE;", "ADD P34 :W0 1,1 2,1 1,2;\nSAVE;"))
        self.assert_invalid_check(self.validate(), "only_active_M1_M6_no_vias")

    def test_explicit_sensitivity_factor_does_not_relax_nominal(self):
        (self.input_dir / "proj_a").write_text(egs(1.5))
        (self.input_dir / "proj.pin").write_text(pin_xml(1.5))
        self.assert_invalid_check(self.validate(frame_factor=1.5), "declared_frame_condition")
        self.assertEqual(self.validate(frame_factor=1.5, sensitivity=True)["status"], "SATISFIED")

    def test_wrong_conductor_thickness_and_units_are_rejected(self):
        (self.input_dir / "proj.ltd").write_text(LTD.replace("EXPAND=9.9e-7", "EXPAND=1.2e-6"))
        self.assert_invalid_check(self.validate(), "Metal6_thickness_m")
        (self.input_dir / "proj.ltd").write_text(LTD.replace("DISTANCE=METRE", "DISTANCE=MM"))
        self.assert_invalid_check(self.validate(), "source_unit_distance")

    def test_extra_dielectric_conductivity_and_active_vertical_mask_are_rejected(self):
        altered = LTD.replace("ResearchOx1 PERMITTIVITY=4.2", "ResearchOx1 CONDUCTIVITY=1000 PERMITTIVITY=4.2")
        (self.input_dir / "proj.ltd").write_text(altered)
        self.assert_invalid_check(self.validate(), "ResearchOx1_only_frozen_material_parameters")
        altered = LTD.replace("Name=s8 HEIGHT=8e-7", "Name=s8 MASK={Metal6} HEIGHT=8e-7")
        (self.input_dir / "proj.ltd").write_text(altered)
        self.assert_invalid_check(self.validate(), "Metal6_mapped_only_at_one_interface")


if __name__ == "__main__":
    unittest.main()
