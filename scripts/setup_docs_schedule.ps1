<#
  setup_docs_schedule.ps1  (1회 실행)
  1) 문서 다운로드 비밀번호를 DPAPI 로 암호화해 scripts\.docs_password.xml 에 저장
  2) Windows 작업 스케줄러에 "KIBA Docs Download" 작업을 등록
     - 매일 09:00, 13:00, 17:50 에 download_docs_scheduled.ps1 실행
     - PC가 꺼져 있어 시각을 놓치면 다음에 켜졌을 때 실행(StartWhenAvailable)

  실행 방법 (저장소 루트에서):
    .\scripts\setup_docs_schedule.ps1
      -> 실행 중 비밀번호를 물어봅니다(입력 시 화면에 안 보임).
    또는 비밀번호를 바로 넘기려면:
    .\scripts\setup_docs_schedule.ps1 -Password "kiba1234"
#>

param(
  [string]$Password = "",
  [string]$TaskName = "KIBA Docs Download"
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$pwFile    = Join-Path $scriptDir ".docs_password.xml"
$wrapper   = Join-Path $scriptDir "download_docs_scheduled.ps1"

if (-not (Test-Path $wrapper)) {
  throw "래퍼 스크립트를 찾을 수 없습니다: $wrapper"
}

# 1) 비밀번호 입력/암호화 저장 -------------------------------------------------
if ([string]::IsNullOrWhiteSpace($Password)) {
  $secure = Read-Host "문서 다운로드 비밀번호(DOCS_PASSWORD)" -AsSecureString
} else {
  $secure = ConvertTo-SecureString $Password -AsPlainText -Force
}

if ($secure.Length -eq 0) {
  throw "비밀번호가 비어 있습니다."
}

# DPAPI(현재 사용자 + 이 PC)로 암호화 — 다른 PC/사용자는 복호화 불가
$secure | ConvertFrom-SecureString | Set-Content -Path $pwFile -Encoding ASCII
Write-Host "[OK] 비밀번호를 암호화해 저장했습니다: $pwFile"

# 2) 작업 스케줄러 등록 --------------------------------------------------------
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $wrapper)

$triggers = @(
  New-ScheduledTaskTrigger -Daily -At (Get-Date "09:00")
  New-ScheduledTaskTrigger -Daily -At (Get-Date "13:00")
  New-ScheduledTaskTrigger -Daily -At (Get-Date "17:50")
  New-ScheduledTaskTrigger -Daily -At (Get-Date "18:00")  # 17:55 ASK/Todo 로그 작성 직후 백업
)

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
  -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $TaskName `
  -Action $action -Trigger $triggers -Settings $settings `
  -Description "KIBA 문서 다운로드(.\docs) + docs/ASK/Todo R2 양방향 동기화 (매일 09:00/13:00/17:50/18:00)" `
  -Force | Out-Null

Write-Host "[OK] 작업 스케줄러에 '$TaskName' 등록 완료 (매일 09:00, 13:00, 17:50, 18:00)"

# 3) 즉시 1회 테스트 실행 ------------------------------------------------------
Write-Host "`n[테스트] 지금 한 번 실행합니다..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wrapper
$log = Join-Path $scriptDir "download_docs.log"
if (Test-Path $log) {
  Write-Host "`n--- 최근 로그 ---"
  Get-Content $log -Tail 10
}

Write-Host "`n완료. 등록 확인: Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "해제하려면:   Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
