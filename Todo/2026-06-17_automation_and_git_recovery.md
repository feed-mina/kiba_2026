# ASK/Todo 자동화 및 git 복구 후속 작업 (2026-06-17)

> 목적: 2026년 6월 17일 Claude 작업 중 정해진 ASK/Todo 일일 자동 정리 스케줄과 git 손상 복구 관련 후속 작업을 관리합니다.

---

## 1. [자동화] 일일 ASK/Todo 정리 스케줄 검증

**상세 내용:** 매일 17:55에 오늘 대화를 `ASK/`와 `Todo/`에 누적하는 스케줄 작업 `daily-ask-todo-log`를 만들었습니다. 정상 동작을 확인해야 합니다.

**체크리스트:**
- [ ] 사이드바 "Scheduled"에서 `daily-ask-todo-log` 작업이 보이는지 확인.
- [ ] 첫 자동 실행(17:55) 후 그날 `ASK/{날짜}_ai.md`에 블록이 누적됐는지 확인.
- [ ] 실행 항목이 있을 때 `Todo/{날짜}_*.md`가 생성되는지 확인.
- [ ] 앱이 꺼져 있던 날은 다음 실행 시 처리되는 점 유의.
- [ ] Codex 대화는 자동 수집이 안 되므로, 필요 시 KIBA 폴더에 Codex 메모를 남겨 반영.

---

## 2. [git 복구] main 잘못된 커밋(c487063) 정리

**상세 내용:** `git switch --orphan notes` 중단 후 잘못 실행된 명령으로 main에 `index.html`, `worker/`, `.gitignore`, `quali-fit` 등을 추적에서 삭제한 커밋이 생기고 index가 손상됐습니다. push는 실패해 GitHub은 안전합니다.

**체크리스트:**
- [ ] 손상된 index 복구(`git reset` 또는 `.git/index` 재생성) 후 상태 확인.
- [ ] 잘못된 커밋(c487063)을 되돌려 `index.html`·`worker/`·`quali-fit` 추적 복원.
- [ ] origin/main이 잘못된 커밋을 가리키지 않는지 확인 후 정상 커밋만 push.
- [ ] ASK/Todo 기록은 별도 `notes` 브랜치 대신 main에서 안전하게 유지.

---

## 3. [기록 유지] ASK/Todo 누적 루틴 정착

**상세 내용:** 오늘 대화는 `ASK/2026-06-17_ai.md`와 이 Todo 파일에 정리했습니다. 이후에도 자동/수동으로 기록을 누적합니다.

**체크리스트:**
- [ ] 자동 스케줄이 ASK 로그를 매일 누적하는지 주기적으로 점검.
- [ ] 실행할 일은 Todo 파일 또는 GitHub Issue로 분리.
- [ ] 중요한 결정 사항은 README 또는 Pages에 반영.
