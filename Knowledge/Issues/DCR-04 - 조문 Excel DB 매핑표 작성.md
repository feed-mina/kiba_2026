---
repo: feed-mina/kiba_2026
issue_key: DCR-04
status: done
tags:
  - issue
  - dcr
  - defense-cost-rule
  - project-status
---

# DCR-04 - 조문 Excel DB 매핑표 작성

## 현재 상태

- 상태: `done`
- 생성일: 2026-06-30
- 산출물: [article_excel_mapping.json](../../data/defense_cost_rule_db/article_excel_mapping.json)

## 체크리스트

- [x] 핵심 조문을 DDD 객체 후보로 매핑.
- [x] 조문별 Excel 시트/셀 범위 또는 DB 테이블 후보 연결.
- [x] 현재 workbook 범위 밖의 용역원가 조문을 별도 scope로 분리.
- [x] 방산 규칙과 sample ver2 기준이 다른 부분을 notes에 표시.

## 실행 결과

제6조, 제15조, 제16조, 제17조, 제18조, 제19조, 제20조, 제23조, 제24조, 제26조는 현재 ver2 구조에 직접 연결 가능하다. 제25조, 제28조, 제35조는 기준/증빙/정산 컨텍스트 확장이 필요하다.
