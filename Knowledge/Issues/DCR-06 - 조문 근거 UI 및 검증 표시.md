---
repo: feed-mina/kiba_2026
issue_key: DCR-06
status: done
tags:
  - issue
  - dcr
  - defense-cost-rule
  - project-status
---

# DCR-06 - 조문 근거 UI 및 검증 표시

## 현재 상태

- 상태: `done`
- 생성일: 2026-06-30
- 산출물: [방산원가_조문_DB_뷰.html](../../docs/원가계산보고서샘플/방산원가_조문_DB_뷰.html)

## 체크리스트

- [x] 별도 HTML에서 `legal_article`, `legal_rule_to_domain_mapping` 표시.
- [x] 계산정책과 조문 근거 표시.
- [x] Excel 캐시값, DB 계산값 요약 표시.
- [x] ver2 샘플에서 방산 규칙과 예정가격작성기준이 다른 부분을 경고로 표시.

## 실행 결과

`scripts/build_defense_rule_db_view.py`가 `data/defense_cost_rule_db`의 JSON 산출물을 읽어 정적 HTML을 생성한다. 서버 없이 열 수 있는 작업용 뷰로, 후속 단계에서 `db-tables.html`에 통합할 수 있다.
