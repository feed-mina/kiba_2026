import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_API_BASE,
  loadSettings,
  normalizeSettings,
  parseProjectList,
  parseRepositoryList,
  saveSettings,
  validateProjectUrl,
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
    projectName: "KIBA 2026",
    githubRepositories: ["feed-mina/kiba_2026"],
    githubProjects: ["https://github.com/users/feed-mina/projects/3"],
    githubProjectNames: {
      "https://github.com/users/feed-mina/projects/3": "@feed-mina's KIBA 로컬 문서/수동 작업을 자동화하여 관리",
    },
    apiBase: "https://worker.example",
    turnstileSiteKey: "",
  });
  assert.deepEqual(normalizeSettings({ githubRepositories: ["owner/repository"] }).githubRepositories, []);
});

test("loads invalid JSON safely and saves normalized settings", () => {
  let stored = "{bad json";
  const storage = {
    getItem: () => stored,
    setItem: (_key, value) => { stored = value; },
  };
  assert.deepEqual(loadSettings(storage).githubRepositories, ["feed-mina/kiba_2026"]);
  saveSettings({ githubRepositories: [" feed-mina/kiba_2026 "] }, storage);
  assert.deepEqual(JSON.parse(stored).githubRepositories, ["feed-mina/kiba_2026"]);
  assert.equal(JSON.parse(stored).apiBase, DEFAULT_API_BASE);
});

test("validates owner/repository names", () => {
  assert.equal(validateRepoFullName("feed-mina/kiba_2026"), true);
  assert.equal(validateRepoFullName("missing-slash"), false);
});

test("normalizes and validates multiple GitHub Project URLs", () => {
  assert.deepEqual(parseProjectList([
    "https://github.com/users/feed-mina/projects/3",
    "https://github.com/orgs/example/projects/7/",
    "https://github.com/users/feed-mina/projects/3",
  ]), [
    "https://github.com/users/feed-mina/projects/3",
    "https://github.com/orgs/example/projects/7/",
  ]);
  assert.equal(validateProjectUrl("https://github.com/users/feed-mina/projects/3"), true);
  assert.equal(validateProjectUrl("https://example.com/projects/3"), false);
  assert.deepEqual(normalizeSettings({
    githubProjects: ["https://github.com/users/feed-mina/projects/3"],
    githubProjectNames: {
      "https://github.com/users/feed-mina/projects/3": "KIBA 운영 자동화",
      "https://github.com/users/feed-mina/projects/99": "선택되지 않은 프로젝트",
    },
  }).githubProjectNames, {
    "https://github.com/users/feed-mina/projects/3": "KIBA 운영 자동화",
  });
});
