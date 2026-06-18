<#
  watch_sw_guide_scheduled.ps1
  Windows 작업 스케줄러가 무인 실행하는 래퍼 (GitHub Actions 백업용).

  하는 일
   1) python scripts\watch_sw_guide.py 실행
        - GITHUB_REPOSITORY = feed-mina/kiba_2026
        - GITHUB_TOKEN      = scripts\.sw_guide_token.xml (DPAPI) 가 있으면 주입 (이슈 코멘트용)
                              없으면 피드(data\sw_guide_latest.json)만 갱신
   2) 변경된 피드/상태 파일을 main 에 commit & push (PC 에 git 자격증명이 있음)

  로그는 scripts\watch_sw_guide.log 에 누적됩니다.

  매개변수
   -DryRun : git commit/push 를 건너뜀 (실행/감지만)
#>

param(
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = $PSScriptRoot
$repoRoot  = Split-Path -Parent $scriptDir
$tokenFile = Join-Path $scriptDir ".sw_guide_token.xml"
$logFile   = Join-Path $scriptDir "watch_sw_guide.log"

function Write-Log([string]$msg) {
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
  Add-Content -Path $logFile -Value $line -Encoding UTF8
}

# ---- Step 1: run the watcher ------------------------------------------------
function Invoke-Watch {
  $py = Get-Command python -ErrorAction SilentlyContinue
  if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
  if (-not $py) { throw "python 을 PATH 에서 찾을 수 없습니다." }

  $env:GITHUB_REPOSITORY = "feed-mina/kiba_2026"
  $env:SW_GUIDE_ISSUE    = "3"
  $env:PYTHONIOENCODING  = "utf-8"

  if (Test-Path $tokenFile) {
    $secure = Get-Content $tokenFile | ConvertTo-SecureString
    $bstr   = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $env:GITHUB_TOKEN = ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)).Trim() }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    Write-Log "Watch: token loaded (issue comment enabled)"
  } else {
    Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
    Write-Log "Watch: no token (feed-only; run setup_sw_guide_schedule.ps1 to enable issue comments)"
  }

  Write-Log "Watch: start"
  # python 이 stderr(재시도 경고 등)에 쓰더라도 중단되지 않도록 Continue 로.
  # 종료코드는 $LASTEXITCODE 로 직접 판정한다.
  $prevEAP = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    & $py.Source (Join-Path $scriptDir "watch_sw_guide.py") 2>&1 |
      ForEach-Object { Write-Log $_.ToString() }
    $code = $LASTEXITCODE
  }
  finally { $ErrorActionPreference = $prevEAP }
  Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
  if ($code -ne 0) { throw "watch_sw_guide.py 비정상 종료 (exit $code)" }
  Write-Log "Watch: done"
}

# ---- Step 2: commit & push feed/state --------------------------------------
function Invoke-GitPush {
  $git = Get-Command git -ErrorAction SilentlyContinue
  if (-not $git) { Write-Log "Git: skipped (git not found)"; return }

  $prevEAP = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  Push-Location $repoRoot
  try {
    $logGit = { $s = $_.ToString().TrimEnd(); if ($s -and $s -notmatch 'RemoteException') { Write-Log ("git: " + $s) } }
    & git add data/sw_guide_latest.json scripts/sw_guide_state.json 2>&1 | ForEach-Object $logGit
    $staged = (& git diff --cached --name-only) -join "`n"
    if ([string]::IsNullOrWhiteSpace($staged)) {
      Write-Log "Git: no feed/state changes"
      return
    }
    if ($DryRun) { Write-Log "Git: DRY-RUN, skip commit/push"; & git reset 2>&1 | ForEach-Object $logGit; return }
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    & git commit -m "chore: SW 대가 게시판 모니터링 갱신 $stamp [skip ci]" 2>&1 | ForEach-Object $logGit
    & git pull --rebase origin main 2>&1 | ForEach-Object $logGit
    & git push origin main 2>&1 | ForEach-Object $logGit
    Write-Log "Git: push done"
  }
  catch { Write-Log ("Git: error " + $_.Exception.Message) }
  finally { Pop-Location; $ErrorActionPreference = $prevEAP }
}

try {
  Invoke-Watch
  Invoke-GitPush
}
catch {
  Write-Log ("ERROR: " + $_.Exception.Message)
  exit 1
}
