-- 001_lineage_and_category.sql
-- 적용 대상: schema.sql 초판으로 생성된 기존 DB
-- 내용: (1) cost_category 분류 단일 출처, (2) cost_line 계보 FK,
--       (3) applied_price / unit_cost_component 분류 코드.
-- Issue: https://github.com/feed-mina/kiba_2026/issues/40

begin;

create table if not exists cost_category (
  code text primary key,
  name text not null,
  roll_up_target text not null
);

insert into cost_category (code, name, roll_up_target) values
  ('MAT',     '재료비',       '원가계산서!E7'),
  ('LAB',     '노무비',       '원가계산서!E10'),
  ('EXP_DIR', '직접경비',     '원가계산서!E13'),
  ('EXP_IND', '간접경비(법정)', '원가계산서!E14:E23')
on conflict (code) do nothing;

alter table cost_line            add column if not exists unit_cost_item_id uuid;
alter table cost_line            add column if not exists price_item_id uuid;
alter table applied_price        add column if not exists cost_category_code text;
alter table unit_cost_component  add column if not exists cost_category_code text;

create index if not exists idx_cost_line_unit_cost_item on cost_line(unit_cost_item_id);
create index if not exists idx_cost_line_price_item on cost_line(price_item_id);

alter table cost_line
  add constraint fk_cost_line_unit_cost_item
  foreign key (unit_cost_item_id) references unit_cost_item(id);
alter table cost_line
  add constraint fk_cost_line_price_item
  foreign key (price_item_id) references reference_price_item(id);
alter table applied_price
  add constraint fk_applied_price_category
  foreign key (cost_category_code) references cost_category(code);
alter table unit_cost_component
  add constraint fk_unit_cost_component_category
  foreign key (cost_category_code) references cost_category(code);

commit;
