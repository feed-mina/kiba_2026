# Configuration

## Repository variables

- `PUBLISH_REPOSITORY`: 템플릿을 발행할 `owner/repository`
- `WIKI_SOURCE_DIR`: Wiki에 발행할 폴더, 기본값 `wiki-template`

## Worker variables

- `ALLOWED_ORIGINS`: 대시보드 원본 URL 목록
- `ALLOWED_REPOS`: 연결할 GitHub 저장소 목록
- `MEETING_ISSUE_REPO`: 회의록 Issue를 생성할 저장소

## Worker secrets

- `GITHUB_TOKEN`
- `DOCS_PASSWORD`
- `TURNSTILE_SECRET`
- `GEMINI_API_KEY`
- 음성 인식을 사용할 경우 Clova API 자격 증명