param(
  [string]$Uri = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$logFile = Join-Path $scriptDir "kiba_run_protocol.log"

function Write-RunLog([string]$Message) {
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Add-Content -Path $logFile -Value $line -Encoding UTF8
}

try {
  if ($Uri -notmatch '^kiba-run://docs-sync/?$') {
    throw "Unsupported URI: $Uri"
  }

  Write-RunLog "Start requested by URL protocol: $Uri"
  Start-ScheduledTask -TaskName "KIBA Docs Download"
  Write-RunLog "Started scheduled task: KIBA Docs Download"
}
catch {
  Write-RunLog ("ERROR: " + $_.Exception.Message)
  throw
}

