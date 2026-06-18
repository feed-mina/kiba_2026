# 스케줄러 및 Codex ASK/Todo 자동화 후속 작업 (2026-06-18)

> 목적: 2026년 6월 18일 확인된 스케줄러 404 실패, 누락 실행 보충, Codex 쪽 ASK/Todo 자동 기록 구성을 관리합니다.

---

## 1. [스케줄러] 오늘 09:00 실행 실패 원인 확인

**상세 내용:** `KIBA Docs Download`는 오늘 09:00에 실행됐지만 `/docs/list` 호출에서 404가 발생했습니다. 로컬 Worker에는 해당 라우트가 있으므로 배포본이 최신인지 확인해야 합니다.

**체크리스트:**

- [x] `scripts/download_docs.log`에서 오늘 09:00 실행 기록 확인.
- [x] 실제 `/docs/list?repo=feed-mina%2Fkiba_2026` 호출이 404를 반환하는지 확인.
- [ ] Cloudflare Worker 배포 상태와 GitHub Actions `deploy-worker` 실행 여부 확인.
- [x] 최신 `worker/worker.js`를 Cloudflare에 재배포한 뒤 `/docs/list`가 200을 반환하는지 확인. (2026-06-18: DOCS_PASSWORD 재설정 후 `kiba1234`로 200·files 응답 확인. 이전 404는 미배포가 아니라 workers.dev 라우트 플래핑이 원인 — 5분 워치독이 완화.)

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

---

## 4. [Git 공유] 자동화/스케줄러/Claude/Codex 관련 파일 묶음 공유

**상세 내용:** 자동화와 스케줄러 운영에 필요한 스크립트, GitHub Actions, ASK/Todo 운영 문서를 Git에 공유 가능한 형태로 정리합니다. 민감 정보가 들어가는 DPAPI 암호 파일, R2 자격증명, 로그 파일, 다운로드 문서 원본은 `.gitignore` 기준으로 제외합니다.

**공유 대상 파일:**
- `ASK/README.md`: Claude/Codex 질문·응답 로그 작성 규칙.
- `ASK/2026-06-17_ai.md`, `ASK/2026-06-18_ai.md`: Claude/Codex 작업 누적 로그.
- `Todo/2026-06-17_automation_and_git_recovery.md`: ASK/Todo 자동화 및 git 복구 후속 작업.
- `Todo/2026-06-18_scheduler_codex_automation.md`: 스케줄러, 다운로드, Codex 자동 기록 후속 작업.
- `scripts/setup_docs_schedule.ps1`: 문서 다운로드 Windows 작업 스케줄러 등록.
- `scripts/download_docs_scheduled.ps1`: 문서 다운로드, ASK/Todo git push, R2 동기화 래퍼.
- `scripts/download_docs.ps1`: Worker 문서 다운로드 클라이언트.
- `scripts/setup_r2_sync.ps1`: R2 동기화 자격증명/설정 등록.
- `scripts/setup_sw_guide_schedule.ps1`, `scripts/watch_sw_guide_scheduled.ps1`, `scripts/watch_sw_guide.py`: SW 대가 가이드 모니터링.
- `scripts/setup_worker_watchdog.ps1`, `scripts/worker_healthcheck.ps1`: Worker 장애 감지·복구 스케줄러.
- `.github/workflows/todo-reflect.yml`: Todo 문서를 GitHub Issue와 Pages 보드에 반영.
- `.github/workflows/watch-sw-guide.yml`: SW 대가 가이드 GitHub Actions 모니터링.
- `.github/workflows/deploy-worker.yml`: Worker 배포 자동화.

**2026-06-18 점검 결과:**
- [x] GitHub CLI `gh` portable 설치 완료: `C:\Users\User\Desktop\KIBA\.tools\gh\bin\gh.exe`.
- [x] `.tools/`는 `.gitignore`에 추가해 설치 파일이 커밋되지 않도록 처리.
- [x] `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\download_docs_scheduled.ps1`로 수동 다운로드 실행 시도.
- [ ] 다운로드 실패 원인 1: 13:00 자동 실행 로그 기준 Worker `/docs/list` 404 재발.
- [ ] 다운로드 실패 원인 2: 수동 실행 시 DPAPI 암호 파일이 현재 실행 컨텍스트에서 풀리지 않아 `Key not valid for use in specified state` 발생.
- [ ] `setup_docs_schedule.ps1`을 실제 스케줄러 실행 사용자로 다시 실행해 `scripts/.docs_password.xml`을 재생성할지 결정.
- [ ] Worker 배포 상태를 복구한 뒤 `/docs/list` 200 응답 확인.
