"""Strict Momentum CITIFILE S-matrix reader and Touchstone RI exporter.

Only one packet, one explicit frequency list (Hz), and a complete complex RI
S matrix are accepted. No interpolation, fitting, renormalization or passivity
repair is performed. The reference resistance must be supplied by the caller.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import TextIO


class CitiError(ValueError):
    """The input cannot be represented by this deliberately narrow reader."""


@dataclass(frozen=True)
class SNetwork:
    frequencies_hz: tuple[float, ...]
    # For every frequency, rows are receiving ports and columns exciting ports.
    s: tuple[tuple[tuple[complex, ...], ...], ...]
    name: str

    @property
    def port_count(self) -> int:
        return len(self.s[0])


def _number(token: str, line: int) -> float:
    try:
        value = float(token)
    except ValueError as exc:
        raise CitiError(f"Line {line}: invalid numeric value {token!r}") from exc
    if not math.isfinite(value):
        raise CitiError(f"Line {line}: nonfinite numeric value")
    return value


def parse_citi(text: str) -> SNetwork:
    """Read an explicit CITIFILE packet without changing sample ordering.

    Supports CITIFILE A.01.00 and A.01.01, VAR freq MAG, DATA S[i,j] RI,
    VAR_LIST_BEGIN/END, and one BEGIN/END block per DATA declaration. Metadata
    NAME and COMMENT are retained or ignored; constants and segmented/rational
    data are rejected because their meaning needs separate review.
    """
    records: list[tuple[int, str]] = []
    for line_no, raw in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("!", "#")):
            continue
        if line.upper().startswith("COMMENT"):
            if line.upper() == "COMMENT" or line[7:8].isspace():
                continue
        records.append((line_no, line))
    if not records or records[0][1].upper() not in (
        "CITIFILE A.01.00", "CITIFILE A.01.01"
    ):
        raise CitiError("Expected CITIFILE A.01.00 or A.01.01 header")

    name = "unnamed"
    name_seen = False
    point_count: int | None = None
    declarations: list[tuple[int, int]] = []
    frequencies: list[float] | None = None
    blocks: list[list[complex]] = []
    cursor = 1
    while cursor < len(records):
        line_no, line = records[cursor]
        upper = line.upper()
        if upper.startswith("NAME "):
            if name_seen or frequencies is not None or blocks:
                raise CitiError(f"Line {line_no}: repeated or misplaced NAME")
            name, name_seen = line[5:].strip(), True
        elif upper.startswith("VAR "):
            match = re.fullmatch(r"VAR\s+(?:FREQ|FREQUENCY)\s+MAG\s+([1-9][0-9]*)", line, re.I)
            if not match or point_count is not None or frequencies is not None:
                raise CitiError(f"Line {line_no}: expected exactly one VAR freq MAG count")
            point_count = int(match.group(1))
        elif upper.startswith("DATA "):
            match = re.fullmatch(r"DATA\s+S\[\s*([1-9][0-9]*)\s*,\s*([1-9][0-9]*)\s*\]\s+RI", line, re.I)
            if not match or frequencies is not None or blocks:
                raise CitiError(f"Line {line_no}: only RI S-matrix declarations are supported")
            key = (int(match.group(1)), int(match.group(2)))
            if key in declarations:
                raise CitiError(f"Line {line_no}: duplicate S{key} declaration")
            declarations.append(key)
        elif upper == "VAR_LIST_BEGIN":
            if point_count is None or not declarations or frequencies is not None or blocks:
                raise CitiError(f"Line {line_no}: misplaced variable list")
            frequencies = []
            cursor += 1
            while cursor < len(records) and records[cursor][1].upper() != "VAR_LIST_END":
                value_line, value_text = records[cursor]
                if len(value_text.split()) != 1 or "," in value_text:
                    raise CitiError(f"Line {value_line}: expected one frequency per line")
                frequency = _number(value_text, value_line)
                if frequency < 0:
                    raise CitiError(f"Line {value_line}: negative frequency")
                frequencies.append(frequency)
                cursor += 1
            if cursor == len(records):
                raise CitiError("Unterminated variable list")
            if len(frequencies) != point_count:
                raise CitiError("Frequency-list length differs from VAR count")
            if len(set(frequencies)) != len(frequencies):
                raise CitiError("Duplicate frequency samples")
        elif upper == "BEGIN":
            if frequencies is None or len(blocks) >= len(declarations):
                raise CitiError(f"Line {line_no}: unexpected data block")
            values: list[complex] = []
            cursor += 1
            while cursor < len(records) and records[cursor][1].upper() != "END":
                value_line, value_text = records[cursor]
                parts = value_text.split(",")
                if len(parts) != 2 or any(not part.strip() for part in parts):
                    raise CitiError(f"Line {value_line}: expected real,imaginary pair")
                values.append(complex(_number(parts[0], value_line), _number(parts[1], value_line)))
                cursor += 1
            if cursor == len(records):
                raise CitiError("Unterminated data block")
            if len(values) != point_count:
                raise CitiError("Data-block length differs from VAR count")
            blocks.append(values)
        else:
            raise CitiError(f"Line {line_no}: unsupported or misplaced record {line!r}")
        cursor += 1

    if frequencies is None or not frequencies or len(blocks) != len(declarations):
        raise CitiError("Missing frequency list or complex data blocks")
    ports = max(max(key) for key in declarations)
    if set(declarations) != {(i, j) for i in range(1, ports + 1) for j in range(1, ports + 1)}:
        raise CitiError("S matrix is incomplete or port numbering is not contiguous")
    data = dict(zip(declarations, blocks, strict=True))
    matrix = tuple(
        tuple(tuple(data[i, j][k] for j in range(1, ports + 1)) for i in range(1, ports + 1))
        for k in range(len(frequencies))
    )
    return SNetwork(tuple(frequencies), matrix, name)


def write_touchstone(network: SNetwork, stream: TextIO, reference_ohm: float) -> None:
    """Write full precision RI data with original sample order.

    Touchstone 1 uses S11,S21,S12,S22 for two ports. For three or more ports,
    it uses rows of the matrix. Requiring increasing frequencies prevents an
    implicit reorder that could conceal an input/sample association error.
    """
    if not math.isfinite(reference_ohm) or reference_ohm <= 0:
        raise CitiError("Reference resistance must be finite and positive")
    if not network.frequencies_hz or len(network.s) != len(network.frequencies_hz):
        raise CitiError("Network has inconsistent frequency and matrix counts")
    if any(a >= b for a, b in zip(network.frequencies_hz, network.frequencies_hz[1:])):
        raise CitiError("Touchstone export requires strictly increasing frequency order")
    ports = network.port_count
    if ports < 1:
        raise CitiError("Network has no ports")
    for frequency, matrix in zip(network.frequencies_hz, network.s, strict=True):
        if not math.isfinite(frequency) or frequency < 0 or len(matrix) != ports:
            raise CitiError("Invalid frequency or matrix dimensions")
        if any(len(row) != ports for row in matrix):
            raise CitiError("Inconsistent matrix dimensions")
        if any(not (math.isfinite(z.real) and math.isfinite(z.imag)) for row in matrix for z in row):
            raise CitiError("Nonfinite S-matrix data")
    stream.write("! Complete raw S matrix; no fitting, interpolation, or renormalization.\n")
    stream.write(f"# Hz S RI R {reference_ohm:.17g}\n")
    for frequency, matrix in zip(network.frequencies_hz, network.s, strict=True):
        if ports == 2:
            order = ((0, 0), (1, 0), (0, 1), (1, 1))
            values = " ".join(f"{matrix[i][j].real:.17g} {matrix[i][j].imag:.17g}" for i, j in order)
            stream.write(f"{frequency:.17g} {values}\n")
        else:
            for i, row in enumerate(matrix):
                for start in range(0, ports, 4):
                    values = " ".join(f"{value.real:.17g} {value.imag:.17g}" for value in row[start:start + 4])
                    prefix = f"{frequency:.17g}" if i == 0 and start == 0 else " "
                    stream.write(f"{prefix} {values}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reference-ohm", type=float, required=True,
                        help="Real port reference resistance from the retained solver setup")
    args = parser.parse_args()
    network = parse_citi(args.input.read_text(encoding="utf-8-sig"))
    expected = f".s{network.port_count}p"
    if args.output.suffix.lower() != expected:
        parser.error(f"Output filename must use {expected} for this matrix")
    # Render and validate completely before creating the destination file.
    import io
    rendered = io.StringIO()
    write_touchstone(network, rendered, args.reference_ohm)
    with args.output.open("x", encoding="ascii", newline="\n") as stream:
        stream.write(rendered.getvalue())
    print(f"Exported {len(network.frequencies_hz)} samples, {network.port_count} ports, RI format")


if __name__ == "__main__":
    main()
