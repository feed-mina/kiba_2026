/**
 * KIBA 2026 - 의견 메모 -> GitHub Issue 코멘트 프록시 (Cloudflare Worker)
 *
 * 하는 일
 *  - 정적 페이지(index.html)에서 보낸 의견을 GitHub Issue 코멘트로 등록한다.
 *  - GitHub 토큰은 이 서버(시크릿)에만 있고, 페이지에는 절대 노출되지 않는다.
 *  - 익명 등록을 허용하므로 스팸/봇 차단 장치를 둔다:
 *      1) 출처(Origin) allowlist
 *      2) 저장소(repo) allowlist
 *      3) Cloudflare Turnstile 봇 검증 (TURNSTILE_SECRET 설정 시)
 *      4) 허니팟 필드("website")
 *      5) 본문 길이 제한
 *
 * 엔드포인트
 *  - POST /comment   { repo, issue, title, comment, source, ref, website, turnstileToken }
 *  - POST /upload    multipart/form-data { repo, issue, title, comment, source, ref, password, file, website, turnstileToken }
 *  - POST /cost/generate multipart/form-data { repo, issue, password, priceComparison, detail, summary, templateVersion }
 *  - GET  /counts?repo=<owner/name>&issues=1,2,3   -> { "1": 4, "2": 0, ... }
 *  - GET  /docs/list?repo=<owner/name>&issue=1      (header: X-Docs-Password)
 *  - GET  /docs/download?repo=<owner/name>&key=...  (header: X-Docs-Password)
 *
 * 필요한 환경변수 (wrangler.toml / 대시보드)
 *  - GITHUB_TOKEN     (Secret)  Issues: Read and write 권한의 fine-grained PAT
 *  - DOCS_PASSWORD    (Secret)  문서 업로드/다운로드 비밀번호
 *  - DOCS_BUCKET      (R2)      비공개 문서 저장용 R2 bucket binding
 *  - ALLOWED_ORIGINS  (Var)     쉼표 구분. 예) "https://feed-mina.github.io"
 *  - ALLOWED_REPOS    (Var)     쉼표 구분. 예) "feed-mina/kiba_2026"
 *  - TURNSTILE_SECRET (Secret)  선택. 설정하면 Turnstile 검증을 강제한다.
 */

