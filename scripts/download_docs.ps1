param(
  [string]$ApiBase = "https://kiba.kibayerin.workers.dev",
  [string]$Repo = "feed-mina/kiba_2026",
  [int]$Issue = 0,
  [string]$OutputDir = ".\docs",
  [string]$Password = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Password)) {
  $secure = Read-Host "Docs download password" -AsSecureString
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try {
    $Password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  }
}

if ([string]::IsNullOrWhiteSpace($Password)) {
  throw "Password is required."
}

$headers = @{ "X-Docs-Password" = $Password }
$base = $ApiBase.TrimEnd("/")
$encodedRepo = [uri]::EscapeDataString($Repo)
$listUrl = "$base/docs/list?repo=$encodedRepo"
if ($Issue -gt 0) {
  $listUrl = "$listUrl&issue=$Issue"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Write-Host "Fetching document list..."
$list = Invoke-RestMethod -Method Get -Uri $listUrl -Headers $headers

if (-not $list.ok -or -not $list.files -or $list.files.Count -eq 0) {
  Write-Host "No documents found."
  exit 0
}

foreach ($file in $list.files) {
  $issueFolder = if ($file.issue) { "issue-$($file.issue)" } else { "misc" }
  $targetDir = Join-Path $OutputDir $issueFolder
  New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

  $safeName = ($file.filename -replace '[\\/:*?"<>|]', '_')
  $target = Join-Path $targetDir $safeName
  $encodedKey = [uri]::EscapeDataString($file.key)
  $downloadUrl = "$base/docs/download?repo=$encodedRepo&key=$encodedKey"

  Write-Host "Downloading $($file.filename) -> $target"
  Invoke-WebRequest -Method Get -Uri $downloadUrl -Headers $headers -OutFile $target | Out-Null
}

Write-Host "Done. Files were saved under $OutputDir"
