# KIBA Pages 및 GitHub Issue 운영 후속 작업 (2026-06-17)

> 목적: 2026년 6월 17일 Codex 작업 중 정리된 KIBA Pages, GitHub Issue, `bookseal/quali-fit` 연동 관련 후속 작업을 관리합니다.

---

## 1. [GitHub Pages] KIBA 진행 페이지 공개 확인

**상세 내용:** `feed-mina/kiba_2026`의 Pages가 `main / root` 기준으로 정상 배포되는지 확인해야 합니다.

**체크리스트:**
- [x] GitHub Pages 설정에서 `Source = Deploy from a branch` 선택.
- [x] Branch를 `main`, Folder를 `/root`로 설정.
- [x] `https://feed-mina.github.io/kiba_2026/` 접속 확인(자동 배포 동작 중).
- [x] 모바일/노트북 화면에서 보드와 메모창이 깨지지 않는지 확인. (2026-06-18 점검: 375px 가로 오버플로 없음, 메모 모달 정상; 데스크톱 .wrap 1120px 중앙정렬)

---

## 2. [진행 보드] KIBA Issue 상태 관리 규칙 정하기

**상세 내용:** 현재 KIBA 이슈 5개는 임시로 `다음에 할 일 / 지금 하는 중 / 끝난 일`에 배치되어 있으므로, 실제 운영 규칙이 필요합니다.

**체크리스트:**
- [x] 이슈 라벨 후보 정하기 → `todo`/`doing`/`done` 상태 라벨 채택(생성 완료). `quali-fit`/`meeting`은 필요 시 추가.
- [x] KIBA 요구사항 Issue #1~#5에 라벨 부여 → 모두 `doing` 부여(진행 중).
- [x] 완료된 이슈가 생기면 `끝난 일` 영역으로 옮기는 기준 정하기 → Todo 체크리스트 `done==total`이면 자동으로 Pages 보드 "끝난 일" 아코디언(`<details>`)으로 이동(2026-06-19 reflect_todo.py 반영). 이슈는 `done` 라벨.
- [x] 매주 회의 후 Pages 보드 업데이트 루틴 정하기 → 보드는 `ASK/**`·`Todo/**` push 시 `todo-reflect`가 자동 갱신, 주간 회의록은 `meetings/`로 누적·반영.

---

## 3. [quali-fit 연동] 원본 진행 화면 반영 방식 유지

**상세 내용:** `bookseal/quali-fit` Pages의 진행 화면을 KIBA Pages에서도 함께 보여주도록 통합했으므로, 이후 원본 변경사항을 반영하는 절차가 필요합니다.

**체크리스트:**
- [x] `bookseal/quali-fit` 원본 Pages 변경 시 KIBA Pages에도 반영할지 확인 → 서브모듈 포인터 최신화로 반영하기로 결정.
- [x] `quali-fit/` 서브모듈 포인터를 최신 커밋으로 유지할지 결정 → 유지(주기적 업데이트).
- [x] KIBA 페이지의 `quali-fit` 태그와 연결 섹션 위치를 계속 유지 → 통합 보드 + 접이식 원본 섹션 유지.
- [x] 원본 링크와 KIBA 요약 내용이 서로 어긋나지 않는지 주기적으로 확인 → 주간 회의 시 점검 루틴으로 운영.

---

## 4. [의견 메모] 과업별 의견 수집 흐름 개선

**상세 내용:** 과업 카드를 클릭하면 초록색 메모창이 뜨고 의견을 작성할 수 있게 했습니다. 정적 Pages 환경에서는 자동 GitHub 댓글 작성에 제한이 있으므로 안전한 저장 흐름을 정해야 합니다.

**체크리스트:**
- [x] 현재 메모창 UI 동작 확인: 카드 클릭, 의견 작성, 저장, 복사, 이슈 열기 → 메모 모달 정상 동작 확인(2026-06-18 점검).
- [x] 의견이 어느 GitHub Issue에 모일지 운영 기준 정하기 → quali-fit 의견은 #7(`qfCollectorIssue`), 과업 카드는 각 이슈에 적재.
- [x] 서버리스 함수 또는 GitHub Actions를 사용할지 결정 → Cloudflare Worker(`kiba`) 프록시 채택.
- [x] 자동 저장이 필요하면 인증 토큰을 HTML에 넣지 않는 방식으로 설계 → 토큰은 Worker 시크릿에만 보관(HTML 비노출).
- [x] 의견이 들어온 후 HTML 보드에 반영하는 업데이트 절차 정하기 → 카드의 `/counts` 코멘트 수 표시로 반영. ⚠️ 단 현재 Worker `GITHUB_TOKEN` 만료로 0 반환(섹션 6 참고) → 토큰 재설정 필요.

---

## 5. [문서 관리] ASK와 Todo 기록 유지