const GITHUB_API = "https://api.github.com";
const MAX_COMMENT = 4000;
const MAX_TITLE = 300;
const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
const COST_GENERATOR_ISSUE = 41;
/*
const COST_INPUTS = [
  { field: "priceComparison", label: "단가대비표" },
  { field: "detail", label: "내역서" },
  { field: "summary", label: "집계표" },
];
/*
  { field: "priceComparison", label: "단가대비표" },
  { field: "detail", label: "내역서" },
  { field: "summary", label: "집계표" },
];
*/
const COST_INPUTS = [
  { field: "priceComparison", label: "\uB2E8\uAC00\uB300\uBE44\uD45C" },
  { field: "detail", label: "\uB0B4\uC5ED\uC11C" },
  { field: "summary", label: "\uC9D1\uACC4\uD45C" },
];
const BLOCKED_EXTENSIONS = new Set([
  "exe", "bat", "cmd", "com", "scr", "ps1", "vbs", "js", "msi", "dll"
]);
/*
const DB_TABLES = [
  {
    name: "employee",
    label: "직원 기본정보",
    source: "db_직원기본정보.csv",
    description: "직원 번호, 이름, 소속, 직책을 담은 기본 테이블입니다.",
    sensitive: true,
  },
  {
    name: "cert_master",
    label: "자격증 마스터",
    source: "db_자격증마스터.csv",
    description: "자격증 코드, 분류, 설명, 수행 가능 업무, 발급기관을 담은 기준 테이블입니다.",
    sensitive: false,
  },
  {
    name: "work_code_master",
    label: "업무코드 마스터",
    source: "db_업무분류마스터.csv",
    description: "업무분류 코드와 분류 기준, 담당 부서, 관련 법령을 담은 기준 테이블입니다.",
    sensitive: true,
  },
  {
    name: "education",
    label: "직원 학력",
    source: "db_직원정보_학력.csv",
    description: "직원별 학력, 학교, 전공, KECO 분류를 담은 테이블입니다.",
    sensitive: true,
  },
  {
    name: "employee_cert",
    label: "직원 자격증",
    source: "db_자격증보유.csv",
    description: "직원별 보유 자격증과 취득일, 등록일, 만료일을 담은 매핑 테이블입니다.",
    sensitive: true,
  },
  {
    name: "work_code_cert_map",
    label: "업무코드-자격증 매핑",
    source: "db_업무분류자격증매핑.csv",
    description: "업무분류 코드와 자격증의 영향도 매핑을 담은 테이블입니다.",
    sensitive: false,
  },
  {
    name: "assoc_register",
    label: "협회 등록 현황",
    source: "db_협회등록현황_2026-06-19.xlsx",
    description: "엔지니어링협회 등록 현황 엑셀 자료(2026-06-19)입니다.",
    sensitive: true,
    kind: "xlsx",
  },
];
// 우선순위 매트릭스용 라벨 접두사 (중요도/긴급도)
const IMP_PREFIX = "중요도:";
const URG_PREFIX = "긴급도:";

*/
const DB_TABLES = [
  {
    name: "employee",
    label: "\uC9C1\uC6D0 \uAE30\uBCF8\uC815\uBCF4",
    source: "db_\uC9C1\uC6D0\uAE30\uBCF8\uC815\uBCF4.csv",
    description: "Employee base information table.",
    sensitive: true,
  },
  {
    name: "cert_master",
    label: "\uC790\uACA9\uC99D \uB9C8\uC2A4\uD130",
    source: "db_\uC790\uACA9\uC99D\uB9C8\uC2A4\uD130.csv",
    description: "Certification master table.",
    sensitive: false,
  },
  {
    name: "work_code_master",
    label: "\uC5C5\uBB34\uCF54\uB4DC \uB9C8\uC2A4\uD130",
    source: "db_\uC5C5\uBB34\uBD84\uB958\uB9C8\uC2A4\uD130.csv",
    description: "Work category and code master table.",
    sensitive: true,
  },
  {
    name: "education",
    label: "\uC9C1\uC6D0 \uD559\uB825",
    source: "db_\uC9C1\uC6D0\uC815\uBCF4_\uD559\uB825.csv",
    description: "Employee education history table.",
    sensitive: true,
  },
  {
    name: "employee_cert",
    label: "\uC9C1\uC6D0 \uC790\uACA9\uC99D",
    source: "db_\uC790\uACA9\uC99D\uBCF4\uC720.csv",
    description: "Employee certification holding table.",
    sensitive: true,
  },
  {
    name: "work_code_cert_map",
    label: "\uC5C5\uBB34\uCF54\uB4DC-\uC790\uACA9\uC99D \uB9E4\uD551",
    source: "db_\uC5C5\uBB34\uBD84\uB958\uC790\uACA9\uC99D\uB9E4\uD551.csv",
    description: "Work code to certification mapping table.",
    sensitive: false,
  },
  {
    name: "assoc_register",
    label: "\uD611\uD68C \uB4F1\uB85D \uD604\uD669",
    source: "db_\uD611\uD68C\uB4F1\uB85D\uD604\uD669_2026-06-19.xlsx",
    description: "Association registration workbook as of 2026-06-19.",
    sensitive: true,
    kind: "xlsx",
  },
];
const IMP_PREFIX = "\uC911\uC694 ";
const URG_PREFIX = "\uAE34\uAE09 ";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";
    const cors = corsHeaders(origin, env);

    // 사전 요청(preflight)
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    try {
      if (url.pathname === "/comment" && request.method === "POST") {
        return await handleComment(request, env, cors, origin);
      }
      if (url.pathname === "/upload" && request.method === "POST") {
        return await handleUpload(request, env, cors, origin);
      }
      if (url.pathname === "/cost/generate" && request.method === "POST") {
        return await handleCostGenerate(request, env, cors, origin);
      }
      if (url.pathname === "/counts" && request.method === "GET") {
        return await handleCounts(url, env, cors);
      }
      if (url.pathname === "/labels" && request.method === "GET") {
        return await handleLabelsGet(url, env, cors);
      }
      if (url.pathname === "/labels" && request.method === "POST") {
        return await handleLabelsSet(request, env, cors, origin);
      }
      if (url.pathname === "/docs/list" && request.method === "GET") {
        return await handleDocsList(request, url, env, cors);
      }
      if (url.pathname === "/docs/download" && request.method === "GET") {
        return await handleDocsDownload(request, url, env, cors);
      }
      if (url.pathname === "/db/tables" && request.method === "GET") {
        return await handleDbTables(request, url, env, cors);
      }
      if (url.pathname === "/db/table" && request.method === "GET") {
        return await handleDbTable(request, url, env, cors);
      }
      if (url.pathname === "/db/download" && request.method === "GET") {
        return await handleDbDownload(request, url, env, cors);
      }
      if (url.pathname === "/" || url.pathname === "/health") {
        return json({ ok: true, service: "kiba-memo-proxy" }, 200, cors);
      }
      return json({ error: "not_found" }, 404, cors);
    } catch (err) {
      return json({ error: "server_error", detail: String(err && err.message || err) }, 500, cors);
    }
  },
};

/* ----------------------------- POST /comment ----------------------------- */

