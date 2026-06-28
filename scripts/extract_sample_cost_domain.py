#!/usr/bin/env python3
"""Extract normalized domain-table rows from a sample 원가계산보고서 workbook.

Reuses the cell parser in import_sample_ver1_cost_workbook.py and emits
domain_tables.json consumed by db-tables.html (sample_ver1 실제 값 보기).

Currently extracts:
  - cost_line           ← 내역서(detail) 시트
  - unit_cost_item      ← 일위대가목록(unit_price_list) 시트
  - unit_cost_component ← 일위대가표(unit_price_detail) 시트
  - price_comparison    ← 단가대비표(price_comparison) 시트

단가대비표 컬럼 매핑(헤더 r5/r6, 데이터 r7+):
  A 품명 / B 규격 / C 단위 /
  D 거래가격단가 E Page / F 물가정보단가 G Page / H 물가정보단가 I Page /
  J 조사단가 A업체 K B업체 L C업체 / M 적용단가 / N 비고 / O 구분
  (품명이 〃/" 면 직전 품명 상속, 적용단가(M)가 있어야 데이터 행으로 인정.
   단위가 "인" 이면 노무비(LAB), 그 외는 재료비(MAT)로 분류 — 분류는
   프로젝트(=revision)별로 달라질 수 있어 적용 시점 값으로 본다.)

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
    "price_comparison": 57,
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


def read_grid_with_formula(imp, archive: zipfile.ZipFile, sheet, shared_strings):
    """값 grid 와 수식 grid 를 함께 반환한다(원가계산서 비율/수식 추출용)."""
    root = ET.fromstring(archive.read(sheet.path))
    values: dict[tuple[int, int], Any] = {}
    formulas: dict[tuple[int, int], str] = {}
    for cell in root.iter(imp.q("c")):
        address = cell.attrib.get("r", "")
        if not address:
            continue
        row = imp.row_number(address)
        col = imp.column_number(address)
        value, _ = imp.cell_value(cell, shared_strings)
        if value is not None and str(value).strip() != "":
            values[(row, col)] = value
        formula_node = cell.find(imp.q("f"))
        if formula_node is not None and formula_node.text:
            formulas[(row, col)] = formula_node.text
    return values, formulas


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


# 품명 칸의 "같은 항목 반복" 표기(따옴표/이음표)
_DITTO = {'"', '〃', '″', '“', '”', ',,'}


def classify_cost_category(unit: str) -> str:
    """단가대비표 항목의 원가 분류. 단위 '인' → 노무비, 그 외 → 재료비."""
    return "LAB" if unit.strip() == "인" else "MAT"


def normalized_key(name: Any, spec: Any, unit: Any) -> str:
    """품명+규격+단위를 공백 제거·대문자화한 정규화 매칭 키."""
    norm = lambda x: re.sub(r"\s+", "", str(x or "")).upper()
    return f"{norm(name)}|{norm(spec)}|{norm(unit)}"


# 단가대비표 단가 컬럼 → 증빙 유형(reference_price_quote.source_type)
QUOTE_SOURCES = [
    ("deal_price", "거래가격"),
    ("info_price1", "물가정보1"),
    ("info_price2", "물가정보2"),
    ("survey_a", "조사단가A업체"),
    ("survey_b", "조사단가B업체"),
    ("survey_c", "조사단가C업체"),
]


def build_reference_price_tables(price_rows: list[dict]) -> tuple[dict, dict, dict]:
    """단가대비표 평면 행 → 정규화 3종(품목 마스터/단가 증빙/적용 단가).

    같은 정규화 키는 한 품목(price_item_id=RP###)으로 묶고, 비어있지 않은
    각 단가 컬럼을 증빙(quote)으로, 적용단가를 applied_price 로 승격한다.
    """
    key_to_pid: dict[str, str] = {}
    ref_items: list[dict] = []
    ref_quotes: list[dict] = []
    applied: list[dict] = []
    seen_quote: set[tuple] = set()
    order = 0
    for r in price_rows:
        key = normalized_key(r["item_name"], r["specification"], r["unit"])
        if key not in key_to_pid:
            order += 1
            pid = f"RP{order:03d}"
            key_to_pid[key] = pid
            ref_items.append({
                "price_item_id": pid,
                "normalized_key": key,
                "item_name": r["item_name"],
                "specification": r["specification"],
                "unit": r["unit"],
            })
            applied.append({
                "price_item_id": pid,
                "applied_unit_price": r["applied_unit_price"],
                "cost_category": r["cost_category"],
                "selection_rule": "수기선택(조사단가 기준)",
            })
        pid = key_to_pid[key]
        for field, label in QUOTE_SOURCES:
            value = r.get(field)
            if value is None:
                continue
            dedupe = (pid, label, value)
            if dedupe in seen_quote:
                continue
            seen_quote.add(dedupe)
            ref_quotes.append({
                "price_item_id": pid,
                "source_type": label,
                "quoted_unit_price": value,
            })
    return (
        {"columns": ["price_item_id", "normalized_key", "item_name", "specification", "unit"], "rows": ref_items},
        {"columns": ["price_item_id", "source_type", "quoted_unit_price"], "rows": ref_quotes},
        {"columns": ["price_item_id", "applied_unit_price", "cost_category", "selection_rule"], "rows": applied},
    )


def link_price_items(tables: dict, ref_item_rows: list[dict]) -> dict:
    """cost_line / unit_cost_component 행에 price_item_id 를 연결하고 매칭률을 돌려준다."""
    key_to_pid = {it["normalized_key"]: it["price_item_id"] for it in ref_item_rows}
    coverage: dict[str, str] = {}
    targets = [
        ("cost_line", "item_name"),
        ("unit_cost_component", "component_name"),
    ]
    for table_name, name_field in targets:
        table = tables.get(table_name)
        if not table:
            continue
        if "price_item_id" not in table["columns"]:
            table["columns"].append("price_item_id")
        matched = 0
        for row in table["rows"]:
            pid = key_to_pid.get(normalized_key(row[name_field], row["specification"], row["unit"]), "")
            row["price_item_id"] = pid
            if pid:
                matched += 1
        coverage[table_name] = f"{matched}/{len(table['rows'])}"
    return coverage


def extract_price_comparison(imp, archive, sheet, shared_strings) -> dict:
    """단가대비표(price_comparison) 시트 → price_comparison 행.

    적용단가(M, col13)가 채워진 행만 데이터로 인정한다. 품명이 〃/" 이면
    직전 품명을 상속한다.
    """
    grid = read_grid(imp, archive, sheet, shared_strings)
    max_row = max((r for (r, _c) in grid), default=0)
    columns = [
        "sort_order", "item_name", "specification", "unit",
        "deal_price", "info_price1", "info_price2",
        "survey_a", "survey_b", "survey_c",
        "applied_unit_price", "cost_category", "note",
    ]
    rows = []
    order = 0
    last_name = ""
    for r in range(7, max_row + 1):
        def cell(c):
            return grid.get((r, c))

        applied = to_number(cell(13))
        if applied is None:
            continue
        raw_name = str(cell(1)).strip() if cell(1) is not None else ""
        if raw_name in _DITTO or raw_name == "":
            name_text = last_name
        else:
            name_text = raw_name
            last_name = raw_name
        if not name_text:
            continue
        unit = str(cell(3)).strip() if cell(3) is not None else ""
        order += 1
        rows.append({
            "sort_order": order,
            "item_name": name_text,
            "specification": (str(cell(2)).strip() if cell(2) is not None else ""),
            "unit": unit,
            "deal_price": to_number(cell(4)),
            "info_price1": to_number(cell(6)),
            "info_price2": to_number(cell(8)),
            "survey_a": to_number(cell(10)),
            "survey_b": to_number(cell(11)),
            "survey_c": to_number(cell(12)),
            "applied_unit_price": applied,
            "cost_category": classify_cost_category(unit),
            "note": (str(cell(14)).strip() if cell(14) is not None else ""),
        })
    return {"columns": columns, "rows": rows}


_E_REF = re.compile(r"E(\d+)")
_J_REF = re.compile(r"J\d+")


def _collapse(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def extract_rate_and_indirect(imp, archive, sheet, shared_strings) -> tuple[dict, dict]:
    """원가계산서 시트 → rate_rule(비율 규칙) + indirect_cost_charge(적용 결과).

    비율(J열)이 있고 수식이 base*비율 형태인 행만 대상으로 한다. base 금액은
    수식 안의 E 참조 셀 값 합으로 해석하고, 금액은 E열 Excel 캐시값을 쓴다.
    """
    values, formulas = read_grid_with_formula(imp, archive, sheet, shared_strings)
    rate_rows: list[dict] = []
    charge_rows: list[dict] = []
    max_row = max((r for (r, _c) in values), default=0)
    for r in range(1, max_row + 1):
        formula = formulas.get((r, 5))  # E열 수식
        if not formula:
            continue
        rate = to_number(values.get((r, 10)))  # J열 비율
        if rate is None or rate == 0:
            continue
        # base*비율 형태인지 확인(J 참조 또는 리터럴 %)
        if "%" not in formula and not _J_REF.search(formula):
            continue
        label = _collapse(values.get((r, 3)) or values.get((r, 2)) or values.get((r, 1)))
        amount = to_number(values.get((r, 5)))
        base_refs = sorted({int(m) for m in _E_REF.findall(formula)})
        base_amount = sum_numbers(*[to_number(values.get((br, 5))) for br in base_refs])
        base_expr = "+".join(f"E{br}" for br in base_refs)
        rounding = "trunc_0" if ("ROUNDDOWN" in formula.upper() or "TRUNC" in formula.upper()) else "none"
        component_code = f"E{r}"
        rate_rows.append({
            "component_code": component_code,
            "component_name": label,
            "base_amount_type": base_expr,
            "rate_percent": rate,
            "rounding_rule": rounding,
            "formula_text": formula,
        })
        charge_rows.append({
            "component_code": component_code,
            "component_name": label,
            "base_expr": base_expr,
            "base_amount": base_amount,
            "rate_percent": rate,
            "calculated_amount": amount,
            "source_cell_address": f"원가계산서!E{r}",
        })
    rate_rule = {
        "columns": ["component_code", "component_name", "base_amount_type", "rate_percent", "rounding_rule", "formula_text"],
        "rows": rate_rows,
    }
    indirect = {
        "columns": ["component_code", "component_name", "base_expr", "base_amount", "rate_percent", "calculated_amount", "source_cell_address"],
        "rows": charge_rows,
    }
    return rate_rule, indirect


def extract_estimate_meta(imp, archive, sheet, shared_strings, version: str) -> tuple[dict, dict]:
    """원가계산서 시트 → cost_estimate / cost_estimate_revision 메타 1행씩."""
    values, _formulas = read_grid_with_formula(imp, archive, sheet, shared_strings)
    title = _collapse(values.get((1, 1))) or "공사원가계산서"
    total_cost = to_number(values.get((34, 5)))  # 원가계산서!E34 총원가
    estimate = {
        "columns": ["estimate_code", "title", "status", "basis_note"],
        "rows": [{
            "estimate_code": f"SAMPLE_{version.upper()}",
            "title": f"{title} (sample_{version})",
            "status": "imported",
            "basis_note": "단가대비표 조사기준 2026-06",
        }],
    }
    revision = {
        "columns": ["estimate_code", "revision_no", "total_cost", "vat_excluded", "calculation_status"],
        "rows": [{
            "estimate_code": f"SAMPLE_{version.upper()}",
            "revision_no": 1,
            "total_cost": total_cost,
            "vat_excluded": True,
            "calculation_status": "verified",
        }],
    }
    return estimate, revision


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
        price_cmp = next((s for s in sheets if imp.infer_sheet_role(s.name) == "price_comparison"), None)
        if price_cmp is not None:
            tables["price_comparison"] = extract_price_comparison(imp, archive, price_cmp, shared_strings)

    coverage: dict[str, str] = {}
    if "price_comparison" in tables:
        ref_items, ref_quotes, applied = build_reference_price_tables(tables["price_comparison"]["rows"])
        tables["reference_price_item"] = ref_items
        tables["reference_price_quote"] = ref_quotes
        tables["applied_price"] = applied
        coverage = link_price_items(tables, ref_items["rows"])

    version = "ver2" if "ver2" in str(args.input).lower() else "ver1"
    with zipfile.ZipFile(args.input) as archive:
        shared_strings = imp.read_shared_strings(archive)
        sheets = imp.read_sheets(archive)
        statement = next((s for s in sheets if imp.infer_sheet_role(s.name) == "cost_statement"), None)
        if statement is not None:
            rate_rule, indirect = extract_rate_and_indirect(imp, archive, statement, shared_strings)
            tables["rate_rule"] = rate_rule
            tables["indirect_cost_charge"] = indirect
            estimate, revision = extract_estimate_meta(imp, archive, statement, shared_strings, version)
            tables["cost_estimate"] = estimate
            tables["cost_estimate_revision"] = revision

    validate_expected_counts(tables)

    output = args.output
    if not output.is_absolute():
        output = REPO_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(tables, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = ", ".join(f"{name}={len(t['rows'])}행" for name, t in tables.items()) or "(없음)"
    print(f"wrote {output}  {summary}")
    if coverage:
        cov = ", ".join(f"{name} {ratio}" for name, ratio in coverage.items())
        print(f"price_item_id 연결: {cov}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
