# Cloudflare Worker 헬스 워치독 (Issue #17)
<!-- merged-into: #13 -->

> 상태: Issue #13으로 통합 완료. (일일 Todo 보드에서 자동 숨김)
> 대표 이슈: #13 ASK/Todo·스케줄러·Worker 워치독 통합 운영

---

## 1. [통합] Worker 워치독 운영 이관

**상세 내용:** Worker 404 감지·자동 재배포·Cloudflare 토큰 안정화·라우트 근본 원인 추적은 Issue #13에서 통합 관리한다.

**체크리스트:**

- [x] `worker_healthcheck.ps1` 구현 내역을 Issue #13으로 이관.
- [x] `setup_worker_watchdog.ps1` 구현 내역을 Issue #13으로 이관.
- [x] 2026-06-19 실제 `/health = 404` 자동 복구 확인 내역을 Issue #13에 반영.
- [x] 워치독 기본 주기 5분 변경 사항을 Issue #13에 반영.
- [x] 본 이슈는 중복 추적을 막기 위해 닫음.

## 2. [남은 일] Issue #13에서 계속 관리

**체크리스트:**

- [ ] Cloudflare API 토큰 저장 여부 결정.
- [ ] 현재 PC 기준 Windows 작업 스케줄러 등록 상태 재확인.
- [ ] Cloudflare 대시보드에서 workers.dev 라우트 상태 확인.
- [ ] 필요 시 커스텀 도메인 라우트 전환 검토.
