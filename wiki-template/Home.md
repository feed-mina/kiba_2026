# Project Operations Wiki

이 Wiki는 GitHub Issues를 기준으로 프로젝트 진행 상황을 관리하는 범용 템플릿입니다.

## 제공 기능

- 녹음 또는 자막 파일을 Markdown 회의록으로 변환
- 회의 후속 작업을 GitHub Issue로 생성
- Issue 기반 진행 보드와 우선순위 매트릭스
- 관리자 비밀번호로 비공개 파일 업로드, 조회, 다운로드
- 매트릭스 이동에 따른 Issue 중요도·긴급도 라벨 동기화

## 시작하기

1. 저장소 변수와 Cloudflare Worker 설정을 자신의 조직에 맞게 입력합니다.
2. GitHub Issues에 프로젝트 작업을 등록합니다.
3. 대시보드 설정의 저장소와 Worker 주소를 변경합니다.
4. 실제 업무 자료와 비밀값은 저장소에 커밋하지 않습니다.