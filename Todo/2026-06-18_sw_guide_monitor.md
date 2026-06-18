# SW 대가 산정 가이드 자동 모니터링·데이터화 (2026-06-18)

> 목적: 소프트웨어산업협회 "SW사업대가" 게시판(cbIdx=276)을 자동 감시해, 새 대가산정 가이드/인건비/엑셀 템플릿이 올라오면 KIBA 보드(Issue #3)와 quali-fit 관리 화면에서 바로 알 수 있게 합니다.
> 관련: 원장님 요구 #3 [대가 산정] / GitHub Issue #3.

---

## 1. [Phase 1·구현완료] 게시판 변경 감지 + 알림

**상세 내용:** `scripts/watch_sw_guide.py` 가 게시판 1페이지를 받아 글(bcIdx/제목/등록일/첨부)을 파싱하고, `scripts/sw_guide_state.json` 의 "이미 본 bcIdx" 와 비교해 새 글을 감지합니다. 관심 키워드(대가/인건비/가이드/템플릿/단가/산정) 매칭 글이 새로 올라오면 알림을 보냅니다. 표준 라이브러리만 사용(=`reflect_todo.py` 와 동일 패턴).

**체크리스트:**

- [x] 게시판 파서 작성 및 라이브 검증(현재 관심 9건 파싱 확인).
- [x] 첫 실행 시드 모드(기존 글을 기준선으로 기록, 알림 없음)로 과거 글 무더기 알림 방지.
- [x] GitHub Actions 워크플로 `watch-sw-guide.yml` — 매일 09:30 KST cron + 수동 실행.
- [x] Windows 작업 스케줄러 백업(`setup_sw_guide_schedule.ps1`, 매일 09:10) — Actions 장애/IP 차단 대비.
- [ ] 첫 cron 실행 후 정상 동작 및 커밋(`[skip ci]`) 확인.

---

## 2. [Phase 1·알림 경로] Issue #3 코멘트 + Pages JSON 피드

**상세 내용:** 새 글 감지 시 두 경로로 알립니다. (1) GitHub Issue #3 에 코멘트 + `대가산정-업데이트` 라벨(Actions 의 GITHUB_TOKEN). (2) `data/sw_guide_latest.json` 피드를 갱신해 GitHub Pages 로 공개(`https://feed-mina.github.io/kiba_2026/data/sw_guide_latest.json`). quali-fit 관리 화면이 이 피드를 fetch 해 "새 가이드 있음" 배너를 띄웁니다.

**체크리스트:**

- [x] Issue #3 코멘트/라벨 등록 로직.
- [x] `data/sw_guide_latest.json` 피드 생성(최신 가이드 + 최근 목록 + new_since_last_check).
- [ ] quali-fit(`?mode=manage&cat=employee_group&svc=employee`)에서 피드 fetch → 배너 표시 코드 추가. (quali-fit 저장소: bookseal/quali-fit)
- [ ] KIBA 페이지에서도 피드를 읽어 헤더 근처에 "최신 가이드: …" 표시할지 결정.

---

## 3. [Phase 2·후속] PDF 데이터화 (대가 계산 로직)

**상세 내용:** 감지·보관을 넘어, 가이드 PDF 안의 기능점수(FP) 산정식과 인건비 단가표를 구조화 데이터로 추출해 견적/대가 계산 로직에 반영합니다. Phase 1 과 난이도가 크게 달라 분리합니다.

**체크리스트:**

- [ ] 새 PDF 첨부를 R2(기존 `DOCS_BUCKET`)에 자동 보관(Worker `/upload` 또는 rclone).
- [ ] PDF 파싱으로 인건비 단가표 → 표 형태 데이터 추출.
- [ ] FP 산정식 분석 → 계산 모듈 설계.
- [ ] 과거 버전(2025 등) → 최신 기준으로 자동 교체/버전 관리.
