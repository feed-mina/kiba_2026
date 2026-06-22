<#
  daily_claude_ask_todo.ps1
  Windows Task Scheduler 가 매일 무인 실행하는 래퍼. (Claude 쪽)

  Codex 자동화 `daily-codex-ask-todo-log` 의 Claude 버전입니다.
  Codex 는 17:00 에 자기 작업을 기록하고, 이 작업은 17:30 에 Claude 작업을 같은
  ASK/Todo 파일에 누적합니다. (두 도구가 같은 파일을 공유 = "합침")

  단계:
   1) 최신 claude.exe 를 자동으로 찾는다.
   2) claude 를 headless(-p) 로 KIBA 폴더에서 실행해, 오늘(Asia/Seoul) Claude 쪽
      작업을 ASK/YYYY-MM-DD_ai.md 에 ASK 형식으로 누적하고, 구체 후속 작업이 있으면
      Todo/ 에만 추가한다. (에이전트는 git 을 만지지 않는다 — 충돌 방지)
   3) scripts/download_docs_scheduled.ps1 -SkipDownload 로 ASK/Todo 커밋·푸시 +
      R2 동기화를 수행한다. (검증된 기존 백업 경로 재사용)

  새 Claude 작업이 없으면 ASK/Todo 에 빈 파일을 만들지 않고, 백업/동기화만 수행한다.

  [인증 주의] headless(`claude -p`) 실행은 구독 인증이 조직 정책으로 차단될 수 있다
  ("Your organization has disabled Claude subscription access for Claude Code").
  그 경우 무인 실행에는 ANTHROPIC_API_KEY 환경변수(사용자 레벨)가 필요하다.
  설정 예) setx ANTHROPIC_API_KEY "sk-ant-..."  (설정 후 작업 스케줄러가 상속)

  로그는 scripts\daily_claude_ask_todo.log 에 누적된다.

  파라미터:
   -SkipBackup : 3단계(백업/동기화) 생략. ASK/Todo 기록만.
#>

