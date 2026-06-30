# 기획 하네스 (Planning Harness) 스펙

## 목적
상세기획 단계의 반복 수작업을 자동화하고, 녹음된 회의를 회의록으로 변환하여 기획 루프에 통합합니다.

**자동화 대상:**
- 요구사항 분해
- 시퀀스/플로우 시각화
- 예외·테스트 케이스 도출
- **Git Issue & Git Project 자동 생성** (JIRA 대신)
- **녹음 → 회의록 생성 → 이슈·프로젝트 동기화**

---

## 기획 하네스 4대 구성요소

### 1. **Context (컨텍스트)**
- `CLAUDE.md`: 서비스 핵심 정책·규격 고정
- `spec.md`: 진실의 원천 (단일 소스)
- AI가 상시 인지할 수 있는 배경 정보

### 2. **Tool Definition (도구 정의)**
- 7개 전용 스킬(슬래시 커맨드)
- 정해진 도구만 사용해 이탈 방지
- 각 도구는 명확한 입출력 규약 정의

### 3. **Guardrails (가드레일)**
- 위험·불확실한 작업은 사람이 확인 후 진행
- 자동 검증 전 사람의 승인 필요한 작업 명시
- 폴백(fallback) 프로세스 정의

### 4. **Verification (자동 검증)**
- 산출물이 `spec.md` 의도와 부합하는지 AI 자동 검수
- 회의록이 이슈·프로젝트와 일관성 있게 동기화되는지 확인

---

## 7개 전용 스킬 정의

### 스킬 명령어 체계

| 명령어 | 역할 | 출력 | 승인 필요 |
|--------|------|------|----------|
| `/search-documents` | 관련 정책·기존 문서 검색 | 근거 목록 (`docs-found.md`) | ✗ |
| `/split-requirements` | 기능을 세부 요구사항으로 분해 | `requirements.md` | ✓ (최종 승인) |
| `/sequence-diagram` | 백엔드 로직 → 시퀀스 다이어그램 | `sequence.mermaid` | ✗ |
| `/user-flow` | 사용자 플로우 시각화 | `user-flow.mermaid` | ✗ |
| `/logic-check` | 예외·테스트 케이스 도출 + spec 검증 | `logic-check.md` | ✓ (테스트 케이스 확정) |
| `/release-note` | 스펙 변경 요약 (Slack/공유용) | `release-note.md` | ✗ |
| `/git-project-sync` | **Git Issue & Project 자동 생성·동기화** | `git-sync.json` | ✓ (프로젝트 반영 전) |

---

## 🎙️ 녹음 → 회의록 → 이슈·프로젝트 통합 흐름

### 단계 1: 녹음 및 STT 변환
```
녹음 (클로바노트/Teams) 
→ `meetings/raw/YYYY-MM-DD_meeting.txt` (STT 텍스트)
→ `.gitignore` 제외 (PII/기밀)
```

### 단계 2: 회의록 자동 생성
```
python scripts/summarize_meeting.py 2026-06-30 --engine gemini
→ `meetings/summary/2026-06-30_meeting.md` (구조화된 회의록)
```

**회의록 구조:**
```markdown
## 참석자
- ...

## 주요 결정사항
- [ ] 결정 1
- [ ] 결정 2

## 할 일
- [ ] 내용 — @담당자 ~마감일 (이슈 #N)

## 기획 루프 액션 아이템
- 새 기능: ...
- 분해 필요: ...
- 시각화: ...
```

### 단계 3: Git Issue 자동 생성
```
python scripts/reflect_meeting.py 2026-06-30
→ 회의록의 "## 할 일" → GitHub Issues 생성
→ 담당자, 마감일, 레이블 자동 설정
```

**생성되는 이슈:**
- 기본 레이블: `todo`, `from-meeting`
- 담당자: `@담당자` 파싱
- 마감일: `~YYYY-MM-DD` 파싱
- 본문: 회의록 링크 포함

### 단계 4: Git Project 자동 동기화
```
python scripts/sync_git_project.py 2026-06-30
→ 생성된 Issues를 Git Project V2에 추가
→ 상태: "Todo" 열에 배치
→ 우선순위 설정 (회의 중요도 기반)
```

**프로젝트 구조:**
- **칼럼**: 상태별 (Todo, In Progress, Review, Done)
- **필드**: 우선순위, 담당자, 마감일, 기획 루프 단계
- **자동화**: 이슈 상태 변경 시 프로젝트 자동 업데이트

---

## 완료 기준 (Checklist)

