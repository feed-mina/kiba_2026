# GitHub Projects v2 권한 및 ASK/Todo Codex 자동 업데이트

> 목적: GitHub Projects v2 보드 자동 추가 실패를 복구하고, Codex가 작성하는 ASK/Todo 기록이 GitHub Issue와 Pages 보드에 자동 반영되도록 한다.

## 1. [권한] Projects v2 토큰 갱신

**상태:** 완료 (2026-06-19)

**확인된 문제**
- `add-to-project` workflow 실패 원인: `ADD_TO_PROJECT_PAT`가 `Bad credentials` 상태.
- 로컬 `gh project view 3 --owner feed-mina` 실패 원인: 현재 CLI 토큰에 `read:project` scope 없음.

**해결 결과**
- [x] 로컬 터미널에서 `gh auth refresh -h github.com -s read:project -s project` 실행.
- [x] 토큰 발급 — fine-grained PAT는 user Projects 쓰기가 막혀(`Resource not accessible`) **Classic PAT**로 전환. 필요한 scope: `repo`, `project`, `read:org`, `read:discussion`(없으면 `gh project item-add`가 `unknown owner type`로 실패).
- [x] `ADD_TO_PROJECT_PAT` repository secret 교체 — `gh secret set`에 stdin 사용(`--body -`는 값을 `-`로 저장하니 금지).
- [x] 권한 확인 — `gh api graphql`로 Project #3(`PVT_kwHOBc53JM4Ba3_X`) 읽기·쓰기 확인.

## 2. [자동화] 새 이슈 Project 자동 추가

**상태:** 완료 (2026-06-19)

**검증 결과**
- [x] `PROJECT_URL`이 `https://github.com/users/feed-mina/projects/3`인지 확인.
- [x] 새 이슈(#26)를 열어 `add-to-project.yml` 성공 확인 — Project #3에 자동 추가됨(검증 후 #26 닫음).
- [x] 실패 시 Actions 로그의 credentials/scope 메시지 확인 — 교체 전 `Bad credentials`/`unknown owner type` 메시지로 원인 추적함.

## 3. [자동화] 기존 이슈 Project backfill

**상태:** 완료 (2026-06-19)

**실행 결과**
- [x] `project-backfill.yml` 수동 실행 (success).
- [x] 열린 이슈 22건이 Project #3에 추가됨(아이템 24건).
- [x] closed/all 이슈 추가 — 현재 open 백필로 충분하다고 판단, 미실행으로 결정.

## 4. [자동화] ASK/Todo Codex 반영

**상태:** 완료 (2026-06-19)

**검증 결과**
- [x] `ASK/**`·`Todo/**` 모두 `todo-reflect.yml` 트리거에 포함됨(yml `paths` 확인).
- [x] `Todo/**` 변경 시 GitHub Issue·Pages 보드 갱신 확인(수동 dispatch로 재생성).
- [x] 동시 push 경합 시 `git pull --rebase origin main` retry로 회복 확인(연속 reflect 커밋 정상 처리).

## 참고 문서

- `.github/PROJECTS_V2_SETUP.md`
- `.github/workflows/todo-reflect.yml`
- `.github/workflows/add-to-project.yml`
- `.github/workflows/project-backfill.yml`
