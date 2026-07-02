---
repo: feed-mina/kiba_2026
issue_key: DCR-02
status: done
tags:
  - issue
  - dcr
  - defense-cost-rule
  - project-status
---

# DCR-02 - 방산원가 PDF 조문 JSON seed 생성

## 현재 상태

- 상태: `done`
- 생성일: 2026-06-30
- 산출물: [legal_articles.json](../../data/defense_cost_rule_db/legal_articles.json)

## 체크리스트

- [x] PDF 텍스트 추출.
- [x] 장/절/조문 제목 파싱.
- [x] 삭제 조문과 부칙 조문 플래그 분리.
- [x] 제2조 정의 항목 20개를 `legal_article_term` 후보로 추출.

## 실행 결과

`scripts/analyze_defense_cost_rule_sources.py`로 `legal_articles.json`을 생성했다. 현재 추출 기준으로 PDF 12쪽에서 조문 53개와 정의 20개가 잡힌다.
