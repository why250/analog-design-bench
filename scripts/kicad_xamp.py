"""Configure and validate native KiCad SPICE exports for the NMOS LDO XAMP."""

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


PORTS = ['ibias', 'vdd', 'vfb', 'loop_out', 'vref', 'vss']
MODEL_BY_SYMBOL = {
    'SKY130_NMOS_LVT_4T': 'sky130_fd_pr__nfet_01v8_lvt',
    'SKY130_PMOS_LVT_4T': 'sky130_fd_pr__pfet_01v8_lvt',
}
SIM_FIELDS = {
    'Sim.Device': 'SPICE',
    'Sim.Pins': '1=1 2=2 3=3 4=4',
    'Sim.Params': 'type="X" model="${Model} w=${W} l=${L} m=${m} mult=${mult}"',
}


def read_text(path):
    return Path(path).read_bytes().decode('utf-8-sig')


def write_text(path, text):
    Path(path).write_bytes(text.encode('utf-8'))


def parse_sexpr(text):
    """Retain source ranges so configuration does not rewrite drawing geometry."""
    tokens = list(re.finditer(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text, re.S))

    def parse(index):
        if tokens[index].group() != '(':
            raise ValueError('Expected an S-expression')
        start = tokens[index].start()
        items = []
        index += 1
        while tokens[index].group() != ')':
            value = tokens[index].group()
            if value == '(':
                node, index = parse(index)
                items.append(node)
            else:
                items.append(json.loads(value) if value.startswith('"') else value)
                index += 1
        return {'start': start, 'end': tokens[index].end(), 'items': items}, index + 1

    root, end = parse(0)
    if end != len(tokens):
        raise ValueError('Unexpected data after schematic')
    return root


def children(node, head):
    return [item for item in node['items']
            if isinstance(item, dict) and item['items'][0] == head]


def configure_text(text):
    root = parse_sexpr(text)
    nodes = children(root, 'symbol')
    for library in children(root, 'lib_symbols'):
        nodes += children(library, 'symbol')
    edits = []
    configured = 0
    eol = '\r\n' if '\r\n' in text else '\n'
    for node in nodes:
        lib_id = children(node, 'lib_id')
        name = lib_id[0]['items'][1] if lib_id else node['items'][1]
        if name.split(':')[-1] not in MODEL_BY_SYMBOL:
            continue
        props = children(node, 'property')
        by_name = {prop['items'][1]: prop for prop in props}
        additions = []
        for key, value in SIM_FIELDS.items():
            prop_text = (f'(property {json.dumps(key)} {json.dumps(value)} '
                         '(at 0 0 0) (hide yes) (effects (font (size 1 1))))')
            if key in by_name:
                prop = by_name[key]
                if prop['items'][2] != value:
                    edits.append((prop['start'], prop['end'], prop_text))
            else:
                additions.append(eol + '\t\t' + prop_text)
        if additions:
            pos = props[-1]['end']
            edits.append((pos, pos, ''.join(additions)))
        configured += 1
    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text, configured


def fresh_result(workspace, prefix):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    result = workspace / 'results' / f'{prefix}-{stamp}'
    result.mkdir(parents=True, exist_ok=False)
    return result


def configure(workspace):
    project = workspace / 'kicad'
    # An editor with an older in-memory copy could overwrite the new fields.
    if (project / '~nmos-ldo.kicad_sch.lck').exists():
        raise ValueError('Save and close the schematic editor before configuration.')
    paths = [project / 'AnalogBench.kicad_sym',
             project / 'sheets' / 'error-amplifier.kicad_sch']
    prepared = [(path, *configure_text(read_text(path))) for path in paths]
    for path, _, count in prepared:
        if not count:
            raise ValueError(f'No supported symbols in {path}')
    result = fresh_result(workspace, 'kicad-spice-config')
    for path, updated, count in prepared:
        shutil.copy2(path, result / path.name)
        if read_text(path) != updated:
            write_text(path, updated)
    write_text(result / 'README.md',
               '# Native SPICE configuration backup\n\n'
               'These are the files before configuration. Only hidden Sim.* '
               'properties were added or updated; drawing geometry is retained.\n')
    return result


