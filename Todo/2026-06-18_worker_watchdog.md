# Cloudflare Worker 헬스 워치독 (2026-06-18)

> 목적: `kiba.kibayerin.workers.dev` 라우트가 간헐적으로 죽어 빈 404를 반환하는 사고(매트릭스 네트워크 오류·docs 다운로드 404의 공통 원인)를 자동 감지·복구합니다.
> 배경: `workers_dev=true`가 커밋돼 있는데도 같은 날 라우트가 다시 죽음(00:26 200 → 14:00 빈 404). 설정만으론 못 막아 워치독을 둔다.

---

## 1. [워치독] /health 자동 감시·재배포

**상세 내용:** `scripts/worker_healthcheck.ps1`이 `/health`를 확인해 200이 아니면(빈 404 포함) `worker/`에서 `npx wrangler deploy`로 자동 재배포하고, 전파(15~20초) 후 재확인한다. 결과는 `scripts/worker_health.log`에 기록.

**체크리스트:**

- [x] `worker_healthcheck.ps1` 작성 (정상 시 OK 로깅, 비정상 시 재배포→재확인).
- [x] `setup_worker_watchdog.ps1` 작성 (30분 간격 작업 등록 + CF 토큰 선택 저장).
- [x] Windows 작업 스케줄러 `KIBA Worker Watchdog` 30분 간격 등록.
- [x] 즉시 1회 실행으로 정상 동작 확인(`OK (/health 200)`).
- [ ] 무인 재배포 안정화를 위해 Cloudflare API 토큰 저장(`setup_worker_watchdog.ps1` 또는 `.cf_api_token.xml`). 미설정 시 wrangler OAuth로 시도하나 만료 시 실패할 수 있음.
- [ ] 실제 라우트 다운 발생 시 워치독이 자동 복구하는지 1회 관찰.

---

## 2. [후속] 근본 원인 추적 (선택)

**상세 내용:** 워치독은 증상 완화책이다. 라우트가 죽는 근본 원인(CI 배포 타이밍, Cloudflare 측 토글 등)을 추적해 재발 자체를 줄인다.

**체크리스트:**

- [ ] 라우트 다운 시각과 `deploy-worker`/수동 배포 시각 상관관계 분석.
- [ ] Cloudflare 대시보드에서 workers.dev 라우트 상태 직접 확인.
- [ ] 필요 시 커스텀 도메인 라우트로 전환 검토(workers.dev 의존 제거).
