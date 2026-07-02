#!/usr/bin/env python3
"""Analyze the defense cost rule PDF against the sample cost workbook.

Outputs are intentionally data-first:
  - parsed legal articles
  - workbook/sheet/domain-table inventory
  - rule-to-Excel mapping candidates
  - a concise Markdown comparison and DDD implementation plan
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "docs" / "원가계산보고서샘플"
OUT_DIR = REPO_ROOT / "data" / "defense_cost_rule_db"
REPORT_PATH = SOURCE_DIR / "방산원가_규칙_PDF_vs_원가계산보고서ver2_DDD_분석.md"


@dataclass
class Marker:
    pos: int
    kind: str
    title: str


def load_importer():
    path = REPO_ROOT / "scripts" / "import_sample_ver1_cost_workbook.py"
    spec = importlib.util.spec_from_file_location("cost_workbook_importer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load importer: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cost_workbook_importer"] = mod
    spec.loader.exec_module(mod)
    return mod


def find_one(patterns: list[str], directory: Path) -> Path:
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(directory.glob(pattern))
    unique = sorted(set(matches), key=lambda p: p.name)
    if not unique:
        raise FileNotFoundError(f"no source file for patterns: {patterns}")
    if len(unique) > 1:
        # Prefer the latest named/legal version when multiple samples match.
        unique = sorted(unique, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    return unique[0]


def clean_text(value: str) -> str:
    value = value.replace("\u00a0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def extract_pdf_text(pdf_path: Path) -> tuple[list[str], str]:
    reader = PdfReader(str(pdf_path))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    return page_texts, "\n".join(page_texts)


def parse_markers(text: str) -> list[Marker]:
    markers: list[Marker] = []
    pattern = re.compile(r"^\s*(제\d+장\s+(?!및\b).+|제\d+절\s+.+)\s*$", re.MULTILINE)
    for match in pattern.finditer(text):
        title = clean_text(match.group(1))
        if "「" in title or len(title) > 80:
            continue
        kind = "chapter" if "장 " in title else "section"
        markers.append(Marker(match.start(), kind, title))
    return markers


def marker_context(markers: list[Marker], pos: int) -> tuple[str, str]:
    chapter = ""
    section = ""
    for marker in markers:
        if marker.pos > pos:
            break
        if marker.kind == "chapter":
            chapter = marker.title
            section = ""
        elif marker.kind == "section":
            section = marker.title
    return chapter, section


def parse_articles(text: str) -> list[dict[str, Any]]:
    markers = parse_markers(text)
    # Captures normal articles such as 제24조(일반관리비의 계산) and deleted ones.
    article_re = re.compile(r"(제\d+조(?:의\d+)?(?:\([^\n)]+\)|\s+삭제))")
    matches = list(article_re.finditer(text))
    articles: list[dict[str, Any]] = []
    supplementary_start = text.find("부칙")
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        heading = clean_text(match.group(1))
        normal = re.match(r"제(?P<num>\d+)조(?P<sub>의\d+)?\((?P<title>[^)]+)\)", heading)
        deleted = re.match(r"제(?P<num>\d+)조(?P<sub>의\d+)?\s+삭제", heading)
        if normal:
            article_no = f"제{normal.group('num')}조{normal.group('sub') or ''}"
            title = normal.group("title")
            deleted_flag = False
        elif deleted:
            article_no = f"제{deleted.group('num')}조{deleted.group('sub') or ''}"
            title = "삭제"
            deleted_flag = True
        else:
            continue
        chapter, section = marker_context(markers, start)
        body = clean_text(text[match.end():end])
        articles.append(
            {
                "article_no": article_no,
                "title": title,
                "chapter": chapter,
                "section": section,
                "is_deleted": deleted_flag,
                "is_supplementary": supplementary_start >= 0 and start > supplementary_start,
                "text": body,
                "char_count": len(body),
                "preview": body[:240],
            }
        )
    return articles


def parse_definitions(article: dict[str, Any]) -> list[dict[str, Any]]:
    if article["article_no"] != "제2조":
        return []
    text = article["text"]
    item_re = re.compile(r"(?:^|\n)(\d+)\.\s+(.+?)(?=\n\d+\.\s+|\Z)", re.DOTALL)
    rows: list[dict[str, Any]] = []
    term_re = re.compile(r"[“\"]([^”\"]+)[”\"]")
    for item in item_re.finditer(text):
        body = clean_text(item.group(2))
        term_match = term_re.search(body)
        rows.append(
            {
                "sort_order": int(item.group(1)),
                "term": term_match.group(1) if term_match else "",
                "definition": body,
            }
        )
    return rows


def workbook_inventory(xlsx_path: Path) -> dict[str, Any]:
    importer = load_importer()
    with zipfile.ZipFile(xlsx_path) as archive:
        sheets = importer.read_sheets(archive)
        return {
            "source_path": str(xlsx_path.relative_to(REPO_ROOT).as_posix()),
            "sheet_count": len(sheets),
            "sheets": [
                {
                    "display_order": sheet.display_order,
                    "name": sheet.name,
                    "role": importer.infer_sheet_role(sheet.name),
                    "path": sheet.path,
                }
                for sheet in sheets
            ],
        }


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def domain_inventory() -> dict[str, Any]:
    base = REPO_ROOT / "data" / "sample_ver1_cost_db" / "ver2"
    tables = load_json(base / "domain_tables.json")
    golden = load_json(base / "golden_value_check.json")
    return {
        "domain_tables_path": str((base / "domain_tables.json").relative_to(REPO_ROOT).as_posix()),
        "golden_check_path": str((base / "golden_value_check.json").relative_to(REPO_ROOT).as_posix()),
        "table_counts": {name: len(table.get("rows", [])) for name, table in tables.items()},
        "golden_checks": golden.get("checks", []),
        "rollup_cells": golden.get("rollup_cells", []),
    }


def article_mapping() -> list[dict[str, Any]]:
    """Initial domain mapping from legal clauses to workbook DB/read-model objects."""
    return [
        {
            "article_no": "제2조",
            "rule_theme": "용어 정의",
            "domain_objects": ["LegalTerm", "CostConcept", "CostCategory"],
            "excel_or_db_targets": ["legal_article_term", "cost_category", "calculation_policy.policy_name"],
            "implementation_status": "seed_candidate",
            "notes": "원가, 제조원가, 총원가, 계산가격, 방산노임단가 등 용어 사전.",
        },
        {
            "article_no": "제3조",
            "rule_theme": "비원가 항목 제외",
            "domain_objects": ["NonCostExclusionPolicy", "CostLineValidation"],
            "excel_or_db_targets": ["cost_line.note", "validation_rule", "calculation_policy"],
            "implementation_status": "todo",
            "notes": "완성과 관련 없는 비용, 비정상 손실, 법정 손금불산입 등 제외 규칙.",
        },
        {
            "article_no": "제6조",
            "rule_theme": "원가 구성요소",
            "domain_objects": ["CostEstimateRevision", "CostCategory", "CostTotalComponent"],
            "excel_or_db_targets": ["원가계산서", "cost_category", "cost_total_component"],
            "implementation_status": "mapped",
            "notes": "제조원가=재료비+노무비+경비, 총원가=제조원가+일반관리비.",
        },
        {
            "article_no": "제7조",
            "rule_theme": "배부기준",
            "domain_objects": ["AllocationBasis", "AllocationPolicy"],
            "excel_or_db_targets": ["rate_rule.condition_json", "sheet_line_projection"],
            "implementation_status": "todo",
            "notes": "간접비 배부 기준과 변경 금지 불변식을 별도 정책으로 관리.",
        },
        {
            "article_no": "제11조",
            "rule_theme": "제품 단위당 재료 소요량",
            "domain_objects": ["QuantityBasis", "BillOfMaterialLine"],
            "excel_or_db_targets": ["내역서.quantity", "unit_cost_component.quantity"],
            "implementation_status": "mapped",
            "notes": "수량 산출 근거를 단가/금액 계산과 분리해 evidence_ref로 추적.",
        },
        {
            "article_no": "제15조",
            "rule_theme": "재료비 분류",
            "domain_objects": ["MaterialCost", "CostCategory"],
            "excel_or_db_targets": ["cost_line.material_*", "unit_cost_component.material_*", "원가계산서!E7:E9"],
            "implementation_status": "mapped",
            "notes": "직접재료비와 간접재료비 구분.",
        },
        {
            "article_no": "제16조",
            "rule_theme": "노무비 분류",
            "domain_objects": ["LaborCost", "LaborRate"],
            "excel_or_db_targets": ["cost_line.labor_*", "간노비", "원가계산서!E10:E12"],
            "implementation_status": "mapped",
            "notes": "직접노무비와 간접노무비 구분. 방산노임단가 출처는 reference table 필요.",
        },
        {
            "article_no": "제17조",
            "rule_theme": "경비 분류",
            "domain_objects": ["ExpenseCost", "IndirectExpenseCharge"],
            "excel_or_db_targets": ["cost_line.expense_*", "경비/보험료 시트", "원가계산서!E13:E30"],
            "implementation_status": "mapped",
            "notes": "직접경비와 간접경비, 보험료/안전관리비 등 세부 비목 연결.",
        },
        {
            "article_no": "제18조",
            "rule_theme": "일반관리비 정의",
            "domain_objects": ["GeneralAdminCost"],
            "excel_or_db_targets": ["일반", "일반비율", "원가계산서!E32"],
            "implementation_status": "mapped",
            "notes": "정의와 제외 항목을 Article 제24조 계산 정책과 연결.",
        },
        {
            "article_no": "제19조",
            "rule_theme": "이윤 정의",
            "domain_objects": ["Profit"],
            "excel_or_db_targets": ["이윤", "이윤비율", "원가계산서!E33"],
            "implementation_status": "mapped",
            "notes": "방산 이윤산정기준을 별도 RuleSet으로 관리.",
        },
        {
            "article_no": "제20조",
            "rule_theme": "직접재료비 계산",
            "domain_objects": ["MaterialCostCalculator", "ReferencePrice"],
            "excel_or_db_targets": ["단가대비표", "내역서", "reference_price_*", "applied_price"],
            "implementation_status": "mapped",
            "notes": "소요량 * 단위당 가격. 수입재료/구입재료 가격정책 분기 필요.",
        },
        {
            "article_no": "제21조",
            "rule_theme": "직접노무비 계산",
            "domain_objects": ["LaborCostCalculator"],
            "excel_or_db_targets": ["unit_cost_component.labor_*", "rate_rule_set"],
            "implementation_status": "partial",
            "notes": "방산노임단가 * 노무량. sample ver2는 노무 금액 일부를 단가표 구조로 보유.",
        },
        {
            "article_no": "제22조",
            "rule_theme": "직접경비 계산",
            "domain_objects": ["DirectExpenseCalculator"],
            "excel_or_db_targets": ["cost_line.expense_*", "unit_cost_component.expense_*"],
            "implementation_status": "mapped",
            "notes": "실제 발생 금액 기준. 증빙/산출기준 링크가 필요.",
        },
        {
            "article_no": "제23조",
            "rule_theme": "제조간접비 계산",
            "domain_objects": ["IndirectCostCalculator", "RateRule"],
            "excel_or_db_targets": ["indirect_cost_charge", "rate_rule", "원가계산서!E13:E30"],
            "implementation_status": "mapped",
            "notes": "간접재료/간접노무/간접경비율을 rate_rule로 표현.",
        },
        {
            "article_no": "제24조",
            "rule_theme": "일반관리비 계산",
            "domain_objects": ["GeneralAdminCalculator"],
            "excel_or_db_targets": ["rate_rule", "indirect_cost_charge", "원가계산서!E32"],
            "implementation_status": "mapped",
            "notes": "방산 규칙은 관급재료비 포함 제조원가 기준. sample은 예정가격 기준 8%라 차이 표시 필요.",
        },
        {
            "article_no": "제25조",
            "rule_theme": "일반관리비율 산정",
            "domain_objects": ["RateRuleSet"],
            "excel_or_db_targets": ["일반비율", "rate_rule_set.source_ref"],
            "implementation_status": "todo",
            "notes": "과거 2년 이상 실적치와 고시/기관 기준을 versioned rate로 관리.",
        },
        {
            "article_no": "제26조",
            "rule_theme": "이윤 계산",
            "domain_objects": ["ProfitCalculator", "ProfitRuleSet"],
            "excel_or_db_targets": ["이윤비율", "rate_rule", "원가계산서!E33"],
            "implementation_status": "mapped",
            "notes": "sample은 15% 고정식, 방산은 별도 이윤산정기준을 참조.",
        },
        {
            "article_no": "제28조",
            "rule_theme": "정산원가 계산",
            "domain_objects": ["SettlementCostRevision", "EvidenceSubmission"],
            "excel_or_db_targets": ["cost_estimate_revision.calculation_status", "evidence_ref"],
            "implementation_status": "todo",
            "notes": "개산원가/정산원가 revision을 분리할 필요가 있음.",
        },
        {
            "article_no": "제29조",
            "rule_theme": "용역원가 구성요소",
            "domain_objects": ["ServiceCostEstimate"],
            "excel_or_db_targets": ["future_service_cost_tables"],
            "implementation_status": "out_of_current_workbook_scope",
            "notes": "현재 workbook은 제조/공사형 샘플이라 용역원가 컨텍스트는 별도 확장.",
        },
        {
            "article_no": "제32조",
            "rule_theme": "용역 일반관리비 및 이윤",
            "domain_objects": ["ServiceGeneralAdminCalculator", "ServiceProfitCalculator"],
            "excel_or_db_targets": ["future_service_rate_rule"],
            "implementation_status": "out_of_current_workbook_scope",
            "notes": "노무비+경비 기준 일반관리비, 별도 율 상한/산정근거 필요.",
        },
        {
            "article_no": "제35조",
            "rule_theme": "구분회계/보고서 제출",
            "domain_objects": ["AccountingEvidence", "ComplianceReport"],
            "excel_or_db_targets": ["source_document", "evidence_ref"],
            "implementation_status": "todo",
            "notes": "계산 자체보다 감사/증빙 자료 관리 컨텍스트.",
        },
    ]


def keyword_counts(text: str) -> dict[str, int]:
    keywords = [
        "재료비",
        "노무비",
        "경비",
        "일반관리비",
        "이윤",
        "총원가",
        "제조원가",
        "용역원가",
        "계산가격",
        "관급재료비",
        "배부",
        "비원가",
    ]
    return {keyword: text.count(keyword) for keyword in keywords}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_report(comparison: dict[str, Any], mapping: list[dict[str, Any]]) -> str:
    pdf = comparison["pdf"]
    workbook = comparison["workbook"]
    domain = comparison["domain"]
    checks = domain.get("golden_checks", [])
    total_check = next((c for c in checks if c.get("cell") == "원가계산서!E34"), {})
    result_check = next((c for c in checks if c.get("cell") == "결과!J10"), {})
    mapped = [m for m in mapping if m["implementation_status"] in {"mapped", "partial", "seed_candidate"}]
    todo = [m for m in mapping if m["implementation_status"] == "todo"]

    sheet_rows = "\n".join(
        f"| {s['display_order']} | {s['name']} | `{s['role']}` |"
        for s in workbook["sheets"]
    )
    table_counts = "\n".join(
        f"| `{name}` | {count} |" for name, count in sorted(domain["table_counts"].items())
    )
    mapping_rows = "\n".join(
        f"| {m['article_no']} | {m['rule_theme']} | {', '.join(m['domain_objects'])} | {', '.join(m['excel_or_db_targets'])} | `{m['implementation_status']}` |"
        for m in mapping
    )

    return f"""# 방산원가 규칙 PDF vs 원가계산보고서 ver2 분석 및 DDD 실행계획

