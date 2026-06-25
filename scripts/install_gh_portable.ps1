param(
  [string]$Version = "2.95.0",
  [switch]$AddToUserPath
)

$ErrorActionPreference = "Stop"

$workspaceRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$toolsDir = Join-Path $workspaceRoot ".tools"
$zipPath = Join-Path $toolsDir "gh_$Version_windows_amd64.zip"
$installDir = Join-Path $toolsDir "gh-$Version"
$downloadUrl = "https://github.com/cli/cli/releases/download/v$Version/gh_${Version}_windows_amd64.zip"

New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null

Write-Host "Downloading GitHub CLI $Version..."
Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath

if (Test-Path $installDir) {
  Remove-Item -LiteralPath $installDir -Recurse -Force
}

Expand-Archive -LiteralPath $zipPath -DestinationPath $installDir -Force

$ghExe = Get-ChildItem -Path $installDir -Recurse -Filter gh.exe |
  Select-Object -First 1 -ExpandProperty FullName

if (-not $ghExe) {
  throw "gh.exe was not found after extraction."
}

Write-Host "Installed portable gh:"
Write-Host $ghExe

if ($AddToUserPath) {
  $binDir = Split-Path -Parent $ghExe
  $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $parts = @($currentPath -split ";" | Where-Object { $_ })
  if ($parts -notcontains $binDir) {
    $newPath = (@($parts + $binDir) -join ";")
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "Added to user PATH. Open a new terminal for PATH changes to apply."
  } else {
    Write-Host "Portable gh is already on the user PATH."
  }
}

& $ghExe --version
