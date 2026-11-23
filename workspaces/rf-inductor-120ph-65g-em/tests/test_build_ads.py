"""Guard native physical port mapping across observed ADS getter formats."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import build_ads


EXPECTED = [
    [["P1"], ["P4"], 50.0, 0.0, 0, 0.0],
    [["P2"], ["P4"], 50.0, 0.0, 0, 0.0],
]


class AELValueResult:
    """Match the installed AELValue.as_python_value(convert=...) interface."""

    def __init__(self, value):
        self.value = value
        self.conversion_requests = []

    def as_python_value(self, convert=None):
        self.conversion_requests.append(convert)
        return self.value


class NativePortCalls:
    def __init__(self, observed):
        self.observed = observed
        self.events = []

    def db_set_port_definitions(self, design, definitions):
        self.events.append(("set", design, copy.deepcopy(definitions)))

    def db_get_port_definitions(self, design):
        self.events.append(("get", design))
        return self.observed


class NativePortDefinitionTests(unittest.TestCase):
    def exercise(self, observed):
        calls = NativePortCalls(observed)
        design = object()
        result = build_ads._set_native_port_definitions(design, SimpleNamespace(call=calls))
        self.assertEqual(result, EXPECTED)
        self.assertEqual(calls.events, [("set", design, EXPECTED), ("get", design)])
        return result

    def test_six_electrical_fields_are_preserved(self):
        self.exercise(copy.deepcopy(EXPECTED))

    def test_empty_seventh_metadata_is_accepted_per_row(self):
        for extra_on_first, extra_on_second in ((True, True), (True, False), (False, True)):
            with self.subTest(first=extra_on_first, second=extra_on_second):
                rows = copy.deepcopy(EXPECTED)
                if extra_on_first:
                    rows[0].append("")
                if extra_on_second:
                    rows[1].append("")
                self.exercise(rows)

    def test_ael_value_result_is_explicitly_converted(self):
        rows = copy.deepcopy(EXPECTED)
        for row in rows:
            row.append("")
        wrapped = AELValueResult(rows)
        self.exercise(wrapped)
        self.assertEqual(wrapped.conversion_requests, [True])

    def test_wrong_negative_pin_is_not_hidden_by_optional_metadata(self):
        for wrong_negative in ([], ["P3"], ["P4", "P3"]):
            with self.subTest(negative=wrong_negative):
                rows = copy.deepcopy(EXPECTED)
                rows[1][1] = wrong_negative
                rows[1].append("")
                with self.assertRaisesRegex(RuntimeError, "finite P4 return"):
                    self.exercise(rows)

    def test_unknown_metadata_and_extra_fields_are_rejected(self):
        for extra in (("unknown",), (None,), ("", "")):
            with self.subTest(extra=extra):
                rows = copy.deepcopy(EXPECTED)
                rows[0].extend(extra)
                with self.assertRaises(RuntimeError):
                    self.exercise(rows)


if __name__ == "__main__":
    unittest.main()
