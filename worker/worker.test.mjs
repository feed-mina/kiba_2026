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
    assert.ok(accepted.files.every((file) => file.inputMode === "separate"));
    assert.match(issueComment, /<!-- kiba-cost-job/);
    assert.match(issueComment, /"inputMode":"separate"/);

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


test("cost request accepts one combined workbook for all three sheets", async () => {
  const originalFetch = globalThis.fetch;
  let issueComment = "";
  globalThis.fetch = async (_url, init) => {
    issueComment = JSON.parse(init.body).body;
    return new Response(JSON.stringify({ html_url: "https://github.com/feed-mina/kiba_2026/issues/42#combined" }), {
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
    form.append("combinedWorkbook", new File(["combined"], "three-sheets.xlsx"));

    const response = await worker.fetch(new Request("https://worker.example/cost/generate", {
      method: "POST",
      headers: { Origin: "https://feed-mina.github.io" },
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
    assert.match(geminiPrompt, /## 기획 루프 반영/);
    assert.match(geminiPrompt, /#44 기획 루프 엔지니어링/);
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

test("meeting transcript rejects binary files renamed as text", async () => {
  const originalFetch = globalThis.fetch;
  let externalCalled = false;
  globalThis.fetch = async () => {
    externalCalled = true;
    throw new Error("external services should not be called for invalid text");
  };

  try {
    const env = {
      ALLOWED_ORIGINS: "https://feed-mina.github.io",
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
      headers: { Origin: "https://feed-mina.github.io" },
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
      headers: { Origin: "https://feed-mina.github.io" },
      body: form,
    }), {
      ALLOWED_ORIGINS: "https://feed-mina.github.io",
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
    form.append("topic", "인사 서류");
    form.append("transcript", [
      "[참석자 2] 수습 기간과 입사 서류를 다시 확인해야 합니다.",
      "[참석자 2] 결재판에서 담당자를 표시해서 올리라고요.",
      "[참석자 2] 둘이 협의해서 다시 설명해서 나한테 다시 와요.",
    ].join("\n"));

    const response = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
      method: "POST",
      headers: { Origin: "https://feed-mina.github.io" },
      body: form,
    }), {
      ALLOWED_ORIGINS: "https://feed-mina.github.io",
      DOCS_PASSWORD: "test-password",
      GEMINI_API_KEY: "gemini-key",
    });

    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.ok, true);
    assert.equal(result.fallbackUsed, true);
    assert.match(result.report, /원문 기반 자동 초안/);
    assert.match(result.report, /## 기획 루프 반영/);
    assert.match(result.report, /#44 기획 루프 엔지니어링/);
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
      headers: { Origin: "https://feed-mina.github.io" },
      body: form,
    }), {
      ALLOWED_ORIGINS: "https://feed-mina.github.io",
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
      headers: { Origin: "https://feed-mina.github.io" },
      body: form,
    }), {
      ALLOWED_ORIGINS: "https://feed-mina.github.io",
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

  const browserRecording = new FormData();
  browserRecording.append("password", "test-password");
  browserRecording.append("audio", new File([new Uint8Array([1, 2, 3, 4])], "browser-recording.webm", { type: "audio/webm" }));

  const browserRecordingResponse = await worker.fetch(new Request("https://worker.example/meeting/summarize", {
    method: "POST",
    headers: { Origin: "https://feed-mina.github.io" },
    body: browserRecording,
  }), env);
  assert.equal(browserRecordingResponse.status, 502);
  assert.equal((await browserRecordingResponse.json()).error, "stt_failed");

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
