"""Check measured WP0 SP data against the fixed ideal LC two-port.

Consumes simulator-exported data only. This module never creates a circuit,
starts a simulator, or establishes native source-to-result readiness.
Python 3.11+; standard library only, except optional Bridge PSF reading.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


FIELDS = ["freq_hz", "s11_real", "s11_imag", "s21_real", "s21_imag",
          "s12_real", "s12_imag", "s22_real", "s22_imag"]
ORDER = ("s11", "s21", "s12", "s22")
REQUESTED_HZ = (1e6, 10e9, 65e9, 80e9)
FREQUENCY_TOLERANCE_HZ = 1.0
COMPLEX_TOLERANCE = 1e-6
PHYSICS_TOLERANCE = 1e-8
L_H = 100e-12
C_F = 100e-15
Z0_OHM = 50.0


def finite(value: complex | float) -> bool:
    return math.isfinite(complex(value).real) and math.isfinite(complex(value).imag)


def validate(rows: list[tuple[float, tuple[complex, ...]]]) -> None:
    if not rows:
        raise ValueError("No S-parameter samples")
    previous = 0.0
    for frequency, s in rows:
        if not math.isfinite(frequency) or frequency <= previous:
            raise ValueError("Frequencies must be finite, positive, unique and increasing")
        if len(s) != 4 or not all(finite(value) for value in s):
            raise ValueError("Every sample must contain four finite complex S entries")
        previous = frequency


def read_data(path: Path) -> list[tuple[float, tuple[complex, ...]]]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != FIELDS:
                raise ValueError("Unexpected CSV columns or S-parameter ordering")
            rows = []
            for row in reader:
                values = [float(row[field]) for field in FIELDS]
                rows.append((values[0], tuple(complex(values[i], values[i + 1])
                                             for i in (1, 3, 5, 7))))
    elif path.suffix.lower() == ".s2p":
        tokens = []
        header = None
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.split("!", 1)[0].strip()
            if not line:
                continue
            if line.startswith("#"):
                if header is not None:
                    raise ValueError("Multiple Touchstone option lines")
                header = line[1:].lower().split()
                continue
            if line.startswith("["):
                raise ValueError("Only explicit Touchstone v1 two-port files are accepted")
            tokens.extend(line.split())
        if header != ["hz", "s", "ri", "r", "50"]:
            raise ValueError("Touchstone must explicitly declare # Hz S RI R 50")
        if len(tokens) % 9:
            raise ValueError("Incomplete Touchstone two-port sample")
        numbers = [float(value.replace("D", "e").replace("d", "e")) for value in tokens]
        rows = [(numbers[i], tuple(complex(numbers[i + j], numbers[i + j + 1])
                                  for j in (1, 3, 5, 7)))
                for i in range(0, len(numbers), 9)]
    else:
        raise ValueError("Measured input must be CSV or explicit 50-ohm RI Touchstone")
    validate(rows)
    return rows


def from_psf(path: Path, keys: list[str]) -> list[tuple[float, tuple[complex, ...]]]:
    """Read one actual SP file; exact signal keys must come from its own TRACE."""
    from virtuoso_bridge.spectre.psf import frequency_hz, read_psf_ascii, vector

    parsed = read_psf_ascii(path)
    frequencies = frequency_hz(parsed)
    vectors = [vector(parsed, key) for key in keys]
    if any(len(values) != len(frequencies) for values in vectors):
        raise ValueError("PSF frequency and S-vector lengths differ")
    rows = [(float(frequency), tuple(complex(values[i]) for values in vectors))
            for i, frequency in enumerate(frequencies)]
    validate(rows)
    return rows


def analytic(frequency: float) -> tuple[complex, ...]:
    z = 1j * 2 * math.pi * frequency * L_H
    y = 1j * 2 * math.pi * frequency * C_F
    a, b, c, d = 1 + z * y, z, y, 1.0
    q = a + b / Z0_OHM + c * Z0_OHM + d
    return ((a + b / Z0_OHM - c * Z0_OHM - d) / q,
            2 / q, 2 * (a * d - b * c) / q,
            (-a + b / Z0_OHM - c * Z0_OHM + d) / q)


def check(rows, repeat=None) -> dict:
    validate(rows)
    coverage = {str(int(target)): min(abs(frequency - target) for frequency, _ in rows)
                <= FREQUENCY_TOLERANCE_HZ for target in REQUESTED_HZ}
    max_error = reciprocity = unitarity = power_excess = 0.0
    for frequency, (s11, s21, s12, s22) in rows:
        max_error = max(max_error, *(abs(a - b) for a, b in
                                      zip((s11, s21, s12, s22), analytic(frequency))))
        reciprocity = max(reciprocity, abs(s21 - s12))
        col1, col2 = abs(s11) ** 2 + abs(s21) ** 2, abs(s12) ** 2 + abs(s22) ** 2
        cross = s11.conjugate() * s12 + s21.conjugate() * s22
        unitarity = max(unitarity, abs(col1 - 1), abs(col2 - 1), abs(cross))
        power_excess = max(power_excess, col1 - 1, col2 - 1)
    numerical_pass = (all(coverage.values()) and max_error <= COMPLEX_TOLERANCE
                      and max(reciprocity, unitarity, power_excess) <= PHYSICS_TOLERANCE)
    repeated = {"status": "not-provided"}
    if repeat is not None:
        validate(repeat)
        repeat_checks = check(repeat)
        paired = len(rows) == len(repeat) and all(
            abs(a[0] - b[0]) <= FREQUENCY_TOLERANCE_HZ for a, b in zip(rows, repeat))
        error = max((abs(x - y) for a, b in zip(rows, repeat)
                     for x, y in zip(a[1], b[1])), default=None) if paired else None
        repeated = {"frequency_pairing_pass": paired, "max_complex_error": error,
                    "independent_numerical_check": repeat_checks,
                    "status": "passed" if paired and error <= COMPLEX_TOLERANCE
                    and repeat_checks["numerical_check_pass"] else "failed"}
    return {"schema_version": 1, "scope": "WP0 measured-data numerical check only",
            "full_lpf_H1_H4": "not-applicable-to-WP0",
            "native_source_to_result_gate": "requires separately reviewed native evidence",
            "model": {"L_H": L_H, "C_F": C_F, "z0_ohm": Z0_OHM},
            "sample_count": len(rows), "requested_frequency_coverage": coverage,
            "max_complex_abcd_error": max_error, "reciprocity_error": reciprocity,
            "unitarity_error": unitarity, "passive_column_power_excess": power_excess,
            "tolerances": {"frequency_hz": FREQUENCY_TOLERANCE_HZ,
                           "complex_absolute": COMPLEX_TOLERANCE, "physics": PHYSICS_TOLERANCE},
            "numerical_check_pass": numerical_pass, "repeat": repeated}


def export(rows, directory: Path) -> None:
    with (directory / "sparameters.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(FIELDS)
        for frequency, s in rows:
            writer.writerow([format(frequency, ".17g")] + [format(x, ".17g")
                for value in s for x in (value.real, value.imag)])
    with (directory / "sparameters.s2p").open("w", encoding="ascii", newline="\n") as handle:
        handle.write("! Measured WP0 data; order S11 S21 S12 S22\n# Hz S RI R 50\n")
        for frequency, s in rows:
            handle.write(" ".join(format(x, ".17g") for x in [frequency] +
                [x for value in s for x in (value.real, value.imag)]) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="Fresh output directory")
    parser.add_argument("--repeat", type=Path, help="Repeated run CSV or Touchstone")
    parser.add_argument("--psf-keys", nargs=4, metavar=("S11", "S21", "S12", "S22"),
                        help="Read input as PSF ASCII, using these exact TRACE keys")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; use a fresh retained directory")
    args.output.mkdir(parents=True)
    try:
        rows = from_psf(args.input, args.psf_keys) if args.psf_keys else read_data(args.input)
        summary = check(rows, read_data(args.repeat) if args.repeat else None)
        export(rows, args.output)
        summary["inputs"] = {"measured_file": args.input.name,
                             "measured_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest()}
        if args.repeat:
            summary["inputs"].update(repeat_file=args.repeat.name,
                repeat_sha256=hashlib.sha256(args.repeat.read_bytes()).hexdigest())
    except (OSError, ValueError, KeyError, ImportError) as error:
        summary = {"schema_version": 1, "scope": "WP0 measured-data numerical check only",
                   "numerical_check_pass": False, "error": str(error)}
    (args.output / "measurements.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    passed = summary["numerical_check_pass"] and summary.get("repeat", {}).get("status") != "failed"
    report = ["# WP0 measured-data check", "",
              f"Numerical check: {'PASS' if passed else 'FAIL'}.", "",
              "This checks measured SP data for the fixed 100 pH / 100 fF ideal two-port.",
              "H1-H4 for the complete LPF are not applicable to this smoke circuit.",
              "Native creation, check/save/reopen, netlisting, solver execution and source/data correspondence require their own retained evidence.",
              "Full LPF reproduction and design have not been established by this report.", "",
              "See [measurements.json](measurements.json) for measurements and machine-readable provenance.", ""]
    (args.output / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps({"numerical_check_pass": passed, "report": str(args.output / "report.md")}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
