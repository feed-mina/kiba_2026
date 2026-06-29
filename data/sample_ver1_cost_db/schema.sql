-- sample_ver1 원가계산서 DB 설계 초안
-- Issue: https://github.com/feed-mina/kiba_2026/issues/40
-- Target: PostgreSQL

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

-- 원가 분류(재료비/노무비/직접경비/간접경비) 단일 출처.
-- 분류는 항목 사전(reference_price_item)이 아니라 "적용 시점"(applied_price /
-- unit_cost_component)에서 결정한다 → 같은 자재가 프로젝트마다 재료/경비로
-- 달라지는 경우를 데이터로 표현한다.
create table cost_category (
  code text primary key,            -- MAT / LAB / EXP_DIR / EXP_IND
  name text not null,
  roll_up_target text not null      -- 원가계산서 귀속 셀(E7/E10/E13..)
);

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

create table cost_line (
  id uuid primary key,
  revision_id uuid not null references cost_estimate_revision(id),
  parent_id uuid references cost_line(id),
  sheet_role text not null,
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
  note text,
  -- 계보(lineage) 링크: 이 내역 라인의 단가가 어디서 왔는지.
  -- 합성단가는 일위대가, 기초단가는 단가대비표에서 직접 온다.
  -- 참조 테이블이 아래에 정의되므로 FK 제약은 파일 끝 ALTER 로 추가한다.
  unit_cost_item_id uuid,
  price_item_id uuid
);

create index idx_cost_line_revision_role on cost_line(revision_id, sheet_role);
create index idx_cost_line_parent on cost_line(parent_id);
create index idx_cost_line_unit_cost_item on cost_line(unit_cost_item_id);
create index idx_cost_line_price_item on cost_line(price_item_id);

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
  source_type text not null,
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
  selection_rule text not null,
  applied_unit_price numeric(18,2) not null,
  cost_category_code text references cost_category(code),
  source_cell_id uuid references workbook_cell(id)
);

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
  total_amount numeric(18,0),
  cost_category_code text references cost_category(code)
);

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
  cost_component_code text not null,
  base_amount_type text not null,
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

create table calculation_policy (
  id uuid primary key,
  policy_code text not null,
  policy_name text not null,
  version_no integer not null,
  formula_kind text not null,
  excel_formula_template text,
  parsed_ast_json jsonb not null default '{}'::jsonb,
  calc_expression text,
  rounding_rule text,
  status text not null default 'draft',
  created_at timestamptz not null default now(),
  unique (policy_code, version_no)
);

create table formula_definition (
  id uuid primary key,
  revision_id uuid not null references cost_estimate_revision(id),
  sheet_name text not null,
  cell_address text not null,
  formula_text text not null,
  formula_kind text not null,
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

create table cost_total_component (
  id uuid primary key,
  revision_id uuid not null references cost_estimate_revision(id),
  component_code text not null,
  sheet_name text not null,
  cell_address text not null,
  formula_text text,
  excel_cached_amount numeric(18,0),
  db_calculated_amount numeric(18,0),
  amount_difference numeric(18,0) not null default 0,
  verification_status text not null default 'pending',
  sort_order integer not null,
  created_at timestamptz not null default now(),
  unique (revision_id, component_code)
);

create table cost_total_check (
  id uuid primary key,
  revision_id uuid not null references cost_estimate_revision(id),
  check_code text not null,
  left_sheet_name text not null,
  left_cell_address text not null,
  left_formula_text text,
  left_excel_cached_amount numeric(18,0),
  left_db_calculated_amount numeric(18,0),
  right_sheet_name text not null,
  right_cell_address text not null,
  right_formula_text text,
  right_excel_cached_amount numeric(18,0),
  right_db_calculated_amount numeric(18,0),
  amount_difference numeric(18,0) not null default 0,
  verification_status text not null default 'pending',
  evidence_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (revision_id, check_code)
);

-- cost_line 계보 FK (참조 테이블이 위에서 모두 정의된 뒤 연결)
alter table cost_line
  add constraint fk_cost_line_unit_cost_item
  foreign key (unit_cost_item_id) references unit_cost_item(id);
alter table cost_line
  add constraint fk_cost_line_price_item
  foreign key (price_item_id) references reference_price_item(id);

-- 원가 분류 기준값
insert into cost_category (code, name, roll_up_target) values
  ('MAT',     '재료비',       '원가계산서!E7'),
  ('LAB',     '노무비',       '원가계산서!E10'),
  ('EXP_DIR', '직접경비',     '원가계산서!E13'),
  ('EXP_IND', '간접경비(법정)', '원가계산서!E14:E23')
on conflict (code) do nothing;
