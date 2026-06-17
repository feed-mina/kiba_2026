<#
  download_docs_scheduled.ps1
  Wrapper run unattended by Windows Task Scheduler.

  Steps:
   1) (default) Download docs from the worker into .\docs
        - password decrypted from scripts\.docs_password.xml (DPAPI)
   2) (if R2 credentials present) two-way sync between local docs and the R2 bucket
        - copy-missing-only (--ignore-existing): never re-transfers, never deletes
        - uses scripts\.r2_credentials.xml (DPAPI) + scripts\r2_sync.config.json
        - if rclone missing or no credentials -> sync is skipped (download still runs)

  Log is appended to scripts\download_docs.log (ASCII messages so it never garbles).

  Parameters:
   -SkipDownload : skip step 1 (download), run sync only
   -DryRun       : preview the R2 sync (--dry-run), no real transfer
#>

param(
  [switch]$SkipDownload,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Capture native (rclone) output as UTF-8 so Korean filenames are logged correctly
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = $PSScriptRoot
$repoRoot  = Split-Path -Parent $scriptDir
$pwFile    = Join-Path $scriptDir ".docs_password.xml"
$credFile  = Join-Path $scriptDir ".r2_credentials.xml"
$cfgFile   = Join-Path $scriptDir "r2_sync.config.json"
$logFile   = Join-Path $scriptDir "download_docs.log"
$outputDir = Join-Path $repoRoot "docs"

# Folders to two-way sync with R2.  localDir <-> bucket/<prefix>  ("" = bucket root)
# docs -> bucket root (matches the worker's key layout); ASK/Todo -> ask/ todo/ prefixes.
$syncPairs = @(
  @{ Local = $outputDir;                    Prefix = "" },
  @{ Local = (Join-Path $repoRoot "ASK");   Prefix = "ask" },
  @{ Local = (Join-Path $repoRoot "Todo");  Prefix = "todo" }
)

function Write-Log([string]$msg) {
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
  Add-Content -Path $logFile -Value $line -Encoding UTF8
}

# ---- Step 1: download docs from the worker ---------------------------------
function Invoke-Download {
  if (-not (Test-Path $pwFile)) {
    throw "Password file not found: $pwFile (run setup_docs_schedule.ps1 first)"
  }
  $secure = Get-Content $pwFile | ConvertTo-SecureString
  $bstr   = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }

  Write-Log "Download: start"
  & (Join-Path $scriptDir "download_docs.ps1") -OutputDir $outputDir -Password $password *>&1 |
    ForEach-Object { Write-Log $_.ToString() }
  Write-Log "Download: done"
}

# ---- Step 2: two-way sync local docs <-> R2 (copy missing only) -------------
function Invoke-R2Sync {
  if (-not (Test-Path $credFile) -or -not (Test-Path $cfgFile)) {
    Write-Log "Sync: skipped (no R2 credentials/config; run setup_r2_sync.ps1)"
    return
  }
  $rclone = Get-Command rclone -ErrorAction SilentlyContinue
  if (-not $rclone) {
    Write-Log "Sync: skipped (rclone not installed; winget install Rclone.Rclone)"
    return
  }

  $cfg       = Get-Content $cfgFile -Raw | ConvertFrom-Json
  $accountId = $cfg.accountId
  $bucket    = $cfg.bucket
  $endpoint  = "https://$accountId.r2.cloudflarestorage.com"

  $cred = Import-Clixml $credFile
  $ak   = $cred.UserName
  $sk   = $cred.GetNetworkCredential().Password

  # pass credentials via env vars (avoid argv exposure)
  $env:RCLONE_CONFIG               = "NUL"
  $env:RCLONE_S3_PROVIDER          = "Cloudflare"
  $env:RCLONE_S3_ACCESS_KEY_ID     = $ak
  $env:RCLONE_S3_SECRET_ACCESS_KEY = $sk
  $env:RCLONE_S3_ENDPOINT          = $endpoint
  $env:RCLONE_S3_REGION            = "auto"
  $env:RCLONE_S3_NO_CHECK_BUCKET   = "true"

  $common = @("--ignore-existing", "--transfers", "4", "--log-level", "INFO")
  if ($DryRun) { $common += "--dry-run" }

  Write-Log ("Sync: start (bucket=$bucket" + $(if($DryRun){', DRY-RUN'}else{''}) + ")")

  # rclone logs to stderr even on success; keep Continue during the calls.
  $logRclone = {
    $s = $_.ToString().TrimEnd()
    if ($s -and $s -notmatch 'RemoteException') { Write-Log $s }
  }
  $prevEAP = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    foreach ($pair in $syncPairs) {
      $local  = $pair.Local
      $prefix = $pair.Prefix
      if (-not (Test-Path $local)) {
        Write-Log "Sync: skip '$local' (folder not found)"
        continue
      }
      $remote = if ($prefix) { ":s3:$bucket/$prefix" } else { ":s3:$bucket" }
      $name   = Split-Path $local -Leaf

      Write-Log "Sync[$name]: UPLOAD local -> R2 (missing only)  [$remote]"
      & rclone copy "$local" "$remote" @common 2>&1 | ForEach-Object $logRclone

      Write-Log "Sync[$name]: DOWNLOAD R2 -> local (missing only)  [$remote]"
      & rclone copy "$remote" "$local" @common 2>&1 | ForEach-Object $logRclone
    }
  }
  finally {
    $ErrorActionPreference = $prevEAP
  }

  Write-Log "Sync: done"

  Remove-Item Env:RCLONE_S3_SECRET_ACCESS_KEY -ErrorAction SilentlyContinue
  Remove-Item Env:RCLONE_S3_ACCESS_KEY_ID -ErrorAction SilentlyContinue
}

try {
  if (-not $SkipDownload) { Invoke-Download }
  Invoke-R2Sync
}
catch {
  Write-Log ("ERROR: " + $_.Exception.Message)
  exit 1
}
