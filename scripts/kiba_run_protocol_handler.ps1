param(
  [string]$Uri = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$logFile = Join-Path $scriptDir "kiba_run_protocol.log"
$repoRoot = Split-Path -Parent $scriptDir

function Write-RunLog([string]$Message) {
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Add-Content -Path $logFile -Value $line -Encoding UTF8
}

try {
  if ($Uri -notmatch '^kiba-run://docs-sync/?$') {
    throw "Unsupported URI: $Uri"
  }

  Write-RunLog "Start requested by URL protocol: $Uri"
  $syncScript = Join-Path $scriptDir "sync_workstation_now.ps1"
  if (Test-Path $syncScript) {
    $ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $args = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $syncScript
    Start-Process -FilePath $ps -ArgumentList $args -WorkingDirectory $repoRoot -WindowStyle Hidden
    Write-RunLog "Started workstation sync wrapper: $syncScript"
  } else {
    Start-ScheduledTask -TaskName "KIBA Docs Download"
    Write-RunLog "Started scheduled task: KIBA Docs Download"
  }
}
catch {
  Write-RunLog ("ERROR: " + $_.Exception.Message)
  throw
}