## 1. 자료 성격 비교

### PDF

- 파일: `{pdf['source_path']}`
- 문서: 방산원가대상물자의 원가계산에 관한 규칙
- 시행/개정: 2026-01-30, 국방부령 제1202호
- 페이지: {pdf['page_count']}쪽
- 추출 조문: {pdf['article_count']}개
- 핵심 키워드 빈도: {', '.join(f'{k} {v}' for k, v in pdf['keyword_counts'].items())}

### Excel

- 파일: `{workbook['source_path']}`
- 시트: {workbook['sheet_count']}개
- 기존 DB 추출: `{domain['domain_tables_path']}`
- 검증: `원가계산서!E34` = {total_check.get('excel_cached_value', 'n/a'):,} / `결과!J10` = {result_check.get('excel_cached_value', 'n/a'):,}
- DB 후보값과 Excel 캐시값 차이: {total_check.get('difference', 'n/a')}원

| 순서 | 시트 | 역할 |
|---:|---|---|
{sheet_rows}

## 2. 같은 점

- 둘 다 원가를 `재료비`, `노무비`, `경비`, `일반관리비`, `이윤`의 계산 체계로 다룬다.
- 둘 다 수량, 단가, 비율, 배부 기준, 증빙 근거가 계산의 핵심 변수다.
- Excel의 `cost_line`, `rate_rule`, `indirect_cost_charge`, `cost_total_component` 구조는 PDF의 조문을 계산 정책으로 승격할 수 있는 뼈대를 이미 갖고 있다.
- ver2 샘플은 `단가대비표 -> 일위대가표 -> 내역서 -> 집계표 -> 원가계산서 -> 결과` 흐름이 DB 계산값과 일치한다.

