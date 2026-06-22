# Codex Topics - Docs and R2

Use this note for decisions around private documents, R2 mirroring, and scheduler
reliability.

## Current Anchors

- [[Todo/2026-06-18_scheduler_codex_automation#3. [문서 백업/R2 동기화] 다운로드와 스케줄러 안정화|Document backup and R2 sync]]
- [[ASK/2026-06-18_ai#스케줄러 실행 여부 점검 및 누락분 보충 실행|Scheduler catch-up]]
- [[ASK/2026-06-22_ai#ASK/Todo 일일 Codex 작업 기록 및 백업 동기화|ASK/Todo backup sync]]

## Maintenance Questions

- Does `KIBA Docs Download` finish with `LastTaskResult = 0`?
- Is `scripts/.docs_password.xml` valid for the scheduled-task user?
- Are `docs/`, `ASK/`, and `Todo/` mirrored to the expected R2 prefixes?

#codex #r2 #automation

