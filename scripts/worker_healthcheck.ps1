<#
  worker_healthcheck.ps1
  Cloudflare Worker(kiba.kibayerin.workers.dev) 헬스 워치독.

  하는 일
   1) GET /health 확인 (200 + JSON 이어야 정상)
   2) 비정상(빈 404 등)이면 worker/ 에서 `npx wrangler deploy` 로 자동 재배포
   3) 전파 대기 후 재확인, 결과를 scripts\worker_health.log 에 기록

  배경: workers.dev 라우트가 간헐적으로 죽어 빈 404 를 반환하는 사고가 반복됨
        (workers_dev=true 만으론 못 막음). 이 워치독이 자동 복구한다.

  인증: scripts\.cf_api_token.xml (DPAPI, Cloudflare API 토큰) 이 있으면 그걸 쓰고,
        없으면 기존 wrangler OAuth 로그인으로 배포를 시도한다.

  매개변수
   -Force : /health 상태와 무관하게 재배포를 강제(점검용)
#>

param(
  [switch]$Force
)

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$scriptDir = $PSScriptRoot
$repoRoot  = Split-Path -Parent $scriptDir
$workerDir = Join-Path $repoRoot "worker"
$logFile   = Join-Path $scriptDir "worker_health.log"
$cfTokFile = Join-Path $scriptDir ".cf_api_token.xml"
$healthUrl = "https://kiba.kibayerin.workers.dev/health"

function Write-Log([string]$msg) {
  Add-Content -Path $logFile -Value ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg) -Encoding UTF8
}

function Get-HealthCode {
  # curl.exe 로 상태코드만 받는다(빈 404 도 코드로 잡힘). 실패 시 000.
  $code = & curl.exe -s -o NUL -w "%{http_code}" --max-time 15 $healthUrl 2>$null
  if (-not $code) { return "000" }
  return $code.Trim()
}

function Invoke-Redeploy {
  $npx = Get-Command npx -ErrorAction SilentlyContinue
  if (-not $npx) { Write-Log "redeploy 불가: npx 없음"; return $false }

  # CF API 토큰이 있으면 OAuth 만료와 무관하게 무인 배포
  if (Test-Path $cfTokFile) {
    $secure = Get-Content $cfTokFile | ConvertTo-SecureString
    $bstr   = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $env:CLOUDFLARE_API_TOKEN = ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)).Trim() }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    Write-Log "redeploy: CLOUDFLARE_API_TOKEN 사용"
  } else {
    Write-Log "redeploy: wrangler OAuth 로그인 사용(토큰 파일 없음)"
  }

  $prevEAP = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  Push-Location $workerDir
  try {
    & npx wrangler deploy 2>&1 | ForEach-Object {
      $s = $_.ToString().TrimEnd()
      if ($s -and $s -notmatch 'RemoteException') { Write-Log ("wrangler: " + $s) }
    }
    $ok = ($LASTEXITCODE -eq 0)
  }
  finally {
    Pop-Location
    $ErrorActionPreference = $prevEAP
    Remove-Item Env:CLOUDFLARE_API_TOKEN -ErrorAction SilentlyContinue
  }
  return $ok
}

# ---- main -------------------------------------------------------------------
$code = Get-HealthCode
if (($code -eq "200") -and (-not $Force)) {
  Write-Log "OK (/health 200)"
  exit 0
}

$forceNote = if ($Force) { " (강제 재배포)" } else { "" }
Write-Log "비정상 감지: /health = $code$forceNote -> 재배포 시도"
$deployed = Invoke-Redeploy
if (-not $deployed) {
  Write-Log "재배포 실패 — 수동 점검 필요"
  exit 1
}

# 전파 대기 후 재확인 (배포 직후엔 15~20초간 아직 404 로 보일 수 있음)
Start-Sleep -Seconds 20
$after = Get-HealthCode
if ($after -eq "200") {
  Write-Log "복구 완료 (/health 200)"
  exit 0
} else {
  Write-Log "재배포했으나 여전히 /health = $after — 수동 점검 필요"
  exit 1
}
