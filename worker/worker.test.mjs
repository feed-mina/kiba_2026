import assert from "node:assert/strict";
import test from "node:test";

import worker from "./worker.js";


class MemoryR2Bucket {
  constructor() {
    this.objects = new Map();
  }

  async put(key, value, options = {}) {
    let bytes;
    if (typeof value === "string") bytes = new TextEncoder().encode(value);
    else if (value instanceof Blob) bytes = new Uint8Array(await value.arrayBuffer());
    else if (value instanceof ReadableStream) bytes = new Uint8Array(await new Response(value).arrayBuffer());
    else bytes = new Uint8Array(value);
    const object = { key, bytes, options };
    this.objects.set(key, object);
    return this.metadata(object);
  }

  async get(key) {
    const object = this.objects.get(key);
    if (!object) return null;
    const metadata = this.metadata(object);
    return {
      ...metadata,
      body: new Blob([object.bytes]).stream(),
      json: async () => JSON.parse(new TextDecoder().decode(object.bytes)),
    };
  }

  async head(key) {
    const object = this.objects.get(key);
    return object ? this.metadata(object) : null;
  }

  async list({ prefix = "", limit = 1000 } = {}) {
    const objects = Array.from(this.objects.values())
      .filter((object) => object.key.startsWith(prefix))
      .slice(0, limit)
      .map((object) => this.metadata(object));
    return { objects, truncated: false };
  }

  async delete(key) {
    this.objects.delete(key);
  }

  metadata(object) {
    return {
      key: object.key,
      size: object.bytes.byteLength,
      httpEtag: '"memory-etag"',
      httpMetadata: object.options.httpMetadata || {},
      customMetadata: object.options.customMetadata || {},
    };
  }
}


