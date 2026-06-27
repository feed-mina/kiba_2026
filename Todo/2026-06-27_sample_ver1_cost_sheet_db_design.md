# sample_ver1 원가계산서 DB설계

> 목적: `docs/원가계산보고서샘플/(E)sample_원가계산보고서ver1.xlsx.xlsx`의 `sample_ver1` 원가계산서 구조를 DDD 방식 DB 아키텍처로 전환한다. `원가계산서`, `집계표`, `내역서`, `일위대가목록`, `일위대가표`, `단가대비표`와 보험료/경비/일반관리비/이윤 산출표의 수식 연계를 보존해 재계산 가능한 데이터 모델을 만든다.
> GitHub Issue: https://github.com/feed-mina/kiba_2026/issues/40

---

## 0. [조사완료] sample_ver1 workbook 구조 파악

**상세 내용:** workbook을 ZIP/XML 기준으로 직접 읽어 시트 구조와 주요 수식 흐름을 확인했다. `openpyxl`은 이 파일의 스타일/외부 링크 메타데이터에서 로딩 오류가 있어, DB 설계에는 필요한 값/수식 XML만 추출했다.

**체크리스트**

- [x] 핵심 시트 확인: `원가계산서`, `집계표`, `내역서`, `일위대가목록`, `일위대가표`, `단가대비표`.
- [x] 보조 산출표 확인: `간노비`, `경비`, `산재`, `고용`, `건강`, `연금`, `장기`, `석면`, `임금`, `퇴공`, `안전`, `일반`, `일반비율`, `이윤`, `이윤비율`.
- [x] 주요 흐름 확인: `단가대비표 -> 일위대가표 -> 일위대가목록/내역서 -> 집계표 -> 원가계산서 -> 결과`.
- [x] 대표 수식 확인:
  - `원가계산서!E7 = 집계표!E19`
  - `원가계산서!E10 = 집계표!G19`
  - `집계표!D7 = 내역서!F71`, `집계표!E19 = SUM(E7:E18)`
  - `내역서!E11 = 단가대비표!M7`, `내역서!K11 = F11 + H11 + J11`
  - `일위대가목록!E7 = 일위대가표!F21`
  - `일위대가표!G8 = 단가대비표!M55`
  - `단가대비표!M7 = MIN(D7,H7,J7)`

---

## 1. [객관식 설계 질문] DDD 경계 결정

**Q1. 원가계산서 DB의 Aggregate Root는 무엇으로 둘 것인가?**

- A. `CostEstimate`를 루트로 두고, workbook의 모든 시트/라인/수식은 한 견적 산출 revision 안에 묶는다.
- B. Excel 시트별로 Aggregate를 나눈다.
- C. `CostLine` 한 줄을 Aggregate Root로 둔다.
- D. 수식(`Formula`)을 Aggregate Root로 둔다.

**선택 답변: A. `CostEstimate` 루트**

이유: 최종 결과는 `원가계산서!E34` 같은 전체 산출 결과이고, workbook 내 시트들은 서로 강하게 연결되어 있다. 시트별 Aggregate로 나누면 `집계표 -> 원가계산서`, `경비/보험 -> 원가계산서` 같은 불변식 관리가 어렵다.

**Q2. Excel 수식은 DB에서 어떻게 보존할 것인가?**

- A. 수식 정의와 의존성 그래프를 별도 테이블로 보존하고, 계산 결과는 revision별 snapshot으로 저장한다.
- B. 최종 금액만 저장하고 수식은 버린다.
- C. Excel 원문 수식 문자열만 보관한다.
- D. `FormulaPolicy` 버전으로 둔다. Excel 원문 수식, 파싱 AST, DB 계산식, 적용 버전을 하나의 정책 객체로 관리하고 `formula_definition`은 해당 정책을 참조한다.

**선택 답변: A + D 보완. 수식 정의 + 의존성 그래프 + 계산 snapshot을 기본으로 하되, 검증된 산식은 `FormulaPolicy`로 승격한다.**

이유: `단가대비표!M7 = MIN(D7,H7,J7)`처럼 업무 규칙인 산식과, `원가계산서!E7 = 집계표!E19`처럼 집계 연결인 산식이 섞여 있다. 둘 다 추적 가능해야 하고, Excel 원문도 감사 추적용으로 보존해야 한다.

