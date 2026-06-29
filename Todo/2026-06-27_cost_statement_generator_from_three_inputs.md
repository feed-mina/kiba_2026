# 3개 입력 엑셀 기반 원가계산서 생성기

> 목적: sample1, sample2 원가계산보고서 형식을 참고해 `단가대비표`, `일위대가표`, `내역서(물량)` 3개 Excel 파일을 입력하면 집계표를 자동 생성하고 수식이 연결된 `원가계산서` Excel workbook을 생성한다.
> GitHub Issue: https://github.com/feed-mina/kiba_2026/issues/42

---

## 0. [이슈 생성] 작업 추적 연결

**상세 내용:** 기존 sample_ver1 DB 설계와 별도 작업으로, 3개 입력 Excel 기반 원가계산서 생성기를 새 GitHub Issue에서 추적한다.

- [x] GitHub Issue #41 생성: `3개 입력 엑셀 기반 원가계산서 생성기 구축`
- [x] `todo` 라벨 적용
- [x] 로컬 Todo 항목 추가
- [x] GitHub Pages 로컬 화면에 원장님용 생성 UI 패널 추가
- [x] Quartz 지식베이스 로컬 콘텐츠에 #40/#41과 `엑셀생성` 활동 추가
- [x] GitHub Pages/Cloudflare Pages 배포 후 실제 URL 표시 확인. (`/notes/cost-statement-generator`, HTTP 200 + Cloudflare Access 로그인 확인)

## 1. [패턴 확인] sample1/sample2 생성 기준 비교

**상세 내용:** sample1과 sample2 workbook은 같은 시트명과 수식 체인을 공유하며, `단가대비표`, `일위대가표`, `내역서`가 `집계표`, `원가계산서`, `결과`로 이어진다. 생성기는 우선 템플릿 workbook의 `원가계산서` 레이아웃과 수식을 유지하고, 3개 입력 시트의 XML cell data를 교체한 뒤 `집계표`를 내역서 합계행 기준으로 자동 연결하는 방식으로 구현한다.

- [x] sample_ver1 최종 총액 확인: `원가계산서!E34 = 123,387,460`
- [x] sample_ver2 최종 총액 확인: `원가계산서!E34 = 109,104,460`
- [x] 공통 입력 시트 확정: `단가대비표`, `일위대가표`, `내역서(물량)`
- [x] `집계표`는 입력이 없으면 내역서 합계행 기준으로 자동 생성
- [x] 출력 workbook 기준 확정: 템플릿의 `원가계산서`/`결과` 수식 체인 유지

## 2. [MVP 구현] 3개 입력 Excel -> 원가계산서 workbook

**상세 내용:** `scripts/build_cost_statement_workbook.py`를 추가해 세 입력 파일에서 대상 시트를 찾아 템플릿 workbook에 주입한다. Excel이 열릴 때 수식 재계산을 수행하도록 workbook 계산 속성을 `auto`, `fullCalcOnLoad`, `forceFullCalc`로 맞춘다.

- [x] CLI 인자 추가: `--price-comparison`, `--unit-cost`, `--detail`, `--summary`, `--output`
- [x] 템플릿 선택 추가: `--template` 또는 `--template-version ver1|ver2`
- [x] 입력 workbook에서 정확한 시트명 우선 탐색
- [x] 시트명이 다를 때 기존 role 추론 로직으로 fallback
- [x] 템플릿의 `단가대비표`, `일위대가표`, `내역서` sheet XML cell data 교체
- [x] `--summary`가 없을 때 `집계표`를 내역서 합계행 기준으로 자동 연결
- [x] 출력 workbook 생성

## 3. [검증] sample 기반 smoke test

**상세 내용:** 분리된 샘플 입력 파일(`sample_단가대비표.xlsx`, `sample_일위대가표.xlsx`, `sample_내역서.xlsx`)로 round-trip 검증한다.

- [x] `py_compile` 통과
- [x] sample_ver1 생성: `outputs/issue41/sample_ver1_generated_원가계산서.xlsx`
- [x] sample_ver1 golden 검증: `checks=2/2`, `comparisons=1/1`, diff `0`
- [x] sample_ver2 생성: `outputs/issue41/sample_ver2_generated_원가계산서.xlsx`
- [x] sample_ver2 golden 검증: `checks=2/2`, `comparisons=1/1`, diff `0`
- [x] 실제 분리된 `단가대비표.xlsx`, `일위대가표.xlsx`, `내역서.xlsx` 입력 파일로 end-to-end 검증
- [x] 3입력 생성 결과: `outputs/issue41/e2e_three_input_원가계산서.xlsx`
- [x] 3입력 golden 검증: `checks=2/2`, `comparisons=1/1`, `원가계산서!E34=123,387,460`, formula fallback `0`
- [x] 계산형 검증: ver1/ver2 모두 `55/55` 라인 재현, 금액 커버리지 `100%`, 집계 차이 `0`

## 4. [다음 작업] 운영 품질 보강

**상세 내용:** MVP는 셀 값과 수식 연결 보존에 집중한다. 운영 사용 전에는 입력 파일의 시트 범위/서식 차이와 Excel 외부 재계산 환경을 더 확인해야 한다.

- [ ] 주입된 3개 시트의 서식/병합/인쇄영역까지 입력 파일 기준으로 복사할지 결정
- [ ] LibreOffice 또는 Excel COM 기반 자동 재계산 옵션 검토
- [ ] 입력 파일별 필수 cell/range validation 추가
- [x] 생성 결과를 웹 UI에서 업로드/다운로드할 수 있는 화면 초안 추가
- [x] 웹 UI의 `생성 요청 접수` 버튼을 Worker API `/cost/generate`와 연결
- [x] Worker API가 3개 Excel을 R2에 저장하고 GitHub Issue #41에 접수 코멘트를 남기도록 구현
- [x] GitHub Issue #41에 API 연결 현황 코멘트 반영
- [x] requestId를 받아 실제 `원가계산서.xlsx`를 생성하는 서버/큐 처리 연결. (2026-06-29: Worker가 R2에 3입력·상태를 기록하고, 신뢰된 Issue #42 접수 코멘트가 GitHub Actions 생성 작업을 시작하도록 연결)
- [x] GitHub Issue/PR에 실제 분리 샘플 파일 검증 결과 반영. (PR #43 커밋 `a3f1cf6`, Issue #42 체크리스트 갱신)

## 5. [Quartz 적용] 원장님용 생성기 화면

**상세 내용:** 새 URL을 만들지 않고 `https://quartz-kiba.pages.dev/` 지식베이스 안에서 사용할 수 있도록 원가계산서 생성기 화면을 연결한다.

- [x] Quartz 업무 화면 위치 확정: `/notes/cost-statement-generator`
- [x] Issue #41 페이지에 `원가계산서 생성기` 바로가기 콜아웃 추가
- [x] Quartz 화면에서 Worker API `POST /cost/generate` 호출
- [x] Worker `ALLOWED_ORIGINS`에 `https://quartz-kiba.pages.dev` 추가
- [x] 샘플 다운로드 버튼에 저장 위치 선택 방식 적용
- [x] 생성 서버/큐 연결 후 실제 요청 결과 `원가계산서.xlsx` 다운로드 API 추가. (`GET /cost/status`, `GET /cost/download`, 처리 비밀번호 보호 및 UI 자동 폴링/다운로드)
