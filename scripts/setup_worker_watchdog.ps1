<#
  setup_worker_watchdog.ps1  (1회 실행)
  1) (선택) Cloudflare API 토큰을 DPAPI 로 암호화해 scripts\.cf_api_token.xml 에 저장
       - 있으면 워치독이 OAuth 만료와 무관하게 무인 재배포 가능 (권장)
       - 생략하면 기존 wrangler OAuth 로그인으로 재배포 시도
  2) Windows 작업 스케줄러에 "KIBA Worker Watchdog" 등록
       - 30분마다 worker_healthcheck.ps1 실행 (빈 404 감지 시 자동 재배포)

  실행 (저장소 루트에서, PowerShell):
    .\scripts\setup_worker_watchdog.ps1
      -> Cloudflare API 토큰을 물어봅니다(엔터로 건너뛰면 OAuth 사용).
    또는 바로 넘기려면:
    .\scripts\setup_worker_watchdog.ps1 -CfToken "xxxxx"
#>

param(
  [string]$CfToken = "",
  [string]$TaskName = "KIBA Worker Watchdog",
  [int]$IntervalMinutes = 5
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$cfTokFile = Join-Path $scriptDir ".cf_api_token.xml"
$watch     = Join-Path $scriptDir "worker_healthcheck.ps1"

if (-not (Test-Path $watch)) { throw "워치독 스크립트를 찾을 수 없습니다: $watch" }

# 1) (선택) CF API 토큰 저장 -------------------------------------------------
if ([string]::IsNullOrWhiteSpace($CfToken)) {
  $secure = Read-Host "Cloudflare API 토큰 (무인 재배포용, 없으면 엔터로 건너뜀)" -AsSecureString
} else {
  $secure = ConvertTo-SecureString $CfToken -AsPlainText -Force
}
if ($secure.Length -gt 0) {
  $secure | ConvertFrom-SecureString | Set-Content -Path $cfTokFile -Encoding ASCII
  Write-Host "[OK] Cloudflare API 토큰을 암호화해 저장: $cfTokFile"
} else {
  Write-Host "[i] CF 토큰 생략 — 워치독은 기존 wrangler OAuth 로그인으로 재배포를 시도합니다."
}

# 2) 작업 스케줄러 등록 (30분마다 반복) --------------------------------------
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $watch)

# 30분 간격 무기한 반복: 반복 설정은 보조 트리거에서 복사(5.1 호환 우회)
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1)
$rep = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
          -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
          -RepetitionDuration (New-TimeSpan -Days 3650)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
  -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName `
  -Action $action -Trigger $trigger -Settings $settings `
  -Description "Cloudflare Worker /health 워치독 — 빈 404 감지 시 자동 재배포 ($IntervalMinutes 분마다)" `
  -Force | Out-Null

Write-Host "[OK] 작업 스케줄러에 '$TaskName' 등록 완료 ($IntervalMinutes 분마다)"

# 3) 즉시 1회 실행 -----------------------------------------------------------
Write-Host "`n[테스트] 지금 한 번 실행합니다..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $watch
$log = Join-Path $scriptDir "worker_health.log"
if (Test-Path $log) { Write-Host "`n--- 최근 로그 ---"; Get-Content $log -Tail 8 }

Write-Host "`n완료. 등록 확인: Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "해제하려면:   Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