### Phase 1: 기초 구축
- [ ] `planning-harness/CLAUDE.md` 규칙서 작성 (4대 구성요소 명시)
- [ ] `planning-harness/spec.md` 진실의 원천 템플릿
- [ ] `.claude/commands/` 디렉토리 생성 및 7종 스킬 정의 파일 작성
  - [ ] `search-documents.md`
  - [ ] `split-requirements.md`
  - [ ] `sequence-diagram.md`
  - [ ] `user-flow.md`
  - [ ] `logic-check.md`
  - [ ] `release-note.md`
  - [ ] `git-project-sync.md`

### Phase 2: 산출물 규약
- [ ] `planning-harness/outputs/` 디렉토리 구조 정의
- [ ] 산출물 파일명 규약 (예: `requirements.md`, `sequence.mermaid`)
- [ ] `planning-harness/README.md` 10분 구축·사용 가이드

### Phase 3: 회의록-이슈 연동
- [ ] `scripts/reflect_meeting.py` 업데이트 (Git Issue 자동 생성)
- [ ] `scripts/sync_git_project.py` 신규 작성 (Project V2 동기화)
- [ ] `meetings/TEMPLATE_meeting.md` 업데이트 (기획 루프 액션 섹션 추가)

### Phase 4: 포터블 구조 및 통합
- [ ] 폴더가 다른 프로젝트로 복사 가능한 자기완결(portable) 구조 확인
- [ ] `PLANNING_HARNESS_SETUP.md` (초기 설정 가이드) 작성
- [ ] 로컬 Todo 문서 연결 (`Todo/2026-06-30_planning_harness_loop_engineering.md`)

---

## 결과물 구조

```
planning-harness/
├── CLAUDE.md                    # AI 규칙서
├── spec.md                      # 진실의 원천
├── README.md                    # 10분 가이드
├── SETUP.md                     # 초기 설정
├── .claude/
│   └── commands/
│       ├── search-documents.md
│       ├── split-requirements.md
│       ├── sequence-diagram.md
│       ├── user-flow.md
│       ├── logic-check.md
│       ├── release-note.md
│       └── git-project-sync.md
├── outputs/                     # 산출물 저장소
│   ├── requirements.md
│   ├── sequence.mermaid
│   ├── user-flow.mermaid
│   ├── logic-check.md
│   ├── release-note.md
│   └── git-sync.json
└── templates/
    └── harness-template.md

scripts/
├── summarize_meeting.py         # STT → 회의록 요약
├── reflect_meeting.py           # 회의록 → Git Issues (업데이트됨)
├── sync_git_project.py          # Issues → Git Project V2 (신규)
└── ...
```

---

## Git Project V2 설정

### 프로젝트 이름
`기획 루프 - 상세기획 자동화`

### 칼럼 구조
1. **Backlog** — 큐에 대기 중
2. **Todo** — 이번 스프린트 작업
3. **In Progress** — 진행 중
4. **Review** — 검증 대기
5. **Done** — 완료

### 커스텀 필드
- **Priority**: 긴급/높음/중간/낮음
- **Planning Stage**: 분석/설계/개발/테스트/배포
- **Meeting Link**: 어느 회의에서 나왔는지 추적

---

## 자동화 규칙 (Automation)

### Issue 자동 생성 (from meeting)
```
IF 회의록에 "할 일" 섹션 존재
THEN
  - GitHub Issue 생성
  - 레이블: `from-meeting`, `todo`
  - 담당자/마감일 자동 설정
  - Git Project에 추가
  - 기본 상태: "Todo"
```

### Project 상태 동기화
```
IF Issue 상태 변경
THEN Git Project의 해당 카드도 자동 업데이트
```

### 중복 방지
```
IF 같은 내용의 Issue가 이미 존재
THEN 기존 Issue에 코멘트 추가 (회의 링크 포함)
     새 Issue 미생성
```

---

## Loop Type
`automation` — 자동화 루프

## 공개 상태
`private` — 비공개

---

## 다음 단계 (Next Actions)

1. **Phase 1 착수**: `CLAUDE.md` 규칙서 작성
2. **스킬 정의**: `.claude/commands/` 7개 파일 작성
3. **Python 스크립트 업데이트**: `reflect_meeting.py`, `sync_git_project.py`
4. **Git Project 생성**: 기획 루프 전용 프로젝트 설정
5. **테스트**: 회의록 생성 → Issue → Project 자동화 엔드-투-엔드 테스트

---

## 참고
- 회의록 운영: `meetings/README.md`
- 기본 STT 도구: 클로바노트 (Teams transcript 후속 옵션)
- 회의록 보존: `meetings/raw/` (git 제외), `meetings/summary/` (git 추적)
