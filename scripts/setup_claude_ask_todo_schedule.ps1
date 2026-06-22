<#
  setup_claude_ask_todo_schedule.ps1

  Registers the daily Claude -> ASK/Todo capture task on the current Windows PC.
  The task writes ASK/Todo updates first; scripts\download_docs_scheduled.ps1
  handles commit/push/R2 sync afterwards.
#>

[CmdletBinding()]
param(
  [string]$Time = "17:30",
  [string]$TaskName = "KIBA Claude ASK Todo Log",
  [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$repoRoot  = Split-Path -Parent $scriptDir
$runner    = Join-Path $scriptDir "daily_claude_ask_todo.ps1"

if (-not (Test-Path $runner)) {
  throw "Runner script not found: $runner"
}

$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$arg = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $runner
if ($SkipBackup) { $arg += " -SkipBackup" }

$action = New-ScheduledTaskAction -Execute $ps -Argument $arg -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 45) `
  -RestartCount 1 `
  -RestartInterval (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Principal $principal `
  -Description "KIBA daily Claude ASK/Todo capture, then optional backup/sync" `
  -Force | Out-Null

Write-Host "[OK] Registered scheduled task '$TaskName'"
Write-Host "Daily time : $Time"
Write-Host "Script     : $runner"
Write-Host "Verify     : Get-ScheduledTask -TaskName '$TaskName'"
