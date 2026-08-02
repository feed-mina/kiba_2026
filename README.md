# Project Operations Dashboard

GitHub Issues를 업무 현황의 기준으로 사용하는 재사용 가능한 프로젝트 운영 템플릿입니다. 정적 대시보드, Cloudflare Worker, 비공개 R2 문서 저장소, 회의록 자동화, GitHub Wiki와 Planning Harness 발행 workflow를 포함합니다.

## 주요 기능

- **회의록 자동화:** 녹음 또는 TXT·VTT·SRT 자막을 Markdown 회의록으로 변환하고 GitHub Issue를 생성합니다.
- **진행 현황:** GitHub Issues와 라벨을 기준으로 할 일, 진행 중, 완료 상태를 표시합니다.
- **비공개 문서 관리:** 관리자 비밀번호로 Cloudflare R2 파일을 Issue 연결 또는 공용 파일함에 업로드·조회·다운로드합니다.
- **공유 일정:** GitHub Issue 일정을 R2에 저장하고 저장소별 주간·월간 달력으로 확인합니다.
- **다중 저장소·Project:** 허용된 여러 GitHub 저장소를 한 보드에서 필터링하고 여러 GitHub Project 바로가기를 관리합니다.
- **우선순위 동기화:** 매트릭스에서 Issue를 이동하면 중요도·긴급도 GitHub 라벨을 변경합니다.
- **운영 템플릿 발행:** 범용 GitHub Wiki와 Planning Harness를 별도 저장소에 발행합니다.

## 구성

| 경로 | 역할 |
| --- | --- |
| `index.html` | GitHub Pages에서 제공하는 운영 대시보드 |
| `worker/` | GitHub Issues, R2, STT, Gemini를 연결하는 Cloudflare Worker |
| `meetings/` | 회의록 템플릿과 로컬 처리 안내 |
| `wiki-template/` | GitHub Wiki에 발행할 공개 템플릿 |
| `planning-harness/` | 독립 저장소로 동기화할 기획 workflow 템플릿 |
| `scripts/` | 회의록, 라벨, 문서 다운로드 등의 보조 도구 |

## 시작하기

### 1. 대시보드

GitHub Pages를 활성화한 뒤 페이지의 설정 버튼에서 다음 값을 입력합니다. Worker 주소는 화면에 노출하지 않고 이 저장소의 배포 주소에 자동 연결됩니다.

- 프로젝트 이름
- 이름이 표시되는 GitHub Projects(여러 개 선택 가능)
- `owner/repository` 형식의 GitHub 저장소(여러 개 가능)

대시보드에서 선택할 수 있는 저장소는 Worker 배포 변수 `ALLOWED_REPOS`의 쉼표 구분 목록과 일치해야 합니다. 비공개 저장소는 `PROTECTED_REPOS`에도 추가하면 관리자 비밀번호 확인 전에는 저장소 목록과 Issue 정보가 노출되지 않습니다. 관리자 비밀번호는 브라우저 저장소에 보관하지 않으며 현재 화면에서 R2 파일함·일정을 조회하는 동안에만 사용합니다.

### 2. Worker와 R2

`worker/wrangler.toml`의 샘플 값을 사용할 환경에 맞게 변경하고 다음 secret을 Cloudflare Worker에 등록합니다.

```bash
cd worker
npx wrangler secret put GITHUB_TOKEN
npx wrangler secret put DOCS_PASSWORD
npx wrangler secret put TURNSTILE_SECRET
npx wrangler secret put CLOVA_CSR_CLIENT_ID
npx wrangler secret put CLOVA_CSR_CLIENT_SECRET
npx wrangler secret put GEMINI_API_KEY
npx wrangler deploy
```

Turnstile과 음성 인식 관련 secret은 해당 기능을 사용할 때만 필요합니다. 자세한 API와 보안 설정은 [worker/README.md](worker/README.md)를 참고하세요.

GitHub Actions 자동 배포에는 다음 저장소 설정이 필요합니다.

| 종류 | 이름 |
| --- | --- |
| Variable | `WORKER_NAME`, `ALLOWED_ORIGINS`, `ALLOWED_REPOS`, `DOCS_BUCKET_NAME` |
| 선택 Variable | `MEETING_ISSUE_REPO`, `PROTECTED_REPOS` |
| Secret | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `GH_PAT`, `ADD_TO_PROJECT_PAT` |

필수 Variable이 없으면 `deploy-worker` workflow는 기존 Worker를 덮어쓰지 않고 배포를 건너뜁니다.

### 3. Wiki와 Planning Harness

- Wiki: 저장소 Wiki에서 첫 페이지를 한 번 만든 뒤 `wiki-template/` 변경을 push하면 자동 발행됩니다. 다른 소스를 쓰려면 `WIKI_SOURCE_DIR` Variable을 설정합니다.
- Planning Harness: `PUBLISH_REPOSITORY=owner/repository` Variable과 대상 저장소를 관리할 `GH_PAT` Secret을 설정합니다.

### 4. 회의록

웹 대시보드에서 녹음·자막 파일을 처리하거나 로컬 스크립트를 사용할 수 있습니다. 지원 형식과 NotebookLM 연동은 [meetings/README.md](meetings/README.md)를 참고하세요.

## 검증

```bash
cd worker && npm test
cd ../scripts && python -m unittest test_validate_cost_job.py
cd .. && git diff --check
```

GitHub Actions workflow는 push 전에 YAML 구문과 필요한 저장소 Variable·Secret을 함께 확인하세요.

## 데이터 원칙

실제 회의록, 업무 문서, 개인정보, API token과 비밀번호는 Git에 커밋하지 않습니다. 공개 저장소에는 코드, 템플릿, 익명 예제만 유지하고 파일 원문은 비공개 R2에 저장합니다.
