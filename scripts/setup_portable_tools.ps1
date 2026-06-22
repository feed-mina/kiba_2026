<#
  setup_portable_tools.ps1

  Downloads workstation-local tools into .tools/ without requiring an admin
  install or PATH changes:

   - .tools\python\python.exe  (Python embeddable package)
   - .tools\rclone\rclone.exe

  The KIBA scheduled scripts look in these locations before falling back to PATH.
#>

[CmdletBinding()]
param(
  [string]$PythonVersion = "3.13.14",
  [string]$PythonUrl = "",
  [string]$RcloneUrl = "https://downloads.rclone.org/rclone-current-windows-amd64.zip"
)

$ErrorActionPreference = "Stop"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$scriptDir = $PSScriptRoot
$repoRoot  = Split-Path -Parent $scriptDir
$toolsDir  = Join-Path $repoRoot ".tools"
$dlDir     = Join-Path $toolsDir "downloads"
$pythonDir = Join-Path $toolsDir "python"
$rcloneDir = Join-Path $toolsDir "rclone"

if ([string]::IsNullOrWhiteSpace($PythonUrl)) {
  $PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
}

New-Item -ItemType Directory -Force -Path $dlDir, $pythonDir, $rcloneDir | Out-Null

function Download-File([string]$Url, [string]$OutFile) {
  Write-Host "Downloading: $Url"
  Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $OutFile
}

function Install-PortablePython {
  $pythonExe = Join-Path $pythonDir "python.exe"
  if (Test-Path $pythonExe) {
    Write-Host "[OK] Portable Python already exists: $pythonExe"
    return
  }

  $zip = Join-Path $dlDir ("python-{0}-embed-amd64.zip" -f $PythonVersion)
  Download-File $PythonUrl $zip
  Expand-Archive -Path $zip -DestinationPath $pythonDir -Force

  if (-not (Test-Path $pythonExe)) {
    throw "Portable Python install failed: $pythonExe not found"
  }
  Write-Host "[OK] Installed portable Python: $pythonExe"
}

function Install-PortableRclone {
  $rcloneExe = Join-Path $rcloneDir "rclone.exe"
  if (Test-Path $rcloneExe) {
    Write-Host "[OK] Portable rclone already exists: $rcloneExe"
    return
  }

  $zip = Join-Path $dlDir "rclone-current-windows-amd64.zip"
  $tmp = Join-Path $dlDir "rclone-expanded"
  if (Test-Path $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null

  Download-File $RcloneUrl $zip
  Expand-Archive -Path $zip -DestinationPath $tmp -Force
  $found = Get-ChildItem -Path $tmp -Recurse -Filter rclone.exe | Select-Object -First 1
  if (-not $found) {
    throw "Portable rclone install failed: rclone.exe not found in archive"
  }
  Copy-Item -LiteralPath $found.FullName -Destination $rcloneExe -Force
  Write-Host "[OK] Installed portable rclone: $rcloneExe"
}

Install-PortablePython
Install-PortableRclone

Write-Host ""
Write-Host "Versions:"
& (Join-Path $pythonDir "python.exe") --version
& (Join-Path $rcloneDir "rclone.exe") version