async function handleComment(request, env, cors, origin) {
  // 1) 출처 검증
  if (!isAllowedOrigin(origin, env)) {
    return json({ error: "forbidden_origin" }, 403, cors);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "bad_json" }, 400, cors);
  }

  // 2) 허니팟 - 사람은 비워둠. 채워져 있으면 봇으로 간주하고 조용히 성공 처리.
  if (body.website) {
    return json({ ok: true, skipped: true }, 200, cors);
  }

  const repo = String(body.repo || "").trim();
  const issue = parseInt(body.issue, 10);
  const title = String(body.title || "").slice(0, MAX_TITLE);
  const comment = String(body.comment || "").trim();
  const source = String(body.source || "").slice(0, 40);
  const ref = String(body.ref || "").slice(0, 300);

  // 3) 입력 검증
  if (!isAllowedRepo(repo, env)) {
    return json({ error: "forbidden_repo" }, 403, cors);
  }
  if (!Number.isInteger(issue) || issue <= 0) {
    return json({ error: "bad_issue" }, 400, cors);
  }
  if (!comment) {
    return json({ error: "empty_comment" }, 400, cors);
  }
  if (comment.length > MAX_COMMENT) {
    return json({ error: "comment_too_long" }, 400, cors);
  }

  // 4) Turnstile 봇 검증 (시크릿이 설정된 경우에만 강제)
  if (env.TURNSTILE_SECRET) {
    const ok = await verifyTurnstile(env.TURNSTILE_SECRET, body.turnstileToken, request);
    if (!ok) {
      return json({ error: "turnstile_failed" }, 403, cors);
    }
  }

  // 5) 코멘트 본문 구성
  const lines = [
    "### 페이지 의견",
    "",
    `- 관련 과업: ${title || "(제목 없음)"}`,
    source ? `- 출처 보드: ${source}` : "",
    ref ? `- 원본 링크: ${ref}` : "",
    `- 작성(서버 시각): ${new Date().toISOString()}`,
    "",
    comment,
    "",
    "_KIBA 진행 페이지의 메모창에서 익명으로 전달된 의견입니다._",
  ].filter(Boolean);

  const ghRes = await fetch(`${GITHUB_API}/repos/${repo}/issues/${issue}/comments`, {
    method: "POST",
    headers: githubHeaders(env),
    body: JSON.stringify({ body: lines.join("\n") }),
  });

  if (!ghRes.ok) {
    const detail = await safeText(ghRes);
    return json({ error: "github_error", status: ghRes.status, detail }, 502, cors);
  }

  const data = await ghRes.json();
  return json({ ok: true, url: data.html_url }, 200, cors);
}

/* ------------------------------ POST /upload ----------------------------- */

async function handleUpload(request, env, cors, origin) {
  if (!isAllowedOrigin(origin, env)) {
    return json({ error: "forbidden_origin" }, 403, cors);
  }
  if (!env.DOCS_BUCKET) {
    return json({ error: "missing_r2_binding" }, 500, cors);
  }

  let form;
  try {
    form = await request.formData();
  } catch {
    return json({ error: "bad_form" }, 400, cors);
  }

  if (form.get("website")) {
    return json({ ok: true, skipped: true }, 200, cors);
  }

  if (!isValidDocsPassword(String(form.get("password") || ""), env)) {
    return json({ error: "bad_password" }, 403, cors);
  }

  const repo = String(form.get("repo") || "").trim();
  const issue = parseInt(form.get("issue"), 10);
  const title = String(form.get("title") || "").slice(0, MAX_TITLE);
  const comment = String(form.get("comment") || "").trim().slice(0, MAX_COMMENT);
  const source = String(form.get("source") || "").slice(0, 40);
  const ref = String(form.get("ref") || "").slice(0, 300);
  const file = form.get("file");

  if (!isAllowedRepo(repo, env)) {
    return json({ error: "forbidden_repo" }, 403, cors);
  }
  if (!Number.isInteger(issue) || issue <= 0) {
    return json({ error: "bad_issue" }, 400, cors);
  }
  if (!(file instanceof File) || !file.name) {
    return json({ error: "missing_file" }, 400, cors);
  }
  if (file.size <= 0) {
    return json({ error: "empty_file" }, 400, cors);
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return json({ error: "file_too_large", maxBytes: MAX_UPLOAD_BYTES }, 400, cors);
  }

  const safeName = safeFilename(file.name);
  const ext = extensionOf(safeName);
  if (BLOCKED_EXTENSIONS.has(ext)) {
    return json({ error: "blocked_file_type" }, 400, cors);
  }

  if (env.TURNSTILE_SECRET) {
    const ok = await verifyTurnstile(env.TURNSTILE_SECRET, form.get("turnstileToken"), request);
    if (!ok) {
      return json({ error: "turnstile_failed" }, 403, cors);
    }
  }

  const uploadedAt = new Date().toISOString();
  const repoKey = repo.replace("/", "__");
  const stamp = uploadedAt.replace(/[:.]/g, "-");
  const key = `docs/${repoKey}/${issue}/${stamp}__${safeName}`;

  await env.DOCS_BUCKET.put(key, file.stream(), {
    httpMetadata: {
      contentType: file.type || "application/octet-stream",
      contentDisposition: `attachment; filename*=UTF-8''${encodeURIComponent(safeName)}`,
    },
    customMetadata: {
      repo,
      issue: String(issue),
      title,
      source,
      ref,
      filename: safeName,
      uploadedAt,
    },
  });

  const lines = [
    "### 문서 업로드 기록",
    "",
    `- 관련 과업: ${title || "(제목 없음)"}`,
    `- 관련 이슈: #${issue}`,
    source ? `- 출처 보드: ${source}` : "",
    ref ? `- 원본 링크: ${ref}` : "",
    `- 파일명: \`${safeName}\``,
    `- 크기: ${formatBytes(file.size)}`,
    `- R2 저장 key: \`${key}\``,
    `- 업로드(서버 시각): ${uploadedAt}`,
    "",
    comment ? `#### 업로드 메모\n${comment}` : "",
    "",
    "_원문 파일은 GitHub에 저장하지 않고 비공개 R2 저장소에 보관했습니다._",
  ].filter(Boolean);

  const ghRes = await fetch(`${GITHUB_API}/repos/${repo}/issues/${issue}/comments`, {
    method: "POST",
    headers: githubHeaders(env),
    body: JSON.stringify({ body: lines.join("\n") }),
  });

  if (!ghRes.ok) {
    const detail = await safeText(ghRes);
    return json({ error: "github_error_after_upload", status: ghRes.status, detail, key }, 502, cors);
  }

  const data = await ghRes.json();
  return json({
    ok: true,
    key,
    filename: safeName,
    size: file.size,
    issueUrl: data.html_url,
  }, 200, cors);
}

