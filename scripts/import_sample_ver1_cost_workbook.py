#!/usr/bin/env python3
"""Extract sample_ver1 cost-estimate workbook structure without Excel.

The source workbook currently fails through openpyxl because of workbook metadata,
so this importer reads the XLSX ZIP/XML parts directly. It produces a compact JSON
manifest for the DDD importer/migration work tracked in Issue #40.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKGREL = "http://schemas.openxmlformats.org/package/2006/relationships"

CORE_SHEET_ROLES = {
    "결과": "result",
    "산정기준": "basis",
    "원가계산서": "cost_statement",
    "집계표": "summary",
    "내역서": "detail",
    "일위대가목록": "unit_price_list",
    "일위대가표": "unit_price_detail",
    "단가대비표": "price_comparison",
    "간노비": "indirect_labor_rate",
    "경비": "expense",
    "일반": "general_admin",
    "일반비율": "general_admin_rate",
    "이윤": "profit",
    "이윤비율": "profit_rate",
}

RATE_SHEET_ROLES = {
    "산재": "insurance_rate",
    "고용": "insurance_rate",
    "건강": "insurance_rate",
    "연금": "insurance_rate",
    "장기": "insurance_rate",
    "석면": "insurance_rate",
    "임금": "insurance_rate",
    "퇴공": "insurance_rate",
    "안전": "safety_rate",
}

GOLDEN_CELLS = {
    "결과": ["J10"],
    "원가계산서": ["E7", "E10", "E34"],
    "집계표": ["D7", "E19", "G19", "I19"],
    "내역서": ["E11", "K11"],
    "일위대가목록": ["E7"],
    "일위대가표": ["G8", "F21"],
    "단가대비표": ["M7"],
}


def q(tag: str) -> str:
    return f"{{{NS_MAIN}}}{tag}"


def text_of(node: ET.Element | None) -> str:
    return "" if node is None or node.text is None else node.text


def column_number(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        return 0
    number = 0
    for char in match.group(1):
        number = number * 26 + ord(char) - 64
    return number


def row_number(cell_ref: str) -> int:
    match = re.search(r"(\d+)", cell_ref)
    return int(match.group(1)) if match else 0


def normalize_target(base: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    if base.endswith("/"):
        return base + target
    return str(Path(base) / target).replace("\\", "/")


def infer_sheet_role(sheet_name: str) -> str:
    return CORE_SHEET_ROLES.get(sheet_name) or RATE_SHEET_ROLES.get(sheet_name) or "support"


def formula_kind(formula: str) -> str:
    upper = formula.upper()
    if any(fn in upper for fn in ("SUM(", "SUBTOTAL(")):
        return "aggregate"
    if any(fn in upper for fn in ("TRUNC(", "ROUNDDOWN(", "ROUND(")):
        return "rounding"
    if any(fn in upper for fn in ("MIN(", "MAX(")):
        return "selection"
    if any(fn in upper for fn in ("IF(", "IFS(")):
        return "conditional"
    if "!" in formula:
        return "lookup"
    if formula.startswith('"') or "&" in formula:
        return "narrative"
    return "arithmetic"


def iter_cell_refs(formula: str, current_sheet: str) -> list[dict[str, str]]:
    """Return a lightweight dependency list from an Excel formula."""
    deps: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    quoted = r"'(?P<quoted>[^']+)'!"
    plain = r"(?P<plain>[A-Za-z0-9_가-힣 .\-\(\)]+)!"
    addr = r"(?P<addr>\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)"
    for match in re.finditer(f"(?:{quoted}|{plain}){addr}", formula):
        sheet = (match.group("quoted") or match.group("plain") or "").strip()
        address = match.group("addr").replace("$", "")
        key = (sheet, address)
        if key not in seen:
            deps.append({"sheet": sheet, "address": address, "kind": "cell_or_range"})
            seen.add(key)

    formula_no_sheet_refs = re.sub(f"(?:{quoted}|{plain}){addr}", "", formula)
    for match in re.finditer(r"(?<![A-Za-z0-9_])(\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)(?![A-Za-z0-9_])", formula_no_sheet_refs):
        address = match.group(1).replace("$", "")
        key = (current_sheet, address)
        if key not in seen:
            deps.append({"sheet": current_sheet, "address": address, "kind": "cell_or_range"})
            seen.add(key)

    return deps


@dataclass
class SheetPart:
    name: str
    path: str
    display_order: int


def read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall(q("si")):
        strings.append("".join(text.text or "" for text in item.iter(q("t"))))
    return strings


def read_sheets(archive: zipfile.ZipFile) -> list[SheetPart]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall(f"{{{NS_PKGREL}}}Relationship")
    }

    result: list[SheetPart] = []
    sheets = workbook.find(q("sheets"))
    if sheets is None:
        return result
    for index, sheet in enumerate(sheets.findall(q("sheet")), start=1):
        rel_id = sheet.attrib[f"{{{NS_REL}}}id"]
        target = rel_targets[rel_id]
        result.append(
            SheetPart(
                name=sheet.attrib["name"],
                path=normalize_target("xl", target),
                display_order=index,
            )
        )
    return result


def cell_value(cell: ET.Element, shared_strings: list[str]) -> tuple[str | None, str | None]:
    value_node = cell.find(q("v"))
    inline_node = cell.find(q("is"))
    if value_node is not None and value_node.text is not None:
        value = value_node.text
        if cell.attrib.get("t") == "s":
            try:
                value = shared_strings[int(value)]
            except (IndexError, ValueError):
                pass
        return value, cell.attrib.get("t")
    if inline_node is not None:
        value = "".join(text.text or "" for text in inline_node.iter(q("t")))
        return value, "inlineStr"
    return None, None


def extract_workbook(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest: dict[str, Any] = {
        "source_path": str(path.as_posix()),
        "source_sha256": digest,
        "sheets": [],
        "formulas": [],
        "dependencies": [],
        "sheet_line_projections": [],
        "golden_cells": [],
        "warnings": [],
    }

    with zipfile.ZipFile(path) as archive:
        shared_strings = read_shared_strings(archive)
        sheets = read_sheets(archive)

        for sheet in sheets:
            root = ET.fromstring(archive.read(sheet.path))
            dimension_node = root.find(q("dimension"))
            dimension = dimension_node.attrib.get("ref") if dimension_node is not None else ""
            role = infer_sheet_role(sheet.name)
            summary = {
                "name": sheet.name,
                "role": role,
                "display_order": sheet.display_order,
                "dimension": dimension,
                "nonempty_cells": 0,
                "formula_count": 0,
                "max_row": 0,
                "max_col": 0,
                "label_samples": [],
            }

            formulas_by_address: dict[str, dict[str, str | None]] = {}
            row_labels: dict[int, dict[str, Any]] = {}

            for cell in root.iter(q("c")):
                address = cell.attrib.get("r", "")
                if not address:
                    continue
                row = row_number(address)
                col = column_number(address)
                summary["max_row"] = max(summary["max_row"], row)
                summary["max_col"] = max(summary["max_col"], col)

                formula_node = cell.find(q("f"))
                formula = text_of(formula_node)
                value, value_type = cell_value(cell, shared_strings)

                if formula_node is not None and (formula or formula_node.attrib):
                    summary["nonempty_cells"] += 1
                    summary["formula_count"] += 1
                    formula_record = {
                        "sheet": sheet.name,
                        "address": address,
                        "formula": formula,
                        "formula_kind": formula_kind(formula),
                        "cached_value": value,
                        "cached_value_type": value_type,
                    }
                    formulas_by_address[address] = formula_record
                    manifest["formulas"].append(formula_record)
                    for dependency in iter_cell_refs(formula, sheet.name):
                        manifest["dependencies"].append(
                            {
                                "formula_sheet": sheet.name,
                                "formula_address": address,
                                **dependency,
                            }
                        )
                    if not formula:
                        manifest["warnings"].append(
                            {
                                "kind": "blank_formula",
                                "sheet": sheet.name,
                                "address": address,
                            }
                        )
                    if "#REF!" in formula:
                        manifest["warnings"].append(
                            {
                                "kind": "broken_reference",
                                "sheet": sheet.name,
                                "address": address,
                                "formula": formula,
                            }
                        )
                elif value is not None and str(value).strip():
                    summary["nonempty_cells"] += 1
                    if len(summary["label_samples"]) < 16 and value_type in ("s", "inlineStr"):
                        summary["label_samples"].append(
                            {"address": address, "value": str(value).strip()[:120]}
                        )

                    if role in {
                        "summary",
                        "detail",
                        "unit_price_list",
                        "unit_price_detail",
                        "price_comparison",
                    } and col <= 3:
                        row_labels.setdefault(row, {})["display_label"] = str(value).strip()

            for wanted in GOLDEN_CELLS.get(sheet.name, []):
                formula_record = formulas_by_address.get(wanted, {})
                manifest["golden_cells"].append(
                    {
                        "sheet": sheet.name,
                        "address": wanted,
                        "formula": formula_record.get("formula"),
                        "cached_value": formula_record.get("cached_value"),
                        "cached_value_type": formula_record.get("cached_value_type"),
                    }
                )

            for row, projection in sorted(row_labels.items()):
                if row < 5:
                    continue
                manifest["sheet_line_projections"].append(
                    {
                        "sheet": sheet.name,
                        "sheet_role": role,
                        "row_no": row,
                        "display_label": projection.get("display_label"),
                        "source_range": f"A{row}:Z{row}",
                    }
                )

            manifest["sheets"].append(summary)

    return manifest


def find_default_workbook(repo_root: Path) -> Path:
    matches = sorted(repo_root.glob("docs/원가계산보고서샘플/*ver1*.xlsx*"))
    if not matches:
        matches = sorted(repo_root.glob("docs/**/*ver1*.xlsx*"))
    if not matches:
        raise FileNotFoundError("sample_ver1 workbook not found under docs/")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, help="Path to sample_ver1 xlsx")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/sample_ver1_cost_db/workbook_manifest.json"),
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    input_path = args.input or find_default_workbook(repo_root)
    if not input_path.is_absolute():
        input_path = repo_root / input_path
    output_path = args.output
    if not output_path.is_absolute():
        output_path = repo_root / output_path

    manifest = extract_workbook(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output_path}")
    print(
        f"sheets={len(manifest['sheets'])} "
        f"formulas={len(manifest['formulas'])} "
        f"dependencies={len(manifest['dependencies'])} "
        f"warnings={len(manifest['warnings'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
