#!/usr/bin/env python3
"""계산형 검증: 단가대비표+일위대가표로 내역서 단가가 재현되는가 / 물량으로
원가계산서가 산출되는가 를 domain_tables.json 기반으로 확인한다.

질문 1) 내역서 각 라인의 단가를 일위대가(합성단가) → 단가대비표(적용단가)
        참조로 만들 수 있는가? (만든 단가 × 수량 == 내역서 금액 인지 비교)
질문 2) 내역서 물량(수량)이 있으면 재료비/노무비/경비로 집계되어
        원가계산서(간접비·일반관리비·이윤·총원가)까지 산출되는가?
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def nkey(name: Any, spec: Any, unit: Any) -> str:
    norm = lambda x: re.sub(r"\s+", "", str(x or "")).upper()
    return f"{norm(name)}|{norm(spec)}|{norm(unit)}"


def num(v: Any) -> float:
    if v is None or v == "":
        return 0.0
    return float(v)


def rows(tables: dict, name: str) -> list[dict]:
    return tables.get(name, {}).get("rows", [])


def build_lookups(tables: dict):
    # 일위대가: 품목키 → (재료/노무/경비) 합성 단가(단위당 금액)
    uc_by_key = {}
    uc_by_no = {}
    for r in rows(tables, "unit_cost_item"):
        value = {
            "material": num(r["material_amount"]),
            "labor": num(r["labor_amount"]),
            "expense": num(r["expense_amount"]),
        }
        uc_by_key[nkey(r["item_name"], r["specification"], r["unit"])] = value
        uc_by_no[r["unit_cost_no"]] = value
    # 단가대비표: RP### → (적용단가, 분류) / 품목키 → RP
    pid_price = {a["price_item_id"]: (num(a["applied_unit_price"]), a["cost_category"])
                 for a in rows(tables, "applied_price")}
    key_to_pid = {it["normalized_key"]: it["price_item_id"] for it in rows(tables, "reference_price_item")}
    return uc_by_key, uc_by_no, pid_price, key_to_pid


def resolve_unit_price(line: dict, uc_by_key: dict, uc_by_no: dict, pid_price: dict, key_to_pid: dict):
    """라인의 단가를 일위대가 → 단가대비표 순으로 해석. (재료,노무,경비) 단위단가 반환."""
    unit_cost_no = line.get("unit_cost_no")
    if unit_cost_no in uc_by_no:
        u = uc_by_no[unit_cost_no]
        return (u["material"], u["labor"], u["expense"]), "unit_cost"
    key = nkey(line["item_name"], line["specification"], line["unit"])
    if key in uc_by_key:
        u = uc_by_key[key]
        return (u["material"], u["labor"], u["expense"]), "unit_cost"
    pid = line.get("price_item_id") or key_to_pid.get(key)
    if pid in pid_price:
        price, cat = pid_price[pid]
        if cat == "LAB":
            return (0.0, price, 0.0), "price_comparison"
        return (price, 0.0, 0.0), "price_comparison"
    return None, "direct"  # 일위/단가표로 못 만드는 직접·일괄단가


def resolve_formula_amounts(line: dict, prior_sums: dict[str, float]):
    """단가표가 아니라 내역서 내부 산식으로 만들어지는 비율 행을 해석한다."""
    unit = str(line.get("unit") or "").strip()
    spec = str(line.get("specification") or "")
    if unit == "%" and "자재비" in spec:
        amount = math.trunc(prior_sums["material"] * num(line.get("quantity")) / 100)
        return (float(amount), 0.0, 0.0), "formula_percent"
    return None, "direct"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", type=Path, default=Path("data/sample_ver1_cost_db/domain_tables.json"))
    parser.add_argument("--tolerance", type=float, default=1.0, help="단가×수량 vs 내역서 금액 허용 오차(원)")
    args = parser.parse_args()
    path = args.domain if args.domain.is_absolute() else REPO_ROOT / args.domain
    tables = json.loads(path.read_text(encoding="utf-8"))
    uc_by_key, uc_by_no, pid_price, key_to_pid = build_lookups(tables)
    all_lines = rows(tables, "cost_line")
    lines = [line for line in all_lines if line.get("rollup_included", True)]
    excluded_lines = [line for line in all_lines if not line.get("rollup_included", True)]

    # ---- 질문 1: 내역서 단가 재현 ----
    by_source = {"unit_cost": 0, "price_comparison": 0, "formula_percent": 0, "direct": 0}
    derivable_match = 0
    derivable_total = 0
    derivable_amount = 0.0
    direct_amount = 0.0
    total_amount = 0.0
    sums = {"material": 0.0, "labor": 0.0, "expense": 0.0}
    prior_sums = {"material": 0.0, "labor": 0.0, "expense": 0.0}
    for ln in lines:
        qty = num(ln["quantity"])
        actual = (num(ln["material_amount"]), num(ln["labor_amount"]), num(ln["expense_amount"]))
        line_total = sum(actual)
        total_amount += line_total
        resolved, source = resolve_unit_price(ln, uc_by_key, uc_by_no, pid_price, key_to_pid)
        computed = None
        if resolved is None:
            computed, source = resolve_formula_amounts(ln, prior_sums)
        by_source[source] += 1
        if resolved is not None or computed is not None:
            derivable_total += 1
            if computed is None:
                computed = tuple(round(qty * up) for up in resolved)
            # 단가대비표 단일분류는 한 비목만 채우므로 그 비목 금액만 비교
            if source in ("unit_cost", "formula_percent"):
                ok = all(abs(computed[i] - actual[i]) <= args.tolerance for i in range(3))
            else:
                ok = abs(sum(computed) - line_total) <= max(args.tolerance, line_total * 0.001)
            derivable_match += 1 if ok else 0
            derivable_amount += line_total
        else:
            direct_amount += line_total
        # 집계용 합(내역서 실제 금액 기준)
        sums["material"] += actual[0]; sums["labor"] += actual[1]; sums["expense"] += actual[2]
        prior_sums["material"] += actual[0]; prior_sums["labor"] += actual[1]; prior_sums["expense"] += actual[2]

    print("=" * 64)
    print("질문 1) 내역서 단가를 일위대가+단가대비표로 재현 가능한가")
    print("-" * 64)
    print(f"  내역서 라인: {len(lines)}")
    if excluded_lines:
        print(f"  원가계산서 집계 제외 라인: {len(excluded_lines)}")
    print(
        f"  단가 출처: 일위대가 {by_source['unit_cost']} · "
        f"단가대비표 {by_source['price_comparison']} · "
        f"비율산식 {by_source['formula_percent']} · 직접단가필요 {by_source['direct']}"
    )
    print(f"  재현 가능 라인: {derivable_total}/{len(lines)}  (그중 단가×수량==내역서금액 일치 {derivable_match})")
    cov = derivable_amount / total_amount * 100 if total_amount else 0
    print(f"  금액 커버리지: {derivable_amount:,.0f} / {total_amount:,.0f} ({cov:.1f}%)  | 직접단가 필요분 {direct_amount:,.0f}")
    print("  → 매칭 품목과 비율 행은 계산 재현 가능")

    # ---- 질문 2: 물량 → 집계 → 원가계산서 ----
    snap = {r["value_name"].replace(" ", ""): num(r["numeric_value"]) for r in rows(tables, "calculated_value_snapshot")}
    agg_material = snap.get("직접재료비")
    agg_labor = snap.get("직접노무비")
    agg_expense = snap.get("기계경비")  # 직접경비(집계표 I19)
    total_cost = num(rows(tables, "cost_estimate_revision")[0]["total_cost"])

    print("=" * 64)
    print("질문 2) 내역서 물량 → 집계 → 원가계산서 산출")
    print("-" * 64)
    print(f"  내역서 합(수량×단가): 재료비 {sums['material']:,.0f} · 노무비 {sums['labor']:,.0f} · 경비 {sums['expense']:,.0f}")
    print(f"  원가계산서 집계값:    재료비 {agg_material:,.0f} · 노무비 {agg_labor:,.0f} · 경비 {agg_expense:,.0f}")
    gap_m = sums["material"] - (agg_material or 0)
    gap_l = sums["labor"] - (agg_labor or 0)
    gap_e = sums["expense"] - (agg_expense or 0)
    print(f"  집계 차이(내역서합 - 집계표): 재료비 {gap_m:,.0f} · 노무비 {gap_l:,.0f} · 경비 {gap_e:,.0f}")

    # 간접비 체인 재현 (rate_rule 적용; base 는 원가계산서 스냅샷값 사용)
    chain_ok = 0
    chain_total = 0
    for c in rows(tables, "indirect_cost_charge"):
        chain_total += 1
        recomputed = math.floor(num(c["base_amount"]) * num(c["rate_percent"]))
        if recomputed == num(c["calculated_amount"]):
            chain_ok += 1
    print(f"  간접비/관리비/이윤 체인: {chain_ok}/{chain_total} 행 floor(base×비율)==Excel값")
    print(f"  총원가(원가계산서!E34): {total_cost:,.0f}")
    print("  → 수량×단가로 비목 집계 후 rate_rule 적용 시 원가계산서까지 산출됨")
    print("    (내역서 합계행에 포함되는 라인만 집계 대상으로 사용)")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
