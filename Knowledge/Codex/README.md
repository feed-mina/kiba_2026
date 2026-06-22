# Codex Knowledge Base

Open `C:\Users\User\Desktop\KIBA` as an Obsidian vault, then start here:

- [[코덱스 지식관리 홈]]
- [[Codex MOC]]
- [[Codex Index]]

This folder is an Obsidian-facing layer over the original `ASK/` and `Todo/`
records. Keep the source records in place; regenerate the index when ASK/Todo
changes:

```powershell
python .\scripts\build_codex_obsidian.py
```

## Operating Rules

- `ASK/` remains the daily question/answer log.
- `Todo/` remains the execution and issue-tracking layer.
- `Knowledge/Codex/` is for navigation, synthesis, and backlinks.
- Prefer linking back to source notes instead of duplicating details.

