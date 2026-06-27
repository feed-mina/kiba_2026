#!/usr/bin/env python3
"""Extract normalized domain-table rows from a sample 원가계산보고서 workbook.

Reuses the cell parser in import_sample_ver1_cost_workbook.py and emits
domain_tables.json consumed by db-tables.html (sample_ver1 실제 값 보기).

Currently extracts:
  - cost_line           ← 내역서(detail) 시트
  - unit_cost_item      ← 일위대가목록(unit_price_list) 시트
  - unit_cost_component ← 일위대가표(unit_price_detail) 시트

내역서 컬럼 매핑(확인됨):
  A 품명 / B 규격 / C 단위 / D 수량 /
  E 재료비단가 F 재료비금액 / G 노무비단가 H 노무비금액 /
  I 경비단가 J 경비금액 / K 합계 / L 비고

일위대가목록(unit_cost_item) 컬럼 매핑(헤더 r5, 데이터 r7+):
  A 일위N호 / B 품명 / C 규격 / D 단위 /
  E 재료비 / F 노무비 / G 경비 / H 합계

일위대가표(unit_cost_component) 컬럼 매핑(헤더 r5/r6, `[일위 N호]` 그룹):
  A 구성품명 / B 규격 / C 단위 / D 수량 /
  E 재료비단가 F 재료비금액 / G 노무비단가 H 노무비금액 /
  I 경비단가 J 경비금액 / K 합계단가 L 합계금액
  (그룹 헤더 행 `[일위 N호]` → unit_cost_no, `합 계`/`※ 표준품셈` 행은 스킵)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ROW_COUNTS = {
    "cost_line": 56,
    "unit_cost_item": 4,
    "unit_cost_component": 15,
}


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


def sum_numbers(*values: Any):
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    total = sum(numbers)
    return int(total) if isinstance(total, float) and total.is_integer() else total


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


# 일위대가목록 행에서 "일위  1호" → "1호" 로 정규화 (스키마 unit_cost_no 컬럼 기준)
_UNIT_COST_NO = re.compile(r"(\d+\s*호)")


def extract_unit_cost_item(imp, archive, sheet, shared_strings) -> dict:
    """일위대가목록(unit_price_list) 시트 → unit_cost_item 행.

    헤더 r5, 데이터 r7부터. A열 "일위 N호" 가 unit_cost_no 가 된다.
    """
    grid = read_grid(imp, archive, sheet, shared_strings)
    max_row = max((r for (r, _c) in grid), default=0)
    columns = [
        "unit_cost_no", "item_name", "specification", "unit",
        "material_amount", "labor_amount", "expense_amount", "total_amount",
    ]
    rows = []
    for r in range(7, max_row + 1):
        def cell(c):
            return grid.get((r, c))

        no_raw = cell(1)
        if no_raw is None:
            continue
        no_text = str(no_raw).strip()
        no_match = _UNIT_COST_NO.search(no_text)
        if not no_match:
            # A열이 "일위 N호" 형식이 아니면 종료(데이터 영역 아님)
            continue
        rows.append({
            "unit_cost_no": no_match.group(1).replace(" ", ""),
            "item_name": (str(cell(2)).strip() if cell(2) is not None else ""),
            "specification": (str(cell(3)).strip() if cell(3) is not None else ""),
            "unit": (str(cell(4)).strip() if cell(4) is not None else ""),
            "material_amount": to_number(cell(5)),
            "labor_amount": to_number(cell(6)),
            "expense_amount": to_number(cell(7)),
            "total_amount": to_number(cell(8)),
        })
    return {"columns": columns, "rows": rows}


# 일위대가표 그룹 헤더: `[일위  1호] - [강관 용접 배관  ]`
_GROUP_HEADER = re.compile(r"\[\s*일위\s*(\d+\s*호)\s*\]")


def extract_unit_cost_component(imp, archive, sheet, shared_strings) -> dict:
    """일위대가표(unit_price_detail) 시트 → unit_cost_component 행.

    `[일위 N호]` 그룹 헤더가 나타나면 unit_cost_no 를 갱신하고,
    이후 데이터행(A=구성품명, D=수량)을 그 unit_cost_no 에 묶는다.
    `합 계`/`※ 표준품셈` 행은 건너뛴다.
    """
    grid = read_grid(imp, archive, sheet, shared_strings)
    max_row = max((r for (r, _c) in grid), default=0)
    columns = [
        "unit_cost_no", "sort_order", "component_name", "specification", "unit", "quantity",
        "material_unit_price", "material_amount",
        "labor_unit_price", "labor_amount",
        "expense_unit_price", "expense_amount",
        "total_unit_price", "total_amount",
    ]
    rows = []
    current_no = ""
    order = 0
    for r in range(7, max_row + 1):
        def cell(c):
            return grid.get((r, c))

        name_raw = cell(1)
        name_text = str(name_raw).strip() if name_raw is not None else ""

        header = _GROUP_HEADER.search(name_text)
        if header:
            current_no = header.group(1).replace(" ", "")
            continue
        if not name_text:
            continue
        # 합계행(합 계) · 표준품셈 메모(※) · 데이터 없는 행 제외
        if name_text.startswith("※") or name_text.startswith("합"):
            continue
        # 데이터행: 수량(D)이 있어야 구성 행으로 인정
        qty = to_number(cell(4))
        if qty is None:
            continue
        material_unit_price = to_number(cell(5))
        material_amount = to_number(cell(6))
        labor_unit_price = to_number(cell(7))
        labor_amount = to_number(cell(8))
        expense_unit_price = to_number(cell(9))
        expense_amount = to_number(cell(10))
        total_unit_price = to_number(cell(11))
        total_amount = to_number(cell(12))
        if total_unit_price is None:
            total_unit_price = sum_numbers(material_unit_price, labor_unit_price, expense_unit_price)
        if total_amount is None:
            total_amount = sum_numbers(material_amount, labor_amount, expense_amount)
        order += 1
        rows.append({
            "unit_cost_no": current_no,
            "sort_order": order,
            "component_name": name_text,
            "specification": (str(cell(2)).strip() if cell(2) is not None else ""),
            "unit": (str(cell(3)).strip() if cell(3) is not None else ""),
            "quantity": qty,
            "material_unit_price": material_unit_price,
            "material_amount": material_amount,
            "labor_unit_price": labor_unit_price,
            "labor_amount": labor_amount,
            "expense_unit_price": expense_unit_price,
            "expense_amount": expense_amount,
            "total_unit_price": total_unit_price,
            "total_amount": total_amount,
        })
    return {"columns": columns, "rows": rows}


def validate_expected_counts(tables: dict[str, Any]) -> None:
    """Fail fast when a known sample_ver1 table silently regresses."""
    errors = []
    for name, expected in EXPECTED_ROW_COUNTS.items():
        actual = len(tables.get(name, {}).get("rows", []))
        if actual != expected:
            errors.append(f"{name}: expected {expected}, got {actual}")
    item_totals = {
        row["unit_cost_no"]: row.get("total_amount")
        for row in tables.get("unit_cost_item", {}).get("rows", [])
    }
    component_totals: dict[str, float] = {}
    for row in tables.get("unit_cost_component", {}).get("rows", []):
        total = row.get("total_amount")
        if total is None:
            continue
        component_totals[row["unit_cost_no"]] = component_totals.get(row["unit_cost_no"], 0) + total
    for unit_cost_no, item_total in item_totals.items():
        component_total = component_totals.get(unit_cost_no)
        if item_total != component_total:
            errors.append(
                f"unit_cost_total {unit_cost_no}: item {item_total}, components {component_total}"
            )
    if errors:
        raise RuntimeError("domain extraction count mismatch: " + "; ".join(errors))


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
        unit_list = next((s for s in sheets if imp.infer_sheet_role(s.name) == "unit_price_list"), None)
        if unit_list is not None:
            tables["unit_cost_item"] = extract_unit_cost_item(imp, archive, unit_list, shared_strings)
        unit_detail = next((s for s in sheets if imp.infer_sheet_role(s.name) == "unit_price_detail"), None)
        if unit_detail is not None:
            tables["unit_cost_component"] = extract_unit_cost_component(imp, archive, unit_detail, shared_strings)

    validate_expected_counts(tables)

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