/* --------------------------- POST /cost/generate -------------------------- */

async function handleCostGenerate(request, env, cors, origin) {
  if (!isAllowedOrigin(origin, env)) {
    return json({ error: "forbidden_origin" }, 403, cors);
  }
  if (!env.DOCS_BUCKET) {
    return json({ error: "missing_r2_binding" }, 500, cors);
  }

  let form;
  try {
    form = await request.formData();
  } catch {
    return json({ error: "bad_form" }, 400, cors);
  }

  if (form.get("website")) {
    return json({ ok: true, skipped: true }, 200, cors);
  }

  if (!isValidDocsPassword(String(form.get("password") || ""), env)) {
    return json({ error: "bad_password" }, 403, cors);
  }

  const repo = String(form.get("repo") || "").trim();
  const issue = parseInt(form.get("issue") || COST_GENERATOR_ISSUE, 10);
  const templateVersion = normalizeTemplateVersion(form.get("templateVersion"));
  const note = String(form.get("note") || "").trim().slice(0, MAX_COMMENT);

  if (!isAllowedRepo(repo, env)) {
    return json({ error: "forbidden_repo" }, 403, cors);
  }
  if (!Number.isInteger(issue) || issue <= 0) {
    return json({ error: "bad_issue" }, 400, cors);
  }

  const files = [];
  for (const input of COST_INPUTS) {
    const file = form.get(input.field);
    const checked = validateWorkbookFile(file);
    if (checked.error) {
      return json({ error: checked.error, field: input.field, label: input.label }, checked.status, cors);
    }
    files.push({ ...input, file, safeName: checked.safeName });
  }

  const requestedAt = new Date().toISOString();
  const requestId = requestedAt.replace(/[:.]/g, "-");
  const repoKey = repo.replace("/", "__");
  const prefix = `cost-requests/${repoKey}/${issue}/${requestId}`;
  const saved = [];

  for (const item of files) {
    const key = `${prefix}/${item.field}__${item.safeName}`;
    await env.DOCS_BUCKET.put(key, item.file.stream(), {
      httpMetadata: {
        contentType: item.file.type || contentTypeForWorkbook(item.safeName),
        contentDisposition: `attachment; filename*=UTF-8''${encodeURIComponent(item.safeName)}`,
      },
      customMetadata: {
        repo,
        issue: String(issue),
        title: "Cost statement generator request",
        /*
        title: "3개 입력 엑셀 기반 원가계산서 생성기",
        */
        source: "cost-generator",
        requestId,
        role: item.field,
        label: item.label,
        filename: item.safeName,
        requestedAt,
        templateVersion,
      },
    });
    saved.push({
      role: item.field,
      label: item.label,
      filename: item.safeName,
      size: item.file.size,
      key,
    });
  }

  const lines = [
    "### 원가계산서 생성 요청 접수",
    "",
    `- 요청 ID: \`${requestId}\``,
    `- 템플릿: \`${templateVersion}\``,
    `- 접수(서버 시각): ${requestedAt}`,
    "",
    "| 입력 | 파일명 | 크기 | R2 key |",
    "| --- | --- | ---: | --- |",
    ...saved.map((item) => `| ${item.label} | \`${item.filename}\` | ${formatBytes(item.size)} | \`${item.key}\` |`),
    "",
    note ? `#### 요청 메모\n${note}` : "",
    "",
    "_원문 Excel은 GitHub에 저장하지 않고 비공개 R2 저장소에 보관했습니다. 다음 처리 단계에서 위 requestId로 원가계산서 workbook을 생성합니다._",
  ].filter(Boolean);

  const ghRes = await fetch(`${GITHUB_API}/repos/${repo}/issues/${issue}/comments`, {
    method: "POST",
    headers: githubHeaders(env),
    body: JSON.stringify({ body: lines.join("\n") }),
  });

  if (!ghRes.ok) {
    const detail = await safeText(ghRes);
    return json({ error: "github_error_after_upload", status: ghRes.status, detail, requestId, files: saved }, 502, cors);
  }

  const data = await ghRes.json();
  return json({
    ok: true,
    status: "queued",
    requestId,
    templateVersion,
    files: saved,
    issueUrl: data.html_url,
    message: "원가계산서 생성 요청을 접수하고 GitHub Issue에 기록했습니다.",
  }, 200, cors);
}