## 3. 다른 점

- PDF는 법령/규칙이다. 금액, 품목, 업체 견적, 시트 수식 값은 없고 "무엇을 어떻게 계산해야 하는가"를 정의한다.
- Excel은 특정 산출 예시다. 품목, 수량, 단가, 적용 비율, Excel 수식과 표시 양식을 가진 실행 인스턴스다.
- PDF는 방산 특화 항목을 포함한다. 예: 관급재료비, 수입품, 정산원가, 구분회계, 원가정보, 방산 연구개발 보전.
- Excel ver2의 산정기준은 예정가격작성기준/조달청 기준을 많이 사용한다. 방산 규칙을 적용하려면 일반관리비/이윤/관급재료비 포함 여부를 `RuleSet`으로 분리해야 한다.
- PDF에는 용역원가 장이 있지만 현재 Excel은 제조/공사형 원가계산서 구조에 가깝다. 용역 컨텍스트는 별도 Aggregate로 확장하는 편이 안전하다.

## 4. 기존 DB 테이블 추출 현황

| 테이블 | 행 수 |
|---|---:|
{table_counts}

## 5. 조문 -> Excel/DB 매핑 초안

| 조문 | 규칙 주제 | DDD 객체 | Excel/DB 대상 | 상태 |
|---|---|---|---|---|
{mapping_rows}