**상세 내용:** 오늘 대화는 `ASK/2026-06-17_ai.md`와 이 Todo 파일에 정리했습니다. 이후에도 작업 후 기록을 누적합니다.

**체크리스트:**
- [x] 하루 작업 종료 시 ASK 로그에 질문·응답 요약 누적 → `ASK/YYYY-MM-DD_ai.md`에 Claude/Codex 블록 누적(운영 중).
- [x] 실행해야 할 일은 Todo 파일 또는 GitHub Issue로 분리 → `Todo/*.md` ↔ Issue 자동 반영(`todo-reflect`).
- [x] 중요한 결정 사항은 README 또는 Pages에 반영 → Pages 보드·README로 반영.
- [x] 내부 원문 문서는 `docs/`에 두되 Git 추적 제외 유지 → `.gitignore`로 제외 유지.

---

## 6. [서버리스] 의견 메모 → GitHub Issue 연동 (Claude, 완료분 포함)

**상세 내용:** 정적 Pages의 메모창 의견을 Cloudflare Worker(`kiba`)를 거쳐 GitHub Issue 코멘트로 익명 등록하도록 구현했습니다. 토큰은 Worker 시크릿에만 보관합니다.

**체크리스트:**
- [x] Cloudflare Worker 프록시(`worker/worker.js`) 작성·배포: 출처/저장소 allowlist + Turnstile + 허니팟.
- [x] `index.html` `CONFIG`에 `apiBase`, Turnstile Site key, `qfCollectorIssue: 7` 반영.
- [x] Worker 시크릿 `GITHUB_TOKEN`, `TURNSTILE_SECRET` 등록.
- [x] CORS 네트워크 오류 해결(재배포로 `ALLOWED_ORIGINS` 활성) 후 등록 성공 확인.
- [x] quali-fit 카드로 #7에 코멘트가 정상 적재되는지 최종 확인. (2026-06-19: Worker `GITHUB_TOKEN` 만료로 `/counts`가 `{"7":0}` 반환하던 것을 `wrangler secret put GITHUB_TOKEN` 재설정 후 `{"7":3}`으로 GitHub 실제 코멘트 수와 일치 확인. 코멘트 표시·등록 복구.)
- [x] 노출됐던 GitHub 토큰 폐기(Revoke) 여부 최종 확인. (2026-06-19 폐기 완료. Worker `GITHUB_TOKEN`·`ADD_TO_PROJECT_PAT` 모두 신규 토큰으로 교체됨.)

---

## 7. [CI/CD] worker 자동 배포 Action 마무리

**상세 내용:** `worker/`가 바뀐 채 push되면 `wrangler deploy`가 자동 실행되도록 `.github/workflows/deploy-worker.yml`을 추가했습니다.

**체크리스트:**
- [x] `deploy-worker.yml` 작성(`worker/**` 경로 변경 시 트리거).
- [x] Cloudflare API 토큰 발급(권한: Workers Scripts = Edit).
- [x] GitHub 시크릿 `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`(=`4a361c3d62b0241354ada304a4f94482`) 등록. (2026-06-19 secret list 확인.)
- [x] 워크플로 push 후 Actions 탭에서 성공(초록색) 확인. (deploy-worker 최근 실행 success.)

---

## 8. [정리] Cloudflare 정적 빌드 충돌 방지

**상세 내용:** `kiba_2026`에 연결된 Cloudflare Workers Build가 저장소를 "정적 사이트"로 감지해 API Worker를 덮어쓸 위험이 있습니다.

**체크리스트:**
- [x] GitHub의 #6 PR("Add Cloudflare Workers configuration")은 머지하지 말고 닫기. (2026-06-19 close 완료.)
- [ ] Cloudflare 대시보드 → `kiba` → Settings → Builds에서 깃 연동(Workers Build) 해제. (대시보드 작업 — 사용자 진행 필요.)
- [x] 이후 worker 배포는 `deploy-worker.yml`(GitHub Actions)만 사용. (운영 기준 확정.)

---

## 9. [자동 배포 구조 정리]

**상세 내용:** 세 가지 배포 경로가 각각 독립적으로 동작합니다.

**체크리스트:**
- [x] KIBA 페이지(`feed-mina.github.io/kiba_2026`): GitHub Pages가 `main` push 시 자동 배포.
- [x] quali-fit 앱(`quali-fit.bit-habit.com`): `bookseal/quali-fit`의 `deploy.yml`이 push→SSH→서버로 자동 배포(단, 그 저장소에 push해야 함).
- [x] worker(API): 신규 `deploy-worker.yml`로 자동 배포.
- [ ] quali-fit은 서브모듈이라 `kiba_2026` push로는 배포되지 않음을 팀과 공유. (팀 공유 — 사용자 진행 필요.)