/* ------------------------------ GET /counts ------------------------------ */

async function handleCounts(url, env, cors) {
  const repo = String(url.searchParams.get("repo") || "").trim();
  const issuesParam = String(url.searchParams.get("issues") || "").trim();

  if (!isAllowedRepo(repo, env)) {
    return json({ error: "forbidden_repo" }, 403, cors);
  }

  const issues = issuesParam
    .split(",")
    .map((s) => parseInt(s, 10))
    .filter((n) => Number.isInteger(n) && n > 0)
    .slice(0, 30);

  const result = {};
  await Promise.all(
    issues.map(async (n) => {
      try {
        const res = await fetch(`${GITHUB_API}/repos/${repo}/issues/${n}`, {
          headers: githubHeaders(env),
          // 60초 캐시로 GitHub API 호출 최소화
          cf: { cacheTtl: 60, cacheEverything: true },
        });
        if (res.ok) {
          const issue = await res.json();
          result[n] = typeof issue.comments === "number" ? issue.comments : 0;
        } else {
          result[n] = 0;
        }
      } catch {
        result[n] = 0;
      }
    })
  );

  return json(result, 200, {
    ...cors,
    "Cache-Control": "public, max-age=60",
  });
}

/* ------------------------------- private docs ---------------------------- */

async function handleDocsList(request, url, env, cors) {
  if (!env.DOCS_BUCKET) {
    return json({ error: "missing_r2_binding" }, 500, cors);
  }
  if (!isValidDocsPassword(request.headers.get("X-Docs-Password") || "", env)) {
    return json({ error: "bad_password" }, 403, cors);
  }

  const repo = String(url.searchParams.get("repo") || "").trim();
  const issue = parseInt(url.searchParams.get("issue"), 10);
  if (!isAllowedRepo(repo, env)) {
    return json({ error: "forbidden_repo" }, 403, cors);
  }

  const repoKey = repo.replace("/", "__");
  const prefix = Number.isInteger(issue) && issue > 0
    ? `docs/${repoKey}/${issue}/`
    : `docs/${repoKey}/`;

  const listed = await env.DOCS_BUCKET.list({ prefix, limit: 1000 });
  const files = listed.objects.map((obj) => ({
    key: obj.key,
    size: obj.size,
    uploadedAt: obj.customMetadata?.uploadedAt || obj.uploaded?.toISOString?.() || "",
    filename: obj.customMetadata?.filename || filenameFromKey(obj.key),
    issue: obj.customMetadata?.issue || "",
    title: obj.customMetadata?.title || "",
    source: obj.customMetadata?.source || "",
    ref: obj.customMetadata?.ref || "",
  }));

  return json({ ok: true, files }, 200, cors);
}

async function handleDocsDownload(request, url, env, cors) {
  if (!env.DOCS_BUCKET) {
    return json({ error: "missing_r2_binding" }, 500, cors);
  }
  if (!isValidDocsPassword(request.headers.get("X-Docs-Password") || "", env)) {
    return json({ error: "bad_password" }, 403, cors);
  }

  const repo = String(url.searchParams.get("repo") || "").trim();
  const key = String(url.searchParams.get("key") || "").trim();
  if (!isAllowedRepo(repo, env)) {
    return json({ error: "forbidden_repo" }, 403, cors);
  }

  const repoKey = repo.replace("/", "__");
  if (!key.startsWith(`docs/${repoKey}/`)) {
    return json({ error: "forbidden_key" }, 403, cors);
  }

  const obj = await env.DOCS_BUCKET.get(key);
  if (!obj) {
    return json({ error: "not_found" }, 404, cors);
  }

  const filename = obj.customMetadata?.filename || filenameFromKey(key);
  const headers = {
    ...cors,
    "Content-Type": obj.httpMetadata?.contentType || "application/octet-stream",
    "Content-Length": String(obj.size),
    "Content-Disposition": `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`,
    "Cache-Control": "no-store",
  };
  return new Response(obj.body, { status: 200, headers });
}

