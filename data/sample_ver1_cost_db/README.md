# sample_ver1 원가계산서 DB 설계

Issue #40의 실작업 산출물입니다.

## 파일

- `schema.sql`: PostgreSQL 기준 DDD 스키마 초안
- `workbook_manifest.json`: `scripts/import_sample_ver1_cost_workbook.py`가 만든 workbook 구조/수식/의존성 manifest

## importer 실행

```powershell
python .\scripts\import_sample_ver1_cost_workbook.py
```

기본 입력은 `docs/원가계산보고서샘플/*ver1*.xlsx*`에서 찾습니다.

## 현재 모델링 방향

- Aggregate root: `cost_estimate`
- Revision: `cost_estimate_revision`
- 원본 Excel 추적: `workbook_sheet`, `workbook_cell`
- 도메인 행 구조: `cost_line`
- Excel 표시 read model: `sheet_line_projection`
- 단가/비율 기준정보: `reference_price_*`, `rate_rule_*`
- 수식 정책/의존성: `calculation_policy`, `formula_definition`, `formula_dependency`
