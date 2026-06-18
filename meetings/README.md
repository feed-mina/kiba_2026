# meetings — 일일 회의록 (이슈 #5)

원장님과의 일일 회의를 "녹음 → STT → 요약 → Todo/Issue 반영"의 한 흐름으로 정리하기 위한 폴더입니다.
[Todo/2026-06-16_director_meeting_git_issues.md](../Todo/2026-06-16_director_meeting_git_issues.md) §5 운영안을 구현합니다.

## 운영 결정(2026-06-18)
- **기본 STT 도구: 클로바노트.** 녹음 후 텍스트/문서로 내보내 `meetings/raw/`에 저장. (Teams transcript는 권한 갖춰지면 후속 옵션)
- **회의 시간: 고정하지 않고 하루 전날 다음 날 시간을 정한다.**

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

## NotebookLM 자동 반영 (이슈 #5)
요약본을 NotebookLM 소스로 자동 반영하는 경로는 둘. `scripts/sync_meeting_to_notebooklm.py`가 골격을 잡아두고, 확정 시 구현한다.
- **(A) NotebookLM Enterprise API** — Gemini Enterprise/Google Cloud 조직 보유 시. `notebooks.sources.batchCreate`로 요약본을 소스로 직접 추가. 필요: GCP 프로젝트·서비스계정·OAuth.
  - 참고: <https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/api-notebooks-sources>
- **(B) Google Drive 소스** — 일반 NotebookLM. 요약본을 지정 Drive 폴더에 자동 업로드(Drive API)하고, NotebookLM에서 그 폴더/문서를 소스로 1회 연결한 뒤 동기화. 필요: Google Drive OAuth 자격증명.

## 아직 결정/권한이 필요한 부분
- 클로바노트 내보내기 담당자/주기 지정.
- NotebookLM 경로 (A/B) 확정 및 Google 자격증명 발급.
- Teams transcript(Microsoft Graph) 연동 — 후속 옵션, 관리자 승인 필요.
