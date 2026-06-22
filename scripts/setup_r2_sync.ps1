<#
  setup_r2_sync.ps1  (1회 실행)
  로컬 docs <-> R2 버킷(kiba-docs-private) 양방향 동기화를 위한 1회 설정 스크립트.

  하는 일:
   1) rclone 설치 여부 확인 (없으면 안내 후 종료)
   2) R2 API 토큰(액세스 키 ID + 시크릿)을 DPAPI 로 암호화해
      scripts\.r2_credentials.xml 에 저장
   3) 버킷/계정 정보를 scripts\r2_sync.config.json 에 저장
   4) 실제 전송 없이 --dry-run 미리보기 실행 -> 무엇이 오갈지 확인

  실행 방법 (저장소 루트에서):
    .\scripts\setup_r2_sync.ps1
      -> 실행 중 액세스 키 ID/시크릿을 물어봅니다(시크릿은 화면에 안 보임).
    또는 바로 넘기려면:
    .\scripts\setup_r2_sync.ps1 -AccessKeyId "AKID..." -SecretAccessKey "..."

  R2 토큰 만드는 곳:
    Cloudflare 대시보드 -> R2 -> Manage API tokens -> Create API token
    (권한: Object Read & Write, 버킷: kiba-docs-private 로 제한 권장)
#>

param(
  [string]$AccessKeyId = "",
  [string]$SecretAccessKey = "",
  [string]$Bucket = "kiba-docs-private",
  [string]$AccountId = "4a361c3d62b0241354ada304a4f94482"
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$repoRoot  = Split-Path -Parent $scriptDir
$credFile  = Join-Path $scriptDir ".r2_credentials.xml"
$cfgFile   = Join-Path $scriptDir "r2_sync.config.json"
$wrapper   = Join-Path $scriptDir "download_docs_scheduled.ps1"
$outputDir = Join-Path $repoRoot "docs"

# 1) rclone 확인 --------------------------------------------------------------
$localRclone = Join-Path $repoRoot ".tools\rclone\rclone.exe"
if (Test-Path $localRclone) {
  $rclone = $localRclone
} else {
  $foundRclone = Get-Command rclone -ErrorAction SilentlyContinue
  $rclone = if ($foundRclone) { $foundRclone.Source } else { $null }
}
if (-not $rclone) {
  Write-Host "[!] rclone 이 설치되어 있지 않습니다." -ForegroundColor Yellow
  Write-Host "    설치: .\scripts\setup_portable_tools.ps1"
  Write-Host "    설치 후 새 PowerShell 창에서 이 스크립트를 다시 실행하세요."
  exit 1
}
Write-Host "[OK] rclone 확인: $rclone"

# 2) 자격증명 입력/암호화 저장 ------------------------------------------------
if ([string]::IsNullOrWhiteSpace($AccessKeyId)) {
  $AccessKeyId = Read-Host "R2 Access Key ID"
}
if ([string]::IsNullOrWhiteSpace($AccessKeyId)) { throw "Access Key ID 가 비어 있습니다." }

if ([string]::IsNullOrWhiteSpace($SecretAccessKey)) {
  $secretSecure = Read-Host "R2 Secret Access Key" -AsSecureString
} else {
  $secretSecure = ConvertTo-SecureString $SecretAccessKey -AsPlainText -Force
}
if ($secretSecure.Length -eq 0) { throw "Secret Access Key 가 비어 있습니다." }

# PSCredential 로 묶어 Export-Clixml -> 시크릿은 DPAPI 로 자동 암호화됨
$cred = New-Object System.Management.Automation.PSCredential($AccessKeyId, $secretSecure)
$cred | Export-Clixml -Path $credFile
Write-Host "[OK] R2 자격증명을 암호화해 저장: $credFile"

# 3) 설정 저장 ----------------------------------------------------------------
[ordered]@{ bucket = $Bucket; accountId = $AccountId } |
  ConvertTo-Json | Set-Content -Path $cfgFile -Encoding UTF8
Write-Host "[OK] 설정 저장: $cfgFile  (bucket=$Bucket)"

# 4) 연결 확인 + dry-run 미리보기 --------------------------------------------
$endpoint = "https://$AccountId.r2.cloudflarestorage.com"
$env:RCLONE_CONFIG               = "NUL"   # 설정파일 없이 환경변수만 사용(안내문구 억제)
$env:RCLONE_S3_PROVIDER          = "Cloudflare"
$env:RCLONE_S3_ACCESS_KEY_ID     = $AccessKeyId
$env:RCLONE_S3_SECRET_ACCESS_KEY = $cred.GetNetworkCredential().Password
$env:RCLONE_S3_ENDPOINT          = $endpoint
$env:RCLONE_S3_REGION            = "auto"
$env:RCLONE_S3_NO_CHECK_BUCKET   = "true"

# rclone 은 정상 동작 중에도 안내/진행 로그를 stderr 로 출력하므로,
# 호출 동안만 ErrorActionPreference 를 Continue 로 두어 중단을 막는다.
function Invoke-RcloneSafe {
  param([Parameter(ValueFromRemainingArguments=$true)][string[]]$RcArgs)
  $prev = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try { & $rclone @RcArgs 2>&1 | ForEach-Object { $_.ToString() } }
  finally { $ErrorActionPreference = $prev }
}

Write-Host "`n[확인] 버킷 접근 테스트 (상위 목록)..."
Invoke-RcloneSafe lsd ":s3:$Bucket" | Select-Object -First 20

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
Write-Host "`n[미리보기] 실제 전송 없이 무엇이 오갈지 확인 (--dry-run)"
Write-Host "  -- 업로드(로컬 docs -> R2) --"
Invoke-RcloneSafe copy "$outputDir" ":s3:$Bucket" --ignore-existing --dry-run | Select-Object -First 40
Write-Host "  -- 다운로드(R2 -> 로컬 docs) --"
Invoke-RcloneSafe copy ":s3:$Bucket" "$outputDir" --ignore-existing --dry-run | Select-Object -First 40

Remove-Item Env:RCLONE_S3_SECRET_ACCESS_KEY -ErrorAction SilentlyContinue

Write-Host "`n완료. 위 미리보기 결과가 의도와 맞는지 확인하세요." -ForegroundColor Green
Write-Host "이제부터 'KIBA Docs Download' 작업이 실행될 때마다 다운로드 후 양방향 동기화가 함께 수행됩니다."
Write-Host "지금 실제로 한 번 동기화하려면:  .\scripts\download_docs_scheduled.ps1"
Write-Host "동기화만 미리보기로 다시 보려면:  .\scripts\download_docs_scheduled.ps1 -SkipDownload -DryRun"
