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
 *  - POST /cost/generate multipart/form-data { repo, issue, password, combinedWorkbook | priceComparison, unitCost, detail }
 *  - GET  /cost/status?repo=<owner/name>&issue=42&requestId=... (header: X-Docs-Password)
 *  - GET  /cost/download?repo=<owner/name>&issue=42&requestId=... (header: X-Docs-Password)
 *  - POST /meeting/summarize multipart/form-data { password, audio|transcript|transcriptFile, meetingDate, topic }
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
 *  - CLOVA_CSR_CLIENT_ID / CLOVA_CSR_CLIENT_SECRET (Secret) 짧은 녹음 STT
 *  - GEMINI_API_KEY   (Secret)  회의록 요약. GEMINI_MODEL은 선택 Var/Secret
 */

const GITHUB_API = "https://api.github.com";
const MAX_COMMENT = 4000;
const MAX_TITLE = 300;
const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
const MAX_MEETING_AUDIO_BYTES = 3 * 1024 * 1024;
const MAX_MEETING_TEXT_BYTES = 2 * 1024 * 1024;
const MAX_MEETING_REQUEST_BYTES = Math.max(MAX_MEETING_AUDIO_BYTES, MAX_MEETING_TEXT_BYTES) + 64 * 1024;
const MEETING_DIRECT_TRANSCRIPT_CHARS = 180000;
const MEETING_TRANSCRIPT_CHUNK_CHARS = 180000;
const MEETING_AUDIO_EXTENSIONS = new Set(["mp3", "wav", "flac", "aac", "ogg", "ac3"]);
const MEETING_TEXT_EXTENSIONS = new Set(["txt", "vtt", "srt"]);
const COST_GENERATOR_ISSUE = 42;
const COST_RESULT_FILENAME = "\uC6D0\uAC00\uACC4\uC0B0\uC11C.xlsx";
const COST_INPUTS = [
  { field: "priceComparison", label: "\uB2E8\uAC00\uB300\uBE44\uD45C" },
  { field: "unitCost", label: "\uC77C\uC704\uB300\uAC00\uD45C" },
  { field: "detail", label: "\uB0B4\uC5ED\uC11C" },
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
      if (url.pathname === "/cost/status" && request.method === "GET") {
        return await handleCostStatus(request, url, env, cors, origin);
      }
      if (url.pathname === "/cost/download" && request.method === "GET") {
        return await handleCostDownload(request, url, env, cors, origin);
      }
      if (url.pathname === "/meeting/summarize" && request.method === "POST") {
        return await handleMeetingSummarize(request, env, cors, origin);
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

/* ----------------------- POST /meeting/summarize -------------------------- */
// 회의 전사 텍스트(또는 짧은 오디오) → CLOVA CSR(오디오) → Gemini 회의록(markdown).
// 시크릿: GEMINI_API_KEY, (선택)GEMINI_MODEL, CLOVA_CSR_CLIENT_ID/SECRET.

async function handleMeetingSummarize(request, env, cors, origin) {
  if (!isAllowedOrigin(origin, env)) {
    return json({ error: "forbidden_origin" }, 403, cors);
  }
  const contentLength = Number(request.headers.get("Content-Length") || 0);
  if (Number.isFinite(contentLength) && contentLength > MAX_MEETING_REQUEST_BYTES) {
    return json({ error: "input_too_large", maxAudioBytes: MAX_MEETING_AUDIO_BYTES, maxTextBytes: MAX_MEETING_TEXT_BYTES }, 413, cors);
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

  let transcript = "";
  let sttUsed = false;
  let transcriptFileUsed = false;
  const audio = form.get("audio");
  const transcriptFile = form.get("transcriptFile");
  const directTranscript = form.get("transcript");
  const transcriptFilename = String(form.get("transcriptFilename") || "").trim();
  if (typeof directTranscript === "string" && directTranscript.trim()) {
    if (transcriptFilename && !MEETING_TEXT_EXTENSIONS.has(extensionOf(transcriptFilename))) {
      return json({ error: "bad_text_type" }, 400, cors);
    }
    const checkedTranscript = validateMeetingTranscriptText(directTranscript);
    if (checkedTranscript.error) {
      return json({ error: checkedTranscript.error, maxBytes: MAX_MEETING_TEXT_BYTES }, checkedTranscript.status, cors);
    }
    transcript = normalizeTranscriptText(directTranscript);
  }
  if (!transcript) {
    const textCandidate = transcriptFile instanceof File ? transcriptFile : (isMeetingTextFile(audio) ? audio : null);
    if (textCandidate) {
      const checkedText = validateMeetingTextFile(textCandidate);
      if (checkedText.error) {
        return json({ error: checkedText.error, maxBytes: MAX_MEETING_TEXT_BYTES }, checkedText.status, cors);
      }
      const textBody = await textCandidate.text();
      const checkedBody = validateMeetingTranscriptText(textBody);
      if (checkedBody.error) {
        return json({ error: checkedBody.error, maxBytes: MAX_MEETING_TEXT_BYTES }, checkedBody.status, cors);
      }
      transcript = normalizeTranscriptText(textBody);
      transcriptFileUsed = true;
    }
  }
  if (!transcript) {
    const checked = validateMeetingAudio(audio);
    if (checked.error) {
      return json({ error: checked.error, maxBytes: MAX_MEETING_AUDIO_BYTES }, checked.status, cors);
    }
    try {
      transcript = await clovaCsrTranscribe(await audio.arrayBuffer(), env);
    } catch (error) {
      console.error(JSON.stringify({
        message: "meeting transcription failed",
        error: error instanceof Error ? error.message : String(error),
      }));
      return json({ error: "stt_failed" }, 502, cors);
    }
    sttUsed = true;
  }
  if (!transcript) {
    return json({ error: "empty_input", message: "전사 텍스트를 붙여넣거나 음성 파일을 올려주세요." }, 400, cors);
  }

  const requestedDate = String(form.get("meetingDate") || "").trim();
  const meetingDate = /^\d{4}-\d{2}-\d{2}$/.test(requestedDate)
    ? requestedDate
    : new Date().toISOString().slice(0, 10);
  const topic = String(form.get("topic") || "").trim().slice(0, 100);
  let report;
  try {
    report = await geminiMeetingReport(transcript, env, meetingDate, topic);
  } catch (error) {
    if (canUseMeetingFallback(error)) {
      const detail = error instanceof Error ? error.message : String(error);
      console.error(JSON.stringify({
        message: "meeting summary fallback used",
        error: detail,
      }));
      report = fallbackMeetingReport(transcript, meetingDate, topic, detail);
      return json({ ok: true, report, sttUsed, transcriptFileUsed, transcriptChars: transcript.length, fallbackUsed: true }, 200, cors);
    }
    return meetingSummaryErrorResponse(error, cors);
  }
  return json({ ok: true, report, sttUsed, transcriptFileUsed, transcriptChars: transcript.length }, 200, cors);
}

function canUseMeetingFallback(error) {
  const detail = error instanceof Error ? error.message : String(error);
  return !/missing GEMINI_API_KEY|gemini\s+(401|403|404)\b|API_KEY_INVALID|UNAUTHENTICATED|PERMISSION_DENIED|model.*not found|not found.*model/i.test(detail);
}

function meetingSummaryErrorResponse(error, cors) {
  const detail = error instanceof Error ? error.message : String(error);
  console.error(JSON.stringify({
    message: "meeting summary failed",
    error: detail,
  }));
  if (/missing GEMINI_API_KEY/i.test(detail)) {
    return json({ error: "summary_not_configured" }, 503, cors);
  }
  if (/gemini\s+(401|403)\b|API_KEY_INVALID|UNAUTHENTICATED|PERMISSION_DENIED/i.test(detail)) {
    return json({ error: "summary_auth_failed" }, 502, cors);
  }
  if (/gemini\s+429\b|RESOURCE_EXHAUSTED|quota|rate/i.test(detail)) {
    return json({ error: "summary_rate_limited" }, 429, cors);
  }
  if (/gemini\s+404\b|model.*not found|not found.*model/i.test(detail)) {
    return json({ error: "summary_model_unavailable" }, 502, cors);
  }
  return json({ error: "summary_failed" }, 502, cors);
}

function validateMeetingAudio(file) {
  if (!(file instanceof File) || !file.name) {
    return { error: "missing_input", status: 400 };
  }
  if (file.size <= 0) {
    return { error: "empty_audio", status: 400 };
  }
  if (file.size > MAX_MEETING_AUDIO_BYTES) {
    return { error: "audio_too_large", status: 413 };
  }
  if (!MEETING_AUDIO_EXTENSIONS.has(extensionOf(file.name))) {
    return { error: "bad_audio_type", status: 400 };
  }
  return { file };
}

function isMeetingTextFile(file) {
  return file instanceof File && file.name && MEETING_TEXT_EXTENSIONS.has(extensionOf(file.name));
}

function validateMeetingTextFile(file) {
  if (!(file instanceof File) || !file.name) {
    return { error: "missing_input", status: 400 };
  }
  if (file.size <= 0) {
    return { error: "empty_text", status: 400 };
  }
  if (file.size > MAX_MEETING_TEXT_BYTES) {
    return { error: "text_too_large", status: 413 };
  }
  if (!MEETING_TEXT_EXTENSIONS.has(extensionOf(file.name))) {
    return { error: "bad_text_type", status: 400 };
  }
  return { file };
}

function validateMeetingTranscriptText(value) {
  const text = String(value || "");
  if (!text.trim()) {
    return { error: "empty_text", status: 400 };
  }
  if (looksLikeBinaryText(text)) {
    return { error: "bad_text_content", status: 400 };
  }
  const bytes = new TextEncoder().encode(text).byteLength;
  if (bytes > MAX_MEETING_TEXT_BYTES) {
    return { error: "text_too_large", status: 413 };
  }
  return {};
}

function looksLikeBinaryText(value) {
  const sample = String(value || "").slice(0, 8192);
  if (!sample) return false;
  if (/^PK[\u0003\u0005\u0007]/.test(sample) || (/^PK/.test(sample) && /\b(xl|word|ppt)\/|Content_Types\.xml/i.test(sample))) {
    return true;
  }
  if (sample.includes("\u0000")) return true;
  const suspicious = sample.match(/[\u0001-\u0008\u000B\u000C\u000E-\u001F\uFFFD]/g);
  return Boolean(suspicious && suspicious.length / sample.length > 0.02);
}

function normalizeTranscriptText(value) {
  return String(value || "")
    .replace(/^\uFEFF/, "")
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .filter((line) => {
      const trimmed = line.trim();
      if (/^WEBVTT\b/i.test(trimmed)) return false;
      if (/^\d+$/.test(trimmed)) return false;
      if (/^\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{1,2}:\d{2}:\d{2}[,.]\d{3}/.test(trimmed)) return false;
      return true;
    })
    .join("\n")
    .replace(/<\/?v(?:\s+[^>]*)?>/g, "")
    .replace(/<\d{1,2}:\d{2}:\d{2}[,.]\d{3}>/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

async function clovaCsrTranscribe(arrayBuffer, env) {
  const id = env.CLOVA_CSR_CLIENT_ID;
  const secret = env.CLOVA_CSR_CLIENT_SECRET;
  if (!id || !secret) throw new Error("missing CLOVA_CSR credentials");
  const res = await fetch("https://naveropenapi.apigw.ntruss.com/recog/v1/stt?lang=Kor", {
    method: "POST",
    headers: {
      "X-NCP-APIGW-API-KEY-ID": id,
      "X-NCP-APIGW-API-KEY": secret,
      "Content-Type": "application/octet-stream",
    },
    body: arrayBuffer,
  });
  if (!res.ok) throw new Error("clova " + res.status + " " + (await res.text()).slice(0, 200));
  const data = await res.json();
  return (data.text || "").trim();
}

async function geminiMeetingReport(transcript, env, meetingDate, topic) {
  if (transcript.length > MEETING_DIRECT_TRANSCRIPT_CHARS) {
    const chunks = splitTranscriptIntoChunks(transcript, MEETING_TRANSCRIPT_CHUNK_CHARS);
    const summaries = [];
    for (let i = 0; i < chunks.length; i += 1) {
      summaries.push(await geminiMeetingChunkSummary(chunks[i], env, meetingDate, topic, i + 1, chunks.length));
    }
    return await geminiMeetingReportFromSummaries(summaries, env, meetingDate, topic);
  }
  return await geminiMeetingReportFromTranscript(transcript, env, meetingDate, topic);
}

async function geminiMeetingReportFromTranscript(transcript, env, meetingDate, topic) {
  const key = env.GEMINI_API_KEY;
  if (!key) throw new Error("missing GEMINI_API_KEY");
  const model = env.GEMINI_MODEL || "gemini-2.5-flash";
  const prompt =
    `회의 날짜는 ${meetingDate}이다. 상대 날짜는 이 연도 기준으로 해석하라.\n` +
    (topic ? `회의 주제는 "${topic}"이다.\n` : "") +
    "다음 KIBA 회의 전사본을 원장님 보고용 한국어 회의록(markdown)으로 정리하라. " +
    "원문에 실제로 있는 내용만 사용하고 추측·창작은 금지. 아래 형식을 정확히 따르라:\n" +
    `# ${meetingDate} ${topic || "일일 회의"} 회의록\n## 요약\n- ...\n## 결정 사항\n- ...\n` +
    "## 할 일\n- [ ] 내용 — @담당자 ~YYYY-MM-DD (이슈 #N)\n## 다음 안건\n- ...\n\n전사본:\n" +
    transcript;
  return await geminiGenerateText(key, model, prompt);
}

async function geminiMeetingChunkSummary(transcript, env, meetingDate, topic, index, total) {
  const key = env.GEMINI_API_KEY;
  if (!key) throw new Error("missing GEMINI_API_KEY");
  const model = env.GEMINI_MODEL || "gemini-2.5-flash";
  const prompt =
    `회의 날짜는 ${meetingDate}이다. ${total}개 부분 중 ${index}번째 전사본 일부를 요약하라.\n` +
    (topic ? `회의 주제는 "${topic}"이다.\n` : "") +
    "원문에 있는 내용만 사용하고 추측·창작은 금지. 최종 회의록 작성에 필요한 핵심 발언, 결정 사항, 할 일, 다음 안건 후보만 간결한 markdown bullet로 정리하라.\n\n" +
    `전사본 일부 ${index}/${total}:\n` +
    transcript;
  return await geminiGenerateText(key, model, prompt);
}

async function geminiMeetingReportFromSummaries(summaries, env, meetingDate, topic) {
  const key = env.GEMINI_API_KEY;
  if (!key) throw new Error("missing GEMINI_API_KEY");
  const model = env.GEMINI_MODEL || "gemini-2.5-flash";
  const prompt =
    `회의 날짜는 ${meetingDate}이다. 상대 날짜는 이 연도 기준으로 해석하라.\n` +
    (topic ? `회의 주제는 "${topic}"이다.\n` : "") +
    "아래는 긴 전사본을 부분별로 요약한 내용이다. 중복을 합치고 원문에 근거한 내용만 사용해 원장님 보고용 한국어 회의록(markdown)으로 정리하라. " +
    "추측·창작은 금지. 아래 형식을 정확히 따르라:\n" +
    `# ${meetingDate} ${topic || "일일 회의"} 회의록\n## 요약\n- ...\n## 결정 사항\n- ...\n` +
    "## 할 일\n- [ ] 내용 — @담당자 ~YYYY-MM-DD (이슈 #N)\n## 다음 안건\n- ...\n\n부분 요약:\n" +
    summaries.map((summary, index) => `### 부분 ${index + 1}\n${summary}`).join("\n\n");
  return await geminiGenerateText(key, model, prompt);
}

async function geminiGenerateText(key, model, prompt) {
  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${key}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] }),
    },
  );
  if (!res.ok) throw new Error("gemini " + res.status + " " + (await res.text()).slice(0, 200));
  const data = await res.json();
  const out = data && data.candidates && data.candidates[0] &&
    data.candidates[0].content && data.candidates[0].content.parts &&
    data.candidates[0].content.parts[0] && data.candidates[0].content.parts[0].text;
  if (!out) {
    const blockReason = data && data.promptFeedback && data.promptFeedback.blockReason;
    throw new Error("gemini empty response" + (blockReason ? ` ${blockReason}` : ""));
  }
  return out.trim();
}

