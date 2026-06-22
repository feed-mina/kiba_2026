---
repo: feed-mina/kiba_2026
issue: 10
status: done
github: https://github.com/feed-mina/kiba_2026/issues/10
tags:
  - issue
  - issue-10
  - project-status
---

# Issue 10 - KIBA Pages 및 GitHub Issue 운영 후속 작업 (2026-06-17)

## 현재 상태

- 상태: `done`
- 체크리스트: `38/38` 완료
- GitHub: [feed-mina/kiba_2026 Issue #10](https://github.com/feed-mina/kiba_2026/issues/10)
- 현황판: [index.html](file:///C:/Users/User/Desktop/KIBA/index.html)
- index.html 표시: 2026-06-17 · 38/38 완료

## 다음 행동

- [ ] 다음 점검 시 Todo 또는 GitHub Issue에서 후속 행동을 확인

## 날짜 기록

### 2026-06-17 - KIBA Pages 및 GitHub Issue 운영 후속 작업 (2026-06-17)
- 원본: [[Todo/2026-06-17_kiba_pages_followup|2026-06-17_kiba_pages_followup.md]]
- # KIBA Pages 및 GitHub Issue 운영 후속 작업 (2026-06-17)
- - [x] 모바일/노트북 화면에서 보드와 메모창이 깨지지 않는지 확인. (2026-06-18 점검: 375px 가로 오버플로 없음, 메모 모달 정상; 데스크톱 .wrap 1120px 중앙정렬)
- - [x] 완료된 이슈가 생기면 `끝난 일` 영역으로 옮기는 기준 정하기 → Todo 체크리스트 `done==total`이면 자동으로 Pages 보드 "끝난 일" 아코디언(`<details>`)으로 이동(2026-06-19 reflect_todo.py 반영). 이슈는 `done` 라벨.
- - [x] 현재 메모창 UI 동작 확인: 카드 클릭, 의견 작성, 저장, 복사, 이슈 열기 → 메모 모달 정상 동작 확인(2026-06-18 점검).
- **상세 내용:** 오늘 대화는 `ASK/2026-06-17_ai.md`와 이 Todo 파일에 정리했습니다. 이후에도 작업 후 기록을 누적합니다.
- - [x] quali-fit 카드로 #7에 코멘트가 정상 적재되는지 최종 확인. (2026-06-19: Worker `GITHUB_TOKEN` 만료로 `/counts`가 `{"7":0}` 반환하던 것을 `wrangler secret put GITHUB_TOKEN` 재설정 후 `{"7":3}`으로 GitHub 실제 코멘트 수와 일치 확인. 코멘트 표시·등록 복구.)

## 관련 Todo

- [[Todo/2026-06-17_kiba_pages_followup|KIBA Pages 및 GitHub Issue 운영 후속 작업 (2026-06-17)]] - `done` `38/38`

## 관련 docs / Cloud 링크

- 이슈 자료 목록 후보: [Cloud docs list](https://kiba.kibayerin.workers.dev/docs/list?repo=feed-mina%2Fkiba_2026&issue=10)

## 관련 index.html 카드

- KIBA Pages 및 GitHub Issue 운영 후속 작업 (2026-06-17) / source `todo` / repo `feed-mina/kiba_2026`

#issue #project-status
