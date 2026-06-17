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
 *  - GET  /counts?repo=<owner/name>&issues=1,2,3   -> { "1": 4, "2": 0, ... }
 *
 * 필요한 환경변수 (wrangler.toml / 대시보드)
 *  - GITHUB_TOKEN     (Secret)  Issues: Read and write 권한의 fine-grained PAT
 *  - ALLOWED_ORIGINS  (Var)     쉼표 구분. 예) "https://feed-mina.github.io"
 *  - ALLOWED_REPOS    (Var)     쉼표 구분. 예) "feed-mina/kiba_2026"
 *  - TURNSTILE_SECRET (Secret)  선택. 설정하면 Turnstile 검증을 강제한다.
 */

const GITHUB_API = "https://api.github.com";
const MAX_COMMENT = 4000;
const MAX_TITLE = 300;

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
      if (url.pathname === "/counts" && request.method === "GET") {
        return await handleCounts(url, env, cors);
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

function corsHeaders(origin, env) {
  const allowed = listFromEnv(env.ALLOWED_ORIGINS);
  const allow = allowed.includes(origin) ? origin : (allowed[0] || "");
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
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
