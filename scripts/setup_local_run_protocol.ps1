<#
  Registers the local URL protocol used by the GitHub Pages button:

    kiba-run://docs-sync

  Run once per Windows PC. It writes only to HKCU, so admin is normally not
  required. Browsers will still show a confirmation prompt before opening the
  local handler.
#>

param(
  [string]$Protocol = "kiba-run"
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$handler = Join-Path $scriptDir "kiba_run_protocol_handler.ps1"

if (-not (Test-Path $handler)) {
  throw "Handler not found: $handler"
}

$protocolRoot = "HKCU:\Software\Classes\$Protocol"
$commandKey = Join-Path $protocolRoot "shell\open\command"
$command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" "%1"' -f $handler

New-Item -Path $protocolRoot -Force | Out-Null
New-ItemProperty -Path $protocolRoot -Name "(default)" -Value "URL:KIBA local runner" -PropertyType String -Force | Out-Null
New-ItemProperty -Path $protocolRoot -Name "URL Protocol" -Value "" -PropertyType String -Force | Out-Null
New-Item -Path $commandKey -Force | Out-Null
New-ItemProperty -Path $commandKey -Name "(default)" -Value $command -PropertyType String -Force | Out-Null

Write-Host "[OK] Registered ${Protocol}:// local runner"
Write-Host "Test from browser or Run dialog: ${Protocol}://docs-sync"
