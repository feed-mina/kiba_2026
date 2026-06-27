# sample_ver1 원가계산서 DB 설계

Issue #40의 실작업 산출물입니다.

## 파일

- `schema.sql`: PostgreSQL 기준 DDD 스키마 초안
- `workbook_manifest.json`: `scripts/import_sample_ver1_cost_workbook.py`가 만든 workbook 구조/수식/의존성 manifest
- `golden_value_check.json`: `scripts/verify_sample_ver1_golden_values.py`가 만든 Excel 캐시값과 DB 후보 계산값 비교 결과

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
