# Claude Topics - Automation

Use this note to collect stable decisions about scheduled Claude/ASK/Todo work.

## Current Anchors

- [[Todo/2026-06-22_claude_ask_todo_automation|Claude daily ASK/Todo automation (Codex mirror)]]
- [[Codex Topics - Automation|Codex automation decisions]]

## Decisions

- Claude 일일 기록은 로컬 Windows 작업 `KIBA Claude ASK Todo Log`(매일 17:30)로 실행한다. Codex(17:00) 다음에 돌려 git push 경쟁을 피한다.
- 에이전트 권한은 최소화한다(`acceptEdits` + Read/Edit/Write/Glob/Grep + git 읽기 전용). 커밋·푸시·R2 동기화는 `download_docs_scheduled.ps1 -SkipDownload`가 담당한다.
- headless `claude -p`는 구독 인증이 조직 정책으로 차단될 수 있어 `ANTHROPIC_API_KEY`가 필요할 수 있다.

## Maintenance Questions

- `KIBA Claude ASK Todo Log` 작업이 매일 정상 실행되는가? (`scripts/daily_claude_ask_todo.log`)
- ASK/Todo 변경이 R2 미러 전에 커밋되는가?
- Claude 인덱스가 ASK/Todo 갱신 후 다시 생성되는가?

#claude #automation
