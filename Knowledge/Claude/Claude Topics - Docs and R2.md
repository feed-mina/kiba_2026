# Claude Topics - Docs and R2

Use this note for decisions around private documents, R2 mirroring, and scheduler
reliability that Claude work touches.

## Current Anchors

- [[Todo/2026-06-22_claude_ask_todo_automation|Claude automation reuses download_docs_scheduled.ps1 backup/sync]]
- [[Codex Topics - Docs and R2|Docs/R2 decisions (shared)]]

## Notes

- Claude 자동화는 백업/동기화를 새로 만들지 않고 검증된 `download_docs_scheduled.ps1 -SkipDownload`를 재사용한다(커밋·푸시 + R2 동기화).
- 진짜 미러는 R2 동기화다. 작업 빨간불이 곧 미서비스를 뜻하지는 않는다.

## Maintenance Questions

- `download_docs_scheduled.ps1 -SkipDownload`가 Claude 작업 끝에 정상 실행되는가?
- `docs/`, `ASK/`, `Todo/`가 기대한 R2 prefix로 미러되는가?
- rclone/자격증명(DPAPI)이 예약작업 사용자에게 유효한가?

#claude #r2 #automation
