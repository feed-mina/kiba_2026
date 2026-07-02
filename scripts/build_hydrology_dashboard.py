# -*- coding: utf-8 -*-
"""Build the hydrology cost-analysis dashboard from K-water survey workbooks."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "docs" / "과업수행 관련 자료_한국수자원조사기술원"
OUTPUT_HTML = ROOT / "docs" / "수문조사_원가분석_대시보드.html"
YEARS = ["2021년", "2022년", "2023년", "2024년", "2025년", "2026년"]
REGION_RANGES = [
    ("한강권역", 1, 97),
    ("낙동강권역", 98, 201),
    ("금강권역", 202, 278),
    ("영산강권역", 279, 355),
]

# 표준품셈 유량조사 투입인원수 산정기준 (인·일/단위)
# 출처: 수자원 조사·계획 표준품셈(산업통상자원부, 2023) 제2장 수문조사 · 2-1 유량조사 · 라. 투입인원수 산정기준 (원문 p.6)
# person_days = 등급별(기술사·특급·고급·중급·초급·보조원) 투입 인·일의 합계. scope="회"는 유량측정 횟수(N)에 비례, "지점"은 과업당 1회 적용.
PUMSEM_FLOW = {
    "source": "수자원 조사·계획 표준품셈(산업통상자원부, 2023) · 제2장 유량조사 · 라. 투입인원수 산정기준 (원문 p.6)",
    "note": "인·일/단위 = 기술등급(기술사·특급·고급·중급·초급·보조원)별 투입 인·일의 합계입니다. 등급별 세부는 표준품셈 원문 표를 참조하세요. 측정규모 기준: 교량 설치 지점 1개소·수면폭 100~200m.",
    "rows": [
        {"task": "현지조사", "scope": "지점", "person_days": 1.50},
        {"task": "평·저수 유량측정", "scope": "회", "person_days": 2.45},
        {"task": "홍수(고수) 유량측정", "scope": "회", "person_days": 6.10},
        {"task": "기존자료 수집분석", "scope": "지점", "person_days": 6.00},
        {"task": "수위-유량곡선식 개발", "scope": "지점", "person_days": 12.00},
        {"task": "기존 곡선식 상관분석", "scope": "지점", "person_days": 6.25},
        {"task": "유량자료 생산", "scope": "지점", "person_days": 6.00},
        {"task": "유량측정결과 분석", "scope": "지점", "person_days": 7.50},
        {"task": "홍수예보기준수위 검토", "scope": "지점", "person_days": 7.50},
        {"task": "유량측정성과 검증", "scope": "회", "person_days": 0.30},
        {"task": "수위-유량곡선식 평가", "scope": "지점", "person_days": 2.50},
        {"task": "유출분석 평가", "scope": "지점", "person_days": 8.00},
        {"task": "결론 및 건의", "scope": "지점", "person_days": 1.00},
        {"task": "성과품 작성", "scope": "지점", "person_days": 5.75},
    ],
}


def clean(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\n", " ").strip()
    return value


def number(value: Any, default: float = 0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else default


def won_from_text(value: Any) -> int:
    return int(round(number(value)))


def workbook(needle: str) -> Path:
    matches = [
        path
        for path in SOURCE_DIR.rglob("*.xlsx")
        if needle in path.name and not path.name.startswith("~$")
    ]
    if not matches:
        raise FileNotFoundError(f"Workbook not found: {needle}")
    return sorted(matches)[0]


def region_for_station(no: int) -> str:
    for name, start, end in REGION_RANGES:
        if start <= no <= end:
            return name
    return "미분류"


def expand_range(value: Any) -> list[int]:
    if isinstance(value, (int, float)):
        return [int(value)]
    nums = [int(v) for v in re.findall(r"\d+", str(value or ""))]
    if len(nums) >= 2:
        return list(range(nums[0], nums[1] + 1))
    if len(nums) == 1:
        return [nums[0]]
    return []


def rows_by_year(ws: Any, row_start: int, row_end: int, label_col: int, first_year_col: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row_no in range(row_start, row_end + 1):
        label = clean(ws.cell(row=row_no, column=label_col).value)
        if not label:
            continue
        rows.append(
            {
                "item": label,
                "values": {
                    year[:4]: int(round(number(ws.cell(row=row_no, column=first_year_col + idx).value)))
                    for idx, year in enumerate(YEARS)
                },
            }
        )
    return rows


def parse_budget_and_units() -> dict[str, Any]:
    path = workbook("예산 및 단가 현황_v2")
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)

    counts = rows_by_year(wb["현황"], 5, 11, 3, 4)
    counts_after = rows_by_year(wb["현황"], 5, 11, 12, 13)
    unit_prices = rows_by_year(wb["단가"], 5, 11, 3, 4)
    business_budget = rows_by_year(wb["항목별예산"], 14, 19, 2, 3)
    business_budget_with_carryover = rows_by_year(wb["항목별예산"], 14, 19, 10, 11)

    flow_rows: list[dict[str, Any]] = []
    ws = wb["유량"]
    for row_no in range(6, 12):
        flow_rows.append(
            {
                "year": str(ws.cell(row=row_no, column=2).value)[:4],
                "sites": int(number(ws.cell(row=row_no, column=3).value)),
                "unit_price_million": int(number(ws.cell(row=row_no, column=4).value)),
                "total_million": int(number(ws.cell(row=row_no, column=5).value)),
                "org_million": int(number(ws.cell(row=row_no, column=6).value)),
                "org_pct": number(ws.cell(row=row_no, column=7).value),
                "business_million": int(number(ws.cell(row=row_no, column=8).value)),
                "business_pct": number(ws.cell(row=row_no, column=9).value),
            }
        )

    total_budget: list[dict[str, Any]] = []
    ws = wb["총예산_02"]
    for row_no in range(6, 12):
        total_budget.append(
            {
                "year": str(ws.cell(row=row_no, column=2).value)[:4],
                "total_million": int(number(ws.cell(row=row_no, column=3).value)),
                "org_million": int(number(ws.cell(row=row_no, column=4).value)),
                "org_pct": number(ws.cell(row=row_no, column=5).value),
                "business_million": int(number(ws.cell(row=row_no, column=6).value)),
                "business_pct": number(ws.cell(row=row_no, column=7).value),
            }
        )

    auto_rows: list[dict[str, Any]] = []
    ws = wb["자동유량"]
    current_year = ""
    for row_no in range(7, 30):
        year_cell = ws.cell(row=row_no, column=2).value
        if year_cell:
            current_year = str(year_cell)[:4]
        item = clean(ws.cell(row=row_no, column=3).value)
        if item in {"운영", "설치", "유지관리"}:
            auto_rows.append(
                {
                    "year": current_year,
                    "item": item,
                    "quantity": int(number(ws.cell(row=row_no, column=4).value)),
                    "unit_price_million": int(number(ws.cell(row=row_no, column=5).value)),
                    "total_million": int(number(ws.cell(row=row_no, column=6).value)),
                    "business_million": int(number(ws.cell(row=row_no, column=9).value)),
                }
            )

    return {
        "source": str(path.relative_to(ROOT)).replace("\\", "/"),
        "counts": counts,
        "counts_after": counts_after,
        "unit_prices": unit_prices,
        "business_budget": business_budget,
        "business_budget_with_carryover": business_budget_with_carryover,
        "flow_rows": flow_rows,
        "total_budget": total_budget,
        "auto_rows": auto_rows,
    }


def parse_flow_business_breakdown() -> dict[str, Any]:
    path = workbook("세부예산 현황_v1")
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb["유량"]
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in ws.iter_rows(min_row=4, values_only=True):
        group = clean(row[1])
        stat = clean(row[2])
        value = int(number(row[13]))
        if stat == "소계":
            # 편성목(대분류) 소계 행 - 새 그룹 시작
            if group == "합계":
                current = None
                continue
            current = {"item": group, "amount_won": value, "children": []}
            if value:
                rows.append(current)
            continue
        # 통계목(품목) 하위 라인 - 직전 편성목에 근거로 첨부
        if current is not None and stat and value:
            current["children"].append({"item": stat, "amount_won": value})
    total = sum(row["amount_won"] for row in rows)
    return {
        "source": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sheet": "유량",
        "year": "2026",
        "rows": rows,
        "total_won": total,
    }


def parse_stations_and_traffic() -> dict[str, Any]:
    station_path = workbook("조사지점 현황")
    traffic_path = workbook("교통비")

    wb = openpyxl.load_workbook(station_path, data_only=True, read_only=True)
    ws = wb.active
    stations: dict[int, dict[str, Any]] = {}
    for row in ws.iter_rows(min_row=4, values_only=True):
        no = row[1]
        if isinstance(no, int):
            stations[no] = {
                "no": no,
                "name": clean(row[2]),
                "address": clean(row[3]),
                "region": region_for_station(no),
            }

    wb = openpyxl.load_workbook(traffic_path, data_only=True, read_only=True)
    ws = wb.active
    traffic_ranges: list[dict[str, Any]] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        station_numbers = expand_range(row[0])
        fare = won_from_text(row[4])
        if not station_numbers or not fare:
            continue
        rec = {
            "range": clean(row[0]),
            "place": clean(row[1]),
            "mode": clean(row[2]),
            "hub": clean(row[3]),
            "fare": fare,
            "start": min(station_numbers),
            "end": max(station_numbers),
            "region": region_for_station(min(station_numbers)),
        }
        traffic_ranges.append(rec)
        for no in station_numbers:
            if no in stations:
                stations[no].update(
                    {
                        "fare": fare,
                        "mode": rec["mode"],
                        "hub": rec["hub"],
                        "traffic_place": rec["place"],
                    }
                )

    return {
        "station_source": str(station_path.relative_to(ROOT)).replace("\\", "/"),
        "traffic_source": str(traffic_path.relative_to(ROOT)).replace("\\", "/"),
        "stations": [stations[key] for key in sorted(stations)],
        "traffic_ranges": traffic_ranges,
    }


def parse_equipment() -> dict[str, Any]:
    path = workbook("장비 관련")
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb["보유장비 관련"]
    rows: list[dict[str, Any]] = []
    current_group = ""
    for row in ws.iter_rows(min_row=5, values_only=True):
        group = clean(row[1])
        sub = clean(row[2])
        variant = clean(row[3])
        if group:
            current_group = group
        if current_group == "합계":
            continue
        owned = int(number(row[4], 0))
        if not current_group or not owned:
            continue
        name = " ".join(str(part) for part in [current_group, sub, variant] if part)
        rows.append(
            {
                "name": name,
                "group": current_group,
                "owned": owned,
                "standard": clean(row[5]) or "-",
                "life_elapsed_2026": int(number(row[6], 0)),
                "life_elapsed_2027": int(number(row[7], 0)),
                "purchase_plan_2027": int(number(row[8], 0)),
                "unit_price_won": int(number(row[9], 0)) if row[9] not in (None, "-") else None,
            }
        )

    calibration = []
    ws = wb["월 검·교정 비용"]
    for col in range(3, 15):
        month = clean(ws.cell(row=3, column=col).value)
        amount_thousand = number(ws.cell(row=4, column=col).value, 0)
        calibration.append({"month": month, "amount_won": int(round(amount_thousand * 1000))})

    def avg_price(group: str) -> float:
        values = [
            row["unit_price_won"]
            for row in rows
            if group in row["group"] and row["unit_price_won"]
        ]
        return mean(values) if values else 0

    core_kit = round(
        avg_price("ADCP")
        + avg_price("무선조종 보트")
        + avg_price("전자파 표면유속계")
        + avg_price("측량장비")
    )

    return {
        "source": str(path.relative_to(ROOT)).replace("\\", "/"),
        "rows": rows,
        "total_owned": sum(row["owned"] for row in rows),
        "calibration": calibration,
        "calibration_annual_won": sum(row["amount_won"] for row in calibration),
        "core_kit_price_won": core_kit,
    }


def parse_vehicle_ops() -> dict[str, Any]:
    path = workbook("업무차량")
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)

    ws = wb["업무차량"]
    vehicles: list[dict[str, Any]] = []
    for row in ws.iter_rows(min_row=4, values_only=True):
        if clean(row[1]) and isinstance(row[3], (int, float)):
            vehicles.append(
                {
                    "type": clean(row[1]),
                    "eco_type": clean(row[2]),
                    "monthly_rent_won": int(number(row[3])),
                }
            )
    counts = Counter(row["type"] for row in vehicles)

    ws = wb["전기&주유비"]
    energy_rows: list[dict[str, Any]] = []
    months = [clean(ws.cell(row=3, column=col).value) for col in range(3, 9)]
    for row_no in [4, 5]:
        energy_rows.append(
            {
                "item": clean(ws.cell(row=row_no, column=2).value),
                "values": {
                    month: int(number(ws.cell(row=row_no, column=idx + 3).value))
                    for idx, month in enumerate(months)
                },
            }
        )

    eco_counts = Counter(row["eco_type"] for row in vehicles)
    total_monthly_rent = sum(row["monthly_rent_won"] for row in vehicles)
    # 전기·주유비: 6개월 실적을 연 환산
    energy_annual_won = sum(
        round(sum(row["values"].values()) / len(row["values"]) * 12) if row["values"] else 0
        for row in energy_rows
    )
    return {
        "source": str(path.relative_to(ROOT)).replace("\\", "/"),
        "vehicle_count": len(vehicles),
        "avg_monthly_rent_won": round(mean(row["monthly_rent_won"] for row in vehicles)),
        "total_monthly_rent_won": total_monthly_rent,
        "annual_rent_won": total_monthly_rent * 12,
        "type_counts": [{"type": key, "count": value} for key, value in counts.most_common()],
        "eco_counts": [{"type": key, "count": value} for key, value in eco_counts.most_common()],
        "energy_rows": energy_rows,
        "energy_annual_won": energy_annual_won,
    }


def parse_rent_ops() -> dict[str, Any]:
    path = workbook("임대 관련")
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)

    def annual_by_region(sheet_name: str, start_row: int, end_row: int) -> dict[str, int]:
        ws = wb[sheet_name]
        result: dict[str, int] = {}
        for row in ws.iter_rows(min_row=start_row, max_row=end_row, values_only=True):
            label = clean(row[1])
            if not label:
                continue
            result[label.replace("실", "")] = int(round(number(row[14]) * 1000))
        return result

    container = annual_by_region("컨테이너(창고)_2025년 기준", 5, 8)
    parking = annual_by_region("주차시설_2025년 기준", 6, 9)
    survey_equipment_rent = int(
        round(number(wb["측량장비 대여_2025년 기준"].cell(row=4, column=14).value) * 1000)
    )
    return {
        "source": str(path.relative_to(ROOT)).replace("\\", "/"),
        "container_annual_won": container,
        "parking_annual_won": parking,
        "survey_equipment_rent_won": survey_equipment_rent,
    }


def enrich_regions(station_data: dict[str, Any], rent_data: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"stations": 0, "fares": []})
    for station in station_data["stations"]:
        region = station["region"]
        grouped[region]["stations"] += 1
        if station.get("fare"):
            grouped[region]["fares"].append(station["fare"])

    rows: list[dict[str, Any]] = []
    for region, _, _ in REGION_RANGES:
        fares = grouped[region]["fares"]
        facility = rent_data["container_annual_won"].get(region, 0) + rent_data["parking_annual_won"].get(region, 0)
        count = grouped[region]["stations"]
        rows.append(
            {
                "region": region,
                "stations": count,
                "avg_fare": round(mean(fares)) if fares else 0,
                "min_fare": min(fares) if fares else 0,
                "max_fare": max(fares) if fares else 0,
                "facility_annual_won": facility,
                "facility_per_station_won": round(facility / count) if count else 0,
                "container_annual_won": rent_data["container_annual_won"].get(region, 0),
                "parking_annual_won": rent_data["parking_annual_won"].get(region, 0),
            }
        )
    return rows


def build_data() -> dict[str, Any]:
    budget = parse_budget_and_units()
    flow_breakdown = parse_flow_business_breakdown()
    station_data = parse_stations_and_traffic()
    equipment = parse_equipment()
    vehicles = parse_vehicle_ops()
    rent = parse_rent_ops()
    regions = enrich_regions(station_data, rent)

    flow_2026 = next(row for row in budget["flow_rows"] if row["year"] == "2026")
    total_2026 = next(row for row in budget["total_budget"] if row["year"] == "2026")
    fares = [station["fare"] for station in station_data["stations"] if station.get("fare")]

    # 카드별 자료 출처 상세 (파일 › 시트 › 행) — 회의 피드백 #59-9 대응
    budget_file = Path(budget["source"]).name
    detail_file = Path(flow_breakdown["source"]).name
    station_file = Path(station_data["station_source"]).name
    traffic_file = Path(station_data["traffic_source"]).name
    equip_file = Path(equipment["source"]).name
    vehicle_file = Path(vehicles["source"]).name
    rent_file = Path(rent["source"]).name
    sources_detail = {
        "totalBudget": f"{budget_file} › 총예산_02 시트 · 6~11행",
        "flowStructure": f"{budget_file} › 유량 시트 · 6~11행",
        "itemBudget": f"{budget_file} › 항목별예산 시트 · 14~19행",
        "unitPrice": f"{budget_file} › 단가 시트 · 5~11행 / 현황 시트(수량) · 5~11행",
        "count": f"{budget_file} › 현황 시트 · 5~11행 (자동유량은 자동유량 시트)",
        "flowBreakdown": f"{detail_file} › 유량 시트 · 편성목 소계행(인건비5·운영비10·여비23·업무추진비26·유형자산40행)",
        "station": f"{station_file} › 조사지점 현황 시트 · 4행~",
        "traffic": f"{traffic_file} › 교통비 시트 · 2행~ (연번 구간을 지점번호로 전개)",
        "region": f"{station_file}(연번 구간 배부) + {rent_file}(컨테이너·주차 2025년 기준)",
        "equipment": f"{equip_file} › 보유장비 관련 시트 · 5행~ ※ 전국 보유 기준(권역 구분 없음)",
        "calibration": f"{equip_file} › 월 검·교정 비용 시트 · 3~4행",
        "vehicle": f"{vehicle_file} › 업무차량 시트 4행~, 전기&주유비 시트",
        "rent": f"{rent_file} › 컨테이너(창고)·주차시설·측량장비 대여 시트 (2025년 기준)",
        "pumsem": PUMSEM_FLOW["source"],
    }
    pdf_sources = sorted(
        str(path.relative_to(ROOT)).replace("\\", "/") for path in SOURCE_DIR.rglob("*.pdf")
    )
    workbooks = sorted(
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in SOURCE_DIR.rglob("*.xlsx")
        if not path.name.startswith("~$")
    )
    return {
        "generated_on": date.today().isoformat(),
        "budget": budget,
        "flow_breakdown": flow_breakdown,
        "stations": station_data["stations"],
        "traffic_ranges": station_data["traffic_ranges"],
        "regions": regions,
        "equipment": equipment,
        "vehicles": vehicles,
        "rent": rent,
        "pumsem_flow": PUMSEM_FLOW,
        "sources": {
            "workbooks": workbooks,
            "pdfs": pdf_sources,
        },
        "sources_detail": sources_detail,
        "summary": {
            "station_total": len(station_data["stations"]),
            "flow_sites_2026": flow_2026["sites"],
            "flow_unit_price_won": flow_2026["unit_price_million"] * 1_000_000,
            "flow_total_budget_won": flow_2026["total_million"] * 1_000_000,
            "flow_business_budget_won": flow_breakdown["total_won"],
            "flow_business_per_site_won": round(flow_breakdown["total_won"] / flow_2026["sites"]),
            "total_budget_2026_won": total_2026["total_million"] * 1_000_000,
            "total_business_2026_won": total_2026["business_million"] * 1_000_000,
            "avg_one_way_fare_won": round(mean(fares)),
            "max_one_way_fare_won": max(fares),
            "equipment_total": equipment["total_owned"],
            "vehicle_count": vehicles["vehicle_count"],
            "avg_vehicle_rent_won": vehicles["avg_monthly_rent_won"],
            "vehicle_annual_rent_won": vehicles["annual_rent_won"],
            "vehicle_energy_annual_won": vehicles["energy_annual_won"],
            # 데이터 기반 차량비 지점 배부: 전체 차량 연 임차료 ÷ 전체 조사지점
            "vehicle_rent_per_station_won": round(vehicles["annual_rent_won"] / len(station_data["stations"])),
            "core_equipment_kit_won": equipment["core_kit_price_won"],
            "workbook_count": len(workbooks),
            "pdf_count": len(pdf_sources),
        },
    }


HTML_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>수문조사 원가 분석 대시보드</title>
  <style>
    :root {
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #667085;
      --line: #d8dee9;
      --blue: #2563eb;
      --teal: #0f766e;
      --green: #15803d;
      --amber: #b45309;
      --violet: #7c3aed;
      --rose: #be123c;
      --soft-blue: #e8f0ff;
      --soft-teal: #e7f7f4;
      --soft-amber: #fff4df;
      --soft-green: #e9f8ee;
      --shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", Arial, sans-serif;
      line-height: 1.5;
    }
    button, input, select {
      font: inherit;
    }
    .app {
      min-height: 100vh;
    }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 10;
      background: rgba(245, 247, 251, 0.94);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(12px);
    }
    .topbar-inner {
      max-width: 1480px;
      margin: 0 auto;
      padding: 16px 24px;
      display: grid;
      grid-template-columns: minmax(260px, 1fr) auto;
      gap: 16px;
      align-items: center;
    }
    h1 {
      margin: 0;
      font-size: 22px;
      letter-spacing: 0;
    }
    .subtitle {
      margin-top: 3px;
      color: var(--muted);
      font-size: 13px;
    }
    .actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .button {
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      padding: 9px 12px;
      border-radius: 8px;
      cursor: pointer;
      min-height: 38px;
      box-shadow: 0 1px 0 rgba(15, 23, 42, 0.03);
    }
    .button.primary {
      background: var(--blue);
      border-color: var(--blue);
      color: white;
    }
    .button:hover {
      border-color: #9aa4b2;
    }
    main {
      max-width: 1480px;
      margin: 0 auto;
      padding: 20px 24px 48px;
    }
    .tabs {
      display: flex;
      gap: 6px;
      overflow-x: auto;
      padding-bottom: 10px;
    }
    .tab {
      border: 1px solid var(--line);
      background: white;
      color: #344054;
      border-radius: 8px;
      padding: 9px 13px;
      white-space: nowrap;
      cursor: pointer;
    }
    .tab.active {
      background: #17202a;
      color: white;
      border-color: #17202a;
    }
    .panel {
      display: none;
    }
    .panel.active {
      display: block;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 14px;
      align-items: start;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 16px;
      min-width: 0;
    }
    .span-2 { grid-column: span 2; }
    .span-3 { grid-column: span 3; }
    .span-4 { grid-column: span 4; }
    .span-5 { grid-column: span 5; }
    .span-6 { grid-column: span 6; }
    .span-7 { grid-column: span 7; }
    .span-8 { grid-column: span 8; }
    .span-12 { grid-column: span 12; }
    h2 {
      margin: 0 0 12px;
      font-size: 16px;
      letter-spacing: 0;
    }
    h3 {
      margin: 0 0 8px;
      font-size: 14px;
    }
    .metric-label {
      color: var(--muted);
      font-size: 12px;
    }
    .metric-value {
      margin-top: 6px;
      font-size: 24px;
      font-weight: 800;
      letter-spacing: 0;
      word-break: keep-all;
    }
    .metric-note {
      margin-top: 5px;
      color: var(--muted);
      font-size: 12px;
    }
    .source-note {
      margin-top: 12px;
      padding-top: 9px;
      border-top: 1px dashed #e2e8f0;
      color: #8a94a6;
      font-size: 11px;
      line-height: 1.45;
      word-break: keep-all;
    }
    .source-note b {
      color: #667085;
      font-weight: 700;
    }
    .basis {
      display: inline-block;
      margin-top: 4px;
      font-size: 11px;
      line-height: 1.4;
    }
    .badge {
      display: inline-block;
      border-radius: 999px;
      padding: 1px 7px;
      font-size: 10.5px;
      font-weight: 700;
      vertical-align: 1px;
    }
    .badge.data { background: #e7f7f4; color: #0f766e; border: 1px solid #b8e3db; }
    .badge.assume { background: #fff4df; color: #b45309; border: 1px solid #f0d6a8; }
    .cond-echo {
      margin: 2px 0 10px;
      padding: 8px 10px;
      background: #f4f7ff;
      border: 1px solid #dbe4fb;
      border-radius: 8px;
      font-size: 12px;
      color: #344054;
    }
    .accent-blue { border-top: 4px solid var(--blue); }
    .accent-teal { border-top: 4px solid var(--teal); }
    .accent-green { border-top: 4px solid var(--green); }
    .accent-amber { border-top: 4px solid var(--amber); }
    .accent-violet { border-top: 4px solid var(--violet); }
    .chart {
      width: 100%;
      height: 310px;
      display: block;
      background: #fbfcff;
      border: 1px solid #e5eaf2;
      border-radius: 8px;
    }
    .chart.small {
      height: 250px;
    }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      margin-top: 10px;
      color: var(--muted);
      font-size: 12px;
    }
    .legend i {
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 3px;
      margin-right: 5px;
      vertical-align: -1px;
    }
    .table-wrap {
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      min-width: 680px;
    }
    th, td {
      padding: 10px;
      border-bottom: 1px solid #edf0f5;
      text-align: left;
      vertical-align: top;
    }
    th {
      color: #344054;
      background: #f8fafc;
      font-weight: 700;
    }
    tr:last-child td {
      border-bottom: 0;
    }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }
    label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 5px;
    }
    input, select {
      width: 100%;
      border: 1px solid #cfd7e3;
      border-radius: 8px;
      padding: 9px 10px;
      background: white;
      color: var(--ink);
      min-height: 38px;
    }
    .summary-line {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      padding: 10px 0;
      border-bottom: 1px solid #edf0f5;
      font-size: 13px;
    }
    .summary-line:last-child {
      border-bottom: 0;
    }
    .amount {
      font-weight: 800;
      text-align: right;
      white-space: nowrap;
    }
    .status-band {
      display: grid;
      grid-template-columns: 1.2fr 1fr 1fr;
      gap: 12px;
      align-items: stretch;
    }
    .callout {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 13px;
      background: #fbfcff;
    }
    .callout strong {
      display: block;
      margin-bottom: 4px;
    }
    .soft-blue { background: var(--soft-blue); }
    .soft-teal { background: var(--soft-teal); }
    .soft-green { background: var(--soft-green); }
    .soft-amber { background: var(--soft-amber); }
    .pill {
      display: inline-block;
      border: 1px solid #cfd7e3;
      border-radius: 999px;
      padding: 3px 8px;
      margin: 2px;
      font-size: 12px;
      color: #344054;
      background: white;
      white-space: nowrap;
    }
    .station-strip {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
    }
    .mini-map {
      min-height: 310px;
      display: grid;
      place-items: center;
      background: linear-gradient(180deg, #fbfcff, #f2f7ff);
      border: 1px solid #e5eaf2;
      border-radius: 8px;
    }
    .source-list {
      columns: 2;
      column-gap: 24px;
      padding-left: 18px;
      margin: 0;
      color: #344054;
      font-size: 13px;
    }
    .source-list li {
      break-inside: avoid;
      margin-bottom: 8px;
    }
    .print-title {
      display: none;
    }
    @media (max-width: 1100px) {
      .span-2, .span-3, .span-4, .span-5, .span-6, .span-7, .span-8 { grid-column: span 12; }
      .form-grid, .station-strip, .status-band { grid-template-columns: 1fr 1fr; }
      .topbar-inner { grid-template-columns: 1fr; }
      .actions { justify-content: flex-start; }
    }
    @media (max-width: 640px) {
      main { padding: 14px 12px 34px; }
      .topbar-inner { padding: 14px 12px; }
      .form-grid, .station-strip, .status-band { grid-template-columns: 1fr; }
      .source-list { columns: 1; }
      .metric-value { font-size: 21px; }
      h1 { font-size: 19px; }
    }
    @media print {
      body { background: white; }
      .topbar, .tabs, .no-print { display: none !important; }
      main { max-width: none; padding: 0; }
      .panel { display: block !important; page-break-after: always; }
      .card { box-shadow: none; break-inside: avoid; }
      .print-title { display: block; margin: 0 0 16px; }
    }
  </style>
</head>
<body>
  <script type="application/json" id="dashboard-data">__DATA_JSON__</script>
  <div class="app">
    <header class="topbar">
      <div class="topbar-inner">
        <div>
          <h1>수문조사 원가 분석 대시보드</h1>
          <div class="subtitle" id="subtitle"></div>
        </div>
        <div class="actions no-print">
          <button class="button" id="btnCsv">CSV</button>
          <button class="button" id="btnExcel">Excel</button>
          <button class="button primary" id="btnPrint">인쇄/PDF</button>
        </div>
      </div>
    </header>
    <main>
      <div class="tabs no-print" id="tabs"></div>

      <section class="panel active" id="overview">
        <h2 class="print-title">개요</h2>
        <div class="grid" id="overviewGrid"></div>
      </section>

      <section class="panel" id="station">
        <h2 class="print-title">지점별 원가 조회</h2>
        <div class="grid">
          <div class="card span-12">
            <h2>지점 선택 및 산출 조건</h2>
            <div class="metric-note" style="margin-bottom:10px">
              <span class="badge data">데이터</span> 원자료에서 직접 추출한 값 ·
              <span class="badge assume">가정</span> 원가 모델의 조정 가능한 가정값(원자료 근거 없음, 회의 #59 확인 대상)
            </div>
            <div class="form-grid">
              <div>
                <label for="stationSelect">조사지점</label>
                <select id="stationSelect"></select>
                <span class="basis"><span class="badge data">데이터</span> 조사지점 현황·교통비 파일</span>
              </div>
              <div>
                <label for="staffInput">투입 인원 (최대 6)</label>
                <input id="staffInput" type="number" min="1" max="6" value="2">
                <span class="basis"><span class="badge data">품셈</span> 표준품셈 홍수측정 6.10인·일/회 → 최대 6 (아래 표)</span>
              </div>
              <div>
                <label for="visitInput">연간 방문 횟수</label>
                <input id="visitInput" type="number" min="1" value="12">
                <span class="basis"><span class="badge assume">가정</span> 관측 주기(월 1회=12) 가정</span>
              </div>
              <div>
                <label for="dayInput">방문당 투입일</label>
                <input id="dayInput" type="number" min="0.25" step="0.25" value="1">
                <span class="basis"><span class="badge data">품셈</span> 평·저수 2.45인·일/회 기준 (아래 표)</span>
              </div>
              <div>
                <label for="laborInput">1인 1일 인건비</label>
                <input id="laborInput" type="number" min="0" step="10000" value="250000">
                <span class="basis"><span class="badge assume">가정</span> 엔지니어링 노임단가(협회 공표) 적용 대상 · 잠정 25만원/인·일 (품셈 외부, 세부예산 인건비와 별개)</span>
              </div>
              <div>
                <label for="vehicleSlotInput">차량 월 처리 지점</label>
                <input id="vehicleSlotInput" type="number" min="1" value="22">
                <span class="basis"><span class="badge assume">가정</span> 차량 1대 월 순회 지점 수(잠정 22) · 원자료엔 없음 → 데이터 배부(연임차료÷355지점)는 장비·운영비 탭 참조</span>
              </div>
              <div>
                <label for="equipmentLifeInput">장비 내용연수</label>
                <input id="equipmentLifeInput" type="number" min="1" value="7">
                <span class="basis"><span class="badge assume">가정</span> 원자료엔 경과 내용연수만('26 12대·'27 32대) · 연수 7년은 가정</span>
              </div>
              <div>
                <label for="equipmentUseInput">장비 세트 연간 투입 횟수</label>
                <input id="equipmentUseInput" type="number" min="1" value="160">
                <span class="basis"><span class="badge assume">가정</span> 장비 1세트 연 가동 횟수(잠정 160) · 정수기준(팀당/실당)·단가는 데이터, 가동횟수는 가정</span>
              </div>
              <div>
                <label for="overheadInput">간접비율</label>
                <input id="overheadInput" type="number" min="0" step="1" value="17">
                <span class="basis"><span class="badge assume">가정</span> 표준품셈 관리비율 15~18% 범위 · 잠정 17%</span>
              </div>
            </div>
          </div>
          <div class="card span-4 accent-blue" id="stationInfo"></div>
          <div class="card span-4 accent-teal" id="stationCost"></div>
          <div class="card span-4 accent-amber" id="stationCompare"></div>
          <div class="card span-7">
            <h2>지점 원가 구성</h2>
            <svg class="chart small" id="costDonut" viewBox="0 0 720 250" role="img"></svg>
            <div class="legend" id="costLegend"></div>
          </div>
          <div class="card span-5">
            <h2>산출 내역</h2>
            <div id="costLines"></div>
          </div>
          <div class="card span-7">
            <h2>표준품셈 투입인원 산정기준 (유량조사)</h2>
            <div class="metric-note" style="margin-bottom:8px">위 '투입 인원·방문당 투입일'의 실제 근거입니다. 단위 <b>회</b>는 유량측정 횟수(N)에 비례, <b>지점</b>은 과업당 1회 적용됩니다.</div>
            <div class="table-wrap"><table id="pumsemTable"></table></div>
            <div class="src-slot" data-src="pumsem"></div>
          </div>
          <div class="card span-5">
            <h2>품셈 기반 투입 인·일 (선택 조건)</h2>
            <div id="pumsemCalc"></div>
          </div>
          <div class="card span-12">
            <h2>교통비 상위 지점</h2>
            <div class="table-wrap"><table id="topFareTable"></table></div>
            <div class="src-slot" data-src="traffic"></div>
          </div>
        </div>
      </section>

      <section class="panel" id="region">
        <h2 class="print-title">권역별 비교</h2>
        <div class="grid">
          <div class="card span-12">
            <h2>권역 요약</h2>
            <div class="station-strip" id="regionCards"></div>
          </div>
          <div class="card span-6">
            <h2>평균 편도 교통비</h2>
            <svg class="chart small" id="regionFareChart" viewBox="0 0 720 250" role="img"></svg>
            <div class="src-slot" data-src="traffic"></div>
          </div>
          <div class="card span-6">
            <h2>연간 임차·주차비 지점 배부액</h2>
            <svg class="chart small" id="regionFacilityChart" viewBox="0 0 720 250" role="img"></svg>
            <div class="src-slot" data-src="region"></div>
          </div>
          <div class="card span-12">
            <h2>권역별 비교표</h2>
            <div class="table-wrap"><table id="regionTable"></table></div>
            <div class="src-slot" data-src="region"></div>
          </div>
        </div>
      </section>

      <section class="panel" id="sample">
        <h2 class="print-title">지역 샘플 비교</h2>
        <div class="grid">
          <div class="card span-12">
            <h2>지역별 대표 지점 원가 비교 (이슈 #57)</h2>
            <div class="metric-note" style="margin-bottom:8px">
              전라(영산강)·경상(낙동강)·충청(금강) 각 권역에서 <b>편도 교통비가 가장 높은(운영 부담이 큰) 지점</b>을 대표 샘플로 뽑아,
              동일한 기본 산출 조건(<span class="badge assume">가정</span> 2명·연 12회·1일·인건비 25만원·간접 17%)으로 1건 원가를 나란히 비교합니다.
              고비용 지점을 우선 점검하기 위한 화면으로, 실제 페일 지점 목록이 확정되면 교체 예정입니다.
            </div>
            <div class="station-strip" id="sampleCards" style="grid-template-columns: repeat(3, minmax(0, 1fr));"></div>
          </div>
          <div class="card span-12">
            <h2>샘플 3건 원가 항목 비교표</h2>
            <div class="table-wrap"><table id="sampleTable"></table></div>
            <div class="src-slot" data-src="region"></div>
          </div>
        </div>
      </section>

      <section class="panel" id="equipment">
        <h2 class="print-title">장비·운영비</h2>
        <div class="grid">
          <div class="card span-3 accent-blue" id="equipmentKpi"></div>
          <div class="card span-3 accent-teal" id="vehicleKpi"></div>
          <div class="card span-3 accent-green" id="calibrationKpi"></div>
          <div class="card span-3 accent-amber" id="rentKpi"></div>
          <div class="card span-7">
            <h2>보유 장비 현황</h2>
            <div class="metric-note" style="margin-bottom:8px">전국 보유 기준입니다. 원자료에 권역 구분이 없어 지역별 배분은 별도 가정이 필요합니다.</div>
            <div class="table-wrap"><table id="equipmentTable"></table></div>
            <div class="src-slot" data-src="equipment"></div>
          </div>
          <div class="card span-5">
            <h2>차량·에너지 운영</h2>
            <div id="vehicleOps"></div>
            <div class="src-slot" data-src="vehicle"></div>
          </div>
        </div>
      </section>

      <section class="panel" id="sources">
        <h2 class="print-title">자료 출처</h2>
        <div class="grid">
          <div class="card span-6">
            <h2>Excel 원자료</h2>
            <ul class="source-list" id="workbookSources"></ul>
          </div>
          <div class="card span-6">
            <h2>지침·법령 PDF</h2>
            <ul class="source-list" id="pdfSources"></ul>
          </div>
          <div class="card span-12">
            <h2>데이터 처리 기준</h2>
            <div class="status-band">
              <div class="callout soft-blue"><strong>권역 분류</strong>조사지점 연번 흐름에 따라 1~97 한강, 98~201 낙동강, 202~278 금강, 279~355 영산강으로 배부했습니다.</div>
              <div class="callout soft-teal"><strong>교통비 매칭</strong>교통비 파일의 연번 범위를 조사지점 번호로 펼쳐 355개 지점 모두에 편도 교통비를 연결했습니다.</div>
              <div class="callout soft-amber"><strong>원가 계산</strong>지점별 계산기는 실제 교통비, 권역별 임차비, 차량 평균 임차료, 대표 장비 세트 감가상각을 조합한 추정 모델입니다.</div>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>

  <script>
    const DATA = JSON.parse(document.getElementById("dashboard-data").textContent);
    const TABS = [
      ["overview", "개요"],
      ["station", "지점별"],
      ["region", "권역 비교"],
      ["sample", "지역 샘플"],
      ["equipment", "장비·운영비"],
      ["sources", "자료 출처"]
    ];
    const COLORS = ["#2563eb", "#0f766e", "#15803d", "#b45309", "#7c3aed", "#be123c"];
    const $ = (id) => document.getElementById(id);
    const nf = new Intl.NumberFormat("ko-KR");
    const won = (v) => `${nf.format(Math.round(Number(v) || 0))}원`;
    const billion = (v) => `${(Number(v || 0) / 100000000).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}억원`;
    const million = (v) => `${nf.format(Math.round(Number(v || 0) / 1000000))}백만원`;
    const pct = (v) => `${Number(v || 0).toFixed(1)}%`;
    const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
    const srcNote = (key) => {
      const detail = (DATA.sources_detail || {})[key];
      return detail ? `<div class="source-note"><b>자료 출처</b> · ${escapeHtml(detail)}</div>` : "";
    };

    function initTabs() {
      $("tabs").innerHTML = TABS.map(([id, label], idx) => `<button class="tab ${idx === 0 ? "active" : ""}" data-tab="${id}">${label}</button>`).join("");
      $("tabs").addEventListener("click", (event) => {
        const button = event.target.closest("[data-tab]");
        if (!button) return;
        document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab === button));
        document.querySelectorAll(".panel").forEach((panel) => panel.classList.toggle("active", panel.id === button.dataset.tab));
      });
    }

    function metric(label, value, note, accent) {
      return `<div class="card span-3 ${accent || ""}"><div class="metric-label">${label}</div><div class="metric-value">${value}</div><div class="metric-note">${note}</div></div>`;
    }

    function renderOverview() {
      const s = DATA.summary;
      $("subtitle").textContent = `원자료 ${s.workbook_count}개 workbook, ${s.pdf_count}개 PDF 기준 · 생성일 ${DATA.generated_on}`;
      const latestFlow = DATA.budget.flow_rows.find((row) => row.year === "2026");
      $("overviewGrid").innerHTML = `
        ${metric("2026 유량 지점 수", `${nf.format(s.flow_sites_2026)}개소`, "유량조사 기준", "accent-blue")}
        ${metric("유량 지점당 단가", billion(s.flow_unit_price_won), "2021~2026 고정", "accent-teal")}
        ${metric("2026 수문정보 총예산", billion(s.total_budget_2026_won), "총계 기준", "accent-green")}
        ${metric("평균 편도 교통비", won(s.avg_one_way_fare_won), "355개 지점 매칭", "accent-amber")}
        <div class="card span-8">
          <h2>수문정보 총예산 추이</h2>
          <svg class="chart" id="totalBudgetChart" viewBox="0 0 900 310" role="img"></svg>
          <div class="legend"><span><i style="background:#2563eb"></i>기관운영</span><span><i style="background:#0f766e"></i>사업</span></div>
          ${srcNote("totalBudget")}
        </div>
        <div class="card span-4">
          <h2>2026 유량 예산 구조</h2>
          <div class="summary-line"><span>총계</span><span class="amount">${million(latestFlow.total_million * 1000000)}</span></div>
          <div class="summary-line"><span>기관운영</span><span class="amount">${million(latestFlow.org_million * 1000000)} · ${pct(latestFlow.org_pct)}</span></div>
          <div class="summary-line"><span>사업</span><span class="amount">${million(latestFlow.business_million * 1000000)} · ${pct(latestFlow.business_pct)}</span></div>
          <div class="summary-line"><span>사업 예산 지점 배부</span><span class="amount">${won(s.flow_business_per_site_won)}</span></div>
          ${srcNote("flowStructure")}
        </div>
        <div class="card span-7">
          <h2>항목별 사업 예산</h2>
          <svg class="chart small" id="itemBudgetChart" viewBox="0 0 820 250" role="img"></svg>
          ${srcNote("itemBudget")}
        </div>
        <div class="card span-5">
          <h2>유량 사업 세부예산 분해</h2>
          <div id="flowBreakdown"></div>
          ${srcNote("flowBreakdown")}
        </div>
        <div class="card span-7">
          <h2>항목별 수량·단가·예산 현황 (2026)</h2>
          <div class="metric-note" style="margin-bottom:8px">수량(현황) × 단가 = 사업+기관운영 예산. '단가만' 대신 '수량 대비 단가'로 근거를 함께 표시합니다.</div>
          <div class="table-wrap"><table id="unitPriceTable"></table></div>
          ${srcNote("unitPrice")}
        </div>
        <div class="card span-5">
          <h2>수량 대비 단가</h2>
          <svg class="chart small" id="qtyPriceChart" viewBox="0 0 720 250" role="img"></svg>
          <div class="metric-note">가로축 = 2026 수량(개소), 세로축 = 지점당 단가(백만원)</div>
          ${srcNote("unitPrice")}
        </div>
        <div class="card span-12">
          <h2>수문조사 지점·자동유량 수량 추이 (2021~2026)</h2>
          <svg class="chart small" id="countChart" viewBox="0 0 820 250" role="img"></svg>
          ${srcNote("count")}
        </div>
      `;
      stackedBudgetChart("totalBudgetChart", DATA.budget.total_budget);
      barChart("itemBudgetChart", DATA.budget.business_budget.filter((row) => row.item !== "계").map((row) => ({ label: row.item, value: row.values["2026"] * 1000000 })), "budget");
      renderUnitTable();
      renderFlowBreakdown();
      qtyVsPriceChart("qtyPriceChart");
      groupedLineChart("countChart", DATA.budget.counts.filter((row) => ["유량", "운영", "설치"].includes(row.item)));
    }

    function stackedBudgetChart(id, rows) {
      const width = 900, height = 310, left = 70, right = 24, top = 28, bottom = 44;
      const innerW = width - left - right, innerH = height - top - bottom;
      const max = Math.max(...rows.map((row) => row.total_million));
      const band = innerW / rows.length;
      let html = `<line x1="${left}" y1="${height - bottom}" x2="${width - right}" y2="${height - bottom}" stroke="#98a2b3"/>`;
      rows.forEach((row, i) => {
        const x = left + i * band + band * 0.22;
        const bw = band * 0.56;
        const orgH = row.org_million / max * innerH;
        const bizH = row.business_million / max * innerH;
        const base = height - bottom;
        html += `<rect x="${x}" y="${base - orgH}" width="${bw}" height="${orgH}" rx="4" fill="#2563eb"/>`;
        html += `<rect x="${x}" y="${base - orgH - bizH}" width="${bw}" height="${bizH}" rx="4" fill="#0f766e"/>`;
        html += `<text x="${x + bw / 2}" y="${base + 22}" text-anchor="middle" font-size="13" fill="#667085">${row.year}</text>`;
        html += `<text x="${x + bw / 2}" y="${base - orgH - bizH - 8}" text-anchor="middle" font-size="12" font-weight="700" fill="#17202a">${nf.format(row.total_million)}</text>`;
      });
      $("totalBudgetChart").innerHTML = html;
    }

    function barChart(id, rows, kind) {
      const width = 820, height = 250, left = 120, right = 28, top = 18, bottom = 28;
      const innerW = width - left - right, innerH = height - top - bottom;
      const max = Math.max(...rows.map((row) => row.value), 1);
      const band = innerH / rows.length;
      let html = `<line x1="${left}" y1="${height - bottom}" x2="${width - right}" y2="${height - bottom}" stroke="#d0d5dd"/>`;
      rows.forEach((row, i) => {
        const y = top + i * band + band * 0.2;
        const bh = band * 0.6;
        const bw = row.value / max * innerW;
        html += `<text x="${left - 10}" y="${y + bh * 0.68}" text-anchor="end" font-size="13" fill="#344054">${escapeHtml(row.label)}</text>`;
        html += `<rect x="${left}" y="${y}" width="${bw}" height="${bh}" rx="5" fill="${COLORS[i % COLORS.length]}"/>`;
        const label = kind === "budget" ? billion(row.value) : kind === "won" ? won(row.value) : nf.format(row.value);
        // 막대가 길면 라벨이 차트 밖으로 잘리므로 막대 안쪽에 흰색으로 배치한다.
        const inside = bw > innerW * 0.72;
        const labelX = inside ? left + bw - 8 : left + bw + 8;
        const anchor = inside ? "end" : "start";
        const fill = inside ? "#ffffff" : "#17202a";
        html += `<text x="${labelX}" y="${y + bh * 0.68}" text-anchor="${anchor}" font-size="12" font-weight="700" fill="${fill}">${label}</text>`;
      });
      $(id).innerHTML = html;
    }

    function groupedLineChart(id, rows) {
      const width = 820, height = 250, left = 48, right = 24, top = 24, bottom = 36;
      const years = ["2021", "2022", "2023", "2024", "2025", "2026"];
      const max = Math.max(...rows.flatMap((row) => years.map((year) => row.values[year] || 0)), 1);
      const x = (idx) => left + idx * ((width - left - right) / (years.length - 1));
      const y = (value) => height - bottom - (value / max) * (height - top - bottom);
      let html = `<line x1="${left}" y1="${height - bottom}" x2="${width - right}" y2="${height - bottom}" stroke="#d0d5dd"/>`;
      years.forEach((year, idx) => {
        html += `<text x="${x(idx)}" y="${height - 12}" text-anchor="middle" font-size="12" fill="#667085">${year}</text>`;
      });
      rows.forEach((row, seriesIdx) => {
        const points = years.map((year, idx) => `${x(idx)},${y(row.values[year] || 0)}`).join(" ");
        html += `<polyline fill="none" stroke="${COLORS[seriesIdx]}" stroke-width="3" points="${points}"/>`;
        years.forEach((year, idx) => {
          html += `<circle cx="${x(idx)}" cy="${y(row.values[year] || 0)}" r="4" fill="${COLORS[seriesIdx]}"/>`;
        });
        html += `<text x="${left + seriesIdx * 90}" y="${top - 8}" font-size="12" fill="${COLORS[seriesIdx]}" font-weight="700">${escapeHtml(row.item)}</text>`;
      });
      $(id).innerHTML = html;
    }

    function renderUnitTable() {
      const years = ["2021", "2022", "2023", "2024", "2025", "2026"];
      const prices = Object.fromEntries(DATA.budget.unit_prices.map((r) => [r.item, r.values]));
      const counts = Object.fromEntries(DATA.budget.counts.map((r) => [r.item, r.values]));
      const items = DATA.budget.unit_prices.map((r) => r.item);
      const head = `<thead><tr><th>항목</th>${years.map((y) => `<th>${y.slice(2)} 수량</th>`).join("")}<th>'26 단가</th><th>'26 예산</th></tr></thead>`;
      const body = items.map((item) => {
        const c = counts[item] || {};
        const p = prices[item] || {};
        const budgetEok = ((c["2026"] || 0) * (p["2026"] || 0)) / 100; // 백만원 × 수량 → 억원
        return `<tr><td>${escapeHtml(item)}</td>${years.map((y) => `<td>${nf.format(c[y] || 0)}</td>`).join("")}<td>${nf.format(p["2026"] || 0)}백만원</td><td>${budgetEok.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}억원</td></tr>`;
      }).join("");
      $("unitPriceTable").innerHTML = head + `<tbody>${body}</tbody>`;
    }

    function qtyVsPriceChart(id) {
      const width = 720, height = 250, left = 52, right = 24, top = 18, bottom = 40;
      const innerW = width - left - right, innerH = height - top - bottom;
      const prices = Object.fromEntries(DATA.budget.unit_prices.map((r) => [r.item, r.values["2026"] || 0]));
      const counts = Object.fromEntries(DATA.budget.counts.map((r) => [r.item, r.values["2026"] || 0]));
      const pts = DATA.budget.unit_prices.map((r) => ({ label: r.item, x: counts[r.item] || 0, y: prices[r.item] || 0 })).filter((p) => p.x || p.y);
      const maxX = Math.max(...pts.map((p) => p.x), 1), maxY = Math.max(...pts.map((p) => p.y), 1);
      const X = (v) => left + (v / maxX) * innerW, Y = (v) => height - bottom - (v / maxY) * innerH;
      let s = `<line x1="${left}" y1="${height - bottom}" x2="${width - right}" y2="${height - bottom}" stroke="#d0d5dd"/><line x1="${left}" y1="${top}" x2="${left}" y2="${height - bottom}" stroke="#d0d5dd"/>`;
      s += `<text x="${left}" y="${height - 12}" font-size="11" fill="#98a2b3">0</text><text x="${width - right}" y="${height - 12}" text-anchor="end" font-size="11" fill="#98a2b3">${nf.format(maxX)}개</text>`;
      s += `<text x="${left - 6}" y="${top + 8}" text-anchor="end" font-size="11" fill="#98a2b3">${nf.format(maxY)}</text>`;
      pts.forEach((p, i) => {
        const cx = X(p.x), cy = Y(p.y);
        const flip = cx > width - right - 96;
        const tx = flip ? cx - 9 : cx + 9;
        const anchor = flip ? "end" : "start";
        s += `<circle cx="${cx}" cy="${cy}" r="6" fill="${COLORS[i % COLORS.length]}" opacity="0.85"/>`;
        s += `<text x="${tx}" y="${cy + 4}" text-anchor="${anchor}" font-size="11" fill="#344054">${escapeHtml(p.label)}·${nf.format(p.y)}백만</text>`;
      });
      $(id).innerHTML = s;
    }

    function renderFlowBreakdown() {
      const rows = DATA.flow_breakdown.rows;
      const total = DATA.flow_breakdown.total_won;
      $("flowBreakdown").innerHTML = rows.map((row, idx) => {
        const children = (row.children || []).length
          ? `<br><span class="metric-note">└ ${row.children.map((c) => `${escapeHtml(c.item)} ${won(c.amount_won)}`).join(" · ")}</span>`
          : "";
        return `
        <div class="summary-line">
          <span><i style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${COLORS[idx % COLORS.length]};margin-right:6px"></i>${escapeHtml(row.item)}${children}</span>
          <span class="amount">${billion(row.amount_won)} · ${pct(row.amount_won / total * 100)}</span>
        </div>`;
      }).join("") + `<div class="metric-note">2026 유량 사업 예산 ${billion(total)} 기준 · 편성목별 소계 아래 실제 통계목(품목)을 표기. 예: 인건비 = 기타직보수.</div>`;
    }

    function initStationSelect() {
      $("stationSelect").innerHTML = DATA.stations.map((station) => `<option value="${station.no}">${station.no}. ${escapeHtml(station.name)} · ${escapeHtml(station.region)} · ${won(station.fare)}</option>`).join("");
      ["stationSelect", "staffInput", "visitInput", "dayInput", "laborInput", "vehicleSlotInput", "equipmentLifeInput", "equipmentUseInput", "overheadInput"].forEach((id) => {
        $(id).addEventListener("input", renderStation);
        $(id).addEventListener("change", renderStation);
      });
    }

    function selectedStation() {
      const no = Number($("stationSelect").value || DATA.stations[0].no);
      return DATA.stations.find((station) => station.no === no) || DATA.stations[0];
    }

    const DEFAULT_PARAMS = { staff: 2, visits: 12, days: 1, laborDaily: 250000, vehicleSlots: 22, equipmentLife: 7, equipmentUses: 160, overheadRate: 17 };

    function readParams() {
      return {
        staff: Number($("staffInput").value || 0),
        visits: Number($("visitInput").value || 0),
        days: Number($("dayInput").value || 0),
        laborDaily: Number($("laborInput").value || 0),
        vehicleSlots: Number($("vehicleSlotInput").value || 1),
        equipmentLife: Number($("equipmentLifeInput").value || 1),
        equipmentUses: Number($("equipmentUseInput").value || 1),
        overheadRate: Number($("overheadInput").value || 0),
      };
    }

    function computeCost(station, p) {
      const region = DATA.regions.find((row) => row.region === station.region);
      const labor = p.staff * p.days * p.laborDaily * p.visits;
      const traffic = station.fare * 2 * p.staff * p.visits;
      const vehicle = DATA.summary.avg_vehicle_rent_won / p.vehicleSlots * p.visits;
      const facility = region.facility_per_station_won;
      const equipment = DATA.summary.core_equipment_kit_won / p.equipmentLife / p.equipmentUses * p.visits;
      const direct = labor + traffic + vehicle + facility + equipment;
      const overhead = direct * p.overheadRate / 100;
      const total = direct + overhead;
      return {
        station, region, ...p,
        lines: [
          ["직접인건비", labor, `${p.staff}명 × ${p.days}일 × ${won(p.laborDaily)} × ${p.visits}회`],
          ["교통비", traffic, `${won(station.fare)} × 왕복 × ${p.staff}명 × ${p.visits}회`],
          ["차량 운영비", vehicle, `${won(DATA.summary.avg_vehicle_rent_won)} ÷ ${p.vehicleSlots}지점/월 × ${p.visits}회`],
          ["창고·주차 임차 배부", facility, `${station.region} 연간 임차·주차비 ÷ ${region.stations}개 지점`],
          ["장비 감가상각", equipment, `${won(DATA.summary.core_equipment_kit_won)} ÷ ${p.equipmentLife}년 ÷ ${p.equipmentUses}회 × ${p.visits}회`],
          ["간접비", overhead, `직접비 × ${p.overheadRate}%`],
        ],
        direct, overhead, total,
        businessPerSite: DATA.summary.flow_business_per_site_won,
        unitPrice: DATA.summary.flow_unit_price_won
      };
    }

    function calcStationCost() {
      return computeCost(selectedStation(), readParams());
    }

    function renderStation() {
      const calc = calcStationCost();
      $("stationInfo").innerHTML = `
        <div class="metric-label">선택 지점</div>
        <div class="metric-value">${escapeHtml(calc.station.name)}</div>
        <div class="metric-note">${escapeHtml(calc.station.address)}</div>
        <div class="summary-line"><span>권역</span><span class="amount">${escapeHtml(calc.station.region)}</span></div>
        <div class="summary-line"><span>거점</span><span class="amount">${escapeHtml(calc.station.hub)}</span></div>
        <div class="summary-line"><span>교통수단</span><span class="amount">${escapeHtml(calc.station.mode)}</span></div>
      `;
      $("stationCost").innerHTML = `
        <div class="cond-echo">적용 조건 · ${calc.staff}명 × 연 ${calc.visits}회 × ${calc.days}일 · 인건비 ${won(calc.laborDaily)}/일 · 간접 ${calc.overheadRate}%</div>
        <div class="metric-label">연간 지점 추정 원가</div>
        <div class="metric-value">${billion(calc.total)}</div>
        <div class="metric-note">위 산출 조건이 바뀌면 즉시 재계산됩니다</div>
        <div class="summary-line"><span>직접비</span><span class="amount">${won(calc.direct)}</span></div>
        <div class="summary-line"><span>간접비</span><span class="amount">${won(calc.overhead)}</span></div>
      `;
      const businessRatio = calc.total / calc.businessPerSite * 100;
      const unitRatio = calc.total / calc.unitPrice * 100;
      $("stationCompare").innerHTML = `
        <div class="metric-label">예산 기준 대비</div>
        <div class="metric-value">${pct(businessRatio)}</div>
        <div class="metric-note">유량 사업예산 지점 배부액 대비</div>
        <div class="summary-line"><span>사업 배부 기준</span><span class="amount">${won(calc.businessPerSite)}</span></div>
        <div class="summary-line"><span>84백만원 단가 대비</span><span class="amount">${pct(unitRatio)}</span></div>
      `;
      donutChart(calc.lines.map((line) => ({ label: line[0], value: line[1] })));
      $("costLines").innerHTML = calc.lines.map(([label, value, formula]) => `
        <div class="summary-line"><span>${escapeHtml(label)}<br><span class="metric-note">${escapeHtml(formula)}</span></span><span class="amount">${won(value)}</span></div>
      `).join("");
      renderPumsemCalc();
    }

    function donutChart(rows) {
      const total = rows.reduce((sum, row) => sum + row.value, 0) || 1;
      const cx = 170, cy = 125, r = 78, circumference = 2 * Math.PI * r;
      let offset = 0;
      let svg = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#edf0f5" stroke-width="34"/>`;
      rows.forEach((row, idx) => {
        const dash = row.value / total * circumference;
        svg += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${COLORS[idx % COLORS.length]}" stroke-width="34" stroke-dasharray="${dash} ${circumference - dash}" stroke-dashoffset="${-offset}" transform="rotate(-90 ${cx} ${cy})"/>`;
        offset += dash;
      });
      svg += `<text x="${cx}" y="${cy - 4}" text-anchor="middle" font-size="16" font-weight="800" fill="#17202a">${billion(total)}</text><text x="${cx}" y="${cy + 18}" text-anchor="middle" font-size="12" fill="#667085">연간 추정</text>`;
      rows.forEach((row, idx) => {
        const x = 330, y = 44 + idx * 30;
        svg += `<rect x="${x}" y="${y - 11}" width="12" height="12" rx="3" fill="${COLORS[idx % COLORS.length]}"/><text x="${x + 20}" y="${y}" font-size="13" fill="#344054">${escapeHtml(row.label)}</text><text x="${x + 210}" y="${y}" font-size="13" font-weight="700" fill="#17202a">${pct(row.value / total * 100)}</text>`;
      });
      $("costDonut").innerHTML = svg;
      $("costLegend").innerHTML = rows.map((row, idx) => `<span><i style="background:${COLORS[idx % COLORS.length]}"></i>${escapeHtml(row.label)} ${won(row.value)}</span>`).join("");
    }

    function renderPumsem() {
      const pf = DATA.pumsem_flow;
      const head = `<thead><tr><th>기본업무</th><th>단위</th><th>인·일/단위</th></tr></thead>`;
      const body = pf.rows.map((r) => `<tr><td>${escapeHtml(r.task)}</td><td>${escapeHtml(r.scope)}</td><td>${r.person_days.toFixed(2)}</td></tr>`).join("");
      $("pumsemTable").innerHTML = head + `<tbody>${body}</tbody>`;
    }

    function renderPumsemCalc() {
      const pf = DATA.pumsem_flow;
      const visits = Number($("visitInput").value || 0);
      const laborDaily = Number($("laborInput").value || 0);
      const stationFixed = pf.rows.filter((r) => r.scope === "지점").reduce((s, r) => s + r.person_days, 0);
      const routine = pf.rows.find((r) => r.task === "평·저수 유량측정").person_days;
      const verify = pf.rows.find((r) => r.task === "유량측정성과 검증").person_days;
      const flood = pf.rows.find((r) => r.task.indexOf("홍수") === 0).person_days;
      const perVisit = routine + verify;
      const fieldPd = perVisit * visits;
      const taskPd = stationFixed + fieldPd;
      const line = (label, value, note) => `<div class="summary-line"><span>${label}<br><span class="metric-note">${note}</span></span><span class="amount">${value}</span></div>`;
      $("pumsemCalc").innerHTML =
        `<div class="cond-echo">연간 유량측정 ${visits}회 · 노임 ${won(laborDaily)}/인·일 기준</div>` +
        line("현장 유량측정 투입", `${fieldPd.toFixed(1)} 인·일`, `평·저수 ${perVisit.toFixed(2)}인·일/회 × ${visits}회`) +
        line("과업 전체 투입", `${taskPd.toFixed(1)} 인·일`, `지점 고정 ${stationFixed.toFixed(1)}인·일 + 회 ${perVisit.toFixed(2)}×${visits}`) +
        line("홍수 측정(회당)", `${flood.toFixed(2)} 인·일`, `투입인원 최대치(6명) 산정 근거`) +
        line("품셈기반 인건비(현장)", won(fieldPd * laborDaily), `현장 투입 인·일 × 노임단가`) +
        line("품셈기반 인건비(과업전체)", won(taskPd * laborDaily), `과업 전체 인·일 × 노임단가`) +
        `<div class="metric-note" style="margin-top:8px">계산기의 '직접인건비'(투입인원×투입일 가정)와 품셈 산정치를 비교하는 참고값입니다. 노임단가는 엔지니어링 노임단가(협회 공표)를 적용해야 하며 품셈에는 포함되지 않습니다.</div>`;
    }

    function renderTopFares() {
      const rows = [...DATA.stations].sort((a, b) => b.fare - a.fare).slice(0, 12);
      $("topFareTable").innerHTML = `<thead><tr><th>연번</th><th>관측소</th><th>권역</th><th>편도 교통비</th><th>거점</th><th>주소</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${row.no}</td><td>${escapeHtml(row.name)}</td><td>${escapeHtml(row.region)}</td><td>${won(row.fare)}</td><td>${escapeHtml(row.hub)}</td><td>${escapeHtml(row.address)}</td></tr>`).join("")}</tbody>`;
    }

    function renderRegion() {
      $("regionCards").innerHTML = DATA.regions.map((row, idx) => `
        <div class="callout ${["soft-blue", "soft-teal", "soft-green", "soft-amber"][idx]}">
          <strong>${escapeHtml(row.region)}</strong>
          <div class="summary-line"><span>지점</span><span class="amount">${nf.format(row.stations)}개</span></div>
          <div class="summary-line"><span>평균 편도</span><span class="amount">${won(row.avg_fare)}</span></div>
          <div class="summary-line"><span>시설 배부</span><span class="amount">${won(row.facility_per_station_won)}</span></div>
        </div>
      `).join("");
      barChart("regionFareChart", DATA.regions.map((row) => ({ label: row.region, value: row.avg_fare })), "won");
      barChart("regionFacilityChart", DATA.regions.map((row) => ({ label: row.region, value: row.facility_per_station_won })), "won");
      $("regionTable").innerHTML = `<thead><tr><th>권역</th><th>지점 수</th><th>평균 편도</th><th>최소~최대 편도</th><th>컨테이너 임차</th><th>주차비</th><th>지점 배부</th></tr></thead><tbody>${DATA.regions.map((row) => `<tr><td>${escapeHtml(row.region)}</td><td>${nf.format(row.stations)}개</td><td>${won(row.avg_fare)}</td><td>${won(row.min_fare)} ~ ${won(row.max_fare)}</td><td>${won(row.container_annual_won)}</td><td>${won(row.parking_annual_won)}</td><td>${won(row.facility_per_station_won)}</td></tr>`).join("")}</tbody>`;
    }

    function renderSample() {
      const picks = [["영산강권역", "전라"], ["낙동강권역", "경상"], ["금강권역", "충청"]];
      const samples = picks.map(([region, area]) => {
        const inRegion = DATA.stations.filter((st) => st.region === region && st.fare);
        const station = inRegion.sort((a, b) => b.fare - a.fare)[0];
        return station ? { area, calc: computeCost(station, DEFAULT_PARAMS) } : null;
      }).filter(Boolean);

      $("sampleCards").innerHTML = samples.map((s, idx) => `
        <div class="callout ${["soft-amber", "soft-teal", "soft-green"][idx]}">
          <strong>${escapeHtml(s.area)} · ${escapeHtml(s.calc.station.region)}</strong>
          <div class="metric-value" style="font-size:18px">${escapeHtml(s.calc.station.name)}</div>
          <div class="metric-note">${escapeHtml(s.calc.station.address || "")}</div>
          <div class="summary-line"><span>편도 교통비</span><span class="amount">${won(s.calc.station.fare)}</span></div>
          <div class="summary-line"><span>연간 추정 원가</span><span class="amount">${billion(s.calc.total)}</span></div>
          <div class="summary-line"><span>사업배부 대비</span><span class="amount">${pct(s.calc.total / s.calc.businessPerSite * 100)}</span></div>
        </div>
      `).join("");

      const labels = ["직접인건비", "교통비", "차량 운영비", "창고·주차 임차 배부", "장비 감가상각", "간접비"];
      const head = `<thead><tr><th>항목</th>${samples.map((s) => `<th>${escapeHtml(s.area)}<br><span class="metric-note">${escapeHtml(s.calc.station.name)}</span></th>`).join("")}</tr></thead>`;
      const bodyRows = labels.map((label, li) => `<tr><td>${escapeHtml(label)}</td>${samples.map((s) => `<td>${won(s.calc.lines[li][1])}</td>`).join("")}</tr>`).join("");
      const totalRow = `<tr><td><b>연간 지점 추정 원가</b></td>${samples.map((s) => `<td><b>${won(s.calc.total)}</b></td>`).join("")}</tr>`;
      $("sampleTable").innerHTML = head + `<tbody>${bodyRows}${totalRow}</tbody>`;
    }

    function renderEquipment() {
      $("equipmentKpi").innerHTML = `<div class="metric-label">보유 장비</div><div class="metric-value">${nf.format(DATA.summary.equipment_total)}대</div><div class="metric-note">장비 관련 workbook 기준</div>`;
      $("vehicleKpi").innerHTML = `<div class="metric-label">업무 차량</div><div class="metric-value">${nf.format(DATA.summary.vehicle_count)}대</div><div class="metric-note">월 평균 임차료 ${won(DATA.summary.avg_vehicle_rent_won)}</div>`;
      $("calibrationKpi").innerHTML = `<div class="metric-label">검·교정 연간 비용</div><div class="metric-value">${billion(DATA.equipment.calibration_annual_won)}</div><div class="metric-note">월 검·교정 비용 합계</div>`;
      const rentTotal = Object.values(DATA.rent.container_annual_won).reduce((a, b) => a + b, 0) + Object.values(DATA.rent.parking_annual_won).reduce((a, b) => a + b, 0) + DATA.rent.survey_equipment_rent_won;
      $("rentKpi").innerHTML = `<div class="metric-label">임대·주차·측량 대여</div><div class="metric-value">${billion(rentTotal)}</div><div class="metric-note">2025년 기준 합계</div>`;
      $("equipmentTable").innerHTML = `<thead><tr><th>장비</th><th>보유</th><th>정수 기준</th><th>2027 구매계획</th><th>단가</th></tr></thead><tbody>${DATA.equipment.rows.map((row) => `<tr><td>${escapeHtml(row.name)}</td><td>${nf.format(row.owned)}대</td><td>${escapeHtml(row.standard)}</td><td>${nf.format(row.purchase_plan_2027)}대</td><td>${row.unit_price_won ? won(row.unit_price_won) : "-"}</td></tr>`).join("")}</tbody>`;
      const energyRows = DATA.vehicles.energy_rows.map((row) => `<h3>${escapeHtml(row.item)}</h3>${Object.entries(row.values).map(([month, value]) => `<div class="summary-line"><span>${escapeHtml(month)}</span><span class="amount">${won(value)}</span></div>`).join("")}`).join("");
      const vehicleTypes = DATA.vehicles.type_counts.slice(0, 8).map((row) => `<span class="pill">${escapeHtml(row.type)} ${row.count}대</span>`).join("");
      const ecoTypes = (DATA.vehicles.eco_counts || []).map((row) => `<span class="pill">${escapeHtml(row.type)} ${row.count}대</span>`).join("");
      const grounded = `
        <div class="summary-line"><span>차량 대수</span><span class="amount">${nf.format(DATA.summary.vehicle_count)}대</span></div>
        <div class="summary-line"><span>월 임차료 합계</span><span class="amount">${won(DATA.vehicles.total_monthly_rent_won)}</span></div>
        <div class="summary-line"><span>연 임차료 합계</span><span class="amount">${won(DATA.summary.vehicle_annual_rent_won)}</span></div>
        <div class="summary-line"><span>전기·주유비 (연 환산)</span><span class="amount">${won(DATA.summary.vehicle_energy_annual_won)}</span></div>
        <div class="summary-line"><span><span class="badge data">데이터</span> 차량비 지점 배부<br><span class="metric-note">연 임차료 ÷ 355개 조사지점 · 계산기의 '월 처리 지점 22' 가정과 비교</span></span><span class="amount">${won(DATA.summary.vehicle_rent_per_station_won)}</span></div>
      `;
      $("vehicleOps").innerHTML = `<div class="callout soft-blue"><strong>저공해 구성</strong>${ecoTypes}</div><div style="height:8px"></div><div class="callout soft-teal"><strong>차종</strong>${vehicleTypes}</div><div style="height:10px"></div>${grounded}<div style="height:10px"></div>${energyRows}`;
    }

    function renderSources() {
      $("workbookSources").innerHTML = DATA.sources.workbooks.map((path) => `<li>${escapeHtml(path)}</li>`).join("");
      $("pdfSources").innerHTML = DATA.sources.pdfs.map((path) => `<li>${escapeHtml(path)}</li>`).join("");
    }

    function renderSourceSlots() {
      document.querySelectorAll(".src-slot").forEach((slot) => {
        slot.innerHTML = srcNote(slot.dataset.src);
      });
    }

    function currentExportRows() {
      const calc = calcStationCost();
      const rows = [
        ["구분", "항목", "값", "근거"],
        ["선택 지점", "연번", calc.station.no, calc.station.name],
        ["선택 지점", "권역", calc.station.region, calc.station.address],
        ["선택 지점", "편도 교통비", Math.round(calc.station.fare), calc.station.hub],
        ...calc.lines.map(([label, value, formula]) => ["원가", label, Math.round(value), formula]),
        ["원가", "연간 지점 추정 원가", Math.round(calc.total), "직접비 + 간접비"],
        ["비교", "유량 사업예산 지점 배부액", Math.round(calc.businessPerSite), "2026 유량 사업예산 / 144개소"],
        ["비교", "유량 지점당 단가", Math.round(calc.unitPrice), "84백만원"]
      ];
      DATA.regions.forEach((row) => rows.push(["권역", row.region, row.avg_fare, `지점 ${row.stations}개, 시설 배부 ${row.facility_per_station_won}원`]));
      return rows;
    }

    function downloadCsv() {
      const csv = currentExportRows().map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\n");
      const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
      triggerDownload(blob, "수문조사_원가분석_현재뷰.csv");
    }

    function downloadExcel() {
      const rows = currentExportRows();
      const html = `<html><head><meta charset="utf-8"></head><body><table>${rows.map((row, idx) => `<tr>${row.map((value) => {
        const tag = idx === 0 ? "th" : "td";
        return `<${tag}>${escapeHtml(value)}</${tag}>`;
      }).join("")}</tr>`).join("")}</table></body></html>`;
      const blob = new Blob(["\ufeff" + html], { type: "application/vnd.ms-excel;charset=utf-8" });
      triggerDownload(blob, "수문조사_원가분석_현재뷰.xls");
    }

    function triggerDownload(blob, filename) {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    }

    function bindActions() {
      $("btnCsv").addEventListener("click", downloadCsv);
      $("btnExcel").addEventListener("click", downloadExcel);
      $("btnPrint").addEventListener("click", () => window.print());
    }

    function init() {
      initTabs();
      renderOverview();
      initStationSelect();
      renderPumsem();
      renderStation();
      renderTopFares();
      renderRegion();
      renderSample();
      renderEquipment();
      renderSources();
      renderSourceSlots();
      bindActions();
    }

    init();
  </script>
</body>
</html>
"""


def main() -> None:
    data = build_data()
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    OUTPUT_HTML.write_text(HTML_TEMPLATE.replace("__DATA_JSON__", data_json), encoding="utf-8")
    print(f"Wrote {OUTPUT_HTML}")
    print(
        json.dumps(
            {
                "stations": data["summary"]["station_total"],
                "flow_sites_2026": data["summary"]["flow_sites_2026"],
                "avg_one_way_fare_won": data["summary"]["avg_one_way_fare_won"],
                "equipment_total": data["summary"]["equipment_total"],
                "vehicles": data["summary"]["vehicle_count"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
