# Claude ASK/Todo 자동 기록 (Codex 미러) 구성 (2026-06-22)

> 목적: Codex 자동화 `daily-codex-ask-todo-log`(매일 17:00)의 Claude 버전을 추가해,
> Claude 쪽 작업도 매일 같은 `ASK/`·`Todo/` 파일에 누적하고 git/R2에 반영한다.
> 결정: 코덱스 자동화는 그대로 두고 Claude 전용 작업을 별도 시간(17:30)에 추가.
> 실행: 로컬 Windows 작업 스케줄러(코덱스와 동일 PC, headless claude.exe).

---

## 1. [래퍼] scripts/daily_claude_ask_todo.ps1

**상세 내용:** 최신 `claude.exe`를 자동 추적해 headless(`-p`)로 KIBA 폴더에서 실행한다.
에이전트는 오늘(Asia/Seoul) Claude 쪽 작업을 `ASK/YYYY-MM-DD_ai.md`에 ASK 형식으로
누적하고, 구체 후속 작업이 있을 때만 `Todo/`에 추가한다. 이후 검증된
`download_docs_scheduled.ps1 -SkipDownload`로 커밋·푸시·R2 동기화를 수행한다.

**체크리스트:**

- [x] `scripts/daily_claude_ask_todo.ps1` 작성 (claude.exe 자동 탐색 + headless 실행 + 백업 호출).
- [x] 권한 최소화: `--permission-mode acceptEdits` + `--allowedTools`(Read/Edit/Write/Glob/Grep, git 읽기 전용). 임의 명령·푸시 불가.
- [x] git 커밋·푸시·R2 동기화는 에이전트가 아니라 백업 스크립트가 담당 → Codex와 push 경쟁 없음.
- [x] 테스트 1회 실행(`-SkipBackup`): 스크립트 구조·로깅·에러 처리 정상 동작 확인.
- [x] claude 비정상 종료 시 단계 실패로 처리하도록 보강(이전엔 success 로 오인).

## ⚠️ 미해결: headless 인증 차단

테스트에서 확인된 블로커:

```
Your organization has disabled Claude subscription access for Claude Code ·
Use an Anthropic API key instead, or ask your admin to enable access
```

- 대화형(이 세션)은 동작하지만, **headless `claude -p`는 구독 인증이 조직 정책으로 차단**됨.
- 무인 실행 옵션:
  - (A) 사용자 레벨 `ANTHROPIC_API_KEY` 설정 → 별도 API 과금. `setx ANTHROPIC_API_KEY "sk-ant-..."` 후 작업 스케줄러가 상속.
  - (B) 관리자에게 Claude Code 구독 접근 허용 요청.
- 현재 상태: 스크립트·작업은 준비 완료, 인증만 갖추면 동작. 백업 스크립트(2단계)는 인증과 무관하게 정상.

## 2. [스케줄러] Windows 작업 등록

**상세 내용:** `KIBA Claude ASK Todo Log` 작업을 매일 17:30에 실행하도록 등록.
기존 KIBA 작업과 동일한 원칙(UserId=User, Interactive, Limited, StartWhenAvailable,
ExecutionTimeLimit 45분, MultipleInstances=IgnoreNew).

**체크리스트:**

- [x] `KIBA Claude ASK Todo Log` 작업 등록 (매일 17:30, State=Ready).
- [x] Codex 17:00 → Claude 17:30 으로 30분 간격 → push 경쟁 방지.
- [ ] 첫 자동 실행 후 ASK/Todo에 Claude 블록이 정상 누적되는지 확인.

## 3. [후속] 커밋 필요

- [ ] `scripts/daily_claude_ask_todo.ps1`, `Todo/2026-06-22_claude_ask_todo_automation.md` 를 git 에 커밋.
      (백업 스크립트는 ASK/Todo 만 자동 커밋하므로 `scripts/` 변경은 수동 커밋 필요.)