function fallbackMeetingReport(transcript, meetingDate, topic, reason) {
  const lines = extractMeetingLines(transcript);
  const summary = pickImportantLines(lines, 5, FALLBACK_SUMMARY_KEYWORDS, true);
  const decisions = pickImportantLines(lines, 5, FALLBACK_DECISION_KEYWORDS);
  const todos = pickImportantLines(lines, 8, FALLBACK_TODO_KEYWORDS);
  const nextAgenda = pickImportantLines(lines, 5, FALLBACK_NEXT_KEYWORDS);

  return [
    `# ${meetingDate} ${topic || "일일 회의"} 회의록`,
    "",
    "> Gemini 요약이 실패해 서버가 원문 기반 자동 초안으로 생성했습니다. 중요한 내용은 원문과 대조해 주세요.",
    reason ? `> 실패 원인: ${safeReportLine(reason)}` : "",
    "",
    "## 요약",
    bulletBlock(summary),
    "",
    "## 결정 사항",
    bulletBlock(decisions),
    "",
    "## 할 일",
    todoBlock(todos),
    "",
    "## 다음 안건",
    bulletBlock(nextAgenda),
    "",
    "## 원문 주요 발췌",
    bulletBlock(lines.slice(0, 8)),
  ].filter((line) => line !== null).join("\n");
}