def logical_spice(text):
    lines = []
    for raw in text.splitlines():
        line = raw.split(';', 1)[0].strip()
        if not line or line.startswith('*'):
            continue
        if line.startswith('+'):
            if not lines:
                raise ValueError('SPICE continuation without a preceding line')
            lines[-1] += ' ' + line[1:].strip()
        else:
            lines.append(line)
    return lines


def parse_native(text):
    lines = logical_spice(text)
    headers = [line.split() for line in lines if line.lower().startswith('.subckt')]
    if len(headers) != 1 or len(headers[0]) != 8:
        raise ValueError('Expected one named native XAMP subcircuit with six ports.')
    name, ports = headers[0][1], headers[0][2:]
    if len(set(ports)) != 6 or set(ports) != set(PORTS):
        raise ValueError(f'Unexpected native XAMP interface: {ports}')
    devices = {}
    for line in lines:
        if line.startswith('.'):
            if line.split()[0].lower() not in {'.subckt', '.ends'}:
                raise ValueError(f'Unexpected directive in native XAMP: {line}')
            continue
        tokens = line.split()
        if len(tokens) != 10 or not tokens[0].upper().startswith('X'):
            raise ValueError(f'Incomplete or unsupported native device: {line}')
        if tokens[0] in devices:
            raise ValueError(f'Duplicate native instance: {tokens[0]}')
        devices[tokens[0]] = tokens
    if not devices:
        raise ValueError('Native XAMP export contains no devices')
    return name, ports, devices


def net_name(name):
    return name.rsplit('/', 1)[-1]


def validate_export(xml_text, native_text):
    root = ET.fromstring(xml_text)
    _, _, devices = parse_native(native_text)
    pin_nets = {}
    for net in root.findall('./nets/net'):
        for node in net.findall('node'):
            pin_nets[(node.get('ref'), node.get('pin'))] = net_name(net.get('name'))
    rows = []
    names = set()
    refs = set()
    for component in root.findall('./components/comp'):
        ref = component.get('ref')
        fields = {field.get('name'): field.text or ''
                  for field in component.findall('./fields/field')}
        part = component.find('libsource').get('part')
        if part not in MODEL_BY_SYMBOL or fields.get('Model') != MODEL_BY_SYMBOL[part]:
            raise ValueError(f'Unsupported symbol/model on {ref}')
        instance = fields.get('NetlistInstance', '')
        if not re.fullmatch(r'X[A-Za-z0-9_]+', instance) or instance in names:
            raise ValueError(f'Missing or duplicate NetlistInstance on {ref}')
        names.add(instance)
        native_ref = ref if ref.upper().startswith('X') else 'X' + ref
        refs.add(native_ref)
        if native_ref not in devices:
            raise ValueError(f'Native SPICE device missing for {ref}')
        tokens = devices[native_ref]
        expected_nets = [pin_nets.get((ref, str(pin))) for pin in range(1, 5)]
        if None in expected_nets or [net_name(n) for n in tokens[1:5]] != expected_nets:
            raise ValueError(f'Native pin mapping does not match XML on {ref}')
        params = dict(token.split('=', 1) for token in tokens[6:])
        if tokens[5] != fields['Model'] or set(params) != {'w', 'l', 'm', 'mult'}:
            raise ValueError(f'Unexpected model/parameters in native device {ref}')
        for field, param in [('W', 'w'), ('L', 'l'), ('m', 'm'), ('mult', 'mult')]:
            value = float(fields.get(field, ''))
            if not math.isfinite(value) or value <= 0 or float(params[param]) != value:
                raise ValueError(f'Invalid or stale {field} simulation value on {ref}')
        rows.append({'reference': ref, 'native_reference': native_ref,
                     'netlist_instance': instance, 'nets_dgsb': expected_nets,
                     'model': tokens[5], 'parameters': params})
    if refs != set(devices):
        raise ValueError('Native SPICE and XML component sets differ')
    return rows


