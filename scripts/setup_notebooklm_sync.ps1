<#
  setup_notebooklm_sync.ps1  (1회 실행)
  회의록 요약본을 Google Drive 폴더(= NotebookLM 소스)에 자동 업로드하기 위한 1회 설정.

  하는 일:
   1) Google OAuth 자격증명(Client ID/Secret + Refresh Token)과 Drive 폴더 ID를
      DPAPI 로 암호화해 scripts\.notebooklm_creds.xml 에 저장(시크릿은 화면에 안 보임)
   2) Refresh Token 으로 access token 발급이 되는지 즉시 검증

  사전 준비(1회):
   - Google Drive 에 회의록용 폴더 생성 -> URL 의 folders/<ID> 가 DRIVE_FOLDER_ID
   - NotebookLM 에서 그 폴더를 소스로 연결(최초 1회)
   - Google Cloud -> API/사용자 인증 정보 -> OAuth 클라이언트(데스크톱) 생성 -> Client ID/Secret
   - scope drive.file 로 1회 동의 후 Refresh Token 획득
     (예: OAuth Playground 또는 자체 동의 흐름)

  실행 (저장소 루트에서):
    .\scripts\setup_notebooklm_sync.ps1
#>

param(
  [string]$ClientId = "",
  [string]$ClientSecret = "",
  [string]$RefreshToken = "",
  [string]$DriveFolderId = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$credFile  = Join-Path $scriptDir ".notebooklm_creds.xml"

# 1) 입력 ---------------------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($ClientId))      { $ClientId = Read-Host "Google OAuth Client ID" }
if ([string]::IsNullOrWhiteSpace($DriveFolderId)) { $DriveFolderId = Read-Host "Drive Folder ID (folders/<ID>)" }
if ([string]::IsNullOrWhiteSpace($ClientId))      { throw "Client ID 가 비어 있습니다." }
if ([string]::IsNullOrWhiteSpace($DriveFolderId)) { throw "Drive Folder ID 가 비어 있습니다." }

if ([string]::IsNullOrWhiteSpace($ClientSecret)) {
  $secretSecure = Read-Host "Google OAuth Client Secret" -AsSecureString
} else {
  $secretSecure = ConvertTo-SecureString $ClientSecret -AsPlainText -Force
}
if ($secretSecure.Length -eq 0) { throw "Client Secret 가 비어 있습니다." }

if ([string]::IsNullOrWhiteSpace($RefreshToken)) {
  $refreshSecure = Read-Host "Google Refresh Token" -AsSecureString
} else {
  $refreshSecure = ConvertTo-SecureString $RefreshToken -AsPlainText -Force
}
if ($refreshSecure.Length -eq 0) { throw "Refresh Token 이 비어 있습니다." }

# 2) DPAPI 암호화 저장 (SecureString 멤버는 Export-Clixml 가 자동 암호화) -------
$obj = [PSCustomObject]@{
  ClientId      = $ClientId
  DriveFolderId = $DriveFolderId
  ClientSecret  = $secretSecure
  RefreshToken  = $refreshSecure
}
$obj | Export-Clixml -Path $credFile
Write-Host "[OK] NotebookLM 자격증명을 암호화해 저장: $credFile" -ForegroundColor Green

# 3) Refresh Token -> access token 발급 검증 ---------------------------------
function Unprotect-SS($ss) {
  $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($ss)
  try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
}
$plainSecret  = Unprotect-SS $secretSecure
$plainRefresh = Unprotect-SS $refreshSecure

Write-Host "`n[확인] Refresh Token 으로 access token 발급 테스트..."
try {
  $resp = Invoke-RestMethod -Method Post -Uri "https://oauth2.googleapis.com/token" -Body @{
    client_id     = $ClientId
    client_secret = $plainSecret
    refresh_token = $plainRefresh
    grant_type    = "refresh_token"
  }
  if ($resp.access_token) {
    Write-Host "[OK] access token 발급 성공 (만료 $($resp.expires_in)초)." -ForegroundColor Green
  } else {
    Write-Host "[!] 응답에 access_token 이 없습니다. scope/동의를 확인하세요." -ForegroundColor Yellow
  }
} catch {
  Write-Host ("[!] 토큰 발급 실패: " + $_.Exception.Message) -ForegroundColor Yellow
  Write-Host "    Client ID/Secret/Refresh Token 과 OAuth 동의(scope drive.file)를 확인하세요."
}

Write-Host "`n완료. 이제 일일 스케줄러가 실행될 때 meetings\summary\<오늘>_meeting.md 가 있으면"
Write-Host "자동으로 Drive 폴더에 업로드됩니다(없으면 조용히 건너뜀)."
Write-Host "지금 한 번 시도:  .\scripts\download_docs_scheduled.ps1 -SkipDownload"
Write-Host "미리보기(전송 없음):  .\scripts\download_docs_scheduled.ps1 -SkipDownload -DryRun"
