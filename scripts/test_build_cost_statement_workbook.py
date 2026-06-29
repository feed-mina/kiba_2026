#!/usr/bin/env python3

from __future__ import annotations

import unittest
from xml.etree import ElementTree as ET

from build_cost_statement_workbook import CellPayload, replace_sheet_data


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


if __name__ == "__main__":
    unittest.main()
