# KIBA 의견 메모 → GitHub Issue 등록 (서버리스 셋업 가이드)

진행 페이지(`index.html`)의 카드를 누르면 녹색 메모창이 열리고, 적은 의견이
**GitHub 계정 로그인 없이** 해당 GitHub Issue에 코멘트로 자동 등록됩니다.
문서를 함께 선택하면 파일 원문은 **비공개 Cloudflare R2**에 저장하고, GitHub Issue에는
파일명·크기·R2 key 같은 업로드 기록만 남깁니다.

비밀은 GitHub 토큰을 페이지가 아니라 **Cloudflare Worker(서버)** 에 숨겨 둔다는 점입니다.
페이지는 Worker에만 요청을 보내고, Worker가 토큰으로 GitHub에 코멘트를 답니다.

```
방문자 → index.html(메모창) → Cloudflare Worker(토큰 보관) → GitHub Issue 코멘트
방문자 → index.html(문서 업로드) → Cloudflare Worker → 비공개 R2 + GitHub Issue 기록
```

봇/스팸 차단: ① 출처(Origin) 검사 ② 저장소 allowlist ③ Cloudflare Turnstile ④ 허니팟.

---

## 준비물

- Cloudflare 계정 (무료)
- Node.js 설치 (`npx` 사용)
- GitHub fine-grained Personal Access Token
- Cloudflare R2 bucket
- 문서 업로드/다운로드용 비밀번호

---

## 1단계. GitHub 토큰 발급

1. GitHub → Settings → Developer settings → **Fine-grained tokens** → Generate new token
2. **Repository access**: `feed-mina/kiba_2026` 선택
   (quali-fit 의견도 이 저장소의 한 이슈로 모이므로 이 저장소만 있으면 됩니다.)
3. **Permissions → Repository permissions → Issues: Read and write**
4. 토큰 문자열을 복사해 둡니다. (이 값은 절대 페이지/깃에 넣지 마세요.)

> quali-fit 의견을 모을 이슈를 하나 만들어 두세요.
> 예: `feed-mina/kiba_2026`에 "quali-fit 의견 수집" 이슈 생성 → 번호 확인(예: #6).

---

## 2단계. (선택, 권장) Turnstile 키 발급 — 봇 차단

1. Cloudflare 대시보드 → **Turnstile** → Add site
2. 도메인에 `feed-mina.github.io` 추가
3. **Site Key**(공개)와 **Secret Key**(비밀) 두 개를 받습니다.
   - Site Key → `index.html`의 `CONFIG.turnstileSiteKey`
   - Secret Key → Worker 시크릿 `TURNSTILE_SECRET`

Turnstile을 안 쓰려면 이 단계를 건너뛰면 됩니다(허니팟+출처검사만 동작).

---

## 3단계. Worker 배포

먼저 비공개 문서 저장용 R2 bucket을 만듭니다.

```bash
npx wrangler r2 bucket create kiba-docs-private
```

`wrangler.toml`의 R2 바인딩 이름과 bucket 이름도 확인하세요.

```toml
[[r2_buckets]]
binding = "DOCS_BUCKET"
bucket_name = "kiba-docs-private"
```

이 폴더(`worker/`)에서:

```bash
# Cloudflare 로그인
npx wrangler login

# 토큰을 시크릿으로 등록 (화면에 붙여넣기)
npx wrangler secret put GITHUB_TOKEN

# 문서 업로드/다운로드 비밀번호
npx wrangler secret put DOCS_PASSWORD

# Turnstile 쓰는 경우에만
npx wrangler secret put TURNSTILE_SECRET

# 배포
npx wrangler deploy
```

배포가 끝나면 주소가 출력됩니다:
`https://kiba-memo-proxy.<계정>.workers.dev`

`wrangler.toml`의 공개 변수도 확인하세요:

```toml
[vars]
ALLOWED_ORIGINS = "https://feed-mina.github.io"
ALLOWED_REPOS = "feed-mina/kiba_2026"
```

---

## 4단계. index.html 설정 채우기

`index.html` 위쪽 `CONFIG`를 본인 값으로:

```js
const CONFIG = {
  apiBase: "https://kiba-memo-proxy.<계정>.workers.dev",  // 3단계 주소
  defaultRepo: "feed-mina/kiba_2026",
  qfCollectorIssue: 6,             // quali-fit 의견 모을 이슈 번호
  turnstileSiteKey: ""             // Turnstile Site Key (안 쓰면 빈 값)
};
```

커밋 후 GitHub Pages에 반영하면 끝.

---

## 동작 확인

- 카드 클릭 → 메모 작성 → **이슈에 등록** → 해당 이슈에 코멘트가 달리는지 확인
- 카드 클릭 → 문서 선택 → 업로드 비밀번호 입력 → **이슈에 등록** → R2 저장 및 이슈 업로드 기록 확인
- KIBA 카드에는 의견이 쌓이면 "의견 N" 배지가 표시됩니다(약 1분 캐시).

## 내부 담당자 문서 다운로드

문서 원문은 GitHub에 올라가지 않습니다. 권한 있는 담당자는 저장소 루트에서 아래처럼 내려받습니다.

```powershell
.\scripts\download_docs.ps1
```

특정 이슈 문서만 내려받으려면:

```powershell
.\scripts\download_docs.ps1 -Issue 2
```

비밀번호는 실행 시 입력합니다. 파일은 Git 추적에서 제외된 `docs/issue-번호/` 아래에 저장됩니다.

## 자주 묻는 점

- **`apiBase`가 비어 있으면?** 등록 대신 "복사"로 폴백합니다(서버 없이도 페이지는 정상).
- **403 forbidden_origin** → `ALLOWED_ORIGINS`에 실제 페이지 주소가 맞는지 확인.
- **403 forbidden_repo** → `ALLOWED_REPOS`와 카드 `data-repo`가 일치하는지 확인.
- **누가 의견을 냈는지 기록되나요?** 익명 방식이라 작성자 계정은 남지 않습니다.
  코멘트 본문에 과업명·작성 시각·출처가 들어가 구분됩니다.
- **업로드 문서가 GitHub에 보이나요?** 아니요. GitHub Issue에는 업로드 기록만 남고 원문은 R2에만 저장됩니다.
- **문서 다운로드는 누가 하나요?** `DOCS_PASSWORD`를 아는 내부 담당자가 `scripts/download_docs.ps1`로 내려받습니다.
- **스팸이 들어오면?** Turnstile을 켜고, 그래도 심하면 Worker에서 `ALLOWED_REPOS`/이슈를
  제한하거나 Cloudflare WAF 레이트리밋을 추가하세요.

## 비용

- Cloudflare Workers 무료 티어: 하루 10만 요청. 이 용도엔 충분합니다.
