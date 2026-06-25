# KIBA Workstation Automation

Use this on each Windows PC that works on KIBA, including the office desktop
and a laptop.

## One-Time Registration

From the repository root:

```powershell
.\scripts\setup_workstation_automation.ps1 -SkipDocsPasswordSetup
```

This registers:

- portable `.tools\python\python.exe` and `.tools\rclone\rclone.exe`
- `KIBA Docs Download`
- `KIBA Claude ASK Todo Log`
- `KIBA Codex Conversation Log`, when `..\codex-obsidian-conversation-log` exists
- `kiba-run://docs-sync` for the GitHub Pages "local sync" button

To register tasks without downloading tools:

```powershell
.\scripts\setup_workstation_automation.ps1 -SkipDocsPasswordSetup -SkipPortableTools
```

If this is the first setup on the PC, create the per-PC secrets afterwards:

```powershell
.\scripts\setup_docs_schedule.ps1
.\scripts\setup_r2_sync.ps1
.\scripts\setup_notebooklm_sync.ps1
.\scripts\setup_anthropic_api_key.ps1
```

`setup_anthropic_api_key.ps1` is required for the `KIBA Claude ASK Todo Log`
task: the org policy blocks headless `claude -p` from using subscription auth,
so the unattended run needs an API key. The script stores it DPAPI-encrypted and
`daily_claude_ask_todo.ps1` injects it at run time. Without it that task fails
with exit `0x1` (`Your organization has disabled Claude subscription access`).

Those files are protected by Windows DPAPI, so do not copy them from another PC:

- `scripts\.docs_password.xml`
- `scripts\.r2_credentials.xml`
- `scripts\.notebooklm_creds.xml`
- `scripts\.anthropic_api_key.xml`

## Local Sync Button

The Pages button opens:

```text
kiba-run://docs-sync
```

On a configured PC, that URL starts:

```powershell
.\scripts\sync_workstation_now.ps1
```

The sync runner:

1. pulls `origin/main` when the local working tree is clean,
2. runs `download_docs_scheduled.ps1` for docs, ASK/Todo, Git, R2, and NotebookLM,
3. tries one more clean pull for CI-generated updates.

If there are local edits, Git pull is skipped to avoid overwriting work. Check:

```powershell
git status --short
Get-Content .\scripts\sync_workstation_now.log -Tail 40
```

## Laptop Readiness Checklist

Verify:

```powershell
Get-ScheduledTask -TaskName 'KIBA*'
Get-Command git
Get-Command rclone
Get-Command python
Get-Command claude
```

`git` and `claude` are needed for the local automation. `rclone` and the R2
credentials are needed for docs/ASK/Todo R2 mirroring. `python` is needed for
Knowledge/wiki index rebuilds.
