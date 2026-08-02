export const STORAGE_KEY = "projectDashboard.config";

export const DEFAULT_API_BASE = "https://project-operations.kibayerin.workers.dev";

export const DEFAULT_SETTINGS = {
  projectName: "KIBA 2026",
  githubRepositories: ["feed-mina/kiba_2026"],
  githubProjects: ["https://github.com/users/feed-mina/projects/3"],
  apiBase: DEFAULT_API_BASE,
  turnstileSiteKey: "",
};

export const REPO_PATTERN = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
export const PROJECT_PATTERN = /^https:\/\/github\.com\/(?:users|orgs)\/[A-Za-z0-9_.-]+\/projects\/\d+\/?$/;

export function normalizeSettings(input = {}) {
  const merged = { ...DEFAULT_SETTINGS, ...input };
  const legacyRepo = input.githubRepository || input.repo;
  const candidates = Array.isArray(input.githubRepositories)
    ? input.githubRepositories
    : legacyRepo ? [legacyRepo] : DEFAULT_SETTINGS.githubRepositories;
  const projectCandidates = Array.isArray(input.githubProjects)
    ? input.githubProjects
    : input.githubProject ? [input.githubProject] : DEFAULT_SETTINGS.githubProjects;

  return {
    projectName: String(merged.projectName || DEFAULT_SETTINGS.projectName).trim() || DEFAULT_SETTINGS.projectName,
    githubRepositories: [...new Set(candidates.map((repo) => String(repo).trim()).filter((repo) => repo && repo !== "owner/repository"))],
    githubProjects: [...new Set(projectCandidates.map((project) => String(project).trim()).filter(Boolean))],
    apiBase: String(input.apiBase || input.workerUrl || DEFAULT_API_BASE).trim() || DEFAULT_API_BASE,
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

export function parseProjectList(value) {
  if (Array.isArray(value)) return normalizeSettings({ githubProjects: value }).githubProjects;
  return normalizeSettings({ githubProjects: String(value || "").split(/[\n,]+/) }).githubProjects;
}

export function validateProjectUrl(project) {
  return PROJECT_PATTERN.test(String(project || "").trim());
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