/* ----------------------------- protected DB CSV -------------------------- */

async function handleDbTables(request, url, env, cors) {
  const access = validateDbRequest(request, url, env, cors);
  if (access) return access;

  const tables = await Promise.all(
    DB_TABLES.map(async (table) => {
      // xlsx 등 비-CSV는 서버에서 파싱하지 않는다(브라우저에서 SheetJS로 처리).
      if (table.kind && table.kind !== "csv") {
        return { ...publicDbMeta(table), rows: 0, columns: [], available: true };
      }
      try {
        const parsed = await loadDbTable(env, table);
        return {
          ...publicDbMeta(table),
          rows: parsed.rows.length,
          columns: parsed.columns,
          available: true,
        };
      } catch (err) {
        return {
          ...publicDbMeta(table),
          rows: 0,
          columns: [],
          available: false,
          error: String(err && err.message || err),
        };
      }
    })
  );

  return json({ ok: true, tables }, 200, { ...cors, "Cache-Control": "no-store" });
}

async function handleDbTable(request, url, env, cors) {
  const access = validateDbRequest(request, url, env, cors);
  if (access) return access;

  const table = getDbTable(url.searchParams.get("name"));
  if (!table) {
    return json({ error: "bad_table" }, 400, cors);
  }
  if (table.kind && table.kind !== "csv") {
    return json({ error: "not_tabular", detail: "use /db/download for non-csv" }, 400, cors);
  }

  const parsed = await loadDbTable(env, table);
  return json(
    {
      ok: true,
      ...publicDbMeta(table),
      columns: parsed.columns,
      rows: parsed.rows,
    },
    200,
    { ...cors, "Cache-Control": "no-store" }
  );
}

async function handleDbDownload(request, url, env, cors) {
  const access = validateDbRequest(request, url, env, cors);
  if (access) return access;

  const table = getDbTable(url.searchParams.get("name"));
  if (!table) {
    return json({ error: "bad_table" }, 400, cors);
  }

  const obj = await env.DOCS_BUCKET.get(dbKey(table));
  if (!obj) {
    return json({ error: "not_found" }, 404, cors);
  }

  const ext = extensionOf(table.source) || "csv";
  const contentType = DB_CONTENT_TYPES[ext] || "application/octet-stream";
  return new Response(obj.body, {
    status: 200,
    headers: {
      ...cors,
      "Content-Type": contentType,
      "Content-Disposition": `attachment; filename*=UTF-8''${encodeURIComponent(`kiba_${table.name}.${ext}`)}`,
      "Cache-Control": "no-store",
    },
  });
}

const DB_CONTENT_TYPES = {
  csv: "text/csv; charset=utf-8",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  xls: "application/vnd.ms-excel",
};

function validateDbRequest(request, url, env, cors) {
  if (!env.DOCS_BUCKET) {
    return json({ error: "missing_r2_binding" }, 500, cors);
  }
  if (!isValidDocsPassword(request.headers.get("X-Docs-Password") || "", env)) {
    return json({ error: "bad_password" }, 403, cors);
  }
  const repo = String(url.searchParams.get("repo") || "").trim();
  if (!isAllowedRepo(repo, env)) {
    return json({ error: "forbidden_repo" }, 403, cors);
  }
  return null;
}

function publicDbMeta(table) {
  return {
    name: table.name,
    label: table.label,
    source: table.source,
    description: table.description,
    sensitive: table.sensitive,
  };
}

function getDbTable(name) {
  const normalized = String(name || "").trim();
  return DB_TABLES.find((table) => table.name === normalized) || null;
}

function dbKey(table) {
  return `db/${table.source}`;
}

async function loadDbTable(env, table) {
  const obj = await env.DOCS_BUCKET.get(dbKey(table));
  if (!obj) {
    throw new Error(`missing ${dbKey(table)}`);
  }
  const bytes = await obj.arrayBuffer();
  const text = new TextDecoder("utf-8").decode(bytes);
  const matrix = parseCsv(text);
  const columns = matrix.shift() || [];
  const rows = matrix
    .filter((row) => row.some((value) => String(value || "").trim() !== ""))
    .map((row) => {
      const item = {};
      columns.forEach((col, index) => {
        item[col] = row[index] || "";
      });
      return item;
    });
  return { columns, rows };
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;
  const input = String(text || "").replace(/^\uFEFF/, "");

  for (let i = 0; i < input.length; i += 1) {
    const ch = input[i];
    const next = input[i + 1];
    if (inQuotes) {
      if (ch === '"' && next === '"') {
        field += '"';
        i += 1;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        field += ch;
      }
      continue;
    }

    if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (ch !== "\r") {
      field += ch;
    }
  }

  row.push(field);
  if (row.length > 1 || row[0] !== "" || input.endsWith(",")) {
    rows.push(row);
  }
  return rows;
}

