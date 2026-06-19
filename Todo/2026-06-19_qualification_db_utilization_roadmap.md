# 학력·자격증 DB 활용 로드맵 (2026-06-19)

> 목적: `docs/학력_자격증_26.05.14_v13.xlsm` 원천 데이터를 quali-fit 및 KIBA 운영 업무에 활용하기 위한 다음 할 일을 GitHub에서 추적한다.
> GitHub 마일스톤: https://github.com/feed-mina/kiba_2026/milestone/1

## 1. [높음/높음] XLSM 원천데이터 ETL 설계

**GitHub Issue:** https://github.com/feed-mina/kiba_2026/issues/22

**다음 할 일**
- [ ] 시트별 컬럼 매핑 사양 확정.
- [ ] employee, education, cert_master, employee_cert 변환 규칙 정의.
- [ ] 이름 기반 조인 위험과 동명이인 처리 규칙 정리.
- [ ] PII 포함 산출물은 git 추적 제외.

## 2. [높음/높음] 자격증 만료·증빙 누락 대시보드

**GitHub Issue:** https://github.com/feed-mina/kiba_2026/issues/21

**다음 할 일**
- [ ] 만료, 만료예정, 등록일 누락, 증빙 누락 기준 정의.
- [ ] 직원별/부서별 현황 집계.
- [ ] 공개 페이지에는 개인정보를 노출하지 않는 요약만 반영.
- [ ] 비공개 산출물은 git 제외 경로에서 관리.

## 3. [높음/높음] 협회 등록 후보자 자동 분류

**GitHub Issue:** https://github.com/feed-mina/kiba_2026/issues/19

**다음 할 일**
- [ ] 기존 Issue #1의 엔지니어링협회 검토 결과와 연결.
- [ ] 현재 등록 가능, 보완 후 가능, 증빙 확인 필요로 분류.
- [ ] 경력연수·전공·자격증·증빙 보유 여부 입력 항목 정리.
- [ ] 협회별 요건 차이를 별도 규칙으로 관리.

## 4. [높음/낮음] 업무코드별 추천 인력·자격증 매칭

**GitHub Issue:** https://github.com/feed-mina/kiba_2026/issues/23

**다음 할 일**
- [ ] 업무코드와 자격증 중요도 매핑 검증.
- [ ] quali-fit 점수화 규칙과 연결.
- [ ] 추천 근거를 자격증, 학력, 부서, 협회상태로 분리 표시.
- [ ] 입찰/제안서용 인력 편성 시나리오 작성.

## 5. [높음/낮음] 제안서용 인력 프로필 자동 생성

**GitHub Issue:** https://github.com/feed-mina/kiba_2026/issues/20

**다음 할 일**
- [ ] 제안서에 필요한 인력 프로필 항목 정의.
- [ ] 개인정보와 공개 가능 정보를 분리.
- [ ] Word/HWP/Excel에 붙이기 좋은 출력 형식 결정.
- [ ] 후보자 선택 후 프로필 일괄 생성 흐름 설계.

## 보류/권한 필요

- GitHub Projects v2 보드 생성 및 이슈 추가는 현재 토큰에 `read:project`/`project` 권한이 없어 진행하지 못했다.
- 권한이 열리면 위 마일스톤의 이슈들을 GitHub Project 보드의 `Next` 컬럼으로 옮긴다.
