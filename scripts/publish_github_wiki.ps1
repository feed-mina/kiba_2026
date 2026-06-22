<#
  Publish generated wiki/ Markdown files to the GitHub Wiki repository.

  Prerequisite:
    python .\scripts\build_issue_knowledge.py
    python .\scripts\export_obsidian_to_github_wiki.py

  Usage:
    .\scripts\publish_github_wiki.ps1
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

if (-not (Test-Path $wikiSrc)) {
  throw "wiki export not found: $wikiSrc (run export_obsidian_to_github_wiki.py first)"
}

if (-not (Test-Path $wikiWork)) {
  git clone $WikiRemote $wikiWork
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] Wiki clone failed. Initializing a new local wiki repository..."
    New-Item -ItemType Directory -Force -Path $wikiWork | Out-Null
    Push-Location $wikiWork
    try {
      git init
      git remote add origin $WikiRemote
      git checkout -b master
    }
    finally {
      Pop-Location
    }
  }
}

Push-Location $wikiWork
try {
  git pull --rebase
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] Wiki pull skipped/failed; continuing with local contents."
  }
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
