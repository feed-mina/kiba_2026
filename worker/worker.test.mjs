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


test("cost request queues three inputs and exposes result status/download", async () => {
  const originalFetch = globalThis.fetch;
  let issueComment = "";
  globalThis.fetch = async (_url, init) => {
    issueComment = JSON.parse(init.body).body;
    return new Response(JSON.stringify({ html_url: "https://github.com/feed-mina/kiba_2026/issues/42#test" }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    const bucket = new MemoryR2Bucket();
    const env = {
      ALLOWED_ORIGINS: "https://feed-mina.github.io",
      ALLOWED_REPOS: "feed-mina/kiba_2026",
      DOCS_PASSWORD: "test-password",
      GITHUB_TOKEN: "test-token",
      DOCS_BUCKET: bucket,
    };
    const form = new FormData();
    form.append("repo", "feed-mina/kiba_2026");
    form.append("issue", "42");
    form.append("password", "test-password");
    form.append("templateVersion", "ver1");
    form.append("priceComparison", new File(["price"], "price.xlsx"));
    form.append("unitCost", new File(["unit"], "unit.xlsx"));
    form.append("detail", new File(["detail"], "detail.xlsx"));

    const response = await worker.fetch(new Request("https://worker.example/cost/generate", {
      method: "POST",
      headers: { Origin: "https://feed-mina.github.io" },
      body: form,
    }), env);
    assert.equal(response.status, 202);
    const accepted = await response.json();
    assert.equal(accepted.files.length, 3);
    assert.match(issueComment, /<!-- kiba-cost-job/);

    const statusUrl = new URL(accepted.statusUrl, "https://worker.example");
    const authHeaders = {
      Origin: "https://feed-mina.github.io",
      "X-Docs-Password": "test-password",
    };
    const queuedResponse = await worker.fetch(new Request(statusUrl, { headers: authHeaders }), env);
    assert.equal((await queuedResponse.json()).status, "queued");

    const prefix = `cost-requests/feed-mina__kiba_2026/42/${accepted.requestId}`;
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


test("meeting audio is transcribed and summarized with the requested date and topic", async () => {
  const originalFetch = globalThis.fetch;
  let geminiPrompt = "";
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
    throw new Error(`unexpected fetch: ${url}`);
  };

  try {
    const env = {
      ALLOWED_ORIGINS: "https://feed-mina.github.io",
      DOCS_PASSWORD: "test-password",
      CLOVA_CSR_CLIENT_ID: "clova-id",
      CLOVA_CSR_CLIENT_SECRET: "clova-secret",
      GEMINI_API_KEY: "gemini-key",
    };
    const form = new FormData();
    form.append("password", "test-password");
    form.append("meetingDate", "2026-06-29");
    form.append("topic", "운영 연결");
    form.append("audio", new File([new Uint8Array([1, 2, 3, 4])], "meeting.mp3", { type: "audio/mpeg" }));

    const response = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
      method: "POST",
      headers: { Origin: "https://feed-mina.github.io" },
      body: form,
    }), env);
    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.ok, true);
    assert.equal(result.sttUsed, true);
    assert.match(result.report, /운영 연결 회의록/);
    assert.match(geminiPrompt, /회의 날짜는 2026-06-29/);
    assert.match(geminiPrompt, /회의 주제는 "운영 연결"/);
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
      ALLOWED_ORIGINS: "https://feed-mina.github.io",
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
      headers: { Origin: "https://feed-mina.github.io" },
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


test("meeting upload rejects unsupported, oversized audio, and oversized text before external calls", async () => {
  const env = {
    ALLOWED_ORIGINS: "https://feed-mina.github.io",
    DOCS_PASSWORD: "test-password",
  };
  const unsupported = new FormData();
  unsupported.append("password", "test-password");
  unsupported.append("audio", new File(["not audio"], "meeting.pdf", { type: "application/pdf" }));

  const unsupportedResponse = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
    method: "POST",
    headers: { Origin: "https://feed-mina.github.io" },
    body: unsupported,
  }), env);
  assert.equal(unsupportedResponse.status, 400);
  assert.equal((await unsupportedResponse.json()).error, "bad_audio_type");

  const oversizedAudio = new FormData();
  oversizedAudio.append("password", "test-password");
  oversizedAudio.append("audio", new File([new Uint8Array(3 * 1024 * 1024 + 1)], "meeting.mp3", { type: "audio/mpeg" }));

  const oversizedAudioResponse = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
    method: "POST",
    headers: { Origin: "https://feed-mina.github.io" },
    body: oversizedAudio,
  }), env);
  assert.equal(oversizedAudioResponse.status, 413);
  assert.equal((await oversizedAudioResponse.json()).error, "audio_too_large");

  const oversizedText = new FormData();
  oversizedText.append("password", "test-password");
  oversizedText.append("audio", new File([new Uint8Array(2 * 1024 * 1024 + 1)], "teams.txt", { type: "text/plain" }));

  const oversizedTextResponse = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
    method: "POST",
    headers: { Origin: "https://feed-mina.github.io" },
    body: oversizedText,
  }), env);
  assert.equal(oversizedTextResponse.status, 413);
  assert.equal((await oversizedTextResponse.json()).error, "text_too_large");

  const oversizedResponse = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
    method: "POST",
    headers: {
      Origin: "https://feed-mina.github.io",
      "Content-Type": "multipart/form-data; boundary=test",
      "Content-Length": String(3 * 1024 * 1024 + 64 * 1024 + 1),
    },
    body: "--test--",
  }), env);
  assert.equal(oversizedResponse.status, 413);
  assert.equal((await oversizedResponse.json()).error, "input_too_large");
});
