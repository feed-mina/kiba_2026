# SW 대가 모니터링 충돌 정리 (2026-06-24)

> 목적: 모니터링 자동 갱신 이후 남은 JSON 충돌 표식을 정리해 다음 게시판 점검과 동기화가 깨지지 않도록 합니다.

---

## 1. `sw_guide` 상태 파일 충돌 해소

**상세 내용:** `data/sw_guide_latest.json`과 `scripts/sw_guide_state.json`에 남아 있는 merge conflict를 정리하고, 최신 점검 시각과 누적 상태 필드를 함께 보존합니다.

**체크리스트:**

- [ ] `data/sw_guide_latest.json`의 `checked_at`과 `tracking_since_year`를 포함해 충돌 표식 없이 정리.
- [ ] `scripts/sw_guide_state.json`의 `last_check`와 기존 `seen_bcidxs` 이력을 함께 보존하도록 정리.
- [ ] 충돌 정리 후 모니터링/동기화 스크립트가 다시 같은 파일에서 막히지 않는지 확인.
