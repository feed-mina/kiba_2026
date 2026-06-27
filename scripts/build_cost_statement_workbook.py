#!/usr/bin/env python3
"""Build a 원가계산서 workbook from three input workbooks.

The generator uses the sample 원가계산보고서 workbook as a template and replaces
the three source sheets used by the cost statement formula chain:

  단가대비표, 내역서, 집계표

This keeps the sample 원가계산서 layout/formulas intact while allowing users to
provide the three upstream sheets as separate Excel files.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", REL_NS)


@dataclass(frozen=True)
class CellPayload:
    address: str
    formula: str | None
    value: str | None
    value_type: str | None


def q(tag: str) -> str:
    return f"{{{MAIN_NS}}}{tag}"


def load_importer():
    path = REPO_ROOT / "scripts" / "import_sample_ver1_cost_workbook.py"
    spec = importlib.util.spec_from_file_location("costimp", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["costimp"] = mod
    spec.loader.exec_module(mod)
    return mod


def text_of(node: ET.Element | None) -> str:
    return "" if node is None or node.text is None else node.text


def xml_escape(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def find_default_template(repo_root: Path, version: str) -> Path:
    marker = "ver2" if version == "ver2" else "ver1"
    matches = sorted(repo_root.glob(f"docs/원가계산보고서샘플/*{marker}*.xlsx*"))
    if not matches:
        raise FileNotFoundError(f"template workbook not found for {version}")
    return matches[0]


def sheet_by_role_or_name(imp, archive: zipfile.ZipFile, preferred_name: str, role: str):
    sheets = imp.read_sheets(archive)
    exact = next((sheet for sheet in sheets if sheet.name == preferred_name), None)
    if exact is not None:
        return exact
    by_role = next((sheet for sheet in sheets if imp.infer_sheet_role(sheet.name) == role), None)
    if by_role is not None:
        return by_role
    if len(sheets) == 1:
        return sheets[0]
    available = ", ".join(sheet.name for sheet in sheets)
    raise ValueError(f"cannot find sheet {preferred_name!r}/{role!r}; available: {available}")


def sheet_by_name(imp, archive: zipfile.ZipFile, name: str):
    sheets = imp.read_sheets(archive)
    sheet = next((candidate for candidate in sheets if candidate.name == name), None)
    if sheet is None:
        available = ", ".join(candidate.name for candidate in sheets)
        raise ValueError(f"template sheet {name!r} not found; available: {available}")
    return sheet


def extract_cells(imp, archive: zipfile.ZipFile, sheet, shared_strings: list[str]) -> list[CellPayload]:
    root = ET.fromstring(archive.read(sheet.path))
    cells: list[CellPayload] = []
    for cell in root.iter(q("c")):
        address = cell.attrib.get("r", "")
        if not address:
            continue
        formula_node = cell.find(q("f"))
        formula = text_of(formula_node) if formula_node is not None else None
        value, value_type = imp.cell_value(cell, shared_strings)
        if formula is None and (value is None or str(value).strip() == ""):
            continue
        cells.append(CellPayload(address=address, formula=formula, value=value, value_type=value_type))
    return sorted(cells, key=lambda item: (imp.row_number(item.address), imp.column_number(item.address)))


def dimension_for(imp, cells: list[CellPayload]) -> str:
    if not cells:
        return "A1"
    max_row = max(imp.row_number(cell.address) for cell in cells)
    max_col = max(imp.column_number(cell.address) for cell in cells)
    return f"A1:{column_name(max_col)}{max_row}"


def column_name(number: int) -> str:
    chars: list[str] = []
    while number:
        number, remainder = divmod(number - 1, 26)
        chars.append(chr(65 + remainder))
    return "".join(reversed(chars))


def rows_xml(imp, cells: list[CellPayload]) -> str:
    by_row: dict[int, list[CellPayload]] = {}
    for cell in cells:
        by_row.setdefault(imp.row_number(cell.address), []).append(cell)

    rows: list[str] = []
    for row_no in sorted(by_row):
        cells_xml: list[str] = []
        for cell in by_row[row_no]:
            formula_xml = f"<f>{xml_escape(cell.formula)}</f>" if cell.formula is not None else ""
            value = cell.value
            if cell.value_type in ("s", "str", "inlineStr") and value is not None and cell.formula is None:
                cells_xml.append(
                    f'<c r="{cell.address}" t="inlineStr"><is><t>{xml_escape(value)}</t></is></c>'
                )
            elif cell.value_type == "e" and value is not None:
                cells_xml.append(f'<c r="{cell.address}" t="e">{formula_xml}<v>{xml_escape(value)}</v></c>')
            elif value is not None and str(value).strip() != "":
                cells_xml.append(f'<c r="{cell.address}">{formula_xml}<v>{xml_escape(value)}</v></c>')
            else:
                cells_xml.append(f'<c r="{cell.address}">{formula_xml}</c>')
        rows.append(f'<row r="{row_no}">{"".join(cells_xml)}</row>')
    return "".join(rows)


def replace_sheet_data(imp, template_xml: bytes, cells: list[CellPayload]) -> bytes:
    text = template_xml.decode("utf-8")
    dimension = dimension_for(imp, cells)
    row_block = f"<sheetData>{rows_xml(imp, cells)}</sheetData>"
    if re.search(r"<dimension[^>]*/>", text):
        text = re.sub(r"<dimension[^>]*/>", f'<dimension ref="{dimension}"/>', text, count=1)
    else:
        text = text.replace("<worksheet", f'<worksheet><dimension ref="{dimension}"/>', 1)
    if re.search(r"<sheetData>.*?</sheetData>", text, flags=re.S):
        text = re.sub(r"<sheetData>.*?</sheetData>", row_block, text, count=1, flags=re.S)
    else:
        text = text.replace("</worksheet>", f"{row_block}</worksheet>")
    # Merge/style ranges from the template source sheets may not match the user input.
    text = re.sub(r"<mergeCells[^>]*>.*?</mergeCells>", "", text, flags=re.S)
    return text.encode("utf-8")


def force_recalculation(workbook_xml: bytes) -> bytes:
    root = ET.fromstring(workbook_xml)
    calc_pr = root.find(q("calcPr"))
    if calc_pr is None:
        calc_pr = ET.SubElement(root, q("calcPr"))
    calc_pr.attrib["calcMode"] = "auto"
    calc_pr.attrib["fullCalcOnLoad"] = "1"
    calc_pr.attrib["forceFullCalc"] = "1"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def read_source_payload(input_path: Path, preferred_name: str, role: str) -> list[CellPayload]:
    imp = load_importer()
    with zipfile.ZipFile(input_path) as archive:
        shared_strings = imp.read_shared_strings(archive)
        sheet = sheet_by_role_or_name(imp, archive, preferred_name, role)
        return extract_cells(imp, archive, sheet, shared_strings)


def build_workbook(args: argparse.Namespace) -> dict[str, Any]:
    imp = load_importer()
    template_path = args.template
    if template_path is None:
        template_path = find_default_template(REPO_ROOT, args.template_version)
    if not template_path.is_absolute():
        template_path = REPO_ROOT / template_path

    output_path = args.output
    if not output_path.is_absolute():
        output_path = REPO_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    source_specs = [
        ("단가대비표", "price_comparison", args.price_comparison),
        ("내역서", "detail", args.detail),
        ("집계표", "summary", args.summary),
    ]
    source_payloads = {
        sheet_name: read_source_payload(input_path, sheet_name, role)
        for sheet_name, role, input_path in source_specs
    }

    with zipfile.ZipFile(template_path) as template_archive:
        target_sheets = {
            sheet_name: sheet_by_name(imp, template_archive, sheet_name)
            for sheet_name, _role, _input_path in source_specs
        }
        replacements = {
            target_sheets[sheet_name].path: replace_sheet_data(
                imp,
                template_archive.read(target_sheets[sheet_name].path),
                source_payloads[sheet_name],
            )
            for sheet_name in source_payloads
        }
        replacements["xl/workbook.xml"] = force_recalculation(template_archive.read("xl/workbook.xml"))

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as output_archive:
            for info in template_archive.infolist():
                if info.filename in replacements:
                    output_archive.writestr(info, replacements[info.filename])
                else:
                    output_archive.writestr(info, template_archive.read(info.filename))

    return {
        "output": str(output_path),
        "template": str(template_path),
        "replaced_sheets": [
            {"sheet": sheet_name, "cells": len(source_payloads[sheet_name])}
            for sheet_name in source_payloads
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--price-comparison", type=Path, required=True, help="단가대비표 Excel file")
    parser.add_argument("--detail", type=Path, required=True, help="내역서 Excel file")
    parser.add_argument("--summary", type=Path, required=True, help="집계표 Excel file")
    parser.add_argument("--output", type=Path, required=True, help="Generated 원가계산서 workbook")
    parser.add_argument("--template", type=Path, help="원가계산보고서 template workbook")
    parser.add_argument("--template-version", choices=("ver1", "ver2"), default="ver1")
    args = parser.parse_args()

    report = build_workbook(args)
    print(f"wrote {report['output']}")
    print(f"template={report['template']}")
    for item in report["replaced_sheets"]:
        print(f"{item['sheet']}={item['cells']} cells")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