## 6. DDD 처리 플랜

### Bounded Context

- `LegalRuleContext`: PDF 원문, 조문, 용어, 조문별 계산정책 후보를 관리한다.
- `CostEstimateContext`: 견적/원가계산 revision, 원가 라인, 금액 집계를 관리한다.
- `ReferencePriceContext`: 단가대비표, 견적/조사가격, 적용단가와 기준일을 관리한다.
- `CalculationPolicyContext`: Excel 수식과 DB 계산식을 versioned policy로 관리한다.
- `WorkbookProjectionContext`: Excel 시트/셀/행 표시 구조를 read model로 보존한다.
- `VerificationContext`: Excel 캐시값, DB 재계산값, 조문 근거, 차이를 검증한다.

### 핵심 Aggregate

- `RuleDocument`: 법령 PDF 1개. 시행일, 법령번호, 원문 파일, checksum을 가진다.
- `LegalArticle`: 조문 1개. 장/절/조문번호/제목/본문/삭제여부/시행상태를 가진다.
- `CostEstimate`: 하나의 원가계산 업무 루트.
- `CostEstimateRevision`: 특정 입력 파일과 규칙 세트로 계산한 revision.
- `CostLine`: 내역서/일위대가/집계표의 canonical 원가 라인.
- `RateRuleSet`: 특정 기준일의 일반관리비, 이윤, 보험료, 간접비율 묶음.
- `CalculationPolicy`: `quantity * unitPrice`, `floor(base * rate)`, `sum(children)` 같은 계산 규칙의 버전.

