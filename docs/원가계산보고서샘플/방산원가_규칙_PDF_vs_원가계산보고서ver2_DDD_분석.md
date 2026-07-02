# 방산원가 규칙 PDF vs 원가계산보고서 ver2 분석 및 DDD 실행계획

## 1. 자료 성격 비교

### PDF

- 파일: `docs/원가계산보고서샘플/방산원가대상물자의 원가계산에 관한 규칙(국방부령)(제01202호)(20260130).pdf`
- 문서: 방산원가대상물자의 원가계산에 관한 규칙
- 시행/개정: 2026-01-30, 국방부령 제1202호
- 페이지: 12쪽
- 추출 조문: 53개
- 핵심 키워드 빈도: 재료비 40, 노무비 31, 경비 34, 일반관리비 33, 이윤 19, 총원가 4, 제조원가 15, 용역원가 4, 계산가격 5, 관급재료비 7, 배부 7, 비원가 2

### Excel

- 파일: `docs/원가계산보고서샘플/(E)sample_원가계산보고서ver2.xlsx.xlsx`
- 시트: 27개
- 기존 DB 추출: `data/sample_ver1_cost_db/ver2/domain_tables.json`
- 검증: `원가계산서!E34` = 109,104,460 / `결과!J10` = 109,104,460
- DB 후보값과 Excel 캐시값 차이: 0원

| 순서 | 시트 | 역할 |
|---:|---|---|
| 1 | 결과 | `result` |
| 2 | 산정기준 | `basis` |
| 3 | 원가계산서 | `cost_statement` |
| 4 | 집계표 | `summary` |
| 5 | 내역서 | `detail` |
| 6 | 일위대가목록 | `unit_price_list` |
| 7 | 일위대가표 | `unit_price_detail` |
| 8 | 단가대비표 | `price_comparison` |
| 9 | 간노비 | `indirect_labor_rate` |
| 10 | 경비 | `expense` |
| 11 | 산재 | `insurance_rate` |
| 12 | 고용 | `insurance_rate` |
| 13 | 건강 | `insurance_rate` |
| 14 | 연금 | `insurance_rate` |
| 15 | 장기 | `insurance_rate` |
| 16 | 석면 | `insurance_rate` |
| 17 | 임금 | `insurance_rate` |
| 18 | 퇴공 | `insurance_rate` |
| 19 | 안전 | `safety_rate` |
| 20 | 일반 | `general_admin` |
| 21 | 일반비율 | `general_admin_rate` |
| 22 | 이윤 | `profit` |
| 23 | 이윤비율 | `profit_rate` |
| 24 | 참고 | `support` |
| 25 | 참고 (4) | `support` |
| 26 | 참고 (2) | `support` |
| 27 | 참고 (3) | `support` |

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
| `applied_price` | 57 |
| `calculated_value_snapshot` | 24 |
| `calculation_policy` | 11 |
| `cost_estimate` | 1 |
| `cost_estimate_revision` | 1 |
| `cost_line` | 57 |
| `indirect_cost_charge` | 14 |
| `price_comparison` | 57 |
| `rate_rule` | 14 |
| `rate_rule_set` | 1 |
| `reference_price_item` | 57 |
| `reference_price_quote` | 79 |
| `unit_cost_component` | 15 |
| `unit_cost_item` | 4 |

## 5. 조문 -> Excel/DB 매핑 초안

| 조문 | 규칙 주제 | DDD 객체 | Excel/DB 대상 | 상태 |
|---|---|---|---|---|
| 제2조 | 용어 정의 | LegalTerm, CostConcept, CostCategory | legal_article_term, cost_category, calculation_policy.policy_name | `seed_candidate` |
| 제3조 | 비원가 항목 제외 | NonCostExclusionPolicy, CostLineValidation | cost_line.note, validation_rule, calculation_policy | `todo` |
| 제6조 | 원가 구성요소 | CostEstimateRevision, CostCategory, CostTotalComponent | 원가계산서, cost_category, cost_total_component | `mapped` |
| 제7조 | 배부기준 | AllocationBasis, AllocationPolicy | rate_rule.condition_json, sheet_line_projection | `todo` |
| 제11조 | 제품 단위당 재료 소요량 | QuantityBasis, BillOfMaterialLine | 내역서.quantity, unit_cost_component.quantity | `mapped` |
| 제15조 | 재료비 분류 | MaterialCost, CostCategory | cost_line.material_*, unit_cost_component.material_*, 원가계산서!E7:E9 | `mapped` |
| 제16조 | 노무비 분류 | LaborCost, LaborRate | cost_line.labor_*, 간노비, 원가계산서!E10:E12 | `mapped` |
| 제17조 | 경비 분류 | ExpenseCost, IndirectExpenseCharge | cost_line.expense_*, 경비/보험료 시트, 원가계산서!E13:E30 | `mapped` |
| 제18조 | 일반관리비 정의 | GeneralAdminCost | 일반, 일반비율, 원가계산서!E32 | `mapped` |
| 제19조 | 이윤 정의 | Profit | 이윤, 이윤비율, 원가계산서!E33 | `mapped` |
| 제20조 | 직접재료비 계산 | MaterialCostCalculator, ReferencePrice | 단가대비표, 내역서, reference_price_*, applied_price | `mapped` |
| 제21조 | 직접노무비 계산 | LaborCostCalculator | unit_cost_component.labor_*, rate_rule_set | `partial` |
| 제22조 | 직접경비 계산 | DirectExpenseCalculator | cost_line.expense_*, unit_cost_component.expense_* | `mapped` |
| 제23조 | 제조간접비 계산 | IndirectCostCalculator, RateRule | indirect_cost_charge, rate_rule, 원가계산서!E13:E30 | `mapped` |
| 제24조 | 일반관리비 계산 | GeneralAdminCalculator | rate_rule, indirect_cost_charge, 원가계산서!E32 | `mapped` |
| 제25조 | 일반관리비율 산정 | RateRuleSet | 일반비율, rate_rule_set.source_ref | `todo` |
| 제26조 | 이윤 계산 | ProfitCalculator, ProfitRuleSet | 이윤비율, rate_rule, 원가계산서!E33 | `mapped` |
| 제28조 | 정산원가 계산 | SettlementCostRevision, EvidenceSubmission | cost_estimate_revision.calculation_status, evidence_ref | `todo` |
| 제29조 | 용역원가 구성요소 | ServiceCostEstimate | future_service_cost_tables | `out_of_current_workbook_scope` |
| 제32조 | 용역 일반관리비 및 이윤 | ServiceGeneralAdminCalculator, ServiceProfitCalculator | future_service_rate_rule | `out_of_current_workbook_scope` |
| 제35조 | 구분회계/보고서 제출 | AccountingEvidence, ComplianceReport | source_document, evidence_ref | `todo` |

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