/* ------------------------- 우선순위 매트릭스 라벨 ------------------------- */

// GET /labels?repo=<owner/name>&issues=1,2,3
// -> { "1": { importance: "high"|"low"|null, urgency: ... }, ... }
async function handleLabelsGet(url, env, cors) {
  const repo = String(url.searchParams.get("repo") || "").trim();
  const issuesParam = String(url.searchParams.get("issues") || "").trim();
  if (!isAllowedRepo(repo, env)) {
    return json({ error: "forbidden_repo" }, 403, cors);
  }
  const issues = issuesParam
    .split(",")
    .map((s) => parseInt(s, 10))
    .filter((n) => Number.isInteger(n) && n > 0)
    .slice(0, 50);

  const result = {};
  await Promise.all(
    issues.map(async (n) => {
      try {
        const res = await fetch(`${GITHUB_API}/repos/${repo}/issues/${n}`, {
          headers: githubHeaders(env),
          cf: { cacheTtl: 30, cacheEverything: true },
        });
        if (res.ok) {
          const issue = await res.json();
          const names = (issue.labels || []).map((l) => (typeof l === "string" ? l : l.name));
          result[n] = { importance: levelFrom(names, IMP_PREFIX), urgency: levelFrom(names, URG_PREFIX) };
        } else {
          result[n] = { importance: null, urgency: null };
        }
      } catch {
        result[n] = { importance: null, urgency: null };
      }
    })
  );

  return json(result, 200, { ...cors, "Cache-Control": "public, max-age=30" });
}

// POST /labels { repo, issue, importance: "high"|"low", urgency: "high"|"low",
//                clear?: true, password, website }
// 비밀번호(DOCS_PASSWORD)로 보호. 중요도/긴급도 라벨만 교체하고 다른 라벨은 보존한다.
async function handleLabelsSet(request, env, cors, origin) {
  if (!isAllowedOrigin(origin, env)) {
    return json({ error: "forbidden_origin" }, 403, cors);
  }
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "bad_json" }, 400, cors);
  }
  if (body.website) {
    return json({ ok: true, skipped: true }, 200, cors);
  }

  const password = String(body.password || request.headers.get("X-Docs-Password") || "");
  if (!isValidDocsPassword(password, env)) {
    return json({ error: "bad_password" }, 403, cors);
  }

  const repo = String(body.repo || "").trim();
  const issue = parseInt(body.issue, 10);
  if (!isAllowedRepo(repo, env)) {
    return json({ error: "forbidden_repo" }, 403, cors);
  }
  if (!Number.isInteger(issue) || issue <= 0) {
    return json({ error: "bad_issue" }, 400, cors);
  }

  const clear = body.clear === true;
  let impName = null;
  let urgName = null;
  if (!clear) {
    const imp = String(body.importance || "");
    const urg = String(body.urgency || "");
    if (!["high", "low"].includes(imp) || !["high", "low"].includes(urg)) {
      return json({ error: "bad_level" }, 400, cors);
    }
    impName = IMP_PREFIX + (imp === "high" ? "높음" : "낮음");
    urgName = URG_PREFIX + (urg === "high" ? "높음" : "낮음");
  }

  // 현재 라벨 조회
  const cur = await fetch(`${GITHUB_API}/repos/${repo}/issues/${issue}`, {
    headers: githubHeaders(env),
  });
  if (!cur.ok) {
    return json({ error: "github_error", status: cur.status, detail: await safeText(cur) }, 502, cors);
  }
  const issueData = await cur.json();
  const names = (issueData.labels || []).map((l) => (typeof l === "string" ? l : l.name));

  // 같은 카테고리(중요도/긴급도)의 기존 라벨 중 새 값이 아닌 것 제거
  const keep = (name) => (impName && name === impName) || (urgName && name === urgName);
  const toRemove = names.filter(
    (n) => (n.startsWith(IMP_PREFIX) || n.startsWith(URG_PREFIX)) && !keep(n)
  );
  for (const name of toRemove) {
    await fetch(
      `${GITHUB_API}/repos/${repo}/issues/${issue}/labels/${encodeURIComponent(name)}`,
      { method: "DELETE", headers: githubHeaders(env) }
    );
  }

  // 새 라벨 추가(없으면 색상과 함께 생성)
  if (!clear) {
    await ensureLabel(env, repo, impName, "b60205");
    await ensureLabel(env, repo, urgName, "d93f0b");
    const add = await fetch(`${GITHUB_API}/repos/${repo}/issues/${issue}/labels`, {
      method: "POST",
      headers: githubHeaders(env),
      body: JSON.stringify({ labels: [impName, urgName] }),
    });
    if (!add.ok) {
      return json({ error: "github_error", status: add.status, detail: await safeText(add) }, 502, cors);
    }
  }

  return json(
    { ok: true, importance: clear ? null : body.importance, urgency: clear ? null : body.urgency },
    200,
    cors
  );
}

