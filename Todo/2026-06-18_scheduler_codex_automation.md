# 스케줄러 및 Codex ASK/Todo 자동화 후속 작업 (2026-06-18)

> 목적: 2026년 6월 18일 확인된 스케줄러 404 실패, 누락 실행 보충, Codex 쪽 ASK/Todo 자동 기록 구성을 관리합니다.

---

## 1. [스케줄러] 오늘 09:00 실행 실패 원인 확인

**상세 내용:** `KIBA Docs Download`는 오늘 09:00에 실행됐지만 `/docs/list` 호출에서 404가 발생했습니다. 로컬 Worker에는 해당 라우트가 있으므로 배포본이 최신인지 확인해야 합니다.

**체크리스트:**

- [x] `scripts/download_docs.log`에서 오늘 09:00 실행 기록 확인.
- [x] 실제 `/docs/list?repo=feed-mina%2Fkiba_2026` 호출이 404를 반환하는지 확인.
- [ ] Cloudflare Worker 배포 상태와 GitHub Actions `deploy-worker` 실행 여부 확인.
- [ ] 최신 `worker/worker.js`를 Cloudflare에 재배포한 뒤 `/docs/list`가 200을 반환하는지 확인.

---

## 2. [보충 실행] 어제 빠진 18:00 백업/동기화 보충

**상세 내용:** 실제 Windows 작업 스케줄러에는 18:00 트리거가 등록되어 있지 않았습니다. 다운로드 단계는 404로 실패하므로, `-SkipDownload`로 ASK/Todo git push와 R2 동기화만 보충했습니다.

**체크리스트:**

- [x] `.\scripts\download_docs_scheduled.ps1 -SkipDownload` 수동 실행.
- [x] 오늘 ASK/Todo 파일을 `chore: ASK/Todo logs 2026-06-18 09:11` 커밋으로 main에 push.
- [x] docs/ASK/Todo를 R2에 업로드/동기화.
- [ ] Windows 작업 스케줄러에 18:00 트리거를 실제로 다시 등록할지 결정.

---

## 3. [Codex] Codex 쪽 ASK/Todo 자동 기록 추가

**상세 내용:** Claude 쪽 기록뿐 아니라 Codex 작업도 매일 ASK/Todo에 남기고 git/R2에 반영되도록 Codex 앱 자동화를 추가했습니다.

**체크리스트:**

- [x] Codex 자동화 `daily-codex-ask-todo-log` 생성.
- [x] 매일 17:55에 `C:\Users\User\Desktop\KIBA`에서 실행되도록 설정.
- [x] ASK/Todo 변경 commit/push 후 `scripts/download_docs_scheduled.ps1 -SkipDownload`로 백업·동기화하도록 설정.
- [ ] 첫 자동 실행 후 ASK/Todo에 Codex 블록이 정상 누적되는지 확인.
