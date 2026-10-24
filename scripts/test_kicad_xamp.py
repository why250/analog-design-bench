"""Regression checks for native-export configuration and interface adaptation."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from kicad_xamp import (
    PORTS, assemble, children, configure_text, logical_spice, parse_native,
    parse_sexpr, read_text, validate_export, write_text,
)


class NativeExportTests(unittest.TestCase):
    def test_configuration_preserves_geometry_and_is_idempotent(self):
        source = ('(kicad_sch (version 20260306) '
                  '(wire (pts (xy 1 2) (xy 3 4))) '
                  '(symbol (lib_id "AnalogBench:SKY130_NMOS_LVT_4T") '
                  '(property "Reference" "Q7") (property "W" "4") '
                  '(at 10 20 90) (uuid "retained")))')
        configured, count = configure_text(source)
        self.assertEqual(count, 1)
        self.assertIn('(wire (pts (xy 1 2) (xy 3 4)))', configured)
        self.assertIn('(at 10 20 90) (uuid "retained")', configured)
        self.assertIn('${W}', configured)
        self.assertEqual(configure_text(configured), (configured, 1))

    def native(self, width='4'):
        return ('* native output\n.subckt amplifier\n'
                '+ ibias loop_out vdd vfb vref vss ; inout\n'
                f'XQ7 /nleft /nleft vss vss sky130_fd_pr__nfet_01v8_lvt '
                f'w={width} l=1 m=20 mult=20\n.ends\n')

    def xml(self, width='4'):
        return ('<export><components><comp ref="Q7"><fields>'
                '<field name="Model">sky130_fd_pr__nfet_01v8_lvt</field>'
                '<field name="NetlistInstance">XNM0</field>'
                f'<field name="W">{width}</field><field name="L">1</field>'
                '<field name="m">20</field><field name="mult">20</field>'
                '</fields><libsource part="SKY130_NMOS_LVT_4T"/></comp>'
                '</components><nets><net name="/nleft"><node ref="Q7" pin="1"/>'
                '<node ref="Q7" pin="2"/></net><net name="vss">'
                '<node ref="Q7" pin="3"/><node ref="Q7" pin="4"/>'
                '</net></nets></export>')

    def test_adapter_uses_exported_port_order_and_keeps_native_body(self):
        native = self.native()
        core = '.subckt nmos_pass_ldo vdd vout\nR1 vdd vout 1k\n.ends nmos_pass_ldo\n'
        result = assemble(native, core)
        self.assertIn(native.rstrip(), result)
        self.assertIn('XKICAD ibias loop_out vdd vfb vref vss amplifier', result)
        self.assertIn(core.rstrip(), result)

    def test_stale_parameter_and_wrong_pins_are_rejected(self):
        self.assertEqual(len(validate_export(self.xml(), self.native())), 1)
        with self.assertRaises(ValueError):
            validate_export(self.xml('8'), self.native())
        with self.assertRaises(ValueError):
            validate_export(self.xml(), self.native().replace('/nleft /nleft', 'vss /nleft'))

    def test_missing_port_and_placeholder_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_native(self.native().replace(' vref', ''))
        with self.assertRaises(ValueError):
            parse_native(self.native().replace(logical_spice(self.native())[1], 'Q7 __Q7'))


class NativeCliIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        explicit = os.environ.get('KICAD_CLI')
        if explicit:
            cls.cli = Path(explicit).expanduser()
            if not cls.cli.is_file():
                raise ValueError('KICAD_CLI must identify an existing KiCad CLI executable')
            return
        executable = shutil.which('kicad-cli') or shutil.which('kicad-cli.exe')
        if executable:
            cls.cli = Path(executable)
            return
        for variable, suffix in [
            ('LOCALAPPDATA', 'Programs/KiCad/10.0/bin/kicad-cli.exe'),
            ('ProgramFiles', 'KiCad/10.0/bin/kicad-cli.exe'),
        ]:
            directory = os.environ.get(variable)
            if directory and (Path(directory) / suffix).is_file():
                cls.cli = Path(directory) / suffix
                return
        raise unittest.SkipTest('KiCad CLI not found; set KICAD_CLI to run native export checks')

    def export_pair(self, schematic, directory, label):
        outputs = {}
        for fmt in ['spicemodel', 'kicadxml']:
            output = directory / f'{label}-{fmt}.net'
            completed = subprocess.run(
                [str(self.cli), 'sch', 'export', 'netlist', '--format', fmt,
                 '--output', str(output), str(schematic)],
                capture_output=True, timeout=60,
            )
            self.assertEqual(
                completed.returncode, 0,
                (completed.stdout + completed.stderr).decode('utf-8', errors='replace'),
            )
            self.assertTrue(output.is_file(), f'KiCad did not create {output.name}')
            outputs[fmt] = read_text(output)
        validate_export(outputs['kicadxml'], outputs['spicemodel'])
        return outputs['spicemodel']

    def test_native_width_binding_and_named_interface(self):
        workspace = Path(__file__).resolve().parents[1] / 'workspaces/nmos-ldo'
        project = workspace / 'kicad'
        source = project / 'sheets/error-amplifier.kicad_sch'
        library = project / 'AnalogBench.kicad_sym'
        hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in [source, library]}
        configured, count = configure_text(read_text(source))
        self.assertGreater(count, 0)
        instances = children(parse_sexpr(configured), 'symbol')
        target = next(node for node in instances
                      if any(p['items'][1:3] == ['Model', 'sky130_fd_pr__nfet_01v8_lvt']
                             for p in children(node, 'property')))
        props = {p['items'][1]: p for p in children(target, 'property')}
        reference = props['Reference']['items'][2]
        native_reference = reference if reference.upper().startswith('X') else 'X' + reference
        original_width = float(props['W']['items'][2])
        self.assertGreater(original_width, 0)
        new_width = original_width * 2
        width_property = props['W']
        fragment = configured[width_property['start']:width_property['end']]
        fragment, replacements = re.subn(
            r'^(\(\s*property\s+"W"\s+)"(?:\\.|[^"\\])*"',
            lambda match: match[1] + json.dumps(format(new_width, '.17g')),
            fragment, count=1,
        )
        self.assertEqual(replacements, 1)
        changed = (configured[:width_property['start']] + fragment
                   + configured[width_property['end']:])
        with tempfile.TemporaryDirectory(prefix='kicad-xamp-native-test-') as temporary:
            directory = Path(temporary)
            schematic = directory / 'error-amplifier.kicad_sch'
            write_text(directory / 'error-amplifier.kicad_pro', '{}\n')
            shutil.copy2(library, directory / library.name)
            shutil.copy2(project / 'sym-lib-table', directory / 'sym-lib-table')
            write_text(schematic, configured)
            before = self.export_pair(schematic, directory, 'before')
            name, ports, devices_before = parse_native(before)
            self.assertEqual(name, schematic.stem)
            self.assertEqual(set(ports), set(PORTS))
            write_text(schematic, changed)
            after = self.export_pair(schematic, directory, 'after')
            name_after, ports_after, devices_after = parse_native(after)
            self.assertEqual((name_after, ports_after), (name, ports))
            self.assertEqual(set(devices_before), set(devices_after))
            for ref, original in devices_before.items():
                updated = devices_after[ref]
                if ref != native_reference:
                    self.assertEqual(updated, original)
                    continue
                self.assertEqual(updated[:6], original[:6])
                old_params = dict(token.split('=', 1) for token in original[6:])
                new_params = dict(token.split('=', 1) for token in updated[6:])
                self.assertEqual(float(old_params['w']), original_width)
                self.assertEqual(float(new_params['w']), new_width)
                old_params.pop('w')
                new_params.pop('w')
                self.assertEqual(new_params, old_params)
            assembled = assemble(after, read_text(workspace / 'circuit.spi'))
            self.assertIn(after.rstrip(), assembled)
            self.assertIn('XKICAD ' + ' '.join(ports) + ' ' + name, assembled)
        for path, digest in hashes.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)


if __name__ == '__main__':
    unittest.main()