function levelFrom(names, prefix) {
  const hit = names.find((n) => typeof n === "string" && n.startsWith(prefix));
  if (!hit) return null;
  const v = hit.slice(prefix.length);
  if (v === "높음") return "high";
  if (v === "낮음") return "low";
  return null;
}

async function ensureLabel(env, repo, name, color) {
  try {
    await fetch(`${GITHUB_API}/repos/${repo}/labels`, {
      method: "POST",
      headers: githubHeaders(env),
      body: JSON.stringify({ name, color }),
    });
  } catch {
    // 이미 존재(422) 등은 무시
  }
}

/* -------------------------------- helpers -------------------------------- */

function githubHeaders(env) {
  return {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "kiba-memo-proxy",
    "Content-Type": "application/json",
  };
}

function listFromEnv(value) {
  return String(value || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function isAllowedOrigin(origin, env) {
  const allowed = listFromEnv(env.ALLOWED_ORIGINS);
  if (allowed.length === 0) return false;
  return allowed.includes(origin);
}

function isAllowedRepo(repo, env) {
  const allowed = listFromEnv(env.ALLOWED_REPOS);
  if (allowed.length === 0) return false;
  return allowed.includes(repo);
}

function isValidDocsPassword(input, env) {
  const expected = String(env.DOCS_PASSWORD || env.UPLOAD_PASSWORD || "");
  if (!expected || !input) return false;
  return constantTimeEqual(String(input), expected);
}

function constantTimeEqual(a, b) {
  const left = new TextEncoder().encode(a);
  const right = new TextEncoder().encode(b);
  const len = Math.max(left.length, right.length);
  let diff = left.length ^ right.length;
  for (let i = 0; i < len; i++) {
    diff |= (left[i] || 0) ^ (right[i] || 0);
  }
  return diff === 0;
}

function corsHeaders(origin, env) {
  const allowed = listFromEnv(env.ALLOWED_ORIGINS);
  const allow = allowed.includes(origin) ? origin : (allowed[0] || "");
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Docs-Password",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

function safeFilename(name) {
  const cleaned = String(name || "document")
    .replace(/[\\/:*?"<>|]+/g, "_")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 160);
  return cleaned || "document";
}

function filenameFromKey(key) {
  return decodeURIComponent(String(key).split("/").pop() || "document").replace(/^[^_]+__/, "");
}

function extensionOf(name) {
  const parts = String(name).toLowerCase().split(".");
  return parts.length > 1 ? parts.pop() : "";
}

function formatBytes(size) {
  const units = ["B", "KB", "MB", "GB"];
  let value = Number(size) || 0;
  let idx = 0;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  return `${value.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function normalizeTemplateVersion(value) {
  const text = String(value || "ver1").trim().toLowerCase();
  return text === "ver2" ? "ver2" : "ver1";
}

function validateWorkbookFile(file) {
  if (!(file instanceof File) || !file.name) {
    return { error: "missing_file", status: 400 };
  }
  if (file.size <= 0) {
    return { error: "empty_file", status: 400 };
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return { error: "file_too_large", status: 400 };
  }
  const safeName = safeFilename(file.name);
  const ext = extensionOf(safeName);
  if (!["xlsx", "xlsm", "xls"].includes(ext)) {
    return { error: "bad_workbook_type", status: 400 };
  }
  if (BLOCKED_EXTENSIONS.has(ext)) {
    return { error: "blocked_file_type", status: 400 };
  }
  return { safeName };
}

function contentTypeForWorkbook(name) {
  const ext = extensionOf(name);
  if (ext === "xlsx") return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  if (ext === "xlsm") return "application/vnd.ms-excel.sheet.macroEnabled.12";
  if (ext === "xls") return "application/vnd.ms-excel";
  return "application/octet-stream";
}

async function verifyTurnstile(secret, token, request) {
  if (!token) return false;
  const form = new FormData();
  form.append("secret", secret);
  form.append("response", token);
  const ip = request.headers.get("CF-Connecting-IP");
  if (ip) form.append("remoteip", ip);

  const res = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    body: form,
  });
  if (!res.ok) return false;
  const data = await res.json();
  return data.success === true;
}

function json(obj, status, headers) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

async function safeText(res) {
  try {
    return (await res.text()).slice(0, 500);
  } catch {
    return "";
  }
}
