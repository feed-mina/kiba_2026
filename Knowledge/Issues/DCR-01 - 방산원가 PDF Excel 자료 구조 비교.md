---
repo: feed-mina/kiba_2026
issue_key: DCR-01
status: done
tags:
  - issue
  - dcr
  - defense-cost-rule
  - project-status
---

# DCR-01 - 방산원가 PDF Excel 자료 구조 비교

## 현재 상태

- 상태: `done`
- 생성일: 2026-06-30
- 산출물: [방산원가_규칙_PDF_vs_원가계산보고서ver2_DDD_분석.md](../../docs/원가계산보고서샘플/방산원가_규칙_PDF_vs_원가계산보고서ver2_DDD_분석.md)

## 체크리스트

- [x] PDF 페이지 수, 조문 수, 핵심 키워드 빈도 추출.
- [x] Excel ver2 시트 27개와 기존 role 매핑 확인.
- [x] 기존 ver2 DB 검증값 확인: `원가계산서!E34 = 109,104,460`, `결과!J10 = 109,104,460`.
- [x] PDF와 Excel의 같은 점/다른 점 정리.

## 실행 결과

PDF는 방산원가 계산의 법령 근거이고, Excel은 특정 품목/수량/단가/비율이 들어간 실행 인스턴스다. 둘은 같은 원가 비목 체계를 공유하지만, PDF에는 관급재료비, 정산원가, 구분회계, 원가정보 같은 방산 특화 영역이 더 있다.