**D버전 추가 설명:** 모든 수식을 DB trigger로 넣는 방식은 변경 추적과 재현성이 떨어진다. 대신 `FormulaPolicy`를 두면 Excel 수식 원문은 보존하고, DB/서비스 계산식은 버전 관리할 수 있다. 예를 들어 `MIN(D7,H7,J7)`은 `applied_price_min` 정책으로, `TRUNC(D8*F8%,0)`은 `rate_charge_trunc_0` 정책으로 관리한다.

**Q3. `집계표`, `내역서`, `일위대가표`의 행 구조는 어떻게 모델링할 것인가?**

- A. 공통 `CostLine` 계층으로 두고, sheet role과 line type으로 구분한다.
- B. 각 시트별로 완전히 별도 테이블을 만든다.
- C. workbook 전체를 JSON document 하나로 저장한다.
- D. `CostLine`은 canonical 모델로 유지하고, Excel 시트별 행 모양은 `SheetLineProjection`으로 따로 둔다.

**선택 답변: A + D 보완. 공통 `CostLine` 계층을 canonical 모델로 두고, Excel 재현/검증을 위해 `SheetLineProjection`을 추가한다.**

이유: 세 시트 모두 `품명`, `규격`, `단위`, `수량`, `재료비`, `노무비`, `경비`, `합계`의 반복 구조를 가진다. 다만 `일위대가표`는 한 단가 항목의 세부 구성이고, `내역서`는 공사 품목, `집계표`는 품목군 집계라서 역할만 다르게 잡는다.

**D버전 추가 설명:** 공통 `CostLine`만 두면 도메인 계산에는 좋지만, 원본 Excel의 행/열 위치와 시트별 표시 구조를 복원하기 어렵다. `SheetLineProjection`은 `집계표`, `내역서`, `일위대가표`의 실제 행 번호, 병합/표시 구간, 원본 셀 매핑을 저장하는 read model로 사용한다.

**Q4. `단가대비표`와 비율표는 어떻게 이력 관리할 것인가?**

- A. 기준일/출처/업체/적용단가를 가진 versioned reference data로 관리한다.
- B. 현재 적용 단가만 덮어쓴다.
- C. 단가 master 하나만 두고 모든 프로젝트가 공유한다.
- D. 단가/비율은 Excel 업로드 시점의 계산 결과에만 남긴다.

**선택 답변: A. 기준일과 출처가 있는 versioned reference data**

이유: `단가대비표`에는 거래가격, 물가정보, 조사단가, 적용단가가 함께 있고, 보험/일반관리비/이윤은 기준표와 적용 기준일이 중요하다. 나중에 같은 품목을 다른 기준월로 다시 계산할 수 있어야 한다.

---

## 2. [스키마 초안] 선택 답변 기반 PostgreSQL DDL

**설계 원칙**

- `CostEstimate` Aggregate 안에 revision을 둔다.
- Excel 시트/셀은 출처 추적용으로 보존하되, 도메인 모델은 `CostLine`, `Formula`, `ReferencePrice`, `RateRule`로 분리한다.
- 금액은 원 단위 정수에 가깝게 `numeric(18,0)`을 기본으로 하고, 수량/비율은 소수 정밀도를 둔다.
- Excel 수식 원문과 DB 계산식은 분리한다. 초기에는 Excel 원문을 저장하고, 검증된 산식부터 `calc_expression`으로 이관한다.

