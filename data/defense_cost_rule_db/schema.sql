-- 방산원가 규칙 조문 DB 확장 스키마 초안
-- Source: docs/원가계산보고서샘플/방산원가대상물자의 원가계산에 관한 규칙(국방부령)(제01202호)(20260130).pdf
-- Target: PostgreSQL
--
-- 이 파일은 기존 data/sample_ver1_cost_db/schema.sql의 원가계산 도메인에
-- "법령 조문 근거"와 "계산 정책 근거"를 연결하기 위한 별도 bounded context다.

create table legal_rule_document (
  id uuid primary key,
  document_code text not null unique,         -- DEFENSE_COST_RULE_20260130
  title text not null,
  ministry text,
  ordinance_no text,
  effective_date date not null,
  revision_type text,
  source_path text not null,
  source_checksum text,
  created_at timestamptz not null default now()
);

create table legal_article (
  id uuid primary key,
  document_id uuid not null references legal_rule_document(id),
  article_no text not null,                   -- 제24조, 제39조의6
  article_title text not null,
  chapter_title text,
  section_title text,
  article_text text not null,
  is_deleted boolean not null default false,
  is_supplementary boolean not null default false,
  sort_order integer not null,
  unique (document_id, article_no, is_supplementary)
);

create table legal_article_term (
  id uuid primary key,
  article_id uuid not null references legal_article(id),
  term_no integer not null,
  term_name text not null,
  definition_text text not null,
  canonical_domain_type text,                 -- CostCategory, CostConcept, RateRuleSet 등
  canonical_domain_code text,
  unique (article_id, term_no)
);

create table legal_rule_to_domain_mapping (
  id uuid primary key,
  article_id uuid not null references legal_article(id),
  rule_theme text not null,
  bounded_context text not null,
  aggregate_name text not null,
  domain_object_name text not null,
  target_table text,
  target_column text,
  target_sheet_name text,
  target_cell_range text,
  implementation_status text not null default 'todo',
  notes text,
  unique (article_id, bounded_context, aggregate_name, domain_object_name, coalesce(target_table, ''), coalesce(target_cell_range, ''))
);

create table legal_calculation_policy_link (
  id uuid primary key,
  article_id uuid not null references legal_article(id),
  policy_id uuid references calculation_policy(id),
  policy_code text not null,
  legal_basis_kind text not null default 'primary', -- primary / exception / evidence / definition
  required_variables jsonb not null default '[]'::jsonb,
  required_evidence jsonb not null default '[]'::jsonb,
  variable_rules jsonb not null default '{}'::jsonb,
  notes text,
  unique (article_id, policy_code, legal_basis_kind)
);

create table legal_rate_rule_basis (
  id uuid primary key,
  article_id uuid not null references legal_article(id),
  rule_set_id uuid references rate_rule_set(id),
  rule_set_code text not null,
  rate_component_code text not null,
  base_amount_type text not null,
  rate_source_rule text not null,             -- 고시/실적치/기관 산정/엑셀 기준 등
  government_furnished_material_policy text,  -- include / exclude / conditional / not_applicable
  rounding_rule text,
  notes text,
  unique (article_id, rule_set_code, rate_component_code)
);

create table legal_verification_case (
  id uuid primary key,
  article_id uuid not null references legal_article(id),
  revision_id uuid references cost_estimate_revision(id),
  check_code text not null,
  workbook_cell text,
  target_table text,
  target_field text,
  excel_cached_amount numeric(18,0),
  db_calculated_amount numeric(18,0),
  amount_difference numeric(18,0),
  verification_status text not null default 'pending',
  evidence_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (article_id, revision_id, check_code)
);

-- 조문 DB화 후 calculation_policy를 만들 때 우선 연결할 정책 코드 후보.
-- 실제 policy_id는 기존 calculation_policy seed 이후 update로 채운다.
create table legal_policy_candidate (
  id uuid primary key,
  article_no text not null,
  policy_code text not null,
  policy_name text not null,
  formula_kind text not null,
  calc_expression text,
  rounding_rule text,
  variable_schema jsonb not null default '{}'::jsonb,
  status text not null default 'draft',
  unique (article_no, policy_code)
);

insert into legal_policy_candidate (
  id,
  article_no,
  policy_code,
  policy_name,
  formula_kind,
  calc_expression,
  rounding_rule,
  variable_schema
) values
  (gen_random_uuid(), '제20조', 'DEF_DIRECT_MATERIAL_V1', '방산 직접재료비 계산', 'arithmetic', 'quantity * applied_unit_price - residual_deduction', 'trunc_0', '{"quantity":"Quantity","applied_unit_price":"Money","residual_deduction":"Money"}'),
  (gen_random_uuid(), '제21조', 'DEF_DIRECT_LABOR_V1', '방산 직접노무비 계산', 'arithmetic', 'labor_rate * labor_quantity', 'trunc_0', '{"labor_rate":"Money","labor_quantity":"Quantity"}'),
  (gen_random_uuid(), '제22조', 'DEF_DIRECT_EXPENSE_V1', '방산 직접경비 계산', 'evidence_amount', 'actual_expense_amount', 'trunc_0', '{"actual_expense_amount":"Money","evidence_ref":"EvidenceRef"}'),
  (gen_random_uuid(), '제23조', 'DEF_INDIRECT_COST_V1', '방산 제조간접비 계산', 'rate', 'base_amount * rate_percent', 'trunc_0', '{"base_amount":"Money","rate_percent":"Rate","allocation_basis":"AllocationBasis"}'),
  (gen_random_uuid(), '제24조', 'DEF_GENERAL_ADMIN_V1', '방산 일반관리비 계산', 'rate', 'manufacturing_cost_base * general_admin_rate', 'trunc_0', '{"manufacturing_cost_base":"Money","general_admin_rate":"Rate","government_furnished_material_policy":"PolicyFlag"}'),
  (gen_random_uuid(), '제26조', 'DEF_PROFIT_V1', '방산 이윤 계산', 'rate', 'profit_base_amount * profit_rate', 'trunc_0', '{"profit_base_amount":"Money","profit_rate":"Rate","profit_rule_set":"RuleSetRef"}')
on conflict (article_no, policy_code) do nothing;
