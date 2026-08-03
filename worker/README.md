# Project Operations Worker

정적 운영 대시보드와 GitHub Issues, Cloudflare R2, 회의록 AI를 연결하는 Cloudflare Worker입니다.

## 제공 API

- `GET /repos`: 공개 요청은 서버 허용 저장소만, 관리자 인증 요청은 GitHub token이 접근 가능한 저장소 전체 조회(페이지네이션)
- `PUT /admin/repositories`: 관리자 인증 후 선택한 저장소를 서버 허용 목록으로 저장
- `GET /projects`: 관리자 인증 후 이름이 포함된 GitHub Projects 선택 목록 조회
- `GET /issues`: 허용된 여러 GitHub 저장소의 Issue 현황 통합 조회
- `POST /issues`: `targetRepo`를 지정해 허용된 저장소에 Issue 생성
- `POST /comment`: Issue 의견 등록
- `POST /upload`: 비공개 파일 업로드 및 Issue 기록
- `GET /docs/list`, `GET /docs/download`: 비밀번호 기반 파일 조회·다운로드
- `POST /meeting/summarize`: 녹음 또는 자막을 회의록으로 변환하고 Issue 생성
- `GET /labels`, `POST /labels`: 우선순위 라벨 조회·변경

## 준비

1. GitHub fine-grained token에 대상 저장소의 Issues 읽기·쓰기 권한을 부여합니다.
2. Cloudflare R2 버킷을 생성합니다.
3. `wrangler.toml`의 샘플 값을 자신의 환경에 맞게 변경합니다.

```toml
name = "project-operations"

[vars]
ALLOWED_ORIGINS = "https://example.github.io"
ALLOWED_REPOS = "owner/repository"
PROTECTED_REPOS = "owner/private-repository"
DOCS_BUCKET_NAME = "project-docs-private"
MEETING_ISSUE_REPO = "owner/repository"

[[r2_buckets]]
binding = "DOCS_BUCKET"
bucket_name = "project-docs-private"
```

## Secrets

```bash
npx wrangler secret put GITHUB_TOKEN
npx wrangler secret put GITHUB_PROJECT_TOKEN
npx wrangler secret put DOCS_PASSWORD
npx wrangler secret put TURNSTILE_SECRET
npx wrangler secret put CLOVA_CSR_CLIENT_ID
npx wrangler secret put CLOVA_CSR_CLIENT_SECRET
npx wrangler secret put GEMINI_API_KEY
```

Turnstile과 음성 인식 관련 secret은 해당 기능을 사용할 때만 필요합니다.

## 배포

```bash
cd worker
npm test
npx wrangler deploy
```

GitHub Actions 배포를 사용한다면 저장소 변수 `WORKER_NAME`, `ALLOWED_ORIGINS`, `ALLOWED_REPOS`, `PROTECTED_REPOS`, `DOCS_BUCKET_NAME`, `MEETING_ISSUE_REPO`, 저장소 Secret `GH_PAT`, `ADD_TO_PROJECT_PAT`, Cloudflare secrets를 설정합니다. 두 PAT는 배포 중 Worker의 저장소/Projects 전용 Secret으로 동기화되며 로그에 값을 출력하지 않습니다. 필수 변수가 없으면 자동 배포는 기존 Worker를 보호하기 위해 건너뜁니다.

`ALLOWED_REPOS`와 `PROTECTED_REPOS`는 관리자가 아직 목록을 저장하지 않았거나 R2 설정을 읽을 수 없을 때 사용하는 안전한 초기값입니다. 관리자가 대시보드 설정에서 저장소를 선택하고 저장하면 `_system/allowed-repositories.json` 객체에 허용 목록이 기록되며 이후 요청부터 적용됩니다.

`worker/**` 변경을 `main`에 push하면 `deploy-worker` workflow가 실행됩니다.

## 보안

- Worker token과 관리자 비밀번호를 클라이언트 코드에 넣지 않습니다.
- `ALLOWED_ORIGINS`와 초기 `ALLOWED_REPOS`를 실제 사용 범위로 제한합니다.
- 실제 파일은 GitHub가 아니라 비공개 R2 버킷에 저장합니다.
- `POST /docs/upload`는 Issue와 무관한 관리자 파일을 저장하고 `GET /docs/list`는 저장소 전체 또는 특정 Issue의 파일을 조회합니다.
- `GET /schedule`, `POST /schedule`은 관리자 비밀번호로 Issue별 공유 일정을 조회·저장·삭제합니다.
- 비밀번호 없는 `GET /repos`는 서버 허용 목록의 공개 저장소만 반환하며, 접근 가능한 전체 목록은 관리자 인증 후에만 반환합니다.
- 관리자가 저장한 비공개 저장소는 GitHub 메타데이터를 기준으로 자동 보호되며, 목록과 Issue 정보는 올바른 `X-Docs-Password`가 있을 때만 반환합니다.
- `GET /projects`는 `ALLOWED_REPOS`의 소유자만 조회하며 프로젝트 이름과 주소를 관리자에게만 반환합니다.
