"""Independent syntax and asymmetric-port ordering checks for raw conversion."""

import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from convert_cti import CitiError, parse_citi, write_touchstone


def packet(ports=2, frequencies=(1e9, 2e9)):
    # Reverse declaration order deliberately; identifiers determine coordinates.
    keys = [(i, j) for i in range(1, ports + 1) for j in range(1, ports + 1)][::-1]
    lines = ["CITIFILE A.01.00", "NAME synthetic", f"VAR freq MAG {len(frequencies)}"]
    lines += [f"DATA S[{i},{j}] RI" for i, j in keys]
    lines += ["VAR_LIST_BEGIN", *(str(f) for f in frequencies), "VAR_LIST_END"]
    for i, j in keys:
        lines += ["BEGIN", *(f"{10*i+j+k/10},{-10*i-j-k/10}" for k in range(len(frequencies))), "END"]
    return "\n".join(lines)


class ConversionTests(unittest.TestCase):
    def test_asymmetric_two_port_touchstone_order(self):
        network = parse_citi(packet())
        self.assertEqual(network.s[1][0][1], 12.1 - 12.1j)
        output = io.StringIO()
        write_touchstone(network, output, 50)
        values = [float(x) for x in output.getvalue().splitlines()[2].split()]
        self.assertEqual(values, [1e9, 11, -11, 21, -21, 12, -12, 22, -22])

    def test_three_port_uses_rows(self):
        output = io.StringIO()
        write_touchstone(parse_citi(packet(3)), output, 50)
        rows = output.getvalue().splitlines()[2:5]
        self.assertEqual([float(v) for v in rows[0].split()], [1e9, 11, -11, 12, -12, 13, -13])
        self.assertEqual([float(v) for v in rows[1].split()], [21, -21, 22, -22, 23, -23])
        self.assertEqual([float(v) for v in rows[2].split()], [31, -31, 32, -32, 33, -33])

    def test_list_association_is_preserved(self):
        network = parse_citi(packet(frequencies=(2e9, 1e9)))
        self.assertEqual(network.frequencies_hz, (2e9, 1e9))
        self.assertEqual(network.s[0][1][0], 21 - 21j)
        with self.assertRaisesRegex(CitiError, "increasing"):
            write_touchstone(network, io.StringIO(), 50)

    def test_five_port_wraps_rows_without_losing_entries(self):
        output = io.StringIO()
        write_touchstone(parse_citi(packet(5, frequencies=(1e9,))), output, 50)
        rows = output.getvalue().splitlines()[2:]
        self.assertEqual(len(rows), 10)
        values = [float(v) for row in rows for v in row.split()]
        self.assertEqual(values[0], 1e9)
        self.assertEqual(values[1:], [value for i in range(1, 6) for j in range(1, 6)
                                     for value in (10*i+j, -10*i-j)])

    def test_duplicate_frequency_and_missing_data_fail(self):
        for source in (packet(frequencies=(1e9, 1e9)), packet().rsplit("BEGIN", 1)[0]):
            with self.subTest(source=source), self.assertRaises(CitiError):
                parse_citi(source)

    def test_unsupported_and_nonfinite_fail(self):
        for source in (
            packet().replace("S[1,1] RI", "S[1,1] MA"),
            packet().replace("VAR freq MAG 2", "VAR temperature MAG 2"),
            packet().replace("11.0,-11.0", "nan,-11.0"),
            packet().replace("1000000000.0", "inf"),
            packet().replace("DATA S[2,2] RI", "DATA S[1,1] RI"),
            packet() + "\nCITIFILE A.01.00",
            packet().replace("NAME synthetic", "CONSTANT Z0 MAG 50"),
        ):
            with self.subTest(source=source), self.assertRaises(CitiError):
                parse_citi(source)

    def test_incomplete_matrix_fail(self):
        source = packet(1).replace("S[1,1]", "S[2,2]")
        with self.assertRaisesRegex(CitiError, "incomplete"):
            parse_citi(source)

    def test_bad_reference_fails(self):
        for reference in (0, -50, float("inf"), float("nan")):
            with self.subTest(reference=reference), self.assertRaises(CitiError):
                write_touchstone(parse_citi(packet()), io.StringIO(), reference)


if __name__ == "__main__":
    unittest.main()