### 함수 처리

- `resolveCostCategory(line, legalBasis)`: 재료비/노무비/경비/일반관리비/이윤 분류.
- `calculateDirectMaterial(quantity, unitPrice, residualDeductionPolicy)`: 제20조 직접재료비.
- `calculateDirectLabor(laborRate, laborHours, standardLaborPolicy)`: 제21조 직접노무비.
- `calculateDirectExpense(actualAmount, evidenceRef)`: 제22조 직접경비.
- `calculateIndirectCost(baseAmount, rateRule, allocationBasis)`: 제23조 제조간접비.
- `calculateGeneralAdmin(manufacturingCost, governmentFurnishedMaterialPolicy, rateRule)`: 제24조 일반관리비.
- `calculateProfit(baseAmount, profitRuleSet)`: 제26조 이윤.
- `verifyAgainstWorkbook(cellAddress, excelCachedAmount, dbCalculatedAmount, legalArticleRefs)`: Excel/DB/조문 삼각 검증.

### 변수 처리

- 금액: `Money(amount, currency='KRW', scale=0)`로 원 단위 정수 처리.
- 수량: `Quantity(value, unit, precision)`로 품목 단위와 소수 정밀도를 함께 보존.
- 비율: `Rate(percent, basis, effectiveDate, sourceRef)`로 출처/기준일을 반드시 연결.
- 조문 근거: `LegalBasis(documentId, articleNo, paragraphNo, itemNo)`를 모든 정책에 연결.
- 반올림: `RoundingRule.TRUNC_0`, `FLOOR_0`, `ROUND_HALF_UP`처럼 Excel 함수와 DB 구현을 분리.
- 원본 추적: `sourceWorkbookPath`, `sourceSheetName`, `sourceCellAddress`, `sourceFormula`를 projection에 보존.