```sql
-- Aggregate root
create table cost_estimate (
  id uuid primary key,
  estimate_code text not null unique,
  title text not null,
  client_name text,
  standard_name text,
  basis_date date,
  source_workbook_path text not null,
  status text not null default 'draft',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table cost_estimate_revision (
  id uuid primary key,
  estimate_id uuid not null references cost_estimate(id),
  revision_no integer not null,
  source_checksum text not null,
  calculation_status text not null default 'imported',
  total_cost numeric(18,0),
  vat_excluded boolean not null default true,
  created_at timestamptz not null default now(),
  unique (estimate_id, revision_no)
);

-- Workbook trace
create table workbook_sheet (
  id uuid primary key,
  revision_id uuid not null references cost_estimate_revision(id),
  sheet_name text not null,
  sheet_role text not null,
  display_order integer not null,
  unique (revision_id, sheet_name)
);

create table workbook_cell (
  id uuid primary key,
  sheet_id uuid not null references workbook_sheet(id),
  cell_address text not null,
  raw_value text,
  formula_text text,
  value_type text,
  domain_ref_type text,
  domain_ref_id uuid,
  unique (sheet_id, cell_address)
);

-- Cost line tree: 원가계산서/집계표/내역서/일위대가표 공통 구조
create table cost_line (
  id uuid primary key,
  revision_id uuid not null references cost_estimate_revision(id),
  parent_id uuid references cost_line(id),
  sheet_role text not null, -- cost_statement, summary, detail, unit_price_list, unit_price_detail
  line_code text,
  sort_order integer not null,
  item_name text,
  specification text,
  unit text,
  quantity numeric(18,6),
  material_unit_price numeric(18,2),
  material_amount numeric(18,0),
  labor_unit_price numeric(18,2),
  labor_amount numeric(18,0),
  expense_unit_price numeric(18,2),
  expense_amount numeric(18,0),
  total_unit_price numeric(18,2),
  total_amount numeric(18,0),
  note text
);

create index idx_cost_line_revision_role on cost_line(revision_id, sheet_role);
create index idx_cost_line_parent on cost_line(parent_id);

-- Excel sheet별 표시 구조/read model. canonical cost_line을 원본 시트 행으로 되돌리는 용도.
create table sheet_line_projection (
  id uuid primary key,
  revision_id uuid not null references cost_estimate_revision(id),
  sheet_id uuid not null references workbook_sheet(id),
  cost_line_id uuid references cost_line(id),
  sheet_name text not null,
  row_no integer not null,
  row_group_code text,
  display_label text,
  material_amount_cell text,
  labor_amount_cell text,
  expense_amount_cell text,
  total_amount_cell text,
  source_range text,
  projection_json jsonb not null default '{}'::jsonb,
  unique (revision_id, sheet_name, row_no)
);

-- 단가대비표: 기준월/출처/업체별 조사 단가
create table reference_price_item (
  id uuid primary key,
  item_name text not null,
  specification text,
  unit text,
  normalized_key text not null
);

create table reference_price_quote (
  id uuid primary key,
  price_item_id uuid not null references reference_price_item(id),
  basis_month date not null,
  source_type text not null, -- 거래가격, 물가정보, 업체견적, 수기조사
  source_name text,
  vendor_name text,
  quoted_unit_price numeric(18,2),
  page_ref text,
  evidence_ref text,
  created_at timestamptz not null default now()
);

create table applied_price (
  id uuid primary key,
  revision_id uuid not null references cost_estimate_revision(id),
  price_item_id uuid not null references reference_price_item(id),
  selected_quote_id uuid references reference_price_quote(id),
  selection_rule text not null, -- min, manual, preferred_source
  applied_unit_price numeric(18,2) not null,
  source_cell_id uuid references workbook_cell(id)
);

-- 일위대가: 한 품목 단가를 여러 구성 라인으로 계산
create table unit_cost_item (
  id uuid primary key,
  revision_id uuid not null references cost_estimate_revision(id),
  unit_cost_no text not null,
  item_name text not null,
  specification text,
  unit text,
  material_amount numeric(18,0),
  labor_amount numeric(18,0),
  expense_amount numeric(18,0),
  total_amount numeric(18,0),
  unique (revision_id, unit_cost_no)
);

create table unit_cost_component (
  id uuid primary key,
  unit_cost_item_id uuid not null references unit_cost_item(id),
  sort_order integer not null,
  component_name text,
  specification text,
  unit text,
  quantity numeric(18,6),
  price_item_id uuid references reference_price_item(id),
  material_unit_price numeric(18,2),
  labor_unit_price numeric(18,2),
  expense_unit_price numeric(18,2),
  material_amount numeric(18,0),
  labor_amount numeric(18,0),
  expense_amount numeric(18,0),
  total_unit_price numeric(18,2),
  total_amount numeric(18,0)
);

-- 보험료/경비/일반관리비/이윤 비율 규칙
create table rate_rule_set (
  id uuid primary key,
  rule_set_code text not null,
  rule_set_name text not null,
  basis_date date,
  source_name text,
  source_ref text
);

create table rate_rule (
  id uuid primary key,
  rule_set_id uuid not null references rate_rule_set(id),
  cost_component_code text not null, -- 산재, 고용, 건강, 연금, 장기, 안전, 일반관리비, 이윤
  base_amount_type text not null, -- direct_labor, total_labor, material_plus_labor, subtotal
  condition_json jsonb not null default '{}'::jsonb,
  rate_percent numeric(9,5) not null,
  rounding_rule text not null default 'trunc_0'
);

create table indirect_cost_charge (
  id uuid primary key,
  revision_id uuid not null references cost_estimate_revision(id),
  rate_rule_id uuid references rate_rule(id),
  component_code text not null,
  base_amount numeric(18,0) not null,
  rate_percent numeric(9,5) not null,
  calculated_amount numeric(18,0) not null,
  source_sheet_name text,
  source_cell_address text
);

-- Formula policy: Excel 원문 수식을 검증된 도메인 계산 정책으로 승격하는 계층
create table calculation_policy (
  id uuid primary key,
  policy_code text not null,
  policy_name text not null,
  version_no integer not null,
  formula_kind text not null, -- lookup, arithmetic, aggregate, rate, narrative
  excel_formula_template text,
  parsed_ast_json jsonb not null default '{}'::jsonb,
  calc_expression text,
  rounding_rule text,
  status text not null default 'draft',
  created_at timestamptz not null default now(),
  unique (policy_code, version_no)
);

-- Formula graph: Excel 원문과 DB 계산식의 중간 계층
create table formula_definition (
  id uuid primary key,
  revision_id uuid not null references cost_estimate_revision(id),
  sheet_name text not null,
  cell_address text not null,
  formula_text text not null,
  formula_kind text not null, -- lookup, arithmetic, aggregate, rate, narrative
  policy_id uuid references calculation_policy(id),
  calc_expression text,
  target_domain_type text,
  target_domain_id uuid,
  unique (revision_id, sheet_name, cell_address)
);

create table formula_dependency (
  id uuid primary key,
  formula_id uuid not null references formula_definition(id),
  depends_on_sheet text not null,
  depends_on_address text not null,
  dependency_kind text not null default 'cell'
);

create table calculated_value_snapshot (
  id uuid primary key,
  revision_id uuid not null references cost_estimate_revision(id),
  domain_type text not null,
  domain_id uuid not null,
  value_name text not null,
  numeric_value numeric(18,6),
  text_value text,
  source_formula_id uuid references formula_definition(id),
  created_at timestamptz not null default now()
);
```

