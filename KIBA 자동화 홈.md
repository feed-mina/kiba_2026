---
title: KIBA 자동화 홈
tags: [home, automation]
---

# 🏠 KIBA 자동화 홈

이 볼트는 `C:\Users\User\Desktop\KIBA` 전체입니다. ASK·Todo·회의록·docs를 한곳에서 보고 편집합니다.
동기화는 **Windows 작업 스케줄러**가 담당하고, Obsidian은 보기·편집 전용입니다(자동 커밋 안 함).

## 📂 바로가기

- [[ASK/README|ASK 로그 작성 규칙]] — Claude·Codex 대화 일일 요약
- 오늘 ASK 로그: `ASK/YYYY-MM-DD_ai.md`
- Todo 폴더: `Todo/` — `*.md` 파일이 GitHub 이슈로 자동 반영됨
- 회의록: `meetings/`
- 문서 미러: `docs/` (Cloudflare R2 `kiba-docs-private` 와 양방향 동기화)

## ⚙️ 자동화 파이프라인 (요약)

| 흐름 | 트리거 | 동작 |
|---|---|---|
| Todo → GitHub 이슈 | `Todo/**` push | `.github/workflows/todo-reflect.yml` → `scripts/reflect_todo.py` 가 이슈 멱등 생성/갱신 + `index.html` 보드 갱신 |
| 이슈 → Project 보드 | 이슈 opened/reopened | `add-to-project.yml` (PAT 필요) |
| docs ↔ R2 미러 | Windows 작업 `KIBA Docs Download` (매일 09:00/13:00/17:50/18:00) | rclone 으로 docs·ASK·Todo 를 버킷과 양방향 복사(누락분만) |
| ASK/Todo → git push | 같은 작업 3단계 | `git add ASK Todo` 후 commit/push → 위 todo-reflect 트리거 |

> 참고: **ASK 로그는 깃 커밋·R2 백업만 되고 GitHub 이슈로는 만들어지지 않습니다.** 이슈로 추적할 항목은 `Todo/`에 작성하세요.

## 🩺 상태 점검 (PowerShell)

```powershell
# 스케줄 작업 마지막 결과 (0x0=정상)
Get-ScheduledTask -TaskName 'KIBA*' | ForEach-Object {
  $i = $_ | Get-ScheduledTaskInfo
  [PSCustomObject]@{ Name=$_.TaskName; Last=$i.LastRunTime; Result=('0x{0:X}' -f $i.LastTaskResult); Next=$i.NextRunTime }
} | Format-Table -AutoSize

# 최근 동기화 로그
Get-Content .\scripts\download_docs.log -Tail 20
```

## 🔑 알아둘 점

- `docs/` 는 `.gitignore` 대상 → Obsidian에서 docs를 편집해도 git에는 안 올라가지만, R2에는 스케줄러가 미러링합니다.
- 워커 다운로드(1단계)는 **선택 단계**라 실패해도 작업은 정상(초록)입니다. 복구하려면:
  `\.scripts\setup_docs_schedule.ps1 -NoTest` 를 실행해 docs 비밀번호를 다시 입력 → 현재 계정으로 재암호화.
