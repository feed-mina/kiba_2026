---
repo: feed-mina/kiba_2026
issue_key: DCR-03
status: done
tags:
  - issue
  - dcr
  - defense-cost-rule
  - project-status
---

# DCR-03 - 방산원가 법령 조문 DB 스키마 초안

## 현재 상태

- 상태: `done`
- 생성일: 2026-06-30
- 산출물: [schema.sql](../../data/defense_cost_rule_db/schema.sql)

## 체크리스트

- [x] `legal_rule_document` 설계.
- [x] `legal_article` / `legal_article_term` 설계.
- [x] 조문과 기존 도메인 객체를 잇는 `legal_rule_to_domain_mapping` 설계.
- [x] 조문과 `calculation_policy`, `rate_rule_set`, 검증 케이스를 잇는 링크 테이블 설계.
- [x] 제20조, 제21조, 제22조, 제23조, 제24조, 제26조 정책 후보 seed 추가.

## 실행 결과

기존 원가계산 DB에 조문을 직접 섞지 않고, `legal_*` bounded context로 분리한 뒤 policy/rate/verification으로 연결하는 방향으로 잡았다.
