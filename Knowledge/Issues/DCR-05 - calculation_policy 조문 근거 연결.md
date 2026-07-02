---
repo: feed-mina/kiba_2026
issue_key: DCR-05
status: done
tags:
  - issue
  - dcr
  - defense-cost-rule
  - project-status
---

# DCR-05 - calculation_policy 조문 근거 연결

## 현재 상태

- 상태: `done`
- 생성일: 2026-06-30
- 선행 산출물: [schema.sql](../../data/defense_cost_rule_db/schema.sql)

## 체크리스트

- [x] 조문과 계산 정책을 연결할 `legal_calculation_policy_link` 설계.
- [x] 법령 기반 정책 후보 `legal_policy_candidate` 추가.
- [x] 기존 `data/sample_ver1_cost_db/ver2/domain_tables.json`의 `calculation_policy`와 조문 후보를 자동 매칭하는 변환 스크립트 작성.
- [x] `policy_article_links.json` / `policy_article_links.sql` 생성. 현재 8개 정책 연결, 3개 표시/세금 정책 제외.
- [x] 후속 검증 스크립트에서 조문 근거 연결 유효성 확인.

## 실행 결과

`scripts/verify_defense_rule_policy_links.py` 기준 링크 검증이 통과했다. 연결 정책 8개, 표시/세금 분리 정책 3개, 문제 0개다.
