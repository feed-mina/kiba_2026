<#
  setup_docs_schedule.ps1

  One-time setup/repair for the "KIBA Docs Download" Windows scheduled task.

  What it does:
   1) Optionally saves DOCS_PASSWORD to scripts\.docs_password.xml with DPAPI.
   2) Registers the scheduled task for 09:00, 13:00, 17:50, and 18:00.
   3) Runs one immediate test.

  Examples:
    .\scripts\setup_docs_schedule.ps1
    .\scripts\setup_docs_schedule.ps1 -Password "your-docs-password"
    .\scripts\setup_docs_schedule.ps1 -SkipPasswordSetup
#>

param(
  [string]$Password = "",
  [string]$TaskName = "KIBA Docs Download",
  [switch]$SkipPasswordSetup,
  [switch]$NoTest
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$repoRoot  = Split-Path -Parent $scriptDir
$pwFile    = Join-Path $scriptDir ".docs_password.xml"
$wrapper   = Join-Path $scriptDir "download_docs_scheduled.ps1"

if (-not (Test-Path $wrapper)) {
  throw "Wrapper script not found: $wrapper"
}

# 1) Password setup. Use -SkipPasswordSetup to refresh the scheduled task only.
if ($SkipPasswordSetup) {
  if (Test-Path $pwFile) {
    Write-Host "[OK] Keeping existing password file: $pwFile"
  } else {
    Write-Host "[!] Password file is missing. Download will log an error, but R2 sync can still run." -ForegroundColor Yellow
  }
} else {
  if ([string]::IsNullOrWhiteSpace($Password)) {
    $secure = Read-Host "Docs download password (DOCS_PASSWORD)" -AsSecureString
  } else {
    $secure = ConvertTo-SecureString $Password -AsPlainText -Force
  }

  if ($secure.Length -eq 0) {
    throw "Password is empty."
  }

  # DPAPI protects this for the current Windows user on this PC.
  $secure | ConvertFrom-SecureString | Set-Content -Path $pwFile -Encoding ASCII
  Write-Host "[OK] Saved encrypted password: $pwFile"
}

# 2) Register scheduled task.
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -RequireR2Sync' -f $wrapper) `
  -WorkingDirectory $repoRoot

$triggers = @(
  New-ScheduledTaskTrigger -Daily -At (Get-Date "09:00")
  New-ScheduledTaskTrigger -Daily -At (Get-Date "13:00")
  New-ScheduledTaskTrigger -Daily -At (Get-Date "17:50")
  New-ScheduledTaskTrigger -Daily -At (Get-Date "18:00")
)

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
  -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $TaskName `
  -Action $action -Trigger $triggers -Settings $settings `
  -Description "KIBA docs download plus required docs/ASK/Todo R2 mirror (09:00/13:00/17:50/18:00)" `
  -Force | Out-Null

Write-Host "[OK] Registered scheduled task '$TaskName' (09:00, 13:00, 17:50, 18:00)"

if (-not $NoTest) {
  # 3) Immediate test run.
  Write-Host "`n[Test] Running once now..."
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wrapper -RequireR2Sync

  $log = Join-Path $scriptDir "download_docs.log"
  if (Test-Path $log) {
    Write-Host "`n--- Recent log ---"
    Get-Content $log -Tail 10
  }
} else {
  Write-Host "[OK] Skipped immediate test run."
}

Write-Host "`nDone. Verify registration: Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "Remove task: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
