<#
  sync_workstation_now.ps1

  One-shot local workstation sync used by the GitHub Pages button
  (kiba-run://docs-sync) and by manual laptop/desktop catch-up runs.

  The shared state lives in GitHub and R2, so every workstation should:
   1) pull the latest Git state when the working tree is clean,
   2) run the existing docs/ASK/Todo/R2 wrapper,
   3) try one more clean pull in case a CI workflow updated index.html/wiki output.

  Local edits are never overwritten. If the working tree is dirty, the pull step
  is skipped and the status is written to scripts\sync_workstation_now.log.
#>

[CmdletBinding()]
param(
  [switch]$SkipDownload,
  [switch]$DryRun,
  [switch]$SkipNotebookLM,
  [switch]$NoRequireR2Sync
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = $PSScriptRoot
$repoRoot  = Split-Path -Parent $scriptDir
$wrapper   = Join-Path $scriptDir "download_docs_scheduled.ps1"
$logFile   = Join-Path $scriptDir "sync_workstation_now.log"

function Write-Log([string]$Message) {
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Add-Content -Path $logFile -Value $line -Encoding UTF8
}

function Write-NativeLog([string]$Prefix) {
  process {
    $s = $_.ToString().TrimEnd()
    if ($s -and $s -notmatch 'RemoteException') {
      Write-Log ("{0}: {1}" -f $Prefix, $s)
    }
  }
}

function Invoke-GitPullIfClean([string]$Label) {
  $git = Get-Command git -ErrorAction SilentlyContinue
  if (-not $git) {
    Write-Log "Git[$Label]: skipped (git not found on PATH)"
    return
  }

  Push-Location $repoRoot
  try {
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
      $statusLines = @(& git status --porcelain 2>&1)
      $statusCode = $LASTEXITCODE
    }
    finally {
      $ErrorActionPreference = $prevEAP
    }

    if ($statusCode -ne 0) {
      Write-Log "Git[$Label]: status failed (exit $statusCode)"
      $statusLines | Write-NativeLog "git"
      return
    }

    if (@($statusLines).Count -gt 0) {
      Write-Log "Git[$Label]: local changes present; skip pull to avoid overwriting work"
      $statusLines | Write-NativeLog "git-status"
      return
    }

    Write-Log "Git[$Label]: pull --rebase origin main"
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
      & git pull --rebase origin main 2>&1 | Write-NativeLog "git"
      $code = $LASTEXITCODE
    }
    finally {
      $ErrorActionPreference = $prevEAP
    }

    if ($code -ne 0) {
      Write-Log "Git[$Label]: pull failed (exit $code); continuing"
    } else {
      Write-Log "Git[$Label]: pull done"
    }
  }
  finally {
    Pop-Location
  }
}

function Invoke-DocsWrapper {
  if (-not (Test-Path $wrapper)) {
    throw "Wrapper script not found: $wrapper"
  }

  $args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $wrapper
  )
  if ($SkipDownload) { $args += "-SkipDownload" }
  if ($DryRun) { $args += "-DryRun" }
  if ($SkipNotebookLM) { $args += "-SkipNotebookLM" }
  if (-not $NoRequireR2Sync) { $args += "-RequireR2Sync" }

  Write-Log ("Wrapper: start ({0})" -f ($args -join " "))
  $prevEAP = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    & powershell.exe @args 2>&1 | Write-NativeLog "wrapper"
    $code = $LASTEXITCODE
  }
  finally {
    $ErrorActionPreference = $prevEAP
  }
  Write-Log "Wrapper: done (exit $code)"
  return $code
}

$script:failed = $false

try {
  Write-Log ("=== workstation sync start (computer={0}, user={1}) ===" -f $env:COMPUTERNAME, $env:USERNAME)
  Invoke-GitPullIfClean "pre"
  $wrapperCode = Invoke-DocsWrapper
  if ($wrapperCode -ne 0) { $script:failed = $true }
  Invoke-GitPullIfClean "post"
}
catch {
  Write-Log ("ERROR: " + $_.Exception.Message)
  $script:failed = $true
}
finally {
  Write-Log ("=== workstation sync end (failed={0}) ===" -f $script:failed)
}

if ($script:failed) { exit 1 }
