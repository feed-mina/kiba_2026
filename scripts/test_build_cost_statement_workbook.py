#!/usr/bin/env python3

from __future__ import annotations

import unittest
from xml.etree import ElementTree as ET

from build_cost_statement_workbook import (
    CellPayload,
    evaluate_input_payloads,
    non_empty_cell_count,
    replace_sheet_data,
)


class FakeImporter:
    @staticmethod
    def row_number(address: str) -> int:
        return int("".join(ch for ch in address if ch.isdigit()))

    @staticmethod
    def column_number(address: str) -> int:
        result = 0
        for ch in address:
            if not ch.isalpha():
                break
            result = result * 26 + ord(ch.upper()) - 64
        return result


class ReplaceSheetDataTest(unittest.TestCase):
    def test_dimension_is_inserted_inside_root_with_namespaces(self) -> None:
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheetData/><drawing r:id="rId1"/></worksheet>'
        ).encode()
        output = replace_sheet_data(
            FakeImporter(),
            xml,
            [CellPayload(address="A1", formula=None, value="ok", value_type="str")],
        )
        root = ET.fromstring(output)
        self.assertTrue(root.tag.endswith("worksheet"))
        self.assertIn(b'<dimension ref="A1:A1"/>', output)


def _cell(address: str, value=None, formula=None, value_type="str") -> CellPayload:
    return CellPayload(address=address, formula=formula, value=value, value_type=value_type)


class EvaluateInputPayloadsTest(unittest.TestCase):
    def _full_payloads(self):
        return {
            "단가대비표": [_cell("A1", value="자재")],
            "내역서": [_cell("A1", value="공종"), _cell("F2", value="100")],
            "일위대가표": [_cell("A1", value="품목")],
        }

    def test_valid_inputs_have_no_problems(self) -> None:
        problems = evaluate_input_payloads(self._full_payloads(), detail_total_row=5, summary_supplied=False)
        self.assertEqual(problems, [])

    def test_empty_sheet_is_reported(self) -> None:
        payloads = self._full_payloads()
        payloads["단가대비표"] = [_cell("A1", value="   "), _cell("B1", formula="")]
        problems = evaluate_input_payloads(payloads, detail_total_row=5, summary_supplied=False)
        self.assertEqual(len(problems), 1)
        self.assertIn("단가대비표", problems[0])

    def test_missing_detail_total_row_reported_when_no_summary(self) -> None:
        problems = evaluate_input_payloads(self._full_payloads(), detail_total_row=None, summary_supplied=False)
        self.assertEqual(len(problems), 1)
        self.assertIn("합계", problems[0])

    def test_missing_total_row_ok_when_summary_supplied(self) -> None:
        problems = evaluate_input_payloads(self._full_payloads(), detail_total_row=None, summary_supplied=True)
        self.assertEqual(problems, [])

    def test_formula_only_cell_counts_as_non_empty(self) -> None:
        self.assertEqual(non_empty_cell_count([_cell("A1", formula="SUM(B1:B2)")]), 1)
        self.assertEqual(non_empty_cell_count([_cell("A1", value=None, formula=None)]), 0)


if __name__ == "__main__":
    unittest.main()
