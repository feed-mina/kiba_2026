#!/usr/bin/env python3
"""Build a static HTML view for the defense cost rule DB mapping."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "defense_cost_rule_db"
OUT_PATH = REPO_ROOT / "docs" / "원가계산보고서샘플" / "방산원가_조문_DB_뷰.html"


def load_json(name: str) -> dict[str, Any]:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def status_class(status: str) -> str:
    if status in {"mapped", "done", "seed_candidate"}:
        return "ok"
    if status in {"partial", "active"}:
        return "warn"
    if status.startswith("out_of"):
        return "muted"
    return "todo"


def render_badge(text: str, cls: str = "") -> str:
    return f'<span class="badge {esc(cls)}">{esc(text)}</span>'


def render_sheet_table(workbook: dict[str, Any]) -> str:
    rows = []
    for sheet in workbook["sheets"]:
        rows.append(
            "<tr>"
            f"<td>{sheet['display_order']}</td>"
            f"<td>{esc(sheet['name'])}</td>"
            f"<td><code>{esc(sheet['role'])}</code></td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_mapping_table(mappings: list[dict[str, Any]]) -> str:
    rows = []
    for row in mappings:
        cls = status_class(row["implementation_status"])
        rows.append(
            "<tr>"
            f"<td class='nowrap'>{esc(row['article_no'])}</td>"
            f"<td>{esc(row['rule_theme'])}</td>"
            f"<td>{esc(', '.join(row['domain_objects']))}</td>"
            f"<td>{esc(', '.join(row['excel_or_db_targets']))}</td>"
            f"<td>{render_badge(row['implementation_status'], cls)}</td>"
            f"<td>{esc(row['notes'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_policy_links(seed: dict[str, Any]) -> str:
    rows = []
    for row in seed["links"]:
        rows.append(
            "<tr>"
            f"<td><code>{esc(row['source_policy_code'])}</code></td>"
            f"<td>{esc(row['article_no'])}</td>"
            f"<td><code>{esc(row['legal_policy_code'])}</code></td>"
            f"<td>{esc(row['excel_formula_template'])}</td>"
            f"<td>{esc(row['example'])}</td>"
            f"<td>{esc(', '.join(row['required_variables']))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_skipped(seed: dict[str, Any]) -> str:
    rows = []
    for row in seed["skipped"]:
        rows.append(
            "<tr>"
            f"<td><code>{esc(row['source_policy_code'])}</code></td>"
            f"<td>{esc(row['excel_formula_template'])}</td>"
            f"<td>{esc(row['example'])}</td>"
            f"<td>{esc(row['reason'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_article_list(articles: list[dict[str, Any]]) -> str:
    rows = []
    for row in articles:
        if row["is_deleted"]:
            cls = "muted"
        elif row["is_supplementary"]:
            cls = "warn"
        else:
            cls = "ok"
        rows.append(
            "<tr>"
            f"<td class='nowrap'>{esc(row['article_no'])}</td>"
            f"<td>{esc(row['title'])}</td>"
            f"<td>{esc(row['chapter'])}</td>"
            f"<td>{esc(row['section'])}</td>"
            f"<td>{render_badge('삭제' if row['is_deleted'] else ('부칙' if row['is_supplementary'] else '본문'), cls)}</td>"
            f"<td>{esc(row['preview'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_html() -> str:
    comparison = load_json("source_comparison.json")
    articles = load_json("legal_articles.json")
    mappings = load_json("article_excel_mapping.json")["mappings"]
    links = load_json("policy_article_links.json")

    pdf = comparison["pdf"]
    workbook = comparison["workbook"]
    domain = comparison["domain"]
    checks = domain.get("golden_checks", [])
    total = next((c for c in checks if c.get("cell") == "원가계산서!E34"), {})
    result = next((c for c in checks if c.get("cell") == "결과!J10"), {})
    mapped_count = sum(1 for row in mappings if row["implementation_status"] in {"mapped", "partial", "seed_candidate"})
    todo_count = sum(1 for row in mappings if row["implementation_status"] == "todo")

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>방산원가 조문 DB 뷰</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #1f2933;
      --muted: #64748b;
      --line: #d8dee8;
      --head: #e9eef6;
      --ok: #0f766e;
      --warn: #a16207;
      --todo: #b42318;
      --blue: #1d4ed8;
      --violet: #6d28d9;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", "Noto Sans KR", Arial, sans-serif;
      line-height: 1.5;
    }}
    header {{
      padding: 22px 28px 16px;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 0 0 8px; font-size: 24px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; }}
    h3 {{ margin: 0 0 8px; font-size: 15px; }}
    .sub {{ color: var(--muted); font-size: 14px; }}
    main {{ padding: 20px 28px 34px; }}
    .grid {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .span3 {{ grid-column: span 3; }}
    .span4 {{ grid-column: span 4; }}
    .span6 {{ grid-column: span 6; }}
    .span8 {{ grid-column: span 8; }}
    .span12 {{ grid-column: span 12; }}
    .metric {{ font-size: 26px; font-weight: 800; margin-top: 4px; }}
    .label {{ color: var(--muted); font-size: 13px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 9px 10px; text-align: left; vertical-align: top; }}
    th {{ background: var(--head); color: #334155; font-weight: 700; position: sticky; top: 0; }}
    code {{ background: #eef2f7; border: 1px solid #dde4ef; border-radius: 4px; padding: 1px 4px; }}
    .table-wrap {{ overflow: auto; max-height: 520px; border: 1px solid var(--line); border-radius: 8px; }}
    .badge {{ display: inline-block; border-radius: 999px; padding: 3px 8px; font-size: 12px; border: 1px solid var(--line); background: #f8fafc; white-space: nowrap; }}
    .badge.ok {{ color: var(--ok); border-color: #99d4cd; background: #ecfdf5; }}
    .badge.warn {{ color: var(--warn); border-color: #f3d37a; background: #fffbeb; }}
    .badge.todo {{ color: var(--todo); border-color: #f5b5ae; background: #fef3f2; }}
    .badge.muted {{ color: var(--muted); background: #f1f5f9; }}
    .nowrap {{ white-space: nowrap; }}
    .callout {{ border-left: 4px solid var(--blue); padding: 10px 12px; background: #eff6ff; color: #1e3a8a; border-radius: 6px; }}
    .callout.warn {{ border-left-color: var(--warn); background: #fffbeb; color: #78350f; }}
    ul {{ margin: 8px 0 0 18px; padding: 0; }}
    @media (max-width: 980px) {{
      main, header {{ padding-left: 14px; padding-right: 14px; }}
      .span3, .span4, .span6, .span8, .span12 {{ grid-column: span 12; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>방산원가 조문 DB 뷰</h1>
    <div class="sub">PDF 법령 조문, Excel ver2 시트, 기존 원가계산 DB 정책을 연결한 작업용 뷰</div>
  </header>
  <main>
    <section class="grid">
      <div class="panel span3">
        <div class="label">PDF 페이지</div>
        <div class="metric">{pdf['page_count']}</div>
      </div>
      <div class="panel span3">
        <div class="label">추출 조문</div>
        <div class="metric">{pdf['article_count']}</div>
      </div>
      <div class="panel span3">
        <div class="label">Excel 시트</div>
        <div class="metric">{workbook['sheet_count']}</div>
      </div>
      <div class="panel span3">
        <div class="label">정책 링크</div>
        <div class="metric">{len(links['links'])}/{len(links['links']) + len(links['skipped'])}</div>
      </div>

      <div class="panel span6">
        <h2>검증 요약</h2>
        <div class="callout">
          <strong>원가계산서!E34</strong>: {esc(total.get('excel_cached_value'))} /
          <strong>결과!J10</strong>: {esc(result.get('excel_cached_value'))} /
          DB 후보값 차이 {esc(total.get('difference'))}원
        </div>
      </div>
      <div class="panel span6">
        <h2>매핑 상태</h2>
        <div>{render_badge(f'직접/부분/seed {mapped_count}', 'ok')} {render_badge(f'todo {todo_count}', 'todo')} {render_badge(f'표시/세금 제외 {len(links["skipped"])}', 'muted')}</div>
        <div class="callout warn" style="margin-top:10px;">Excel ver2는 예정가격작성기준/조달청 기준을 포함하므로 방산 규칙 적용 시 RuleSet 분기가 필요합니다.</div>
      </div>

      <div class="panel span4">
        <h2>함수 처리</h2>
        <ul>
          <li><code>calculateDirectMaterial(quantity, unitPrice, residualDeductionPolicy)</code></li>
          <li><code>calculateIndirectCost(baseAmount, rateRule, allocationBasis)</code></li>
          <li><code>calculateGeneralAdmin(manufacturingCost, gfmPolicy, rateRule)</code></li>
          <li><code>calculateProfit(baseAmount, profitRuleSet)</code></li>
        </ul>
      </div>
      <div class="panel span4">
        <h2>변수 처리</h2>
        <ul>
          <li><code>Money</code>: 원 단위 금액</li>
          <li><code>Quantity</code>: 단위와 정밀도 포함</li>
          <li><code>Rate</code>: 기준일과 출처 포함</li>
          <li><code>LegalBasis</code>: 문서/조문/항/호 연결</li>
        </ul>
      </div>
      <div class="panel span4">
        <h2>Issue 상태</h2>
        <ul>
          <li>DCR-01, DCR-02, DCR-03, DCR-04 완료</li>
          <li>DCR-05 정책 링크 seed 생성</li>
          <li>DCR-06 정적 HTML 뷰 생성</li>
        </ul>
      </div>

      <div class="panel span12">
        <h2>조문 -> Excel/DB 매핑</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>조문</th><th>주제</th><th>DDD 객체</th><th>Excel/DB 대상</th><th>상태</th><th>메모</th></tr></thead>
            <tbody>{render_mapping_table(mappings)}</tbody>
          </table>
        </div>
      </div>

      <div class="panel span12">
        <h2>계산정책 -> 조문 링크</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>기존 정책</th><th>조문</th><th>법령 정책 코드</th><th>수식 템플릿</th><th>예시</th><th>필수 변수</th></tr></thead>
            <tbody>{render_policy_links(links)}</tbody>
          </table>
        </div>
      </div>

      <div class="panel span6">
        <h2>표시/세금 정책으로 분리</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>정책</th><th>수식 템플릿</th><th>예시</th><th>분리 이유</th></tr></thead>
            <tbody>{render_skipped(links)}</tbody>
          </table>
        </div>
      </div>
      <div class="panel span6">
        <h2>Excel 시트 역할</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>순서</th><th>시트</th><th>역할</th></tr></thead>
            <tbody>{render_sheet_table(workbook)}</tbody>
          </table>
        </div>
      </div>

      <div class="panel span12">
        <h2>추출 조문 목록</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>조문</th><th>제목</th><th>장</th><th>절</th><th>구분</th><th>미리보기</th></tr></thead>
            <tbody>{render_article_list(articles['articles'])}</tbody>
          </table>
        </div>
      </div>
    </section>
  </main>
</body>
</html>
"""


def main() -> int:
    OUT_PATH.write_text(render_html(), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
