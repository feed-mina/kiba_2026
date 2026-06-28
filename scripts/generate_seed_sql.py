#!/usr/bin/env python3
"""domain_tables.json + workbook_manifest.json → schema.sql 적재용 INSERT SQL 생성.

domain_tables.json 은 화면 표시용 평면 데이터라 schema 의 uuid PK/FK 구조와
다르다. 이 스크립트는 자연키 기반 uuid5(결정적 ID)로 PK 를 만들고 FK 를
연결해, schema.sql 로 만든 빈 DB(+ migrations/001) 에 그대로 적재할 수 있는
seed SQL 을 생성한다.

대상 테이블(도메인 ETL 로 실제값이 있는 것):
  cost_estimate, cost_estimate_revision,
  reference_price_item, reference_price_quote, applied_price,
  unit_cost_item, unit_cost_component,
  cost_line, rate_rule_set, rate_rule, indirect_cost_charge
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
# 고정 네임스페이스(이 프로젝트 전용) → 같은 자연키는 항상 같은 uuid 로 재현된다.
NS = uuid.UUID("6b1f0c2a-1d3e-5a7b-9c11-0a1b2c3d4e5f")


def uid(*parts: Any) -> str:
    return str(uuid.uuid5(NS, "|".join(str(p) for p in parts)))


def sql_str(value: Any) -> str:
    if value is None or value == "":
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def sql_num(value: Any) -> str:
    if value is None or value == "":
        return "NULL"
    return str(value)


def sql_bool(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return "true" if str(value).lower() in ("true", "1") else "false"


def rows_of(tables: dict, name: str) -> list[dict]:
    return tables.get(name, {}).get("rows", [])


def build_sql(tables: dict, manifest: dict, version: str) -> str:
    ver = version.upper()
    estimate_code = f"SAMPLE_{ver}"
    estimate_id = uid("cost_estimate", estimate_code)
    revision_no = 1
    revision_id = uid("revision", estimate_code, revision_no)
    source_path = manifest.get("source_path", "")
    checksum = manifest.get("source_sha256", "")

    out: list[str] = []
    out.append(f"-- seed_sample_{version}.sql  (generate_seed_sql.py 자동 생성)")
    out.append("-- 적용: schema.sql + migrations/001 로 만든 빈 DB 에 실행")
    out.append("begin;")
    out.append("")

    # --- cost_estimate / revision ---
    est = rows_of(tables, "cost_estimate")
    title = est[0]["title"] if est else f"공사원가계산서 (sample_{version})"
    rev = rows_of(tables, "cost_estimate_revision")
    total_cost = rev[0]["total_cost"] if rev else None
    vat_excluded = rev[0].get("vat_excluded", True) if rev else True
    calc_status = rev[0].get("calculation_status", "verified") if rev else "verified"

    out.append("insert into cost_estimate (id, estimate_code, title, source_workbook_path, status) values")
    out.append(f"  ('{estimate_id}', {sql_str(estimate_code)}, {sql_str(title)}, {sql_str(source_path)}, 'imported');")
    out.append("")
    out.append("insert into cost_estimate_revision (id, estimate_id, revision_no, source_checksum, calculation_status, total_cost, vat_excluded) values")
    out.append(f"  ('{revision_id}', '{estimate_id}', {revision_no}, {sql_str(checksum)}, {sql_str(calc_status)}, {sql_num(total_cost)}, {sql_bool(vat_excluded)});")
    out.append("")

    # --- reference_price_item ---  (price_item_id=RP### 가 자연키)
    ref_items = rows_of(tables, "reference_price_item")
    pid_map = {r["price_item_id"]: uid("ref_item", r["price_item_id"]) for r in ref_items}
    out.append("insert into reference_price_item (id, item_name, specification, unit, normalized_key) values")
    vals = [
        f"  ('{pid_map[r['price_item_id']]}', {sql_str(r['item_name'])}, {sql_str(r['specification'])}, {sql_str(r['unit'])}, {sql_str(r['normalized_key'])})"
        for r in ref_items
    ]
    out.append(",\n".join(vals) + ";")
    out.append("")

    # --- reference_price_quote ---
    quotes = rows_of(tables, "reference_price_quote")
    out.append("insert into reference_price_quote (id, price_item_id, basis_month, source_type, quoted_unit_price) values")
    vals = [
        f"  ('{uid('quote', q['price_item_id'], q['source_type'])}', '{pid_map[q['price_item_id']]}', DATE '2026-06-01', {sql_str(q['source_type'])}, {sql_num(q['quoted_unit_price'])})"
        for q in quotes
    ]
    out.append(",\n".join(vals) + ";")
    out.append("")

    # --- applied_price ---
    applied = rows_of(tables, "applied_price")
    out.append("insert into applied_price (id, revision_id, price_item_id, selection_rule, applied_unit_price, cost_category_code) values")
    vals = [
        f"  ('{uid('applied', revision_id, a['price_item_id'])}', '{revision_id}', '{pid_map[a['price_item_id']]}', {sql_str(a['selection_rule'])}, {sql_num(a['applied_unit_price'])}, {sql_str(a['cost_category'])})"
        for a in applied
    ]
    out.append(",\n".join(vals) + ";")
    out.append("")

    # --- unit_cost_item ---  (unit_cost_no 가 자연키)
    uc_items = rows_of(tables, "unit_cost_item")
    uc_map = {r["unit_cost_no"]: uid("uc_item", revision_id, r["unit_cost_no"]) for r in uc_items}
    out.append("insert into unit_cost_item (id, revision_id, unit_cost_no, item_name, specification, unit, material_amount, labor_amount, expense_amount, total_amount) values")
    vals = [
        f"  ('{uc_map[r['unit_cost_no']]}', '{revision_id}', {sql_str(r['unit_cost_no'])}, {sql_str(r['item_name'])}, {sql_str(r['specification'])}, {sql_str(r['unit'])}, {sql_num(r['material_amount'])}, {sql_num(r['labor_amount'])}, {sql_num(r['expense_amount'])}, {sql_num(r['total_amount'])})"
        for r in uc_items
    ]
    out.append(",\n".join(vals) + ";")
    out.append("")

    # --- unit_cost_component ---
    uc_comp = rows_of(tables, "unit_cost_component")
    out.append("insert into unit_cost_component (id, unit_cost_item_id, sort_order, component_name, specification, unit, quantity, price_item_id, material_unit_price, labor_unit_price, expense_unit_price, material_amount, labor_amount, expense_amount, total_unit_price, total_amount) values")
    vals = []
    for c in uc_comp:
        parent = uc_map.get(c["unit_cost_no"])
        if parent is None:
            continue
        price_ref = pid_map.get(c.get("price_item_id"))
        price_ref_sql = f"'{price_ref}'" if price_ref else "NULL"
        vals.append(
            f"  ('{uid('uc_comp', parent, c['sort_order'])}', '{parent}', {c['sort_order']}, {sql_str(c['component_name'])}, {sql_str(c['specification'])}, {sql_str(c['unit'])}, {sql_num(c['quantity'])}, {price_ref_sql}, {sql_num(c['material_unit_price'])}, {sql_num(c['labor_unit_price'])}, {sql_num(c['expense_unit_price'])}, {sql_num(c['material_amount'])}, {sql_num(c['labor_amount'])}, {sql_num(c['expense_amount'])}, {sql_num(c['total_unit_price'])}, {sql_num(c['total_amount'])})"
        )
    out.append(",\n".join(vals) + ";")
    out.append("")

    # --- cost_line ---  (sort_order 가 자연키, price_item_id 연결)
    lines = rows_of(tables, "cost_line")
    out.append("insert into cost_line (id, revision_id, sheet_role, line_code, sort_order, item_name, specification, unit, quantity, material_unit_price, material_amount, labor_unit_price, labor_amount, expense_unit_price, expense_amount, total_amount, note, price_item_id) values")
    vals = []
    for r in lines:
        price_ref = pid_map.get(r.get("price_item_id"))
        price_ref_sql = f"'{price_ref}'" if price_ref else "NULL"
        vals.append(
            f"  ('{uid('cost_line', revision_id, r['sort_order'])}', '{revision_id}', 'detail', {sql_str(r.get('section'))}, {r['sort_order']}, {sql_str(r['item_name'])}, {sql_str(r['specification'])}, {sql_str(r['unit'])}, {sql_num(r['quantity'])}, {sql_num(r['material_unit_price'])}, {sql_num(r['material_amount'])}, {sql_num(r['labor_unit_price'])}, {sql_num(r['labor_amount'])}, {sql_num(r['expense_unit_price'])}, {sql_num(r['expense_amount'])}, {sql_num(r['total_amount'])}, {sql_str(r.get('note'))}, {price_ref_sql})"
        )
    out.append(",\n".join(vals) + ";")
    out.append("")

    # --- rate_rule_set / rate_rule / indirect_cost_charge ---
    rs = rows_of(tables, "rate_rule_set")
    set_code = rs[0]["rule_set_code"] if rs else f"{ver}_RATES"
    set_id = uid("rule_set", set_code)
    if rs:
        s = rs[0]
        out.append("insert into rate_rule_set (id, rule_set_code, rule_set_name, basis_date, source_name) values")
        out.append(f"  ('{set_id}', {sql_str(s['rule_set_code'])}, {sql_str(s['rule_set_name'])}, DATE {sql_str(s['basis_date'])}, {sql_str(s['source_name'])});")
        out.append("")

    rate_rows = rows_of(tables, "rate_rule")
    rr_map = {r["component_code"]: uid("rate_rule", set_id, r["component_code"]) for r in rate_rows}
    out.append("insert into rate_rule (id, rule_set_id, cost_component_code, base_amount_type, rate_percent, rounding_rule) values")
    vals = [
        f"  ('{rr_map[r['component_code']]}', '{set_id}', {sql_str(r['component_code'])}, {sql_str(r['base_amount_type'])}, {sql_num(r['rate_percent'])}, {sql_str(r['rounding_rule'])})"
        for r in rate_rows
    ]
    out.append(",\n".join(vals) + ";")
    out.append("")

    charges = rows_of(tables, "indirect_cost_charge")
    out.append("insert into indirect_cost_charge (id, revision_id, rate_rule_id, component_code, base_amount, rate_percent, calculated_amount, source_sheet_name, source_cell_address) values")
    vals = []
    for c in charges:
        rule_ref = rr_map.get(c["component_code"])
        rule_ref_sql = f"'{rule_ref}'" if rule_ref else "NULL"
        cell = c.get("source_cell_address", "")
        sheet_name = cell.split("!")[0] if "!" in cell else "원가계산서"
        addr = cell.split("!")[1] if "!" in cell else cell
        vals.append(
            f"  ('{uid('charge', revision_id, c['component_code'])}', '{revision_id}', {rule_ref_sql}, {sql_str(c['component_code'])}, {sql_num(c['base_amount'])}, {sql_num(c['rate_percent'])}, {sql_num(c['calculated_amount'])}, {sql_str(sheet_name)}, {sql_str(addr)})"
        )
    out.append(",\n".join(vals) + ";")
    out.append("")
    out.append("commit;")
    out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", type=Path, default=Path("data/sample_ver1_cost_db/domain_tables.json"))
    parser.add_argument("--manifest", type=Path, default=Path("data/sample_ver1_cost_db/workbook_manifest.json"))
    parser.add_argument("--version", default="ver1")
    parser.add_argument("--output", type=Path, default=Path("data/sample_ver1_cost_db/migrations/002_seed_sample_ver1.sql"))
    args = parser.parse_args()

    def resolve(p: Path) -> Path:
        return p if p.is_absolute() else REPO_ROOT / p

    tables = json.loads(resolve(args.domain).read_text(encoding="utf-8"))
    manifest = json.loads(resolve(args.manifest).read_text(encoding="utf-8"))
    sql = build_sql(tables, manifest, args.version)
    out_path = resolve(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(sql, encoding="utf-8")
    print(f"wrote {out_path}  ({len(sql.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
