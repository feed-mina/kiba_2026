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
   3) rebuild Obsidian knowledge indexes
   4) commit & push ASK/Todo/Knowledge logs to GitHub
   5) (if NotebookLM creds present) upload today's meeting summary to the Drive
        source folder via sync_meeting_to_notebooklm.py
        - uses scripts\.notebooklm_creds.xml (DPAPI; run setup_notebooklm_sync.ps1)
        - skipped if no creds, no python, or no meetings\summary\<today>_meeting.md

  Log is appended to scripts\download_docs.log (ASCII messages so it never garbles).

  Parameters:
   -SkipDownload   : skip step 1 (download), run sync only
   -DryRun         : preview R2 sync + NotebookLM (--dry-run), no real transfer
   -SkipNotebookLM : skip step 4 (NotebookLM Drive upload)
#>

param(
  [switch]$SkipDownload,
  [switch]$DryRun,
  [switch]$SkipNotebookLM
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

# ---- Step 3: rebuild Obsidian knowledge indexes ----------------------------
function Invoke-ObsidianKnowledge {
  $py = Get-Command python -ErrorAction SilentlyContinue
  if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
  if (-not $py) { Write-Log "Obsidian: skipped (python not on PATH)"; return }

  $scripts = @(
    "build_codex_obsidian.py",
    "build_claude_obsidian.py",
    "build_issue_knowledge.py"
  )
  foreach ($name in $scripts) {
    $script = Join-Path $scriptDir $name
    if (-not (Test-Path $script)) {
      Write-Log "Obsidian: skipped ($name not found)"
      continue
    }
    Write-Log "Obsidian: run $name"
    try {
      & $py.Source $script 2>&1 | ForEach-Object {
        $s = $_.ToString().TrimEnd()
        if ($s) { Write-Log ("obsidian: " + $s) }
      }
    } catch {
      Write-Log ("Obsidian: error in ${name}: " + $_.Exception.Message)
    }
  }
}

# ---- Step 4: commit & push ASK/Todo/Knowledge logs to GitHub (runs in Windows = has git creds)
function Invoke-GitPushLogs {
  $git = Get-Command git -ErrorAction SilentlyContinue
  if (-not $git) { Write-Log "Git: skipped (git not found on PATH)"; return }

  $prevEAP = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  Push-Location $repoRoot
  try {
    $logGit = { $s = $_.ToString().TrimEnd(); if ($s -and $s -notmatch 'RemoteException') { Write-Log ("git: " + $s) } }

    & git add ASK Todo Knowledge 2>&1 | ForEach-Object $logGit
    $staged = (& git diff --cached --name-only) -join "`n"
    if ([string]::IsNullOrWhiteSpace($staged)) {
      Write-Log "Git: no ASK/Todo/Knowledge changes to push"
      return
    }
    Write-Log ("Git: staged ->`n" + $staged)
    if ($DryRun) { Write-Log "Git: DRY-RUN, skip commit/push"; & git reset 2>&1 | ForEach-Object $logGit; return }
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    & git commit -m "chore: ASK/Todo knowledge logs $stamp" 2>&1 | ForEach-Object $logGit
    # integrate any bot commits (e.g. index.html from todo-reflect) before pushing
    & git pull --rebase origin main 2>&1 | ForEach-Object $logGit
    & git push origin main 2>&1 | ForEach-Object $logGit
    Write-Log "Git: push done"
  }
  catch {
    Write-Log ("Git: error " + $_.Exception.Message)
  }
  finally {
    Pop-Location
    $ErrorActionPreference = $prevEAP
  }
}

# ---- Step 5: push today's meeting summary to NotebookLM (Drive source) ------
function Invoke-NotebookLMSync {
  $credNb = Join-Path $scriptDir ".notebooklm_creds.xml"
  if (-not (Test-Path $credNb)) {
    Write-Log "NotebookLM: skipped (no creds; run setup_notebooklm_sync.ps1)"
    return
  }
  $py = Get-Command python -ErrorAction SilentlyContinue
  if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
  if (-not $py) { Write-Log "NotebookLM: skipped (python not on PATH)"; return }

  $date    = Get-Date -Format "yyyy-MM-dd"
  $summary = Join-Path $repoRoot ("meetings/summary/{0}_meeting.md" -f $date)
  if (-not (Test-Path $summary)) {
    Write-Log "NotebookLM: skipped (no summary for $date)"
    return
  }

  $c = Import-Clixml $credNb
  function Unprotect-SS($ss) {
    $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($ss)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
  }
  $env:GOOGLE_CLIENT_ID     = $c.ClientId
  $env:GOOGLE_CLIENT_SECRET = Unprotect-SS $c.ClientSecret
  $env:GOOGLE_REFRESH_TOKEN = Unprotect-SS $c.RefreshToken
  $env:DRIVE_FOLDER_ID      = $c.DriveFolderId

  $prevEAP = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    $script = Join-Path $scriptDir "sync_meeting_to_notebooklm.py"
    if ($DryRun) {
      Write-Log "NotebookLM: DRY-RUN ($date)"
      & $py.Source $script $date --via drive 2>&1 | ForEach-Object { Write-Log ("nblm: " + $_.ToString().TrimEnd()) }
    } else {
      Write-Log "NotebookLM: sync start ($date)"
      & $py.Source $script $date --via drive --confirm 2>&1 | ForEach-Object { Write-Log ("nblm: " + $_.ToString().TrimEnd()) }
      Write-Log "NotebookLM: sync done"
    }
  }
  finally {
    Remove-Item Env:GOOGLE_CLIENT_SECRET -ErrorAction SilentlyContinue
    Remove-Item Env:GOOGLE_REFRESH_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:GOOGLE_CLIENT_ID -ErrorAction SilentlyContinue
    Remove-Item Env:DRIVE_FOLDER_ID -ErrorAction SilentlyContinue
    $ErrorActionPreference = $prevEAP
  }
}

# 각 단계를 독립 실행: 한 단계가 실패해도(예: 다운로드 404 플래핑) 나머지는 계속한다.
# 그래야 ASK/Todo git push 가 불안정한 download 단계에 묶이지 않는다.
$script:failed = $false
function Invoke-Step([string]$name, [scriptblock]$action) {
  try { & $action }
  catch {
    Write-Log ("ERROR [$name]: " + $_.Exception.Message)
    $script:failed = $true
  }
}

Invoke-Step "download"   { if (-not $SkipDownload) { Invoke-Download } }
Invoke-Step "obsidian"   { Invoke-ObsidianKnowledge }
Invoke-Step "gitpush"    { Invoke-GitPushLogs }
Invoke-Step "r2sync"     { Invoke-R2Sync }
Invoke-Step "notebooklm" { if (-not $SkipNotebookLM) { Invoke-NotebookLMSync } }

if ($script:failed) { exit 1 }   # 작업 상태에 부분 실패를 반영하되, 모든 단계는 시도됨
