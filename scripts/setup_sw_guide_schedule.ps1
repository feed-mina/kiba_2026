<#
  setup_sw_guide_schedule.ps1  (1회 실행)
  1) (선택) GitHub PAT 를 DPAPI 로 암호화해 scripts\.sw_guide_token.xml 에 저장
       - 있으면 PC 백업 실행도 Issue #3 에 코멘트를 남길 수 있음
       - 생략하면 피드(data\sw_guide_latest.json)만 갱신 (이슈 코멘트는 GitHub Actions 가 담당)
  2) Windows 작업 스케줄러에 "KIBA SW Guide Watch" 작업 등록
       - 매일 09:10 (문서 다운로드 09:00 직후) watch_sw_guide_scheduled.ps1 실행
       - PC 가 꺼져 시각을 놓치면 다음에 켜졌을 때 실행(StartWhenAvailable)
     => GitHub Actions(watch-sw-guide.yml, 09:30 KST)의 백업 역할

  실행 (저장소 루트에서):
    .\scripts\setup_sw_guide_schedule.ps1
      -> PAT 를 물어봅니다(엔터로 건너뛰면 피드 전용).
    또는 바로 넘기려면:
    .\scripts\setup_sw_guide_schedule.ps1 -Token "github_pat_..."
#>

param(
  [string]$Token = "",
  [string]$TaskName = "KIBA SW Guide Watch"
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$tokenFile = Join-Path $scriptDir ".sw_guide_token.xml"
$wrapper   = Join-Path $scriptDir "watch_sw_guide_scheduled.ps1"

if (-not (Test-Path $wrapper)) {
  throw "래퍼 스크립트를 찾을 수 없습니다: $wrapper"
}

# 1) (선택) PAT 암호화 저장 ---------------------------------------------------
if ([string]::IsNullOrWhiteSpace($Token)) {
  $secure = Read-Host "GitHub PAT (이슈 코멘트용, 없으면 엔터로 건너뜀)" -AsSecureString
} else {
  $secure = ConvertTo-SecureString $Token -AsPlainText -Force
}

if ($secure.Length -gt 0) {
  $secure | ConvertFrom-SecureString | Set-Content -Path $tokenFile -Encoding ASCII
  Write-Host "[OK] PAT 를 암호화해 저장했습니다: $tokenFile"
} else {
  Write-Host "[i] PAT 생략 — PC 백업은 피드만 갱신합니다(이슈 코멘트는 GitHub Actions 담당)."
}

# 2) 작업 스케줄러 등록 -------------------------------------------------------
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $wrapper)

$trigger = New-ScheduledTaskTrigger -Daily -At (Get-Date "09:10")

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
  -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $TaskName `
  -Action $action -Trigger $trigger -Settings $settings `
  -Description "SW 대가 산정 게시판(cbIdx=276) 모니터링 — GitHub Actions 백업 (매일 09:10)" `
  -Force | Out-Null

Write-Host "[OK] 작업 스케줄러에 '$TaskName' 등록 완료 (매일 09:10)"

# 3) 즉시 1회 테스트 실행 -----------------------------------------------------
Write-Host "`n[테스트] 지금 한 번 실행합니다..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wrapper
$log = Join-Path $scriptDir "watch_sw_guide.log"
if (Test-Path $log) {
  Write-Host "`n--- 최근 로그 ---"
  Get-Content $log -Tail 12
}

Write-Host "`n완료. 등록 확인: Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "해제하려면:   Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
