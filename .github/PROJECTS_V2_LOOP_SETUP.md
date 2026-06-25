# KIBA Loop Engineering Project Setup

This file is the concrete Project v2 setup for the KIBA loop:

```text
GitHub Project = 운영판
GitHub Issue = 실행 단위
Obsidian = 사고와 회고
Quartz = 비개발자용 공개 지식
```

## Status field

Create or update the `Status` single-select field with these options:

| Option | Meaning |
|---|---|
| Inbox | 새 아이디어, 회의 메모, 아직 분류 전 |
| Clarify | 목적, 완료 기준, 공개 여부를 정리 중 |
| Ready | 바로 실행 가능한 이슈 |
| Doing | 진행 중 |
| Review / Reflect | 검토, 회고, 공개 판단 |
| Publish Candidate | Quartz 공개 후보 |
| Done | 이슈 close, 루프 1회 완료 |

## Additional fields

| Field | Type | Options or format |
|---|---|---|
| Loop Type | Single select | daily, issue, publish, decision, automation |
| Priority | Single select | P0, P1, P2, Later |
| Cycle | Text | `2026-W26`, `2026-06-23` |
| Obsidian Note | Text | `Knowledge/Issues/Issue NN - title.md` |
| Public | Single select | private, candidate, published |
| Quartz URL | Text | `https://feed-mina.github.io/quartz_kiba/...` |
| Next Action | Text | 다음에 할 행동 1개 |

## Labels

Create these labels if they do not exist:

| Label | Color | Use |
|---|---|---|
| `type/task` | `0e8a16` | 실행 작업 |
| `type/idea` | `5319e7` | 아이디어, 가설 |
| `type/bug` | `d73a4a` | 오류 수정 |
| `type/doc` | `0075ca` | 문서화 |
| `type/decision` | `fbca04` | 결정 필요 또는 결정 기록 |
| `loop/daily` | `bfdadc` | 일간 루프 |
| `loop/issue` | `c2e0c6` | 이슈 단위 루프 |
| `loop/publish` | `fef2c0` | Quartz 공개 루프 |
| `public/candidate` | `f9d0c4` | 공개 후보 |
| `public/published` | `b4a7d6` | 공개 완료 |
| `needs/clarify` | `d4c5f9` | 목적/완료 기준 보강 필요 |
| `needs/reflect` | `fef2c0` | 회고 필요 |

You can apply the labels with:

```powershell
.\scripts\setup_loop_labels.ps1
```

If `gh` is not installed globally, install a portable copy into this workspace:

```powershell
.\scripts\install_gh_portable.ps1 -AddToUserPath
```

Then create the Project fields:

```powershell
.\scripts\setup_loop_project_fields.ps1
```

`setup_loop_project_fields.ps1` creates missing custom fields. If the built-in
`Status` field already exists, set its options in the Project UI to:

```text
Inbox, Clarify, Ready, Doing, Review / Reflect, Publish Candidate, Done
```

## Daily operating rule

1. New issue enters `Inbox`.
2. If purpose or done criteria are unclear, move to `Clarify` and add `needs/clarify`.
3. When it is executable, move to `Ready`.
4. When work starts, move to `Doing`.
5. Before closing, move to `Review / Reflect`.
6. If it should be public, add `public/candidate` and move to `Publish Candidate`.
7. Close the issue only after reflection is captured in the linked Obsidian note.

## First automation order

1. Obsidian note creates GitHub Issue.
2. Issue state updates Obsidian frontmatter.
3. Closed issue asks for reflection.
4. `public/candidate` issues populate Quartz candidates.
5. Daily or weekly loop summary recommends next actions.
