import assert from "node:assert/strict";
import test from "node:test";

import {
  loadSettings,
  normalizeSettings,
  parseRepositoryList,
  saveSettings,
  validateRepoFullName,
} from "./settings.js";

test("normalizes and deduplicates multiple repositories", () => {
  assert.deepEqual(parseRepositoryList("feed-mina/one, feed-mina/two\nfeed-mina/one"), [
    "feed-mina/one",
    "feed-mina/two",
  ]);
});

test("migrates legacy repo and workerUrl settings", () => {
  assert.deepEqual(normalizeSettings({ repo: "feed-mina/kiba_2026", workerUrl: "https://worker.example" }), {
    projectName: "Project Operations",
    githubRepositories: ["feed-mina/kiba_2026"],
    apiBase: "https://worker.example",
    turnstileSiteKey: "",
  });
  assert.deepEqual(normalizeSettings({ repo: "owner/repository" }).githubRepositories, []);
});

test("loads invalid JSON safely and saves normalized settings", () => {
  let stored = "{bad json";
  const storage = {
    getItem: () => stored,
    setItem: (_key, value) => { stored = value; },
  };
  assert.deepEqual(loadSettings(storage).githubRepositories, []);
  saveSettings({ githubRepositories: [" feed-mina/kiba_2026 "] }, storage);
  assert.deepEqual(JSON.parse(stored).githubRepositories, ["feed-mina/kiba_2026"]);
});

test("validates owner/repository names", () => {
  assert.equal(validateRepoFullName("feed-mina/kiba_2026"), true);
  assert.equal(validateRepoFullName("missing-slash"), false);
});