def assemble(native_text, source_text):
    name, ports, _ = parse_native(native_text)
    # The uncompleted LDO core is deliberately taken from the retained source.
    core = re.search(r'^\.subckt\s+nmos_pass_ldo\b.*?^\.ends\b[^\n]*',
                     source_text, re.M | re.S | re.I)
    if not core:
        raise ValueError('Source circuit is missing nmos_pass_ldo')
    return ('* Hybrid diagnostic: native KiCad XAMP plus source-netlist LDO core.\n'
            + native_text.rstrip() + '\n\n'
            + '.subckt ldo_error_amplifier ' + ' '.join(PORTS) + '\n'
            + 'XKICAD ' + ' '.join(ports) + ' ' + name + '\n'
            + '.ends ldo_error_amplifier\n\n' + core.group(0) + '\n')


def export(workspace, cli):
    result = fresh_result(workspace, 'kicad-xamp')
    inputs = result / 'inputs'
    inputs.mkdir()
    project = workspace / 'kicad'
    # Give the CLI a named project for the sheet-only SPICE Model export.
    # No generated device lines are converted, renamed, or reordered.
    shutil.copy2(project / 'sheets' / 'error-amplifier.kicad_sch',
                 inputs / 'error-amplifier.kicad_sch')
    shutil.copy2(project / 'AnalogBench.kicad_sym', inputs / 'AnalogBench.kicad_sym')
    shutil.copy2(project / 'sym-lib-table', inputs / 'sym-lib-table')
    shutil.copy2(project / 'nmos-ldo.kicad_pro', inputs / 'parent-project.kicad_pro')
    shutil.copy2(workspace / 'circuit.spi', inputs / 'source-circuit.spi')
    shutil.copy2(workspace / 'testbench' / 'tb_nominal_export.spi',
                 inputs / 'source-bench.spi')
    write_text(inputs / 'error-amplifier.kicad_pro', '{}\n')
    schematic = inputs / 'error-amplifier.kicad_sch'
    commands = []
    for fmt, filename in [('spicemodel', 'xamp-native.spi'), ('kicadxml', 'connectivity.xml')]:
        command = [str(cli), 'sch', 'export', 'netlist', '--format', fmt,
                   '--output', str(result / filename), str(schematic)]
        completed = subprocess.run(command, capture_output=True)
        (result / f'export-{fmt}.log').write_bytes(completed.stdout + completed.stderr)
        commands.append(command)
        if completed.returncode:
            raise ValueError(f'KiCad {fmt} export failed; see {result}')
    native = read_text(result / 'xamp-native.spi')
    rows = validate_export(read_text(result / 'connectivity.xml'), native)
    write_text(result / 'circuit.spi', assemble(native, read_text(inputs / 'source-circuit.spi')))
    # The shared runner must use this retained bench, not a later workspace edit.
    shutil.copy2(inputs / 'source-bench.spi', result / 'bench-source.spi')
    manifest = {
        'scope': 'native schematic XAMP plus source-netlist LDO core; nominal diagnostic only',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'commands': commands, 'devices': rows,
        'native_header': logical_spice(native)[0],
        'input_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in inputs.iterdir() if p.is_file()},
    }
    write_text(result / 'manifest.json', json.dumps(manifest, indent=2) + '\n')
    write_text(result / 'README.md',
               '# Native KiCad XAMP export\n\n'
               '`xamp-native.spi` is unmodified KiCad SPICE Model output. '
               '`connectivity.xml` is a separate native export used only to validate '
               'pins and field values. No XML-to-SPICE conversion is used.\n\n'
               '`circuit.spi` embeds the native subcircuit verbatim, adds an interface '
               'adapter using its exported port order, and retains the source-netlist '
               'LDO core. It does not overwrite the workspace circuit.spi.\n\n'
               'The simulator and PDK stay in Docker. This is a nominal hybrid '
               'diagnostic, not full-schematic verification or official acceptance.\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['configure', 'export'])
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--kicad-cli', type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if args.mode == 'configure':
        result = configure(workspace)
    else:
        if not args.kicad_cli or not args.kicad_cli.is_file():
            parser.error('--kicad-cli must identify the installed KiCad CLI')
        result = export(workspace, args.kicad_cli)
    print(result)


if __name__ == '__main__':
    main()
