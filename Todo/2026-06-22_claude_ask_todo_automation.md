# Claude ASK/Todo 자동 기록 (Codex 미러) 구성 (2026-06-22)

> 목적: Codex 자동화 `daily-codex-ask-todo-log`(매일 17:00)의 Claude 버전을 추가해,
> Claude 쪽 작업도 매일 같은 `ASK/`·`Todo/` 파일에 누적하고 git/R2에 반영한다.
> 결정: Codex는 정각 2시간 간격, Claude는 30분 뒤 2시간 간격으로 분리해 같은 ASK 파일 충돌을 피한다.
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

## ⚠️ headless 인증 차단 — 해결 경로 구현됨 (2026-06-24)

테스트에서 확인된 블로커:

```
Your organization has disabled Claude subscription access for Claude Code ·
Use an Anthropic API key instead, or ask your admin to enable access
```

- 대화형(이 세션)은 동작하지만, **headless `claude -p`는 구독 인증이 조직 정책으로 차단**됨.
- 무인 실행 옵션:
  - (A) **[채택] `ANTHROPIC_API_KEY` 를 DPAPI 로 암호화 저장** → 래퍼가 실행 시 주입. 별도 API 과금.
  - (B) 관리자에게 Claude Code 구독 접근 허용 요청.
- **구현(A):** 평문 `setx`(레지스트리 노출) 대신, 리포의 기존 시크릿 패턴
  (`.docs_password.xml` 등)과 동일하게 DPAPI 암호화 파일을 쓴다.
  - [x] `scripts/setup_anthropic_api_key.ps1` — 키를 SecureString 으로 받아 `scripts/.anthropic_api_key.xml` 에 DPAPI 암호화 저장(현재 계정 전용). `'sk-ant-'` 형식 경고.
  - [x] `daily_claude_ask_todo.ps1` 에 `Import-AnthropicApiKey` 추가 — env 가 없으면 암호화 파일에서 복호화해 이 프로세스 한정으로 주입(`watch_sw_guide_scheduled.ps1` 의 토큰 로딩과 동일 Marshal/BSTR 패턴).
  - [x] `.gitignore` 에 `scripts/.anthropic_api_key.xml` 추가(커밋 금지).
- **남은 1회 작업(키 보유자):**
  - [ ] `.\scripts\setup_anthropic_api_key.ps1` 실행해 키 저장.
  - [ ] `.\scripts\daily_claude_ask_todo.ps1 -SkipBackup` 로 무인 인증 통과(exit 0) 확인.
  - [ ] 다음 17:30 자동 실행 결과 `0x0` 및 ASK 블록 누적 확인.
- 백업 스크립트(2단계)는 인증과 무관하게 정상.

## 2. [스케줄러] Windows 작업 등록 및 2시간 간격 재배치

**상세 내용:** `KIBA Claude ASK Todo Log` 작업을 같은 날짜 ASK 파일에 순차 누적되도록
매일 `09:30, 11:30, 13:30, 15:30, 17:30, 19:30, 21:30, 23:30`에 실행한다.
Codex 앱 자동화는 `09:00, 11:00, 13:00, 15:00, 17:00, 19:00, 21:00, 23:00`에 돈다.
기존 KIBA 작업의 실행 원칙(UserId=User, Interactive, Limited, StartWhenAvailable,
ExecutionTimeLimit 45분, MultipleInstances=IgnoreNew)은 그대로 유지한다.

**체크리스트:**

- [x] `KIBA Claude ASK Todo Log` 작업 등록 및 재배치 (`09:30`부터 2시간 간격, State=Ready).
- [x] Codex 정각 / Claude 30분 뒤 배치로 ASK append 충돌과 push 경쟁 방지.
- [ ] 첫 자동 실행 후 ASK/Todo에 Claude 블록이 정상 누적되는지 확인.

## 3. [후속] 커밋 필요

- [ ] `scripts/daily_claude_ask_todo.ps1`, `Todo/2026-06-22_claude_ask_todo_automation.md` 를 git 에 커밋.
      (백업 스크립트는 ASK/Todo 만 자동 커밋하므로 `scripts/` 변경은 수동 커밋 필요.)
