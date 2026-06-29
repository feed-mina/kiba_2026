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
0. **메인페이지 간편 입력(짧은 녹음):** `녹음 파일로 회의록 만들기` 영역을 누르고 파일·회의 날짜·비밀번호를 입력하면, 회의록 Markdown을 즉시 내려받는다. 현재 CLOVA CSR 연결 기준 60초·3MB 이하만 지원한다.
1. 회의 녹음 → STT → `meetings/raw/YYYY-MM-DD_meeting.txt` 저장. 두 가지 방법:
   - **클로바노트 export**(긴 회의 권장) → 텍스트를 raw/ 에 직접 저장.
   - **`python scripts/transcribe_clova.py --audio rec.m4a`**(자동, CLOVA CSR API). CSR 은 **짧은 음성(약 60초)**용이라 긴 회의는 클로바노트 export 가 안전.
2. `python scripts/summarize_meeting.py 2026-06-18 --engine gemini` → 원문을 **Gemini(Google AI Studio)**로 요약해 템플릿(요약·결정·할 일)을 채운 `meetings/summary/2026-06-18_meeting.md` 생성.
   - 키 없이/수동으로 채우려면 `--engine none`(골격만, 기본값).
   - 키는 `.env`(`.env.example` 참고): `CLOVA_CSR_*`, `GEMINI_API_KEY`.
3. 요약본의 `## 할 일` 항목을 검토한 뒤 `python scripts/reflect_meeting.py 2026-06-18` → Todo/GitHub Issue 체크리스트에 반영.
4. `## 판단 기준 검증`을 확인한다. 기준 원본은 `Knowledge/Meetings/meeting_decision_criteria.md`이며, Gemini 요약은 관련 기준을 자동 판정한다.

## 할 일 항목 형식 (자동 반영용)
```
- [ ] 내용 — @담당자 ~2026-06-20 (이슈 #5)
```
`reflect_meeting.py` 가 `@담당자`, `~기한`, `(이슈 #N)` 을 파싱한다. 메타데이터는 모두 선택.

## NotebookLM 자동 반영 (이슈 #5 — 경로 확정: Drive 소스)
일반 NotebookLM에 자동 반영한다. `scripts/sync_meeting_to_notebooklm.py --via drive --confirm` 가 요약본을
지정 Drive 폴더에 Google Doc으로 업로드하고, NotebookLM은 그 폴더를 소스로 두고 동기화한다.

**1회 설정**
1. Google Drive에 회의록용 폴더 생성 → 폴더 URL의 `folders/<ID>` 에서 **DRIVE_FOLDER_ID** 확보.
2. NotebookLM에서 새 노트북 → 소스 추가 → **Google Drive 폴더(1번)** 를 소스로 연결(최초 1회).
3. OAuth 자격증명 발급(둘 중 하나):
   - 수동/단발: `gcloud auth print-access-token` → `GOOGLE_ACCESS_TOKEN` 환경변수.
   - 무인/스케줄러: Google Cloud OAuth 클라이언트(데스크톱) 생성 후 1회 동의로 refresh token 획득
     → `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` (scope: `drive.file`).
     스크립트가 매 실행 시 access token을 자동 발급한다.

**실행**
```
python scripts/sync_meeting_to_notebooklm.py "Knowledge/Meetings/meeting_decision_criteria.md" --via drive --confirm
python scripts/sync_meeting_to_notebooklm.py 2026-06-18 --via drive --confirm
```
첫 명령은 25개 판단 기준을 최초 1회 올리고, 둘째 명령은 날짜별 회의록을 올린다. NotebookLM에서는
`meetings/NOTEBOOKLM_VALIDATION_PROMPT.md`의 질문으로 결정 근거·위험·담당자·기한을 재검증한다.
날짜별 회의록 업로드는 `download_docs_scheduled.ps1`에 연결되어 있다.

## 아직 결정/권한이 필요한 부분
- 클로바노트 내보내기 담당자/주기 지정.
- DRIVE_FOLDER_ID + Google OAuth 자격증명 발급(위 1회 설정).
- NotebookLM에 Drive 폴더를 소스로 연결하고 판단 기준 문서를 최초 1회 업로드.
- (선택) Enterprise 경로(`--via enterprise`)는 Gemini Enterprise 보유 시 별도 검증.
- Teams transcript(Microsoft Graph) 연동 — 후속 옵션, 관리자 승인 필요.