---

## 3. [다음 작업] 구현 순서

**체크리스트**

- [x] `sample_ver1` workbook에서 시트/셀/수식/XML을 안정적으로 추출하는 importer 스크립트 작성. (`scripts/import_sample_ver1_cost_workbook.py`)
- [x] 위 DDL을 기준으로 `cost_estimate`, `cost_line`, `unit_cost_item`, `reference_price_quote`, `rate_rule` migration 초안 작성. (`data/sample_ver1_cost_db/schema.sql`)
- [x] Excel 수식 dependency parser 작성: `Sheet!A1`, range, `SUM`, `MIN`, `TRUNC`, `ROUNDDOWN`, `IF` 우선 지원. (manifest 기준 527개 dependency 추출)
- [x] `단가대비표 -> 일위대가표 -> 내역서 -> 집계표 -> 원가계산서` golden test 작성. (`workbook_manifest.json`의 `golden_cells`)
- [ ] `원가계산서!E34`와 `결과!J10`을 Excel 원본 계산값과 DB 계산값으로 비교.
- [ ] GitHub Issue/Project/Pages 보드에서 이 과업 카드가 보이는지 확인.

---

## 4. [주의사항] 설계 리스크

- [ ] 외부 workbook 참조(`'[340]산재비율'!A1`, `'[340]원가 (2)'!E10` 등)는 source workbook 또는 reference table로 분리해야 한다.
- [ ] Excel 파일의 `A1:Z1000` 같은 넓은 used range와 실제 데이터 영역을 분리하는 탐지 규칙이 필요하다.
- [ ] 수식 중 빈 문자열 수식(`=`)과 깨진 참조(`#REF!`)가 있으므로 importer에서 오류/보류 상태를 별도로 기록해야 한다.
- [ ] 금액 반올림 규칙(`TRUNC`, `ROUNDDOWN`)은 DB 계산 엔진에서 Excel과 같은 방식으로 재현해야 한다.
