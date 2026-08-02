export const STORAGE_KEY = "projectDashboard.config";

export const DEFAULT_SETTINGS = {
  projectName: "Project Operations",
  githubRepositories: [],
  apiBase: "",
  turnstileSiteKey: "",
};

export const REPO_PATTERN = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;

export function normalizeSettings(input = {}) {
  const merged = { ...DEFAULT_SETTINGS, ...input };
  const legacyRepo = merged.githubRepository || merged.repo;
  const candidates = Array.isArray(merged.githubRepositories) && merged.githubRepositories.length
    ? merged.githubRepositories
    : legacyRepo ? [legacyRepo] : [];

  return {
    projectName: String(merged.projectName || DEFAULT_SETTINGS.projectName).trim() || DEFAULT_SETTINGS.projectName,
    githubRepositories: [...new Set(candidates.map((repo) => String(repo).trim()).filter((repo) => repo && repo !== "owner/repository"))],
    apiBase: String(merged.apiBase || merged.workerUrl || "").trim(),
    turnstileSiteKey: String(merged.turnstileSiteKey || "").trim(),
  };
}

export function parseRepositoryList(value) {
  if (Array.isArray(value)) return normalizeSettings({ githubRepositories: value }).githubRepositories;
  return normalizeSettings({ githubRepositories: String(value || "").split(/[\n,]+/) }).githubRepositories;
}

export function validateRepoFullName(repo) {
  return REPO_PATTERN.test(String(repo || "").trim());
}

export function loadSettings(storage = globalThis.localStorage) {
  try {
    const raw = storage?.getItem(STORAGE_KEY);
    return raw ? normalizeSettings(JSON.parse(raw)) : normalizeSettings();
  } catch {
    return normalizeSettings();
  }
}

export function saveSettings(settings, storage = globalThis.localStorage) {
  const normalized = normalizeSettings(settings);
  storage?.setItem(STORAGE_KEY, JSON.stringify(normalized));
  return normalized;
}