test("issues endpoint returns repository issues and excludes pull requests", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    assert.match(String(url), /\/repos\/example\/project\/issues\?state=all/);
    return Response.json([
      {
        number: 12,
        title: "Prepare release",
        state: "open",
        html_url: "https://github.com/example/project/issues/12",
        labels: [{ name: "in progress" }, "important"],
        created_at: "2026-07-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
      },
      {
        number: 13,
        title: "Pull request",
        state: "open",
        html_url: "https://github.com/example/project/pull/13",
        labels: [],
        pull_request: {},
      },
    ]);
  };

  try {
    const response = await worker.fetch(
      new Request("https://worker.example/issues?repo=example/project&state=all"),
      { ALLOWED_REPOS: "example/project", GITHUB_TOKEN: "test-token" },
    );
    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.repo, "example/project");
    assert.equal(result.issues.length, 1);
    assert.deepEqual(result.issues[0].labels, ["in progress", "important"]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("repos endpoint follows pagination and removes duplicate repositories", async () => {
  const originalFetch = globalThis.fetch;
  const requestedPages = [];
  globalThis.fetch = async (url) => {
    const page = Number(new URL(url).searchParams.get("page"));
    requestedPages.push(page);
    if (page === 1) {
      return Response.json([
        { id: 1, name: "one", full_name: "example/one", private: false },
      ], {
        headers: { Link: '<https://api.github.com/user/repos?per_page=100&page=2>; rel="next"' },
      });
    }
    return Response.json([
      { id: 1, name: "one", full_name: "example/one", private: false },
      { id: 2, name: "two", full_name: "example/two", private: true },
      { id: 3, name: "secret", full_name: "example/secret", private: true },
    ]);
  };

  try {
    const response = await worker.fetch(
      new Request("https://worker.example/repos"),
      { GITHUB_TOKEN: "test-token", ALLOWED_REPOS: "example/one,example/two" },
    );
    assert.equal(response.status, 200);
    const result = await response.json();
    assert.deepEqual(requestedPages, [1, 2]);
    assert.equal(result.fetchedPages, 2);
    assert.deepEqual(result.repositories.map((repo) => repo.full_name), ["example/one", "example/two"]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("protected repositories stay hidden until the admin password is provided", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => Response.json([
    { id: 1, name: "public", full_name: "example/public", private: false },
    { id: 2, name: "private", full_name: "example/private", private: true },
  ]);

  const env = {
    GITHUB_TOKEN: "test-token",
    DOCS_PASSWORD: "test-password",
    ALLOWED_REPOS: "example/public,example/private",
    PROTECTED_REPOS: "example/private",
  };

  try {
    const publicResponse = await worker.fetch(new Request("https://worker.example/repos"), env);
    assert.equal(publicResponse.status, 200);
    assert.deepEqual((await publicResponse.json()).repositories.map((repo) => repo.full_name), ["example/public"]);

    const adminResponse = await worker.fetch(new Request("https://worker.example/repos", {
      headers: { "X-Docs-Password": "test-password" },
    }), env);
    assert.equal(adminResponse.status, 200);
    assert.deepEqual((await adminResponse.json()).repositories.map((repo) => repo.full_name), ["example/public", "example/private"]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("projects endpoint returns named choices only after admin authentication", async () => {
  const originalFetch = globalThis.fetch;
  let fetchCalls = 0;
  globalThis.fetch = async (url, init) => {
    fetchCalls += 1;
    assert.equal(String(url), "https://api.github.com/graphql");
    assert.equal(init.headers.Authorization, "Bearer project-token");
    const request = JSON.parse(init.body);
    assert.equal(request.variables.login, "feed-mina");
    return Response.json({
      data: {
        user: {
          projectsV2: {
            nodes: [
              { number: 1, title: "2026 하반기", url: "https://github.com/users/feed-mina/projects/1", closed: false, updatedAt: "2026-08-02T00:00:00Z" },
              { number: 3, title: "KIBA 운영 자동화", url: "https://github.com/users/feed-mina/projects/3", closed: true, updatedAt: "2026-08-01T00:00:00Z" },
            ],
          },
        },
      },
    });
  };
  const env = {
    ALLOWED_REPOS: "feed-mina/kiba_2026,feed-mina/planning-harness",
    DOCS_PASSWORD: "test-password",
    GITHUB_PROJECT_TOKEN: "project-token",
  };

  try {
    const denied = await worker.fetch(new Request("https://worker.example/projects?owner=feed-mina"), env);
    assert.equal(denied.status, 403);
    assert.equal(fetchCalls, 0);

    const response = await worker.fetch(new Request("https://worker.example/projects?owner=feed-mina", {
      headers: { "X-Docs-Password": "test-password" },
    }), env);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
    const result = await response.json();
    assert.deepEqual(result.projects.map((project) => [project.title, project.url, project.closed]), [
      ["2026 하반기", "https://github.com/users/feed-mina/projects/1", false],
      ["KIBA 운영 자동화", "https://github.com/users/feed-mina/projects/3", true],
    ]);
    assert.equal(fetchCalls, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("protected issue data requires the admin password and is never publicly cached", async () => {
  const originalFetch = globalThis.fetch;
  let fetchCalls = 0;
  globalThis.fetch = async () => {
    fetchCalls += 1;
    return Response.json([{
      number: 7,
      title: "Private planning",
      state: "open",
      html_url: "https://github.com/example/private/issues/7",
      labels: [],
      updated_at: "2026-08-02T00:00:00Z",
    }]);
  };

  const env = {
    GITHUB_TOKEN: "test-token",
    DOCS_PASSWORD: "test-password",
    ALLOWED_REPOS: "example/public,example/private",
    PROTECTED_REPOS: "example/private",
  };

  try {
    const denied = await worker.fetch(new Request("https://worker.example/issues?repo=example/private"), env);
    assert.equal(denied.status, 403);
    assert.equal((await denied.json()).error, "private_repo_password_required");
    assert.equal(fetchCalls, 0);

    const publicOnly = await worker.fetch(new Request("https://worker.example/issues?repos=example/public,example/private"), env);
    assert.equal(publicOnly.status, 200);
    const publicResult = await publicOnly.json();
    assert.equal(publicResult.issues.length, 1);
    assert.equal(publicResult.issues[0].repository, "example/public");
    assert.equal(publicResult.partial, true);
    assert.equal(publicResult.errors[0].error, "private_repo_password_required");
    assert.equal(fetchCalls, 1);

    const allowed = await worker.fetch(new Request("https://worker.example/issues?repo=example/private", {
      headers: { "X-Docs-Password": "test-password" },
    }), env);
    assert.equal(allowed.status, 200);
    assert.equal(allowed.headers.get("Cache-Control"), "no-store");
    assert.equal((await allowed.json()).issues.length, 1);
    assert.equal(fetchCalls, 2);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("issues endpoint aggregates configured repositories and reports partial failures", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (String(url).includes("/repos/example/one/issues")) {
      return Response.json([{
        number: 1,
        title: "Older issue",
        state: "open",
        html_url: "https://github.com/example/one/issues/1",
        labels: [],
        updated_at: "2026-08-01T00:00:00Z",
      }]);
    }
    return new Response("rate limited", { status: 403 });
  };

  try {
    const response = await worker.fetch(
      new Request("https://worker.example/issues?state=all"),
      { ALLOWED_REPOS: "example/one,example/two", GITHUB_TOKEN: "test-token" },
    );
    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.partial, true);
    assert.equal(result.issues[0].repository, "example/one");
    assert.deepEqual(result.errors, [{ repository: "example/two", error: "github_error", status: 403 }]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("issue creation uses an allowed target repository", async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl = "";
  let requestBody;
  globalThis.fetch = async (url, init) => {
    requestUrl = String(url);
    requestBody = JSON.parse(init.body);
    return Response.json({ number: 7, html_url: "https://github.com/example/two/issues/7" }, { status: 201 });
  };

  try {
    const response = await worker.fetch(new Request("https://worker.example/issues", {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: "https://dashboard.example" },
      body: JSON.stringify({ targetRepo: "example/two", title: "New issue", body: "Details", labels: ["todo"] }),
    }), {
      ALLOWED_ORIGINS: "https://dashboard.example",
      ALLOWED_REPOS: "example/one,example/two",
      GITHUB_TOKEN: "test-token",
    });
    assert.equal(response.status, 201);
    assert.match(requestUrl, /\/repos\/example\/two\/issues$/);
    assert.deepEqual(requestBody, { title: "New issue", body: "Details", labels: ["todo"] });
    const result = await response.json();
    assert.equal(result.repository, "example/two");
    assert.deepEqual(result.issue, {
      number: 7,
      title: "New issue",
      state: "open",
      url: "https://github.com/example/two/issues/7",
      labels: ["todo"],
      createdAt: "",
      updatedAt: "",
      repository: "example/two",
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("administrator uploads and lists a general R2 document without a GitHub issue", async () => {
  const bucket = new MemoryR2Bucket();
  const env = {
    ALLOWED_ORIGINS: "https://example.github.io",
    ALLOWED_REPOS: "example/one",
    DOCS_PASSWORD: "test-password",
    DOCS_BUCKET: bucket,
  };
  const form = new FormData();
  form.append("repo", "example/one");
  form.append("password", "test-password");
  form.append("title", "Shared reference");
  form.append("note", "Available to administrators");
  form.append("file", new File(["hello"], "reference.txt", { type: "text/plain" }));

  const upload = await worker.fetch(new Request("https://worker.example/docs/upload", {
    method: "POST",
    headers: { Origin: "https://example.github.io" },
    body: form,
  }), env);
  assert.equal(upload.status, 201);
  const uploaded = await upload.json();
  assert.match(uploaded.key, /^docs\/example__one\/_general\//);

  const list = await worker.fetch(new Request("https://worker.example/docs/list?repo=example%2Fone", {
    headers: { "X-Docs-Password": "test-password" },
  }), env);
  assert.equal(list.status, 200);
  const listed = await list.json();
  assert.equal(listed.files.length, 1);
  assert.equal(listed.files[0].filename, "reference.txt");
  assert.equal(listed.files[0].repository, "example/one");
  assert.equal(listed.files[0].issue, "");
  assert.equal(listed.files[0].note, "Available to administrators");

  const download = await worker.fetch(new Request(`https://worker.example/docs/download?repo=example%2Fone&key=${encodeURIComponent(uploaded.key)}`, {
    headers: { "X-Docs-Password": "test-password" },
  }), env);
  assert.equal(download.status, 200);
  assert.equal(await download.text(), "hello");
});

test("administrator creates, filters, and deletes a shared R2 schedule entry", async () => {
  const bucket = new MemoryR2Bucket();
  const env = {
    ALLOWED_ORIGINS: "https://example.github.io",
    ALLOWED_REPOS: "example/one,example/two",
    DOCS_PASSWORD: "test-password",
    DOCS_BUCKET: bucket,
  };
  const headers = {
    Origin: "https://example.github.io",
    "Content-Type": "application/json",
    "X-Docs-Password": "test-password",
  };
  const entry = {
    repository: "example/two",
    issue: 42,
    title: "Monthly release",
    startDate: "2026-08-03",
    endDate: "2026-08-05",
    startTime: "09:30",
    endTime: "10:00",
    note: "Release window",
  };
  const save = await worker.fetch(new Request("https://worker.example/schedule", {
    method: "POST",
    headers,
    body: JSON.stringify(entry),
  }), env);
  assert.equal(save.status, 200);
  assert.equal((await save.json()).entry.repository, "example/two");

  const list = await worker.fetch(new Request("https://worker.example/schedule?repos=example%2Fone%2Cexample%2Ftwo&from=2026-08-04&to=2026-08-10", {
    headers: { "X-Docs-Password": "test-password" },
  }), env);
  assert.equal(list.status, 200);
  const listed = await list.json();
  assert.equal(listed.entries.length, 1);
  assert.equal(listed.entries[0].issue, 42);

  const remove = await worker.fetch(new Request("https://worker.example/schedule", {
    method: "POST",
    headers,
    body: JSON.stringify({ repository: "example/two", issue: 42, action: "delete" }),
  }), env);
  assert.equal(remove.status, 200);
  assert.equal((await remove.json()).deleted, true);

  const after = await worker.fetch(new Request("https://worker.example/schedule?repos=example%2Ftwo", {
    headers: { "X-Docs-Password": "test-password" },
  }), env);
  assert.deepEqual((await after.json()).entries, []);
});


test("cost request queues three inputs and exposes result status/download", async () => {
  const originalFetch = globalThis.fetch;
  let issueComment = "";
  globalThis.fetch = async (_url, init) => {
    issueComment = JSON.parse(init.body).body;
    return new Response(JSON.stringify({ html_url: "https://github.com/owner/repository/issues/42#test" }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    const bucket = new MemoryR2Bucket();
    const env = {
      ALLOWED_ORIGINS: "https://example.github.io",
      ALLOWED_REPOS: "owner/repository",
      DOCS_PASSWORD: "test-password",
      GITHUB_TOKEN: "test-token",
      DOCS_BUCKET: bucket,
    };
    const form = new FormData();
    form.append("repo", "owner/repository");
    form.append("issue", "42");
    form.append("password", "test-password");
    form.append("templateVersion", "ver1");
    form.append("priceComparison", new File(["price"], "price.xlsx"));
    form.append("unitCost", new File(["unit"], "unit.xlsx"));
    form.append("detail", new File(["detail"], "detail.xlsx"));

    const response = await worker.fetch(new Request("https://worker.example/cost/generate", {
      method: "POST",
      headers: { Origin: "https://example.github.io" },
      body: form,
    }), env);
    assert.equal(response.status, 202);
    const accepted = await response.json();
    assert.equal(accepted.files.length, 3);
    assert.ok(accepted.files.every((file) => file.inputMode === "separate"));
    assert.match(issueComment, /<!-- project-cost-job/);
    assert.match(issueComment, /"inputMode":"separate"/);

    const statusUrl = new URL(accepted.statusUrl, "https://worker.example");
    const authHeaders = {
      Origin: "https://example.github.io",
      "X-Docs-Password": "test-password",
    };
    const queuedResponse = await worker.fetch(new Request(statusUrl, { headers: authHeaders }), env);
    assert.equal((await queuedResponse.json()).status, "queued");

    const prefix = `cost-requests/owner__repository/42/${accepted.requestId}`;
    await bucket.put(`${prefix}/result__원가계산서.xlsx`, "generated", {
      httpMetadata: { contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
    });
    const readyResponse = await worker.fetch(new Request(statusUrl, { headers: authHeaders }), env);
    const ready = await readyResponse.json();
    assert.equal(ready.ready, true);
    assert.equal(ready.status, "ready");

    const downloadUrl = new URL(ready.downloadUrl, "https://worker.example");
    const download = await worker.fetch(new Request(downloadUrl, { headers: authHeaders }), env);
    assert.equal(download.status, 200);
    assert.equal(await download.text(), "generated");
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("cost request accepts one combined workbook for all three sheets", async () => {
  const originalFetch = globalThis.fetch;
  let issueComment = "";
  globalThis.fetch = async (_url, init) => {
    issueComment = JSON.parse(init.body).body;
    return new Response(JSON.stringify({ html_url: "https://github.com/owner/repository/issues/42#combined" }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    const bucket = new MemoryR2Bucket();
    const env = {
      ALLOWED_ORIGINS: "https://example.github.io",
      ALLOWED_REPOS: "owner/repository",
      DOCS_PASSWORD: "test-password",
      GITHUB_TOKEN: "test-token",
      DOCS_BUCKET: bucket,
    };
    const form = new FormData();
    form.append("repo", "owner/repository");
    form.append("issue", "42");
    form.append("password", "test-password");
    form.append("templateVersion", "ver1");
    form.append("combinedWorkbook", new File(["combined"], "three-sheets.xlsx"));

    const response = await worker.fetch(new Request("https://worker.example/cost/generate", {
      method: "POST",
      headers: { Origin: "https://example.github.io" },
      body: form,
    }), env);
    assert.equal(response.status, 202);
    const accepted = await response.json();
    assert.equal(accepted.files.length, 3);
    assert.deepEqual(accepted.files.map((file) => file.role), ["priceComparison", "unitCost", "detail"]);
    assert.ok(accepted.files.every((file) => file.filename === "three-sheets.xlsx"));
    assert.ok(accepted.files.every((file) => file.inputMode === "combined"));
    assert.match(issueComment, /"inputMode":"combined"/);
    assert.match(issueComment, /priceComparison__three-sheets\.xlsx/);
    assert.match(issueComment, /unitCost__three-sheets\.xlsx/);
    assert.match(issueComment, /detail__three-sheets\.xlsx/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("meeting audio is transcribed and summarized with the requested date and topic", async () => {
  const originalFetch = globalThis.fetch;
  let geminiPrompt = "";
  let createdIssueBody = "";
  globalThis.fetch = async (url, init) => {
    if (String(url).includes("naveropenapi.apigw.ntruss.com")) {
      assert.equal(init.headers["Content-Type"], "application/octet-stream");
      return Response.json({ text: "참석자들이 운영 연결 일정과 담당자를 확정했다." });
    }
    if (String(url).includes("generativelanguage.googleapis.com")) {
      geminiPrompt = JSON.parse(init.body).contents[0].parts[0].text;
      return Response.json({
        candidates: [{ content: { parts: [{ text: "# 2026-06-29 운영 연결 회의록\n\n## 요약\n- 일정 확정" }] } }],
      });
    }
    if (String(url).includes("api.github.com/repos/owner/repository/issues")) {
      createdIssueBody = JSON.parse(init.body).body;
      return Response.json({
        number: 123,
        html_url: "https://github.com/owner/repository/issues/123",
      }, { status: 201 });
    }
    throw new Error(`unexpected fetch: ${url}`);
  };

  try {
    const bucket = new MemoryR2Bucket();
    const env = {
      ALLOWED_ORIGINS: "https://example.github.io",
      ALLOWED_REPOS: "owner/repository",
      DOCS_PASSWORD: "test-password",
      CLOVA_CSR_CLIENT_ID: "clova-id",
      CLOVA_CSR_CLIENT_SECRET: "clova-secret",
      GEMINI_API_KEY: "gemini-key",
      GITHUB_TOKEN: "github-token",
      DOCS_BUCKET_NAME: "project-docs-private",
      DOCS_BUCKET: bucket,
    };
    const form = new FormData();
    form.append("password", "test-password");
    form.append("meetingDate", "2026-06-29");
    form.append("meetingTime", "15:30");
    form.append("topic", "운영 연결");
    form.append("audio", new File([new Uint8Array([1, 2, 3, 4])], "meeting.mp3", { type: "audio/mpeg" }));

    const response = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
      method: "POST",
      headers: { Origin: "https://example.github.io" },
      body: form,
    }), env);
    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.ok, true);
    assert.equal(result.sttUsed, true);
    assert.equal(result.meetingTime, "15:30");
    assert.equal(result.stored, true);
    assert.match(result.storagePrefix, /^meetings\/2026-06-29_1530\//);
    assert.match(result.report, /운영 연결 회의록/);
    assert.equal(result.issueCreated, true);
    assert.equal(result.issueNumber, 123);
    assert.equal(result.issueUrl, "https://github.com/owner/repository/issues/123");
    assert.equal(result.issueError, null);
    assert.match(geminiPrompt, /회의 날짜는 2026-06-29/);
    assert.match(geminiPrompt, /회의 시간은 15:30/);
    assert.match(geminiPrompt, /# 2026-06-29 15:30 운영 연결 회의록/);
    assert.match(geminiPrompt, /회의 주제는 "운영 연결"/);
    assert.match(geminiPrompt, /## 기획 루프 반영/);
    assert.match(geminiPrompt, /회의 내용과 직접 관련된 기존 GitHub Issue/);
    const keys = [...bucket.objects.keys()];
    assert.ok(keys.includes(`${result.storagePrefix}/source/meeting.mp3`));
    assert.ok(keys.some((key) => key.endsWith("/2026-06-29_1530_운영 연결.md")));
    assert.ok(keys.some((key) => key.endsWith("/2026-06-29_1530_운영 연결_transcript.txt")));
    assert.ok(keys.includes(`${result.storagePrefix}/metadata.json`));
    assert.match(createdIssueBody, /R2 회의록 경로: `project-docs-private\/meetings\//);
    assert.match(createdIssueBody, /## 회의록 본문/);
    const metadata = await (await bucket.get(`${result.storagePrefix}/metadata.json`)).json();
    assert.equal(metadata.sourceKind, "audio");
    assert.equal(metadata.sttUsed, true);
    assert.equal(metadata.meetingTime, "15:30");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("meeting summary still succeeds when GitHub issue creation fails", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    const parsed = new URL(String(url));
    if (parsed.hostname === "generativelanguage.googleapis.com") {
      return Response.json({
        candidates: [{ content: { parts: [{ text: "# 2026-06-29 실패 대응 회의록\n\n## 요약\n- 회의록 생성 성공" }] } }],
      });
    }
    if (parsed.hostname === "api.github.com" && parsed.pathname === "/repos/owner/repository/issues") {
      return Response.json({ message: "server error" }, { status: 500 });
    }
    throw new Error(`unexpected fetch: ${url} / ${JSON.stringify(init || {})}`);
  };

  try {
    const bucket = new MemoryR2Bucket();
    const form = new FormData();
    form.append("password", "test-password");
    form.append("meetingDate", "2026-06-29");
    form.append("topic", "실패 대응");
    form.append("transcript", "회의록 생성 후 이슈 생성 실패를 점검합니다.");

    const response = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
      method: "POST",
      headers: { Origin: "https://example.github.io" },
      body: form,
    }), {
      ALLOWED_ORIGINS: "https://example.github.io",
      ALLOWED_REPOS: "owner/repository",
      DOCS_PASSWORD: "test-password",
      GEMINI_API_KEY: "gemini-key",
      GITHUB_TOKEN: "github-token",
      DOCS_BUCKET: bucket,
    });

    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.ok, true);
    assert.equal(result.issueCreated, false);
    assert.equal(result.issueUrl, null);
    assert.equal(result.issueError, "github_issue_failed");
    assert.match(result.report, /실패 대응 회의록/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("meeting transcript text is summarized without calling speech recognition", async () => {
  const originalFetch = globalThis.fetch;
  let clovaCalled = false;
  let geminiPrompt = "";
  globalThis.fetch = async (url, init) => {
    if (String(url).includes("naveropenapi.apigw.ntruss.com")) {
      clovaCalled = true;
      return Response.json({ text: "should not be used" });
    }
    if (String(url).includes("generativelanguage.googleapis.com")) {
      geminiPrompt = JSON.parse(init.body).contents[0].parts[0].text;
      return Response.json({
        candidates: [{ content: { parts: [{ text: "# 2026-06-29 텍스트 회의록\n\n## 요약\n- 자막으로 생성" }] } }],
      });
    }
    throw new Error(`unexpected fetch: ${url}`);
  };

  try {
    const env = {
      ALLOWED_ORIGINS: "https://example.github.io",
      DOCS_PASSWORD: "test-password",
      GEMINI_API_KEY: "gemini-key",
    };
    const form = new FormData();
    form.append("password", "test-password");
    form.append("meetingDate", "2026-06-29");
    form.append("topic", "텍스트 회의");
    form.append("audio", new File([
      "WEBVTT\n\n00:00:00.000 --> 00:00:03.000\n<v 김팀장>이번 주 일정과 담당자를 확정했습니다.",
    ], "teams-caption.vtt", { type: "text/vtt" }));

    const response = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
      method: "POST",
      headers: { Origin: "https://example.github.io" },
      body: form,
    }), env);
    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.ok, true);
    assert.equal(result.sttUsed, false);
    assert.equal(result.transcriptFileUsed, true);
    assert.equal(clovaCalled, false);
    assert.match(result.report, /텍스트 회의록/);
    assert.match(geminiPrompt, /이번 주 일정과 담당자를 확정했습니다/);
    assert.doesNotMatch(geminiPrompt, /WEBVTT/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("meeting transcript rejects binary files renamed as text", async () => {
  const originalFetch = globalThis.fetch;
  let externalCalled = false;
  globalThis.fetch = async () => {
    externalCalled = true;
    throw new Error("external services should not be called for invalid text");
  };

  try {
    const env = {
      ALLOWED_ORIGINS: "https://example.github.io",
      DOCS_PASSWORD: "test-password",
      GEMINI_API_KEY: "gemini-key",
    };
    const form = new FormData();
    form.append("password", "test-password");
    form.append("audio", new File([
      new Uint8Array([0x50, 0x4b, 0x03, 0x04]),
      "xl/_rels/comments1.xml.rels",
    ], "renamed-transcript.txt", { type: "text/plain" }));

    const response = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
      method: "POST",
      headers: { Origin: "https://example.github.io" },
      body: form,
    }), env);

    assert.equal(response.status, 400);
    assert.equal((await response.json()).error, "bad_text_content");
    assert.equal(externalCalled, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("meeting long transcript is summarized in chunks before final report", async () => {
  const originalFetch = globalThis.fetch;
  const prompts = [];
  globalThis.fetch = async (url, init) => {
    assert.match(String(url), /generativelanguage\.googleapis\.com/);
    const prompt = JSON.parse(init.body).contents[0].parts[0].text;
    prompts.push(prompt);
    if (prompt.includes("전사본 일부")) {
      return Response.json({
        candidates: [{ content: { parts: [{ text: prompt.includes("FINAL-MARKER")
          ? "- 마지막 구간에서 민예린 담당자의 후속 확인이 필요함"
          : "- 앞 구간 요약" }] } }],
      });
    }
    assert.match(prompt, /부분 요약/);
    assert.match(prompt, /민예린 담당자/);
    return Response.json({
      candidates: [{ content: { parts: [{ text: "# 2026-06-29 긴 회의 회의록\n\n## 요약\n- 긴 전사본 전체를 반영함" }] } }],
    });
  };

  try {
    const unit = "Speaker 1 00:00\nFollow up action confirmed for the weekly operations meeting.\n\n";
    const transcript = unit.repeat(9000) + "Speaker 2 59:59\nFINAL-MARKER 민예린 담당자 후속 확인 필요";
    const form = new FormData();
    form.append("password", "test-password");
    form.append("meetingDate", "2026-06-29");
    form.append("topic", "긴 회의");
    form.append("transcript", transcript);

    const response = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
      method: "POST",
      headers: { Origin: "https://example.github.io" },
      body: form,
    }), {
      ALLOWED_ORIGINS: "https://example.github.io",
      DOCS_PASSWORD: "test-password",
      GEMINI_API_KEY: "gemini-key",
    });

    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.ok, true);
    assert.match(result.report, /긴 전사본 전체/);
    assert.equal(prompts.length, 5);
    assert.ok(prompts.slice(0, -1).every((prompt) => prompt.includes("전사본 일부")));
    assert.ok(prompts.slice(0, -1).every((prompt) => prompt.includes("기획 루프 반영 후보")));
    assert.ok(prompts.some((prompt) => prompt.includes("FINAL-MARKER")));
    assert.match(prompts.at(-1), /부분 요약/);
    assert.match(prompts.at(-1), /## 기획 루프 반영/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("meeting summary falls back to an extractive report when Gemini returns no text", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    assert.match(String(url), /generativelanguage\.googleapis\.com/);
    return Response.json({
      promptFeedback: { blockReason: "SAFETY" },
      candidates: [],
    });
  };

  try {
    const form = new FormData();
    form.append("password", "test-password");
    form.append("meetingDate", "2026-06-29");
    form.append("meetingTime", "09:10");
    form.append("topic", "인사 서류");
    form.append("transcript", [
      "[참석자 2] 수습 기간과 입사 서류를 다시 확인해야 합니다.",
      "[참석자 2] 결재판에서 담당자를 표시해서 올리라고요.",
      "[참석자 2] 둘이 협의해서 다시 설명해서 나한테 다시 와요.",
    ].join("\n"));

    const response = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
      method: "POST",
      headers: { Origin: "https://example.github.io" },
      body: form,
    }), {
      ALLOWED_ORIGINS: "https://example.github.io",
      DOCS_PASSWORD: "test-password",
      GEMINI_API_KEY: "gemini-key",
    });

    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.ok, true);
    assert.equal(result.fallbackUsed, true);
    assert.equal(result.meetingTime, "09:10");
    assert.match(result.report, /# 2026-06-29 09:10 인사 서류 회의록/);
    assert.match(result.report, /원문 기반 자동 초안/);
    assert.match(result.report, /## 기획 루프 반영/);
    assert.match(result.report, /회의 내용과 직접 관련된 기존 GitHub Issue/);
    assert.match(result.report, /수습 기간과 입사 서류/);
    assert.match(result.report, /다시 설명해서/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("meeting summary returns configuration errors instead of generic server errors", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("Gemini fetch should not be called without a key");
  };

  try {
    const form = new FormData();
    form.append("password", "test-password");
    form.append("transcript", "이번 주 일정과 담당자를 확정했습니다.");

    const response = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
      method: "POST",
      headers: { Origin: "https://example.github.io" },
      body: form,
    }), {
      ALLOWED_ORIGINS: "https://example.github.io",
      DOCS_PASSWORD: "test-password",
    });

    assert.equal(response.status, 503);
    assert.equal((await response.json()).error, "summary_not_configured");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("meeting summary returns Gemini auth failures instead of generic server errors", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    assert.match(String(url), /generativelanguage\.googleapis\.com/);
    return Response.json({
      error: { status: "PERMISSION_DENIED", message: "API key not valid" },
    }, { status: 403 });
  };

  try {
    const form = new FormData();
    form.append("password", "test-password");
    form.append("transcript", "이번 주 일정과 담당자를 확정했습니다.");

    const response = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
      method: "POST",
      headers: { Origin: "https://example.github.io" },
      body: form,
    }), {
      ALLOWED_ORIGINS: "https://example.github.io",
      DOCS_PASSWORD: "test-password",
      GEMINI_API_KEY: "bad-key",
    });

    assert.equal(response.status, 502);
    assert.equal((await response.json()).error, "summary_auth_failed");
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("meeting upload rejects unsupported, oversized audio, and oversized text before external calls", async () => {
  const env = {
    ALLOWED_ORIGINS: "https://example.github.io",
    DOCS_PASSWORD: "test-password",
  };
  const unsupported = new FormData();
  unsupported.append("password", "test-password");
  unsupported.append("audio", new File(["not audio"], "meeting.pdf", { type: "application/pdf" }));

  const unsupportedResponse = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
    method: "POST",
    headers: { Origin: "https://example.github.io" },
    body: unsupported,
  }), env);
  assert.equal(unsupportedResponse.status, 400);
  assert.equal((await unsupportedResponse.json()).error, "bad_audio_type");

  const browserRecording = new FormData();
  browserRecording.append("password", "test-password");
  browserRecording.append("audio", new File([new Uint8Array([1, 2, 3, 4])], "browser-recording.webm", { type: "audio/webm" }));

  const browserRecordingResponse = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
    method: "POST",
    headers: { Origin: "https://example.github.io" },
    body: browserRecording,
  }), env);
  assert.equal(browserRecordingResponse.status, 502);
  assert.equal((await browserRecordingResponse.json()).error, "stt_failed");

  const oversizedAudio = new FormData();
  oversizedAudio.append("password", "test-password");
  oversizedAudio.append("audio", new File([new Uint8Array(3 * 1024 * 1024 + 1)], "meeting.mp3", { type: "audio/mpeg" }));

  const oversizedAudioResponse = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
    method: "POST",
    headers: { Origin: "https://example.github.io" },
    body: oversizedAudio,
  }), env);
  assert.equal(oversizedAudioResponse.status, 413);
  assert.equal((await oversizedAudioResponse.json()).error, "audio_too_large");

  const oversizedText = new FormData();
  oversizedText.append("password", "test-password");
  oversizedText.append("audio", new File([new Uint8Array(2 * 1024 * 1024 + 1)], "teams.txt", { type: "text/plain" }));

  const oversizedTextResponse = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
    method: "POST",
    headers: { Origin: "https://example.github.io" },
    body: oversizedText,
  }), env);
  assert.equal(oversizedTextResponse.status, 413);
  assert.equal((await oversizedTextResponse.json()).error, "text_too_large");

  const oversizedResponse = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
    method: "POST",
    headers: {
      Origin: "https://example.github.io",
      "Content-Type": "multipart/form-data; boundary=test",
      "Content-Length": String(3 * 1024 * 1024 + 64 * 1024 + 1),
    },
    body: "--test--",
  }), env);
  assert.equal(oversizedResponse.status, 413);
  assert.equal((await oversizedResponse.json()).error, "input_too_large");
});


test("quote validate accepts plain integers and thousands-comma amounts", async () => {
  const env = { ALLOWED_ORIGINS: "https://example.github.io" };
  const headers = { Origin: "https://example.github.io", "Content-Type": "application/json" };

  const cases = [
    { input: "0", expected: 0 },
    { input: "1000", expected: 1000 },
    { input: "1000000", expected: 1000000 },
    { input: "1,000", expected: 1000 },
    { input: "1,000,000", expected: 1000000 },
    { input: "123", expected: 123 },
    { input: "1,234,567,890", expected: 1234567890 },
  ];

  for (const { input, expected } of cases) {
    const response = await worker.fetch(new Request("https://worker.example/quote/validate", {
      method: "POST",
      headers,
      body: JSON.stringify({ amount: input }),
    }), env);
    assert.equal(response.status, 200, `expected 200 for "${input}"`);
    const result = await response.json();
    assert.equal(result.ok, true, `expected ok for "${input}"`);
    assert.equal(result.value, expected, `expected ${expected} for "${input}"`);
  }
});


test("quote validate rejects negative amounts, non-numeric characters, and missing amounts", async () => {
  const env = { ALLOWED_ORIGINS: "https://example.github.io" };
  const headers = { Origin: "https://example.github.io", "Content-Type": "application/json" };

  const cases = [
    { input: "-1000", error: "negative_amount" },
    { input: "-1,000", error: "negative_amount" },
    { input: "abc", error: "invalid_amount" },
    { input: "1000원", error: "invalid_amount" },
    { input: "1.5", error: "invalid_amount" },
    { input: "1,00", error: "invalid_amount" },
    { input: "1,0000", error: "invalid_amount" },
    { input: "", error: "missing_amount" },
    { input: "  ", error: "missing_amount" },
  ];

  for (const { input, error } of cases) {
    const response = await worker.fetch(new Request("https://worker.example/quote/validate", {
      method: "POST",
      headers,
      body: JSON.stringify({ amount: input }),
    }), env);
    assert.equal(response.status, 400, `expected 400 for "${input}"`);
    assert.equal((await response.json()).error, error, `expected error "${error}" for "${input}"`);
  }
});


test("quote validate returns missing_amount when amount field is absent", async () => {
  const env = { ALLOWED_ORIGINS: "https://example.github.io" };
  const response = await worker.fetch(new Request("https://worker.example/quote/validate", {
    method: "POST",
    headers: { Origin: "https://example.github.io", "Content-Type": "application/json" },
    body: JSON.stringify({}),
  }), env);
  assert.equal(response.status, 400);
  assert.equal((await response.json()).error, "missing_amount");
});


test("quote validate returns invalid_json for malformed body", async () => {
  const env = { ALLOWED_ORIGINS: "https://example.github.io" };
  const response = await worker.fetch(new Request("https://worker.example/quote/validate", {
    method: "POST",
    headers: { Origin: "https://example.github.io", "Content-Type": "application/json" },
    body: "not json",
  }), env);
  assert.equal(response.status, 400);
  assert.equal((await response.json()).error, "invalid_json");
});


test("quotation generate returns ok with valid client name, items, and amounts", async () => {
  const env = {
    ALLOWED_ORIGINS: "https://example.github.io",
  };
  const body = {
    clientName: "Example Engineering",
    items: [
      { name: "측량 조사", qty: 2, unitPrice: "500,000", amount: "1,000,000" },
      { name: "보고서 작성", qty: 1, unitPrice: "300000", amount: "300000" },
    ],
    note: "VAT 별도",
  };

  const response = await worker.fetch(new Request("https://worker.example/quotation/generate", {
    method: "POST",
    headers: { Origin: "https://example.github.io", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }), env);
  assert.equal(response.status, 200);
  const result = await response.json();
  assert.equal(result.ok, true);
  assert.equal(result.clientName, "Example Engineering");
  assert.equal(result.items.length, 2);
  assert.equal(result.items[0].name, "측량 조사");
  assert.equal(result.items[0].amount, 1000000);
  assert.equal(result.items[1].amount, 300000);
  assert.equal(result.totalAmount, 1300000);
  assert.equal(result.note, "VAT 별도");
  assert.equal(result.issue, 52);
  assert.ok(result.generatedAt);
});


test("quotation generate blocks generation when clientName is missing", async () => {
  const env = { ALLOWED_ORIGINS: "https://example.github.io" };

  const missingName = await worker.fetch(new Request("https://worker.example/quotation/generate", {
    method: "POST",
    headers: { Origin: "https://example.github.io", "Content-Type": "application/json" },
    body: JSON.stringify({
      items: [{ name: "측량", amount: "100000" }],
    }),
  }), env);
  assert.equal(missingName.status, 400);
  assert.equal((await missingName.json()).error, "missing_client_name");

  const emptyName = await worker.fetch(new Request("https://worker.example/quotation/generate", {
    method: "POST",
    headers: { Origin: "https://example.github.io", "Content-Type": "application/json" },
    body: JSON.stringify({
      clientName: "   ",
      items: [{ name: "측량", amount: "100000" }],
    }),
  }), env);
  assert.equal(emptyName.status, 400);
  assert.equal((await emptyName.json()).error, "missing_client_name");
});


test("quotation generate blocks generation when items are missing or empty", async () => {
  const env = { ALLOWED_ORIGINS: "https://example.github.io" };
  const base = { clientName: "테스트 거래처" };

  const noItems = await worker.fetch(new Request("https://worker.example/quotation/generate", {
    method: "POST",
    headers: { Origin: "https://example.github.io", "Content-Type": "application/json" },
    body: JSON.stringify(base),
  }), env);
  assert.equal(noItems.status, 400);
  assert.equal((await noItems.json()).error, "missing_items");

  const emptyItems = await worker.fetch(new Request("https://worker.example/quotation/generate", {
    method: "POST",
    headers: { Origin: "https://example.github.io", "Content-Type": "application/json" },
    body: JSON.stringify({ ...base, items: [] }),
  }), env);
  assert.equal(emptyItems.status, 400);
  assert.equal((await emptyItems.json()).error, "missing_items");

  const missingItemName = await worker.fetch(new Request("https://worker.example/quotation/generate", {
    method: "POST",
    headers: { Origin: "https://example.github.io", "Content-Type": "application/json" },
    body: JSON.stringify({ ...base, items: [{ name: "", amount: "50000" }] }),
  }), env);
  assert.equal(missingItemName.status, 400);
  assert.equal((await missingItemName.json()).error, "missing_item_name");
});


test("quotation generate blocks generation when amount is invalid or zero", async () => {
  const env = { ALLOWED_ORIGINS: "https://example.github.io" };
  const base = { clientName: "테스트 거래처" };

  const missingAmount = await worker.fetch(new Request("https://worker.example/quotation/generate", {
    method: "POST",
    headers: { Origin: "https://example.github.io", "Content-Type": "application/json" },
    body: JSON.stringify({ ...base, items: [{ name: "측량", amount: "" }] }),
  }), env);
  assert.equal(missingAmount.status, 400);
  assert.equal((await missingAmount.json()).error, "bad_item_amount");

  const negativeAmount = await worker.fetch(new Request("https://worker.example/quotation/generate", {
    method: "POST",
    headers: { Origin: "https://example.github.io", "Content-Type": "application/json" },
    body: JSON.stringify({ ...base, items: [{ name: "측량", amount: "-50000" }] }),
  }), env);
  assert.equal(negativeAmount.status, 400);
  assert.equal((await negativeAmount.json()).error, "bad_item_amount");

  const nonNumericAmount = await worker.fetch(new Request("https://worker.example/quotation/generate", {
    method: "POST",
    headers: { Origin: "https://example.github.io", "Content-Type": "application/json" },
    body: JSON.stringify({ ...base, items: [{ name: "측량", amount: "1만원" }] }),
  }), env);
  assert.equal(nonNumericAmount.status, 400);
  assert.equal((await nonNumericAmount.json()).error, "bad_item_amount");

  const zeroAmount = await worker.fetch(new Request("https://worker.example/quotation/generate", {
    method: "POST",
    headers: { Origin: "https://example.github.io", "Content-Type": "application/json" },
    body: JSON.stringify({ ...base, items: [{ name: "측량", amount: "0" }] }),
  }), env);
  assert.equal(zeroAmount.status, 400);
  assert.equal((await zeroAmount.json()).error, "bad_item_amount");
});


test("quotation generate accepts comma-formatted amounts (천단위 콤마)", async () => {
  const env = { ALLOWED_ORIGINS: "https://example.github.io" };
  const response = await worker.fetch(new Request("https://worker.example/quotation/generate", {
    method: "POST",
    headers: { Origin: "https://example.github.io", "Content-Type": "application/json" },
    body: JSON.stringify({
      clientName: "콤마 테스트",
      items: [{ name: "용역비", amount: "1,500,000" }],
    }),
  }), env);
  assert.equal(response.status, 200);
  const result = await response.json();
  assert.equal(result.totalAmount, 1500000);
});
