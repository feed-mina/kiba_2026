<#
  setup_workstation_automation.ps1

  One-time setup for a KIBA workstation (desktop or laptop).

  It registers:
   - KIBA Docs Download
   - kiba-run://docs-sync local URL protocol for the GitHub Pages button
   - KIBA Claude ASK Todo Log
   - KIBA Codex Conversation Log, when the sibling tool folder exists

  Secrets are intentionally not copied between PCs. DPAPI files such as
  .docs_password.xml, .r2_credentials.xml, and .notebooklm_creds.xml must be
  created on each Windows account/PC.
#>

[CmdletBinding()]
param(
  [string]$DocsPassword = "",
  [switch]$SkipPortableTools,
  [switch]$SkipDocsPasswordSetup,
  [switch]$RunDocsTest,
  [switch]$SkipDocsTask,
  [switch]$SkipLocalProtocol,
  [switch]$SkipClaudeTask,
  [switch]$SkipCodexConversationTask,
  [string]$ClaudeTime = "17:30",
  [string]$CodexConversationTime = "23:55",
  [string]$CodexConversationDir = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$repoRoot  = Split-Path -Parent $scriptDir
$workspace = Split-Path -Parent $repoRoot

function Invoke-Step([string]$Name, [scriptblock]$Action) {
  Write-Host ""
  Write-Host "== $Name =="
  try {
    & $Action
    Write-Host "[OK] $Name"
  }
  catch {
    Write-Warning ("{0} failed: {1}" -f $Name, $_.Exception.Message)
  }
}

if (-not $SkipDocsTask) {
  if (-not $SkipPortableTools) {
    Invoke-Step "Install portable Python/rclone" {
      $setup = Join-Path $scriptDir "setup_portable_tools.ps1"
      if (-not (Test-Path $setup)) { throw "Missing: $setup" }
      & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setup
      if ($LASTEXITCODE -ne 0) { throw "setup_portable_tools.ps1 exited $LASTEXITCODE" }
    }
  }

  Invoke-Step "Register KIBA Docs Download" {
    $setup = Join-Path $scriptDir "setup_docs_schedule.ps1"
    if (-not (Test-Path $setup)) { throw "Missing: $setup" }

    $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $setup)
    if (-not [string]::IsNullOrWhiteSpace($DocsPassword)) {
      $args += @("-Password", $DocsPassword)
    } elseif ($SkipDocsPasswordSetup) {
      $args += "-SkipPasswordSetup"
    } else {
      Write-Warning "No DocsPassword supplied; keeping/expecting an existing DPAPI password file."
      Write-Warning "Run .\scripts\setup_docs_schedule.ps1 later if this laptop still needs the docs password."
      $args += "-SkipPasswordSetup"
    }
    if (-not $RunDocsTest) { $args += "-NoTest" }

    & powershell.exe @args
    if ($LASTEXITCODE -ne 0) { throw "setup_docs_schedule.ps1 exited $LASTEXITCODE" }
  }
}

if (-not $SkipLocalProtocol) {
  Invoke-Step "Register kiba-run local protocol" {
    $setup = Join-Path $scriptDir "setup_local_run_protocol.ps1"
    if (-not (Test-Path $setup)) { throw "Missing: $setup" }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setup
    if ($LASTEXITCODE -ne 0) { throw "setup_local_run_protocol.ps1 exited $LASTEXITCODE" }
  }
}

if (-not $SkipClaudeTask) {
  Invoke-Step "Register KIBA Claude ASK Todo Log" {
    $setup = Join-Path $scriptDir "setup_claude_ask_todo_schedule.ps1"
    if (-not (Test-Path $setup)) { throw "Missing: $setup" }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setup -Time $ClaudeTime
    if ($LASTEXITCODE -ne 0) { throw "setup_claude_ask_todo_schedule.ps1 exited $LASTEXITCODE" }
  }
}

if (-not $SkipCodexConversationTask) {
  Invoke-Step "Register KIBA Codex Conversation Log" {
    $dir = $CodexConversationDir
    if ([string]::IsNullOrWhiteSpace($dir)) {
      $dir = Join-Path $workspace "codex-obsidian-conversation-log"
    }
    $setup = Join-Path $dir "setup_schedule.ps1"
    if (-not (Test-Path $setup)) {
      throw "Codex conversation setup script not found: $setup"
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setup -Time $CodexConversationTime
    if ($LASTEXITCODE -ne 0) { throw "setup_schedule.ps1 exited $LASTEXITCODE" }
  }
}

Write-Host ""
Write-Host "Done. Useful checks:"
Write-Host "  Get-ScheduledTask -TaskName 'KIBA*'"
Write-Host "  Start-Process 'kiba-run://docs-sync'"
Write-Host "  Get-Content .\scripts\sync_workstation_now.log -Tail 40"