param(
  [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = $PSScriptRoot
$repoRoot  = Split-Path -Parent $scriptDir
$logFile   = Join-Path $scriptDir "daily_claude_ask_todo.log"

function Write-Log([string]$msg) {
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
  Add-Content -Path $logFile -Value $line -Encoding UTF8
}

# ---- claude.exe 찾기 (버전 폴더가 업데이트로 바뀌어도 자동 추적) -------------
function Resolve-ClaudeExe {
  $bases = @(
    (Join-Path $env:APPDATA "Claude\claude-code"),
    (Join-Path $env:LOCALAPPDATA "Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude-code")
  )
  foreach ($base in $bases) {
    if (-not (Test-Path $base)) { continue }
    $latest = Get-ChildItem $base -Directory -ErrorAction SilentlyContinue |
      Sort-Object { try { [version]$_.Name } catch { [version]"0.0.0" } } |
      Select-Object -Last 1
    if ($latest) {
      $exe = Join-Path $latest.FullName "claude.exe"
      if (Test-Path $exe) { return $exe }
    }
  }
  # 마지막 수단: PATH
  $g = Get-Command claude -ErrorAction SilentlyContinue
  if ($g) { return $g.Source }
  return $null
}

# ---- 1+2단계: claude headless 로 오늘 Claude 작업을 ASK/Todo 에 기록 --------
function Invoke-ClaudeLog {
  $exe = Resolve-ClaudeExe
  if (-not $exe) {
    throw "claude.exe 를 찾지 못했습니다. (AppData\Claude\claude-code 확인)"
  }
  Write-Log "Claude: using $exe"

  $today = Get-Date -Format "yyyy-MM-dd"
  $prompt = @"
KIBA 워크스페이스($repoRoot) 기준으로 오늘(Asia/Seoul, $today) Claude 쪽 작업을 ASK/Todo 에 기록해라.

규칙:
- 오늘 작업 근거: 'git log --since=midnight --oneline', 'git status', 작업트리 변경, 그리고 현재 워크스페이스 아티팩트에서 보이는 Claude 작업만 기록한다. 추측·창작 금지.
- ASK/$today`_ai.md 에 ASK 형식 블록을 누적한다(append). 형식: '## 주제 요약' / '**도구:** Claude' (Codex 와 함께한 작업은 'Claude+Codex') / '**질문:**' 한 줄 / '**응답 요약:**' 2~3줄 불릿. 파일이 없으면 ASK/README.md 의 헤더 규칙대로 새로 만든다.
- 구체적인 후속 작업(follow-up)이 있을 때만 Todo/$today`_*.md 를 만들거나 갱신한다. 단순 기록이면 Todo 파일을 만들지 않는다.
- 기존 내용과 한국어 텍스트를 절대 훼손하지 말고 보존한다.
- git 은 읽기(log/status/diff/show)만 사용해 오늘 작업을 파악하라. add/commit/push 는 하지 마라. 커밋·푸시·R2 동기화는 래퍼 스크립트가 처리한다. 파일 편집까지만 한다.
- 오늘 새로 기록할 Claude 작업이 없으면 빈 ASK/Todo 파일을 만들지 말고 아무 변경 없이 종료한다.
"@

  # 권한 최소화: 파일 편집은 자동 수락(acceptEdits)하되, Bash 는 git 읽기 전용만 허용.
  # 임의 명령/푸시/삭제는 불가 — 커밋·푸시·R2 동기화는 3단계 백업 스크립트가 담당한다.
  $allowed = @(
    "Read","Edit","Write","Glob","Grep",
    "Bash(git log:*)","Bash(git status:*)","Bash(git diff:*)","Bash(git show:*)"
  )
  $claudeArgs = @('-p', $prompt,
    '--permission-mode', 'acceptEdits',
    '--allowedTools') + $allowed +
    @('--add-dir', $repoRoot, '--output-format', 'text')

  Push-Location $repoRoot
  try {
    Write-Log "Claude: log step start ($today)"
    # claude 는 성공해도 경고를 stderr 로 쓰므로 native 호출 동안 Continue 로 둔다.
    # 빈 stdin 을 파이프해 '-p' 모드가 입력을 기다리지 않도록 한다.
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
      $null | & $exe @claudeArgs 2>&1 |
        ForEach-Object { $s = $_.ToString().TrimEnd(); if ($s) { Write-Log ("claude: " + $s) } }
    }
    finally { $ErrorActionPreference = $prevEAP }
    $code = $LASTEXITCODE
    Write-Log "Claude: log step done (exit $code)"
    if ($code -ne 0) {
      # headless 인증 실패가 가장 흔함: 구독 정책 차단 -> ANTHROPIC_API_KEY 필요.
      if (-not $env:ANTHROPIC_API_KEY) {
        throw "claude headless 실행 실패(exit $code). 무인 실행에는 ANTHROPIC_API_KEY 환경변수가 필요할 수 있습니다 (구독 인증은 headless 에서 차단됨)."
      }
      throw "claude headless 실행 실패(exit $code). 로그(claude:) 확인."
    }
  }
  finally {
    Pop-Location
  }
}

# ---- 3단계: 검증된 백업 스크립트로 ASK/Todo 커밋·푸시 + R2 동기화 ----------
function Invoke-Backup {
  $backup = Join-Path $scriptDir "download_docs_scheduled.ps1"
  if (-not (Test-Path $backup)) {
    Write-Log "Backup: skipped (download_docs_scheduled.ps1 not found)"
    return
  }
  Write-Log "Backup: start (download_docs_scheduled.ps1 -SkipDownload)"
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $backup -SkipDownload *>&1 |
    ForEach-Object { $s = $_.ToString().TrimEnd(); if ($s) { Write-Log ("backup: " + $s) } }
  Write-Log "Backup: done (exit $LASTEXITCODE)"
}

# 각 단계 독립 실행: 한 단계가 실패해도 나머지는 계속한다.
$script:failed = $false
function Invoke-Step([string]$name, [scriptblock]$action) {
  try { & $action }
  catch {
    Write-Log ("ERROR [$name]: " + $_.Exception.Message)
    $script:failed = $true
  }
}

Write-Log "=== daily_claude_ask_todo run start ==="
Invoke-Step "claudelog" { Invoke-ClaudeLog }
Invoke-Step "backup"    { if (-not $SkipBackup) { Invoke-Backup } }
Write-Log "=== daily_claude_ask_todo run end (failed=$script:failed) ==="

if ($script:failed) { exit 1 }
