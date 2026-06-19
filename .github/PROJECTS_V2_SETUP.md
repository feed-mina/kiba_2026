# GitHub Projects v2 setup

This repository already has the wiring for GitHub Projects v2:

- Repository variable: `PROJECT_URL`
- Repository secret: `ADD_TO_PROJECT_PAT`
- Workflow for new issues: `.github/workflows/add-to-project.yml`
- Workflow for existing issues: `.github/workflows/project-backfill.yml`

As of 2026-06-19, `PROJECT_URL` points to:

```text
https://github.com/users/feed-mina/projects/3
```

The latest `add-to-project` runs failed with `Bad credentials`, so replace
`ADD_TO_PROJECT_PAT` with a fresh token.

## 1. Refresh local GitHub CLI access

Run this in a local terminal where browser login is available:

```powershell
gh auth refresh -h github.com -s read:project -s project
```

Verify:

```powershell
gh auth status
gh project view 3 --owner feed-mina
```

If `gh project view` works, the local CLI can read Projects v2.

## 2. Create or replace the Project token

Recommended: create a fine-grained personal access token.

GitHub path:

```text
GitHub -> Settings -> Developer settings -> Personal access tokens -> Fine-grained tokens -> Generate new token
```

Use these permissions:

- Account permissions: `Projects` = Read and write
- Repository access: `feed-mina/kiba_2026`
- Repository permissions:
  - `Issues` = Read and write
  - `Metadata` = Read-only

Classic token alternative:

- scopes: `repo`, `project`

Then update the repository secret:

```powershell
gh secret set ADD_TO_PROJECT_PAT --repo feed-mina/kiba_2026
```

Paste the new token when prompted.

## 3. Confirm Project URL

The repository variable should point to the Project board:

```powershell
gh variable set PROJECT_URL --repo feed-mina/kiba_2026 --body "https://github.com/users/feed-mina/projects/3"
```

If creating a new board:

```powershell
gh project create --owner feed-mina --title "KIBA Next"
gh project link <project-number> --owner feed-mina --repo kiba_2026
gh variable set PROJECT_URL --repo feed-mina/kiba_2026 --body "https://github.com/users/feed-mina/projects/<project-number>"
```

## 4. Backfill existing issues

After replacing `ADD_TO_PROJECT_PAT`, run:

```powershell
gh workflow run project-backfill.yml --repo feed-mina/kiba_2026 -f state=open
```

This adds existing open issues to the configured Project v2 board. New issues are
handled by `add-to-project.yml`.

## 5. ASK/Todo automation flow

Codex should update:

- `ASK/YYYY-MM-DD_ai.md` for request/answer logs
- `Todo/YYYY-MM-DD_*.md` for actionable follow-up work

When changes are pushed to `main` under `ASK/**` or `Todo/**`,
`todo-reflect.yml` runs automatically:

1. `Todo/*.md` files are created/updated as GitHub issues with the `todo` label.
2. `index.html` is refreshed for the Pages board.
3. New issues trigger `add-to-project.yml` and enter the Project board.

If the Pages update races with another push, `todo-reflect.yml` now retries with
`git pull --rebase origin main` before pushing.
