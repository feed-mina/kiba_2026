#!/usr/bin/env python3

from __future__ import annotations

import unittest
from xml.etree import ElementTree as ET

from build_cost_statement_workbook import (
    CellPayload,
    evaluate_input_payloads,
    force_recalculation,
    is_external_link_part,
    non_empty_cell_count,
    replace_sheet_data,
    set_visible_sheets,
    strip_content_types,
    strip_relationships,
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


WORKBOOK_XML = (
    "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:x14ac="http://schemas.microsoft.com/office/spreadsheetml/2010/11/ac" '
    'xmlns:hs="http://schemas.haansoft.com/office/spreadsheet/8.0" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'mc:Ignorable="hs">'
    '<sheets><sheet name="원가계산서" sheetId="1" r:id="rId1"/>'
    '<sheet name="간노비" sheetId="2" state="hidden" r:id="rId2"/></sheets>'
    '<externalReferences><externalReference r:id="rId28"/></externalReferences>'
    '<calcPr mc:Ignorable="hs" hs:hclCalcId="904"/>'
    "</workbook>"
).encode()


class WorkbookNamespaceTest(unittest.TestCase):
    """ElementTree 재직렬화로 mc/x14ac/hs prefix가 망가지던 회귀를 막는다."""

    def test_force_recalculation_preserves_namespace_prefixes(self) -> None:
        out = force_recalculation(WORKBOOK_XML).decode()
        self.assertNotIn("ns0:", out)
        self.assertNotIn("ns1:", out)
        self.assertIn('mc:Ignorable="hs"', out)
        self.assertIn('xmlns:hs="http://schemas.haansoft.com/office/spreadsheet/8.0"', out)
        self.assertIn('hs:hclCalcId="904"', out)

    def test_force_recalculation_sets_recalc_attrs_once(self) -> None:
        out = force_recalculation(WORKBOOK_XML).decode()
        self.assertIn('calcMode="auto"', out)
        self.assertIn('fullCalcOnLoad="1"', out)
        self.assertIn('forceFullCalc="1"', out)
        self.assertEqual(out.count('forceFullCalc="1"'), 1)

    def test_force_recalculation_strips_dead_external_references(self) -> None:
        out = force_recalculation(WORKBOOK_XML).decode()
        self.assertNotIn("<externalReferences>", out)

    def test_set_visible_sheets_string_based(self) -> None:
        out = set_visible_sheets(WORKBOOK_XML, ["원가계산서"]).decode()
        self.assertNotIn("ns0:", out)
        # 보이는 시트는 state 제거, 나머지는 hidden
        self.assertRegex(out, r'<sheet name="원가계산서"[^>]*?/>')
        self.assertIn('state="hidden"', out)
        self.assertNotIn('<sheet name="원가계산서" sheetId="1" r:id="rId1" state=', out)


class StripPartsTest(unittest.TestCase):
    def test_strip_relationships_drops_external_and_comment_keeps_others(self) -> None:
        rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId28" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink" Target="externalLinks/externalLink1.xml"/>'
            '<Relationship Id="rId99" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="../comments1.xml"/>'
            "</Relationships>"
        ).encode()
        out = strip_relationships(rels).decode()
        self.assertNotIn("ns0:", out)
        self.assertIn('Target="worksheets/sheet1.xml"', out)
        self.assertNotIn("externalLink1.xml", out)
        self.assertNotIn("comments1.xml", out)

    def test_strip_content_types_drops_external_link_overrides(self) -> None:
        ct = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="vml" ContentType="application/vnd.openxmlformats-officedocument.vmlDrawing"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/externalLinks/externalLink1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.externalLink+xml"/>'
            "</Types>"
        ).encode()
        out = strip_content_types(ct).decode()
        self.assertNotIn("ns0:", out)
        self.assertIn('PartName="/xl/workbook.xml"', out)
        self.assertNotIn("externalLink1.xml", out)
        self.assertNotIn('Extension="vml"', out)

    def test_is_external_link_part(self) -> None:
        self.assertTrue(is_external_link_part("xl/externalLinks/externalLink1.xml"))
        self.assertTrue(is_external_link_part("xl/externalLinks/_rels/externalLink1.xml.rels"))
        self.assertFalse(is_external_link_part("xl/worksheets/sheet1.xml"))


if __name__ == "__main__":
    unittest.main()
