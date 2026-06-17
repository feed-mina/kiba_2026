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
const BLOCKED_EXTENSIONS = new Set([
  "exe", "bat", "cmd", "com", "scr", "ps1", "vbs", "js", "msi", "dll"
]);

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
      if (url.pathname === "/counts" && request.method === "GET") {
        return await handleCounts(url, env, cors);
      }
      if (url.pathname === "/docs/list" && request.method === "GET") {
        return await handleDocsList(request, url, env, cors);
      }
      if (url.pathname === "/docs/download" && request.method === "GET") {
        return await handleDocsDownload(request, url, env, cors);
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
