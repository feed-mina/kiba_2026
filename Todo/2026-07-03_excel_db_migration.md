# 엑셀 원자료 DB화 계획

> 출처: 2026-07-03 일일 회의 지적 사항 (16:39, 17:17)  
> 담당: @민예린

---

## 배경

현재 수문조사 원가 관련 원자료가 엑셀 파일 형태로 분산 관리되고 있어, 자료 조회·분석·보고 시 엑셀을 직접 열어 확인해야 하는 비효율이 발생한다. 회의에서 원장님으로부터 "엑셀 파일을 데이터베이스화하여 관리하라"는 지시가 내려졌다.

---

## 대상 원자료 목록

| 폴더 | 파일 | 테이블 명 (안) | 우선순위 |
|------|------|---------------|---------|
| 01_사업별 예산 | 수문조사 항목별 예산 현황_v2.xlsx | `sumon_budget` | ★★★ |
| 02_수문조사 단가표 | 항목별 단가 현황('21~'26).xlsx | `sumon_unit_price` | ★★★ |
| 04_조사지점 현황 | 조사지점 현황('24년 기준).xlsx | `sumon_station` | ★★☆ |
| 04_조사지점 현황 | 조사거점 별 주요 교통비.xlsx | `sumon_fare` | ★★★ |
| 05_조사장비 관련 | 장비 관련.xlsx | `sumon_equipment` | ★★☆ |
| 06_운영비 관련 | 업무차량 관련.xlsx | `sumon_vehicle` | ★☆☆ |
| 06_운영비 관련 | 임대 관련.xlsx | `sumon_lease` | ★☆☆ |

---

## Phase 1. [즉시] 핵심 테이블 JSON 추출

**상세 내용:** 우선순위 ★★★ 파일 3개를 JSON으로 추출하여 `data/sumon_domain_tables.json`에 통합 저장.

- [ ] `scripts/extract_sumon_domain.py` 작성
  - 각 xlsx 파일을 읽어 정규화된 dict 리스트로 변환
  - `sumon_budget`, `sumon_unit_price`, `sumon_fare` 테이블 생성
  - 출력: `data/sumon_domain_tables.json`
- [ ] 기존 `data/sample_ver1_cost_db/domain_tables.json` 패턴 참고
- [ ] 스크립트 실행 및 결과 검증 (행 수, 컬럼 이름, 숫자 범위 확인)

---

## Phase 2. [단기] 나머지 테이블 추가

**상세 내용:** 나머지 우선순위 ★★☆ 파일을 추가로 추출하여 JSON에 병합.

- [ ] `sumon_station` (조사지점 현황) 추출
- [ ] `sumon_equipment` (장비 현황) 추출
- [ ] 지점별 원가 계산 검증 스크립트 업데이트 (교통비·장비비 자동 계산)

---

## Phase 3. [중기] DB 뷰어 연동

**상세 내용:** `db-tables.html`에 수문조사 테이블 섹션을 추가하여 브라우저에서 조회·검색·엑셀 다운로드 가능하도록 연동.

- [ ] `db-tables.html`에 `sumon_*` 테이블 섹션 추가
  - 패턴: 기존 `assoc_register` 섹션 참고
  - 스키마 보기 (비밀번호 불필요)
  - 실제 값 조회 + 엑셀 다운로드 (비밀번호 필요)
- [ ] worker 또는 R2를 통해 JSON 데이터 서빙

---

## Phase 4. [장기] 원가 대시보드 실데이터 연결

**상세 내용:** 현재 수문조사 원가 분석 대시보드(`docs/수문조사_원가분析_대시보드.html`)의 하드코딩 데이터를 DB 기반 동적 로드로 전환.

- [ ] `data/sumon_domain_tables.json` → 대시보드 DATA 주입 자동화
- [ ] `scripts/build_hydrology_dashboard.py` 업데이트
- [ ] 지점 선택 시 실제 교통비·권역 임대비 자동 계산 연결

---

## 스키마 설계 (안)

### `sumon_budget`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `year` | int | 연도 (2021~2026) |
| `item` | text | 항목명 (유량, 유사량, 토양수분, 증발산, 자동유량) |
| `station_count` | int | 지점 수 |
| `unit_price_won` | int | 지점당 단가 (원) |
| `total_budget_won` | int | 항목 총 예산 (원) |
| `category` | text | 기관운영 / 사업 |

### `sumon_fare`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `seq_range` | text | 연번 범위 (예: 1~20) |
| `region` | text | 권역 (한강, 낙동강, 금강, 영산강) |
| `station_name` | text | 지점명 |
| `transport` | text | 교통 수단 |
| `one_way_fare_won` | int | 편도 교통비 (원) |

---

## 연결 이슈

- #40 sample_ver1 원가계산서 DB설계
- #56 수문(강유량) 과업 데이터 분석 플랜
- #61 2026-07-03 회의록 (원본 지시)
