<#
.SYNOPSIS
  KIBA 폴더를 C:\Users\User\Desktop\vibe_2026\KIBA 로 이동하고,
  깨지는 예약 작업·전역 .gitconfig(credential helper·safe.directory)·
  Knowledge/wiki 절대경로를 새 위치로 자동 보정한다.

.NOTES
  반드시 Claude Code / Codex / Obsidian / 편집기를 모두 닫은 상태에서,
  KIBA 폴더 "바깥"의 PowerShell 창에서 실행할 것.
  (KIBA 를 작업 디렉터리로 점유한 프로세스가 있으면 이동이 막힌다.)

  실행 예:
    powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\User\Desktop\KIBA\scripts\migrate_to_vibe_2026.ps1"
#>

$ErrorActionPreference = 'Stop'

$Old    = 'C:\Users\User\Desktop\KIBA'
$Parent = 'C:\Users\User\Desktop\vibe_2026'
$New    = Join-Path $Parent 'KIBA'

# 0) 자기 자신이 KIBA 안을 cwd 로 잡지 않도록 밖으로 이동
Set-Location 'C:\'

Write-Host "== KIBA -> vibe_2026 마이그레이션 ==" -ForegroundColor Cyan

# 1) 사전 점검 (재실행 가능하도록 idempotent 하게)
if (-not (Test-Path -LiteralPath $Parent)) {
    throw "대상 상위 폴더가 없습니다: $Parent"
}
$oldExists = Test-Path -LiteralPath $Old
$newExists = Test-Path -LiteralPath $New
if ($oldExists -and $newExists) {
    throw "원본과 대상이 모두 존재합니다. 수동 확인 필요:`n  원본: $Old`n  대상: $New"
}
if (-not $oldExists -and -not $newExists) {
    throw "원본/대상 어디에도 KIBA 가 없습니다: $Old / $New"
}
if (-not $oldExists -and $newExists) {
    Write-Host "이미 이동됨. 이동 단계를 건너뛰고 후속 보정만 진행합니다." -ForegroundColor Yellow
}

# 2) 이동 (잠금 시 안내)
if (Test-Path -LiteralPath $Old) {
    try {
        Move-Item -LiteralPath $Old -Destination $New
        Write-Host "[OK] 이동 완료: $New" -ForegroundColor Green
    } catch {
        Write-Host "[실패] 폴더가 사용 중입니다. 아래 앱을 모두 닫고 다시 실행하세요:" -ForegroundColor Red
        Write-Host "       - Claude Code (이 폴더 기준 세션)" -ForegroundColor Red
        Write-Host "       - Codex 데스크톱 앱" -ForegroundColor Red
        Write-Host "       - Obsidian (KIBA 볼트)" -ForegroundColor Red
        Write-Host "       - VS Code / Antigravity 등 편집기, 열려 있는 탐색기 창" -ForegroundColor Red
        throw
    }
}

# 3) 깨진 예약 작업 새 경로로 재지정 (Execute/Arguments/WorkingDirectory 의 경로 치환)
Write-Host "== 예약 작업 경로 보정 ==" -ForegroundColor Cyan
# 경로 경계(backslash 또는 문자열 끝)까지 인식해 $Old -> $New 로 치환한다.
# 이렇게 해야 후행 백슬래시가 없는 WorkingDirectory("...\Desktop\KIBA")도 잡고,
# "...\Desktop\KIBA_backup" 같은 다른 폴더는 오치환하지 않는다.
$rePath  = '(?i)' + [regex]::Escape($Old) + '(?=\\|$)'
function Repoint([string]$value) { [regex]::Replace($value, $rePath, $New) }
$fixed = 0
foreach ($task in (Get-ScheduledTask)) {
    $changed = $false
    # 기존 action 객체의 경로 속성만 제자리(in-place)에서 치환한다.
    # New-ScheduledTaskAction 으로 재생성하면 Exec 가 아닌 action(메시지/COM 등)이나
    # Execute 가 비어 있는 action 에서 검증 오류가 나므로 사용하지 않는다.
    foreach ($a in $task.Actions) {
        # Exec 타입이 아닌 action 은 Execute/Arguments/WorkingDirectory 속성이 없으므로 건너뛴다.
        if (-not ($a.PSObject.Properties.Name -contains 'Execute')) { continue }
        foreach ($prop in 'Execute','Arguments','WorkingDirectory') {
            $cur = $a.$prop
            if ($cur -and ($cur -match $rePath)) { $a.$prop = Repoint $cur; $changed = $true }
        }
    }
    if ($changed) {
        Set-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath -Action $task.Actions | Out-Null
        Write-Host "  [재지정] $($task.TaskName)" -ForegroundColor Green
        $fixed++
    }
}
Write-Host "  예약 작업 $fixed 개 보정 완료" -ForegroundColor Green

