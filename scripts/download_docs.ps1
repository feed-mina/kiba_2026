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
$listRes = Invoke-WebRequest -UseBasicParsing -Method Get -Uri $listUrl -Headers $headers
$ms = New-Object System.IO.MemoryStream
$listRes.RawContentStream.CopyTo($ms)
$listJson = [System.Text.Encoding]::UTF8.GetString($ms.ToArray())
$list = $listJson | ConvertFrom-Json

if (-not $list.ok -or -not $list.files -or $list.files.Count -eq 0) {
  Write-Host "No documents found."
  exit 0
}

$index = 0
foreach ($file in $list.files) {
  $index += 1
  $issueFromKey = ""
  if ($file.key -match '^docs/[^/]+/([^/]+)/') {
    $issueFromKey = $Matches[1]
  }
  $issueFolder = if ($file.issue) { "issue-$($file.issue)" } elseif ($issueFromKey) { "issue-$issueFromKey" } else { "misc" }
  $targetDir = Join-Path $OutputDir $issueFolder
  New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

  $safeName = ($file.filename -replace '[\\/:*?"<>|]', '_')
  $safeName = $safeName.Trim()
  if ([string]::IsNullOrWhiteSpace($safeName)) {
    $safeName = "document-$index"
  }
  $ext = [System.IO.Path]::GetExtension($safeName)
  $baseName = [System.IO.Path]::GetFileNameWithoutExtension($safeName)
  $prefix = "{0:000}_" -f $index
  $maxLen = 96
  if (($prefix.Length + $safeName.Length) -gt $maxLen) {
    $keep = [Math]::Max(12, $maxLen - $prefix.Length - $ext.Length)
    $baseName = $baseName.Substring(0, [Math]::Min($baseName.Length, $keep)).Trim()
    $safeName = "$baseName$ext"
  }
  $safeName = "$prefix$safeName"
  $target = Join-Path $targetDir $safeName
  $encodedKey = [uri]::EscapeDataString($file.key)
  $downloadUrl = "$base/docs/download?repo=$encodedRepo&key=$encodedKey"

  Write-Host "Downloading $($file.filename) -> $target"
  $downloadRes = Invoke-WebRequest -UseBasicParsing -Method Get -Uri $downloadUrl -Headers $headers
  $downloadMs = New-Object System.IO.MemoryStream
  $downloadRes.RawContentStream.CopyTo($downloadMs)
  [System.IO.File]::WriteAllBytes($target, $downloadMs.ToArray())
}

Write-Host "Done. Files were saved under $OutputDir"
