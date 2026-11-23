"""Focused native-consumer guards; no ADS imports or simulator execution."""

from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_s2p_roundtrip import _wire_references_to_ground, validate_native_netlist


class NativeFileGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.model = Path(self.temporary.name) / "retained input" / "model.s2p"
        self.model.parent.mkdir()
        self.model.write_text("! retained model\n", encoding="ascii")

    def netlist(self, file_value):
        return (
            f'S2P:S2P1 p n 0 File="{file_value}" Type="touchstone" '
            'InterpMode="linear" InterpDom="ri" Temp=25\n'
            'Port:T1 p 0 Num=1 Z=50 Ohm Temp=25\n'
            'Port:T2 n 0 Num=2 Z=50 Ohm Temp=25\n'
        )

    def test_posix_and_windows_separators_resolve_to_exact_copy(self):
        original = self.model.read_bytes()
        for file_value in (self.model.as_posix(), self.model.as_posix().replace("/", "\\")):
            with self.subTest(file_value=file_value):
                self.assertEqual(validate_native_netlist(self.netlist(file_value), self.model)["reference_ohm"], 50)
        self.assertEqual(self.model.read_bytes(), original)

    def test_other_existing_model_is_rejected(self):
        other = self.model.with_name("other.s2p")
        other.write_bytes(self.model.read_bytes())
        with self.assertRaisesRegex(ValueError, "retained model copy"):
            validate_native_netlist(self.netlist(other.as_posix().replace("/", "\\")), self.model)

    def test_missing_and_relative_model_paths_are_rejected(self):
        for file_value in (self.model.with_name("missing.s2p").as_posix(), "model.s2p"):
            with self.subTest(file_value=file_value), self.assertRaisesRegex(ValueError, "retained model copy"):
                validate_native_netlist(self.netlist(file_value), self.model)

    def test_duplicate_file_and_changed_interpolation_are_rejected(self):
        native = self.netlist(self.model.as_posix())
        duplicate = native.replace('Type="touchstone"', f'File="{self.model.as_posix()}" Type="touchstone"')
        with self.assertRaisesRegex(ValueError, "exactly one quoted File"):
            validate_native_netlist(duplicate, self.model)
        for changed in (native.replace('InterpDom="ri"', 'InterpDom=""'),
                        native.replace('InterpMode="linear"', 'InterpMode="spline"')):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate_native_netlist(changed, self.model)

    def test_shared_floating_reference_is_rejected(self):
        native = self.netlist(self.model.as_posix()).replace("p n 0", "p n reference").replace("p 0", "p reference").replace("n 0", "n reference")
        with self.assertRaisesRegex(ValueError, "common-reference order"):
            validate_native_netlist(native, self.model)


class NativeGroundWiringTests(unittest.TestCase):
    @staticmethod
    def instance(points):
        terminals = {number: SimpleNamespace(term_number=number, first_inst_pin=SimpleNamespace(
            snap_point=SimpleNamespace(x=point[0], y=point[1]))) for number, point in points.items()}
        return SimpleNamespace(inst_terms=list(terminals.values()), inst_term_numbered=terminals.__getitem__)

    def test_reference_pins_connect_directly_to_actual_ground_pin_without_labels(self):
        wires = []
        design = SimpleNamespace(add_wire=lambda points: wires.append(points))
        component = self.instance({3: (0.5, -0.5)})
        term1 = self.instance({2: (-2, 1)})
        term2 = self.instance({2: (4, 1)})
        ground = self.instance({7: (0.5, -2)})
        _wire_references_to_ground(design, [(component, 3), (term1, 2), (term2, 2)], ground)
        self.assertEqual(wires, [[(0.5, -0.5), (0.5, -2.0)],
                                 [(-2.0, 1.0), (-2.0, -2.0), (0.5, -2.0)],
                                 [(4.0, 1.0), (4.0, -2.0), (0.5, -2.0)]])
        # add_wire returns None in this mock: any attempted alias label would fail.

    def test_ambiguous_ground_symbol_is_rejected(self):
        design = SimpleNamespace(add_wire=lambda points: None)
        with self.assertRaisesRegex(ValueError, "exactly one terminal"):
            _wire_references_to_ground(design, [], self.instance({1: (0, 0), 2: (1, 0)}))


if __name__ == "__main__":
    unittest.main()
