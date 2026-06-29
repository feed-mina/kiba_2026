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
