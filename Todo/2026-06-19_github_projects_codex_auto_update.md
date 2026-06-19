# GitHub Projects v2 권한 및 ASK/Todo Codex 자동 업데이트

> 목적: GitHub Projects v2 보드 자동 추가 실패를 복구하고, Codex가 작성하는 ASK/Todo 기록이 GitHub Issue와 Pages 보드에 자동 반영되도록 한다.

## 1. [권한] Projects v2 토큰 갱신

**상태:** 진행 중

**확인된 문제**
- `add-to-project` workflow 실패 원인: `ADD_TO_PROJECT_PAT`가 `Bad credentials` 상태.
- 로컬 `gh project view 3 --owner feed-mina` 실패 원인: 현재 CLI 토큰에 `read:project` scope 없음.

**다음 할 일**
- [ ] 로컬 터미널에서 `gh auth refresh -h github.com -s read:project -s project` 실행.
- [ ] GitHub fine-grained PAT를 새로 만들고 `Projects: Read and write`, `Issues: Read and write` 권한 부여.
- [ ] `ADD_TO_PROJECT_PAT` repository secret 교체.
- [ ] `gh project view 3 --owner feed-mina`로 권한 확인.

## 2. [자동화] 새 이슈 Project 자동 추가

**상태:** 보강 완료, 토큰 교체 후 검증 필요

**다음 할 일**
- [ ] `PROJECT_URL`이 `https://github.com/users/feed-mina/projects/3`인지 확인.
- [ ] 새 이슈를 하나 열어 `add-to-project.yml` 성공 여부 확인.
- [ ] 실패 시 Actions 로그의 credentials/scope 메시지 확인.

## 3. [자동화] 기존 이슈 Project backfill

**상태:** workflow 추가 완료, 토큰 교체 후 실행 필요

**다음 할 일**
- [ ] `project-backfill.yml` 수동 실행.
- [ ] 열린 이슈가 Project #3에 추가됐는지 확인.
- [ ] 필요하면 closed/all 이슈도 추가.

## 4. [자동화] ASK/Todo Codex 반영

**상태:** workflow 보강 완료

**다음 할 일**
- [ ] `ASK/**` 변경도 `todo-reflect.yml` 트리거에 포함됐는지 push 후 확인.
- [ ] `Todo/**` 변경 시 GitHub Issue와 Pages 보드가 갱신되는지 확인.
- [ ] 동시 push 경합이 발생해도 `git pull --rebase origin main` retry로 회복되는지 확인.

## 참고 문서

- `.github/PROJECTS_V2_SETUP.md`
- `.github/workflows/todo-reflect.yml`
- `.github/workflows/add-to-project.yml`
- `.github/workflows/project-backfill.yml`