const FALLBACK_SUMMARY_KEYWORDS = ["결정", "확정", "정리", "비교", "자료", "금액", "적용", "보고", "입사", "수습", "연봉", "급여", "내역서", "단가", "대가", "원가"];
const FALLBACK_DECISION_KEYWORDS = ["결정", "확정", "적용", "바꿨", "완료", "다 됐", "정리되었습니다", "하면 되는"];
const FALLBACK_TODO_KEYWORDS = ["해야", "해줘", "해 주", "가져와", "다시", "확인", "정리", "올리", "보고", "설명", "검토", "작성", "바꿔", "수정", "준비", "비교", "처리", "연락"];
const FALLBACK_NEXT_KEYWORDS = ["어떻게", "왜", "맞나", "검토", "다시", "확인", "비교", "설명", "다음", "후속"];

function extractMeetingLines(transcript) {
  const seen = new Set();
  const lines = [];
  for (const rawLine of String(transcript || "").split("\n")) {
    const line = safeReportLine(rawLine.replace(/^\[[^\]]+\]\s*/, ""));
    if (line.length < 8 || seen.has(line)) continue;
    seen.add(line);
    lines.push(line);
  }
  return lines;
}

function pickImportantLines(lines, limit, keywords, useReadableBase = false) {
  return lines
    .map((line, index) => ({ line, index, score: fallbackLineScore(line, keywords, useReadableBase) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .slice(0, limit)
    .sort((a, b) => a.index - b.index)
    .map((item) => item.line);
}

function fallbackLineScore(line, keywords, useReadableBase) {
  let score = useReadableBase && line.length > 18 ? 1 : 0;
  for (const keyword of keywords) {
    if (line.includes(keyword)) score += 3;
  }
  if (/[?？]$/.test(line)) score += 1;
  return score;
}

function bulletBlock(lines) {
  return lines.length
    ? lines.map((line) => `- ${line}`).join("\n")
    : "- 원문 기반 자동 초안에서는 별도 항목을 확정하지 못했습니다.";
}

function todoBlock(lines) {
  return lines.length
    ? lines.map((line) => `- [ ] ${line} — @담당자`).join("\n")
    : "- [ ] 원문을 검토해 담당자와 기한을 확정하세요. — @담당자";
}

function safeReportLine(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .replace(/[|`]/g, "")
    .trim()
    .slice(0, 220);
}

function splitTranscriptIntoChunks(transcript, maxChars) {
  const chunks = [];
  let remaining = String(transcript || "").trim();
  while (remaining.length > maxChars) {
    const window = remaining.slice(0, maxChars + 1);
    const breakAt = Math.max(
      window.lastIndexOf("\n\n"),
      window.lastIndexOf("\n참석자"),
      window.lastIndexOf("\n")
    );
    const cut = breakAt > maxChars * 0.55 ? breakAt : maxChars;
    chunks.push(remaining.slice(0, cut).trim());
    remaining = remaining.slice(cut).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}

/* --------------------------- POST /cost/generate -------------------------- */

function costInputFilesFromForm(form) {
  const combinedWorkbook = form.get("combinedWorkbook");
  if (combinedWorkbook instanceof File && combinedWorkbook.name) {
    const checked = validateWorkbookFile(combinedWorkbook);
    if (checked.error) {
      return {
        error: { error: checked.error, field: "combinedWorkbook", label: "통합 엑셀" },
        status: checked.status,
      };
    }
    return COST_INPUTS.map((input) => ({
      ...input,
      file: combinedWorkbook,
      safeName: checked.safeName,
      inputMode: "combined",
    }));
  }

  const files = [];
  for (const input of COST_INPUTS) {
    const file = form.get(input.field);
    const checked = validateWorkbookFile(file);
    if (checked.error) {
      return {
        error: { error: checked.error, field: input.field, label: input.label },
        status: checked.status,
      };
    }
    files.push({ ...input, file, safeName: checked.safeName, inputMode: "separate" });
  }
  return files;
}

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
  if (!Number.isInteger(issue) || issue !== COST_GENERATOR_ISSUE) {
    return json({ error: "bad_issue" }, 400, cors);
  }

  const files = costInputFilesFromForm(form);
  if (files.error) {
    return json(files.error, files.status, cors);
  }

  const requestedAt = new Date().toISOString();
  const requestId = `${requestedAt.replace(/[:.]/g, "-")}-${crypto.randomUUID()}`;
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
        inputMode: item.inputMode || "separate",
      },
    });
    saved.push({
      role: item.field,
      label: item.label,
      filename: item.safeName,
      size: item.file.size,
      key,
      inputMode: item.inputMode || "separate",
    });
  }

  const templateKey = costTemplateKey(templateVersion);
  const inputMode = saved.every((item) => item.inputMode === "combined") ? "combined" : "separate";
  const outputKey = `${prefix}/result__${COST_RESULT_FILENAME}`;
  const statusKey = `${prefix}/status.json`;
  const job = {
    version: 1,
    repo,
    issue,
    requestId,
    requestedAt,
    templateVersion,
    templateKey,
    inputMode,
    inputKeys: Object.fromEntries(saved.map((item) => [item.role, item.key])),
    outputKey,
    statusKey,
  };
  await Promise.all([
    env.DOCS_BUCKET.put(`${prefix}/request.json`, JSON.stringify(job), {
      httpMetadata: { contentType: "application/json; charset=utf-8" },
      customMetadata: { repo, issue: String(issue), requestId, requestedAt, templateVersion },
    }),
    env.DOCS_BUCKET.put(statusKey, JSON.stringify({
      ok: true,
      status: "queued",
      requestId,
      requestedAt,
      updatedAt: requestedAt,
    }), {
      httpMetadata: { contentType: "application/json; charset=utf-8" },
      customMetadata: { repo, issue: String(issue), requestId, status: "queued" },
    }),
  ]);

  const lines = [
    "### 원가계산서 생성 요청 접수",
    "",
    `- 요청 ID: \`${requestId}\``,
    `- 접수(서버 시각): ${requestedAt}`,
    `- 입력 방식: ${inputMode === "combined" ? "통합 엑셀 1개" : "3개 파일 분리"}`,
    "",
    "| 입력 | 파일명 | 크기 | R2 key |",
    "| --- | --- | ---: | --- |",
    ...saved.map((item) => `| ${item.label} | \`${item.filename}\` | ${formatBytes(item.size)} | \`${item.key}\` |`),
    "",
    note ? `#### 요청 메모\n${note}` : "",
    "",
    "_원문 Excel은 GitHub에 저장하지 않고 비공개 R2 저장소에 보관했습니다. GitHub Actions 작업 큐가 위 requestId로 원가계산서 workbook을 생성합니다._",
    "",
    "<!-- kiba-cost-job",
    JSON.stringify(job),
    "-->",
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
    statusUrl: `/cost/status?repo=${encodeURIComponent(repo)}&issue=${issue}&requestId=${encodeURIComponent(requestId)}`,
    message: "원가계산서 생성 요청을 접수하고 GitHub Actions 작업 큐에 넣었습니다.",
  }, 202, cors);
}

/* ------------------------ GET /cost/status|download ---------------------- */

async function handleCostStatus(request, url, env, cors, origin) {
  const access = validateCostResultRequest(request, url, env, cors, origin);
  if (access instanceof Response) return access;

  const { repo, issue, requestId, prefix } = access;
  const statusKey = `${prefix}/status.json`;
  const outputKey = `${prefix}/result__${COST_RESULT_FILENAME}`;
  const [statusObject, outputObject] = await Promise.all([
    env.DOCS_BUCKET.get(statusKey),
    env.DOCS_BUCKET.head(outputKey),
  ]);

  let state = { status: outputObject ? "ready" : "queued" };
  if (statusObject) {
    try {
      state = await statusObject.json();
    } catch {
      state = { status: outputObject ? "ready" : "processing" };
    }
  }
  if (outputObject) state.status = "ready";

  return json({
    ok: true,
    ...state,
    repo,
    issue,
    requestId,
    ready: Boolean(outputObject),
    filename: outputObject ? COST_RESULT_FILENAME : null,
    size: outputObject?.size || null,
    downloadUrl: outputObject
      ? `/cost/download?repo=${encodeURIComponent(repo)}&issue=${issue}&requestId=${encodeURIComponent(requestId)}`
      : null,
  }, 200, { ...cors, "Cache-Control": "no-store" });
}

async function handleCostDownload(request, url, env, cors, origin) {
  const access = validateCostResultRequest(request, url, env, cors, origin);
  if (access instanceof Response) return access;

  const key = `${access.prefix}/result__${COST_RESULT_FILENAME}`;
  const object = await env.DOCS_BUCKET.get(key);
  if (!object) {
    return json({ error: "not_ready" }, 404, cors);
  }

  return new Response(object.body, {
    status: 200,
    headers: {
      ...cors,
      "Content-Type": object.httpMetadata?.contentType || contentTypeForWorkbook(COST_RESULT_FILENAME),
      "Content-Length": String(object.size),
      "Content-Disposition": `attachment; filename*=UTF-8''${encodeURIComponent(COST_RESULT_FILENAME)}`,
      "Cache-Control": "no-store",
      ETag: object.httpEtag,
    },
  });
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

function costTemplateKey(templateVersion) {
  const version = normalizeTemplateVersion(templateVersion);
  return `원가계산보고서샘플/(E)sample_원가계산보고서${version}.xlsx.xlsx`;
}

function validateCostResultRequest(request, url, env, cors, origin) {
  if (!isAllowedOrigin(origin, env)) {
    return json({ error: "forbidden_origin" }, 403, cors);
  }
  if (!env.DOCS_BUCKET) {
    return json({ error: "missing_r2_binding" }, 500, cors);
  }
  if (!isValidDocsPassword(request.headers.get("X-Docs-Password") || "", env)) {
    return json({ error: "bad_password" }, 403, cors);
  }

  const repo = String(url.searchParams.get("repo") || "").trim();
  const issue = parseInt(url.searchParams.get("issue") || COST_GENERATOR_ISSUE, 10);
  const requestId = String(url.searchParams.get("requestId") || "").trim();
  if (!isAllowedRepo(repo, env)) {
    return json({ error: "forbidden_repo" }, 403, cors);
  }
  if (!Number.isInteger(issue) || issue !== COST_GENERATOR_ISSUE) {
    return json({ error: "bad_issue" }, 400, cors);
  }
  if (!/^[0-9A-Za-z-]{20,120}$/.test(requestId)) {
    return json({ error: "bad_request_id" }, 400, cors);
  }

  const repoKey = repo.replace("/", "__");
  return {
    repo,
    issue,
    requestId,
    prefix: `cost-requests/${repoKey}/${issue}/${requestId}`,
  };
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
  if (!["xlsx", "xlsm"].includes(ext)) {
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