# 4) 전역 .gitconfig 의 옛 경로 보정
#    credential helper(gh.exe 경로)·safe.directory 등은 절대경로로 저장되어
#    폴더 이동 시 깨진다(예: git push 시 자격증명 헬퍼 실행 실패로 인증 불가).
#    .gitconfig 는 백슬래시(\)와 슬래시(/) 표기가 섞여 있으므로 두 표기 모두 치환하고,
#    경로 경계(구분자/따옴표/공백/줄끝)까지만 매칭해 다른 폴더 오치환을 막는다.
Write-Host "== 전역 .gitconfig 경로 보정 ==" -ForegroundColor Cyan
$gitConfig = Join-Path $env:USERPROFILE '.gitconfig'
if (Test-Path -LiteralPath $gitConfig) {
    $before = Get-Content -LiteralPath $gitConfig -Raw -Encoding UTF8
    if ($null -eq $before) { $before = '' }
    $OldF = $Old -replace '\\', '/'
    $NewF = $New -replace '\\', '/'
    $reB = '(?i)' + [regex]::Escape($Old)  + '(?=[\\''"\s]|$)'   # C:\...\KIBA
    $reF = '(?i)' + [regex]::Escape($OldF) + '(?=[/''"\s]|$)'    # C:/.../KIBA
    # 치환 문자열에 $ 등 특수문자 영향이 없도록 MatchEvaluator(스크립트블록) 사용
    $after = [regex]::Replace($before, $reB, { param($m) $New })
    $after = [regex]::Replace($after,  $reF, { param($m) $NewF })
    if ($after -ne $before) {
        Copy-Item -LiteralPath $gitConfig -Destination "$gitConfig.bak" -Force
        [System.IO.File]::WriteAllText($gitConfig, $after, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host "  [보정] $gitConfig  (백업: $gitConfig.bak)" -ForegroundColor Green
    } else {
        Write-Host "  변경 없음(옛 경로 참조 없음)" -ForegroundColor DarkGray
    }
} else {
    Write-Host "  .gitconfig 없음, 건너뜀" -ForegroundColor DarkGray
}

# 5) 절대경로가 박힌 Knowledge / wiki 재생성 (스크립트는 위치 독립적)
Write-Host "== Knowledge / wiki 재생성 ==" -ForegroundColor Cyan
Push-Location $New
try {
    python scripts\build_issue_knowledge.py
    python scripts\export_obsidian_to_github_wiki.py
} finally {
    Pop-Location
}

# 6) Quartz 발행(선택): 형제 폴더 자동탐지로 ../KIBA 를 소스로 사용
$Quartz = Join-Path $Parent 'quartz_kiba'
if (Test-Path -LiteralPath (Join-Path $Quartz 'scripts\build-garden.mjs')) {
    Write-Host "== Quartz content 발행 ==" -ForegroundColor Cyan
    Push-Location $Quartz
    try {
        node scripts\build-garden.mjs
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "완료. 새 위치: $New" -ForegroundColor Cyan
Write-Host "남은 수동 작업:" -ForegroundColor Yellow
Write-Host "  - Obsidian 에서 새 경로($New)로 볼트 다시 열기" -ForegroundColor Yellow
Write-Host "  - Claude Code 를 새 폴더에서 다시 시작" -ForegroundColor Yellow
Write-Host "  - 변경된 파일 검토 후 git commit/push" -ForegroundColor Yellow
