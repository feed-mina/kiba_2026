<#
  setup_anthropic_api_key.ps1  (1회 실행)

  무인(headless) `claude -p` 실행에 필요한 ANTHROPIC_API_KEY 를 DPAPI 로 암호화해
  scripts\.anthropic_api_key.xml 에 저장한다.

  배경: 조직 정책이 Claude Code 의 "구독 인증"을 headless 에서 차단하기 때문에
  (대화형은 됨) `daily_claude_ask_todo.ps1` 의 무인 실행에는 API 키가 필요하다.

  왜 setx 가 아니라 암호화 파일인가:
  - `setx ANTHROPIC_API_KEY "sk-ant-..."` 는 사용자 레지스트리에 *평문* 으로 남고,
    같은 PC 의 다른 프로세스/스크립트에서 그대로 노출된다.
  - 이 리포의 다른 시크릿(.docs_password.xml/.r2_credentials.xml/.sw_guide_token.xml)
    과 동일하게 DPAPI(현재 Windows 계정 전용)로 묶으면, 그 계정에서만 복호화된다.

  실행 (저장소 루트에서):
    .\scripts\setup_anthropic_api_key.ps1
      -> 키를 물어봅니다(입력은 화면에 표시되지 않음).
    또는 바로 넘기려면(주의: 셸 히스토리에 남음):
    .\scripts\setup_anthropic_api_key.ps1 -ApiKey "sk-ant-..."

  해제:  Remove-Item .\scripts\.anthropic_api_key.xml
#>

param(
  [string]$ApiKey = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$keyFile   = Join-Path $scriptDir ".anthropic_api_key.xml"

# 1) 키 입력 (SecureString — 화면에 표시되지 않음) ----------------------------
if ([string]::IsNullOrWhiteSpace($ApiKey)) {
  $secure = Read-Host "ANTHROPIC_API_KEY (sk-ant-...)" -AsSecureString
} else {
  $secure = ConvertTo-SecureString $ApiKey -AsPlainText -Force
}

if ($secure.Length -eq 0) {
  throw "키가 비어 있습니다. ANTHROPIC_API_KEY 를 입력해야 합니다."
}

# 형식 가벼운 검증 (오타로 빈/엉뚱한 값 저장 방지) ----------------------------
$bstr  = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try   { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
if ($plain -notmatch '^sk-ant-') {
  Write-Warning "키가 'sk-ant-' 로 시작하지 않습니다. 그래도 저장은 진행합니다."
}

# 2) DPAPI 암호화 저장 (현재 Windows 계정 전용) --------------------------------
$secure | ConvertFrom-SecureString | Set-Content -Path $keyFile -Encoding ASCII
Write-Host "[OK] ANTHROPIC_API_KEY 를 암호화해 저장했습니다: $keyFile"
Write-Host "     (현재 계정 '$env:USERNAME' 에서만 복호화됩니다. 다른 PC 로 복사 금지.)"

# 3) 즉시 검증: daily_claude_ask_todo.ps1 가 키를 읽어 headless 1줄을 실행 ------
$runner = Join-Path $scriptDir "daily_claude_ask_todo.ps1"
Write-Host ""
Write-Host "확인: 다음 명령으로 무인 실행을 테스트하세요 (백업/푸시는 생략):"
Write-Host "  .\scripts\daily_claude_ask_todo.ps1 -SkipBackup"
Write-Host "  Get-Content .\scripts\daily_claude_ask_todo.log -Tail 20"
Write-Host ""
Write-Host "스케줄 작업은 이미 등록돼 있으면 그대로 키를 상속합니다:"
Write-Host "  Get-ScheduledTask -TaskName 'KIBA Claude ASK Todo Log'"