## 7. 이슈 실행 순서

- `DCR-01`: PDF/Excel 자료 구조 비교 및 차이 분석. 완료.
- `DCR-02`: PDF 조문 JSON seed 생성. 완료.
- `DCR-03`: 법령 조문 DB 스키마 초안 작성. 완료.
- `DCR-04`: 조문 -> Excel/DB 매핑표 작성. 완료.
- `DCR-05`: `calculation_policy`에 조문 근거/RuleSet 연결 seed와 검증. 완료.
- `DCR-06`: 별도 HTML에 조문 근거와 계산 검증 표시. 완료.
"""


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = find_one(["*20260130*.pdf", "*1202*.pdf"], SOURCE_DIR)
    xlsx_path = find_one(["*ver2*.xlsx*"], SOURCE_DIR)

    page_texts, full_text = extract_pdf_text(pdf_path)
    articles = parse_articles(full_text)
    definitions = []
    for article in articles:
        definitions.extend(parse_definitions(article))

    mapping = article_mapping()
    workbook = workbook_inventory(xlsx_path)
    domain = domain_inventory()
    pdf = {
        "source_path": str(pdf_path.relative_to(REPO_ROOT).as_posix()),
        "page_count": len(page_texts),
        "article_count": len(articles),
        "definition_count": len(definitions),
        "keyword_counts": keyword_counts(full_text),
    }
    comparison = {
        "pdf": pdf,
        "workbook": workbook,
        "domain": domain,
        "same": [
            "원가 구성요소와 비목 체계가 겹친다.",
            "수량, 단가, 비율, 배부 기준이 계산 변수의 중심이다.",
            "기존 ver2 DB는 조문 기반 CalculationPolicy를 연결할 수 있는 구조다.",
        ],
        "different": [
            "PDF는 규칙 원천이고 Excel은 특정 계산 인스턴스다.",
            "PDF는 방산 특화 개념(관급재료비, 정산원가, 원가정보)을 포함한다.",
            "Excel ver2는 예정가격작성기준/조달청 기준을 섞어 쓰므로 RuleSet 분리가 필요하다.",
        ],
    }

    write_json(OUT_DIR / "legal_articles.json", {"articles": articles, "definitions": definitions})
    write_json(OUT_DIR / "article_excel_mapping.json", {"mappings": mapping})
    write_json(OUT_DIR / "source_comparison.json", comparison)
    REPORT_PATH.write_text(render_report(comparison, mapping), encoding="utf-8")

    print(f"wrote {OUT_DIR / 'legal_articles.json'}")
    print(f"wrote {OUT_DIR / 'article_excel_mapping.json'}")
    print(f"wrote {OUT_DIR / 'source_comparison.json'}")
    print(f"wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
