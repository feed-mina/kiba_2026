# sample_ver1 원가계산서 DB 설계

Issue #40의 실작업 산출물입니다.

## 파일

- `schema.sql`: PostgreSQL 기준 DDD 스키마 초안
- `workbook_manifest.json`: `scripts/import_sample_ver1_cost_workbook.py`가 만든 workbook 구조/수식/의존성 manifest
- `golden_value_check.json`: `scripts/verify_sample_ver1_golden_values.py`가 만든 Excel 캐시값과 DB 후보 계산값 비교 결과
- `domain_tables.json`: `scripts/extract_sample_cost_domain.py`가 만든 공개 도메인 테이블 실제값

## importer 실행

```powershell
python .\scripts\import_sample_ver1_cost_workbook.py
```

기본 입력은 `docs/원가계산보고서샘플/*ver1*.xlsx*`에서 찾습니다.

## golden value 검증

```powershell
python .\scripts\verify_sample_ver1_golden_values.py
```

현재 기준 검증 결과는 `원가계산서!E34 = 123,387,460`, `결과!J10 = 123,387,460`이며, Excel 캐시값과 DB 후보 계산값이 일치합니다.

## domain table ETL

```powershell
python .\scripts\extract_sample_cost_domain.py --input "docs\원가계산보고서샘플\(E)sample_원가계산보고서ver1.xlsx.xlsx" --output "data\sample_ver1_cost_db\domain_tables.json"
```

현재 기준 추출 결과는 `cost_line=57`, `unit_cost_item=4`, `unit_cost_component=15`입니다.
`unit_cost_item.total_amount`와 `unit_cost_component`의 그룹별 합계도 일치합니다.

`cost_line`에는 원본 내역서 행 번호(`source_row_no`)와 원가계산서 합계행 포함 여부
(`rollup_included`)를 함께 저장합니다. 샘플 workbook은 내역서 합계행 뒤에 안전장치
2개 행이 있어 표시용 라인과 원가계산서 집계 대상 라인이 다릅니다.

`generation_rules.json`은 내역서 명칭과 일위대가/단가대비표 명칭이 다른 경우의 alias
규칙입니다. 단가대비표는 원본 수식의 `단가대비표!M##` 참조가 있으면 그 참조를
명칭 매칭보다 우선합니다.

## 계산형 검증

```powershell
python .\scripts\compute_cost_statement.py --domain data\sample_ver1_cost_db\domain_tables.json
python .\scripts\compute_cost_statement.py --domain data\sample_ver1_cost_db\ver2\domain_tables.json
```

현재 결과는 두 버전 모두 내역서 집계 대상 55라인 중 `일위대가 4`, `단가대비표 50`,
`비율산식 1`로 55/55 라인의 금액이 재현됩니다. 내역서 물량 합계도 원가계산서
집계값과 재료비/노무비/경비 차이 0으로 일치합니다.

## 현재 모델링 방향

- Aggregate root: `cost_estimate`
- Revision: `cost_estimate_revision`
- 원본 Excel 추적: `workbook_sheet`, `workbook_cell`
- 도메인 행 구조: `cost_line`
- Excel 표시 read model: `sheet_line_projection`
- 단가/비율 기준정보: `reference_price_*`, `rate_rule_*`
- 수식 정책/의존성: `calculation_policy`, `formula_definition`, `formula_dependency`
- 총액 검증: `cost_total_component`, `cost_total_check`

## 총액 검증 저장 방식

- `cost_total_component`: `원가계산서!E7`, `E30`, `E31`, `E32`, `E33`, `E34`처럼 총액 산출에 직접 참여하는 중간 금액을 Excel 캐시값과 DB 후보 계산값으로 나란히 저장합니다.
- `cost_total_check`: `결과!J10 == 원가계산서!E34` 같은 최종 총액 검증 쌍을 저장합니다.
- `MIN(D7,H7,J7)`에서 빈 셀은 0으로 계산하지 않고 Excel처럼 제외해야 총액이 일치합니다.
