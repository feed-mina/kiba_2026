# ASK/Todo·스케줄러·Worker 워치독 통합 운영 (Issue #13)

> 상태: ✅ 완료 (2026-06-26 종료) — 자동화 골격 구축·검증 완료, 남은 운영 판단은 보류/현행 유지로 결정하고 상시 운영으로 이관.
> 목적: 기존 Issue #9(ASK/Todo 자동화와 git 복구), Issue #13(스케줄러·Codex 자동 기록), Issue #17(Cloudflare Worker 워치독)을 하나의 운영 이슈로 통합 관리한다.
> 대표 이슈: #13
> 통합 대상: #9, #17

---

## 1. [운영 기준] 통합 범위 정리

**상세 내용:** ASK/Todo 기록, GitHub Issue 자동 반영, 문서 백업/R2 동기화, Worker 배포·헬스체크를 분리된 이슈 대신 하나의 운영 흐름으로 관리한다.

**체크리스트:**

- [x] Issue #9의 ASK/Todo 자동화·git 복구 후속 작업을 #13으로 통합.
- [x] Issue #17의 Worker 헬스 워치독 후속 작업을 #13으로 통합.
- [x] #9와 #17에는 #13으로 통합했다는 댓글을 남기고 닫는다.
- [x] #13 제목과 본문이 통합 운영 이슈임을 GitHub에서 확인. (2026-06-26 확인: 제목 "ASK/Todo·스케줄러·Worker 워치독 통합 운영")

---

## 2. [ASK/Todo 자동화] 일일 기록 및 GitHub 반영

**상세 내용:** Claude/Codex 작업 내용을 `ASK/`와 `Todo/`에 남기고, Todo는 GitHub Issue와 Pages 보드에 자동 반영한다.

**체크리스트:**

- [x] `daily-ask-todo-log` 작업 생성 및 수동 테스트 완료.
- [x] `daily-codex-ask-todo-log` 자동화 생성.
- [x] 매일 17:55에 `C:\Users\User\Desktop\KIBA` 기준으로 ASK/Todo commit/push 및 R2 동기화 수행하도록 설정.
- [x] `todo-reflect.yml`이 Todo 문서를 GitHub Issue와 Pages 보드에 반영하도록 구성.
- [x] 첫 자동 실행 후 ASK/Todo에 Codex 블록이 정상 누적되는지 확인. (2026-06-26 확인: ASK 2026-06-17~06-26 Codex 블록 누적)
- [x] 자동 스케줄이 ASK 로그를 매일 누적하는지 주기적으로 점검. (상시 운영 항목으로 이관; `KIBA Claude ASK Todo Log` 작업 Ready, 06-26 로그까지 누적 확인)

---

## 3. [문서 백업/R2 동기화] 다운로드와 스케줄러 안정화

**상세 내용:** `download_docs_scheduled.ps1`을 통해 문서 다운로드, ASK/Todo git push, R2 동기화를 운영한다. Worker 라우트 문제와 DPAPI 실행 사용자 문제는 별도 점검한다.

**체크리스트:**

- [x] `.\scripts\download_docs_scheduled.ps1 -SkipDownload` 수동 실행.
- [x] ASK/Todo 변경을 main에 push하고 docs/ASK/Todo를 R2에 업로드/동기화.
- [x] 18:00 중복 Windows 트리거는 등록하지 않기로 결정. Codex 자동화가 17:55에 보충 수행.
- [x] Worker 배포 상태 복구 후 `/docs/list` 200 응답 확인.
- [x] 수동 실행 시 DPAPI 암호 파일이 현재 실행 컨텍스트에서 풀리지 않는 문제(`Key not valid for use in specified state`) 해결 여부 결정. (결정: **보류** — 현행 수동 실행 컨텍스트 유지, 무인 자동화 전환 시 재검토)
- [x] 필요 시 `setup_docs_schedule.ps1`을 실제 스케줄러 실행 사용자로 다시 실행해 `scripts/.docs_password.xml` 재생성. (현 시점 불필요 — DPAPI 무인화 보류로 N/A, 필요 시 재실행)

---

## 4. [Worker 워치독] 404 자동 감지·복구

**상세 내용:** `kiba.kibayerin.workers.dev`가 간헐적으로 빈 404를 반환하는 문제를 `/health` 감시와 자동 재배포로 완화한다.

**체크리스트:**

- [x] `scripts/worker_healthcheck.ps1` 작성.
- [x] `scripts/setup_worker_watchdog.ps1` 작성.
- [x] 워치독 기본 주기를 30분에서 5분으로 조정. workers.dev 라우트가 8~15분 단위로 흔들리는 현상 대응.
- [x] 실제 `/health = 404` 발생 시 자동 재배포 후 `/health 200` 복구 확인. 2026-06-19 11:26, 12:31, 12:41, 12:46, 12:51 로그 확인.
- [x] 2026-06-19 현재 `/health` 직접 확인 결과 200 OK.
- [x] 무인 재배포 안정화를 위해 Cloudflare API 토큰 저장(`scripts/.cf_api_token.xml`) 여부 결정. 현재는 wrangler OAuth에 의존. (결정: **보류** — 토큰 평문 저장 리스크 고려해 wrangler OAuth 유지, OAuth 만료 빈발 시 재검토)
- [x] Windows 작업 스케줄러에 현재 PC 기준 `KIBA Worker Watchdog`가 실제 등록되어 있는지 권한 있는 세션에서 재확인. (2026-06-26 확인: 작업 "KIBA Worker Watchdog" State=Ready)
- [x] Cloudflare 대시보드에서 workers.dev 라우트 상태 직접 확인. (2026-06-26 확인: `/health`=200 OK, `/docs/list`=403 인증필요 → 라우트 정상 동작)
- [x] 필요 시 커스텀 도메인 라우트로 전환 검토. (검토 결과: 현행 workers.dev 유지 — `/health` 안정, 워치독으로 완화. 404 재발 빈번해지면 전환 재검토)

---

## 5. [Git 복구 및 운영 문서] 완료된 복구 내역

**상세 내용:** 2026-06-17의 git index 손상과 잘못된 main 커밋 문제는 복구 완료했다. 관련 기록은 운영 이슈의 배경으로만 유지한다.

**체크리스트:**

- [x] 손상된 git index 복구.
- [x] 잘못된 커밋은 복구 커밋으로 추적 파일 복원 확인.
- [x] origin/main에 정상 커밋 push 완료.
- [x] ASK/Todo 기록은 별도 notes 브랜치 대신 main에서 유지.
- [x] GitHub CLI portable 설치 및 `.tools/` gitignore 처리.

---

## 6. [남은 운영 리스크] — 알려진 잔여 리스크로 수용·문서화 (이슈 종료 시점)

**체크리스트:**

- [x] (수용) Cloudflare API 토큰 저장 전까지 Worker 자동 복구는 wrangler OAuth 만료에 취약함. → 토큰 저장 보류 결정에 따른 알려진 리스크로 수용.
- [x] (수용) DPAPI 암호 파일은 생성 사용자/실행 사용자 차이에 따라 스케줄러에서 실패할 수 있음. → 무인화 보류, 수동 실행 컨텍스트로 대응.
- [x] (수용) Worker 404의 근본 원인은 아직 확정되지 않았고, 워치독은 완화책임. → 워치독(5분 주기, 자동 재배포)으로 완화 운영.
- [x] 자동화가 너무 많아졌으므로 대표 이슈 #13에서만 상태를 관리하고, 중복 이슈는 닫힌 상태로 유지. (확인 완료 — #9·#17 닫힘 유지)
