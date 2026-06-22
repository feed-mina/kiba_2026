<#
  Publish generated wiki/ Markdown files to the GitHub Wiki repository.

  Prerequisite:
    python .\scripts\build_issue_knowledge.py
    python .\scripts\export_obsidian_to_github_wiki.py

  Usage:
    .\scripts\publish_github_wiki.ps1

  Note:
    .wiki-worktree is a generated publishing worktree. Each run aligns it to
    the remote GitHub Wiki branch before copying the generated wiki/ files.
#>

param(
  [string]$WikiRemote = "https://github.com/feed-mina/kiba_2026.wiki.git",
  [string]$WorkDir = ".wiki-worktree"
)

$ErrorActionPreference = "Stop"

function Invoke-GitChecked {
  param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
  & git @Args
  if ($LASTEXITCODE -ne 0) {
    throw "git $($Args -join ' ') failed with exit code $LASTEXITCODE"
  }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$wikiSrc = Join-Path $repoRoot "wiki"
$wikiWork = Join-Path $repoRoot $WorkDir
$wikiWebUrl = "https://github.com/feed-mina/kiba_2026/wiki"

if (-not (Test-Path $wikiSrc)) {
  throw "wiki export not found: $wikiSrc (run export_obsidian_to_github_wiki.py first)"
}

$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& git ls-remote $WikiRemote 1>$null 2>$null
$remoteCheckExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorActionPreference
if ($remoteCheckExitCode -ne 0) {
  throw @"
GitHub Wiki remote is not available yet: $WikiRemote

GitHub requires an initial Wiki page before the .wiki.git repository can be cloned or pushed.
Open $wikiWebUrl, create any first page, click Save Page, then run this script again.
"@
}

if (-not (Test-Path $wikiWork)) {
  Invoke-GitChecked clone $WikiRemote $wikiWork
}
elseif (-not (Test-Path (Join-Path $wikiWork ".git"))) {
  throw "wiki worktree exists but is not a git repository: $wikiWork"
}

Push-Location $wikiWork
try {
  Invoke-GitChecked remote set-url origin $WikiRemote
  Invoke-GitChecked fetch origin master
  Invoke-GitChecked checkout -B master origin/master
  Get-ChildItem -Force | Where-Object { $_.Name -ne ".git" } | Remove-Item -Recurse -Force
  Copy-Item -Path (Join-Path $wikiSrc "*") -Destination $wikiWork -Recurse -Force
  Invoke-GitChecked add .
  $staged = (git diff --cached --name-only) -join "`n"
  if ([string]::IsNullOrWhiteSpace($staged)) {
    Write-Host "[OK] Wiki already up to date."
    return
  }
  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
  Invoke-GitChecked commit -m "Update project wiki $stamp"
  Invoke-GitChecked push -u origin master
  Write-Host "[OK] Published GitHub Wiki."
}
finally {
  Pop-Location
}
