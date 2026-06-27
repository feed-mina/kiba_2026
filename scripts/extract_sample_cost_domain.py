#!/usr/bin/env python3
"""Extract normalized domain-table rows from a sample 원가계산보고서 workbook.

Reuses the cell parser in import_sample_ver1_cost_workbook.py and emits
domain_tables.json consumed by db-tables.html (sample_ver1 실제 값 보기).

Currently extracts:
  - cost_line  ← 내역서(detail) 시트

내역서 컬럼 매핑(확인됨):
  A 품명 / B 규격 / C 단위 / D 수량 /
  E 재료비단가 F 재료비금액 / G 노무비단가 H 노무비금액 /
  I 경비단가 J 경비금액 / K 합계 / L 비고
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_importer():
    path = REPO_ROOT / "scripts" / "import_sample_ver1_cost_workbook.py"
    spec = importlib.util.spec_from_file_location("costimp", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["costimp"] = mod
    spec.loader.exec_module(mod)
    return mod


def to_number(value: Any):
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text == "":
        return None
    try:
        num = float(text)
    except ValueError:
        return None
    return int(num) if num.is_integer() else num


def read_grid(imp, archive: zipfile.ZipFile, sheet, shared_strings) -> dict[tuple[int, int], Any]:
    root = ET.fromstring(archive.read(sheet.path))
    grid: dict[tuple[int, int], Any] = {}
    for cell in root.iter(imp.q("c")):
        address = cell.attrib.get("r", "")
        if not address:
            continue
        row = imp.row_number(address)
        col = imp.column_number(address)
        value, _ = imp.cell_value(cell, shared_strings)
        if value is None or str(value).strip() == "":
            continue
        grid[(row, col)] = value
    return grid


def extract_cost_line(imp, archive, sheet, shared_strings) -> dict:
    grid = read_grid(imp, archive, sheet, shared_strings)
    max_row = max((r for (r, _c) in grid), default=0)
    columns = [
        "sort_order", "section", "item_name", "specification", "unit", "quantity",
        "material_unit_price", "material_amount", "labor_unit_price", "labor_amount",
        "expense_unit_price", "expense_amount", "total_amount", "note",
    ]
    rows = []
    section = ""
    order = 0
    for r in range(9, max_row + 1):
        def cell(c):
            return grid.get((r, c))

        name = cell(1)
        name_text = str(name).strip() if name is not None else ""
        qty = to_number(cell(4))
        # 섹션 헤더 행(□ … / "1. 자재비" 등): 수량 없이 품명만 → section 갱신, 행 미생성
        if name_text and qty is None and cell(6) is None and cell(11) is None:
            section = name_text
            continue
        # 데이터 행: 실제 라인은 수량(D)이 있다. 수량 없는 행(소계/합계/소제목)은
        # 이중 계상을 막기 위해 제외한다.
        total = to_number(cell(11))
        if not name_text or qty is None:
            continue
        order += 1
        rows.append({
            "sort_order": order,
            "section": section,
            "item_name": name_text,
            "specification": (str(cell(2)).strip() if cell(2) is not None else ""),
            "unit": (str(cell(3)).strip() if cell(3) is not None else ""),
            "quantity": qty,
            "material_unit_price": to_number(cell(5)),
            "material_amount": to_number(cell(6)),
            "labor_unit_price": to_number(cell(7)),
            "labor_amount": to_number(cell(8)),
            "expense_unit_price": to_number(cell(9)),
            "expense_amount": to_number(cell(10)),
            "total_amount": total,
            "note": (str(cell(12)).strip() if cell(12) is not None else ""),
        })
    return {"columns": columns, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="원가계산보고서 xlsx 경로")
    parser.add_argument("--output", type=Path, required=True, help="domain_tables.json 출력 경로")
    args = parser.parse_args()

    imp = load_importer()
    tables: dict[str, Any] = {}
    with zipfile.ZipFile(args.input) as archive:
        shared_strings = imp.read_shared_strings(archive)
        sheets = imp.read_sheets(archive)
        detail = next((s for s in sheets if imp.infer_sheet_role(s.name) == "detail"), None)
        if detail is not None:
            tables["cost_line"] = extract_cost_line(imp, archive, detail, shared_strings)

    output = args.output
    if not output.is_absolute():
        output = REPO_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(tables, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = ", ".join(f"{name}={len(t['rows'])}행" for name, t in tables.items()) or "(없음)"
    print(f"wrote {output}  {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
