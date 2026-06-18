# meetings — 일일 회의록 (이슈 #5)

원장님과의 일일 회의를 "녹음 → STT → 요약 → Todo/Issue 반영"의 한 흐름으로 정리하기 위한 폴더입니다.
[Todo/2026-06-16_director_meeting_git_issues.md](../Todo/2026-06-16_director_meeting_git_issues.md) §5 운영안을 구현합니다.

## 폴더 규칙
- `meetings/raw/` — 녹음에서 변환한 **원문(STT) 텍스트**. PII/회사 기밀이라 **git 추적 제외**(`.gitignore`). 파일명: `YYYY-MM-DD_meeting.txt`.
- `meetings/summary/` — AI로 정리한 **회의록 요약본**. Todo/ASK 와 동일하게 **git 추적**. 파일명: `YYYY-MM-DD_meeting.md`.
- `meetings/TEMPLATE_meeting.md` — 요약본 템플릿(요약·결정·할 일·다음 안건·비고).

## 흐름
1. 회의 녹음 → STT(클로바노트/Teams transcript 등) → `meetings/raw/YYYY-MM-DD_meeting.txt` 저장.
2. `python scripts/summarize_meeting.py 2026-06-18` → 원문을 템플릿에 채워 `meetings/summary/2026-06-18_meeting.md` 생성.
   - 요약 엔진은 아직 미연동(골격). 현재는 원문을 섹션 골격에 담아 사람이 채우거나, `--via` 옵션으로 추후 AI 요약을 붙인다.
3. 요약본의 `## 할 일` 항목을 검토한 뒤 `python scripts/reflect_meeting.py 2026-06-18` → Todo/GitHub Issue 체크리스트에 반영.

## 할 일 항목 형식 (자동 반영용)
```
- [ ] 내용 — @담당자 ~2026-06-20 (이슈 #5)
```
`reflect_meeting.py` 가 `@담당자`, `~기한`, `(이슈 #N)` 을 파싱한다. 메타데이터는 모두 선택.

## 아직 결정/권한이 필요한 부분 (오늘 범위 밖)
- 회의 시간 확정, Teams vs 클로바노트 선택 — 팀 결정.
- Teams transcript(Microsoft Graph) 연동 — 관리자 승인/권한 필요.
- NotebookLM 소스 반영 — 공식 업로드 API 미확인, 수동/브라우저 자동화 별도 검증.
