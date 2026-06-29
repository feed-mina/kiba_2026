#!/usr/bin/env python3
"""
summarize_meeting.py  (이슈 #5 - STT→요약 파이프라인 골격)

meetings/raw/<날짜>_meeting.txt (STT 원문) 을 읽어
meetings/summary/<날짜>_meeting.md (요약본) 를 TEMPLATE_meeting.md 골격으로 만든다.

사용:
  python scripts/summarize_meeting.py 2026-06-18
  python scripts/summarize_meeting.py 2026-06-18 --force      # 기존 요약본 덮어쓰기
  python scripts/summarize_meeting.py path/to/raw.txt         # 임의 경로 원문

기본(engine="none")은 템플릿 골격 + 원문 발췌만 채워 사람이 직접 요약하도록 한다.
engine="gemini"는 요약·결정·할 일과 25개 판단 기준 검증을 JSON으로 생성한다.
표준 라이브러리만 사용한다.
"""

import re
import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from datetime import date as _date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    """REPO_ROOT/.env 가 있으면 환경변수로 로드(이미 설정된 값은 보존)."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
MEET_DIR = REPO_ROOT / "meetings"
RAW_DIR = MEET_DIR / "raw"
SUMMARY_DIR = MEET_DIR / "summary"
TEMPLATE = MEET_DIR / "TEMPLATE_meeting.md"
DECISION_CRITERIA = REPO_ROOT / "Knowledge" / "Meetings" / "meeting_decision_criteria.md"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def resolve_raw(arg: str) -> Path:
    """날짜(YYYY-MM-DD) 또는 파일 경로를 받아 원문 파일 경로로 해석."""
    if DATE_RE.match(arg):
        return RAW_DIR / f"{arg}_meeting.txt"
    return Path(arg)


def date_of(raw: Path) -> str:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw.name)
    return m.group(1) if m else _date.today().isoformat()


def _summarize_gemini(raw_text: str):
    """Google AI Studio(Gemini)로 STT 원문 → {summary, decisions, todos}."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        sys.exit("[summarize] GEMINI_API_KEY 가 필요합니다 (.env 또는 셸).")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
    criteria_text = DECISION_CRITERIA.read_text(encoding="utf-8-sig") if DECISION_CRITERIA.exists() else ""
    prompt = (
        f"오늘은 {_date.today().isoformat()} 이다. 상대 날짜(예: '6월 30일')는 이 연도 기준으로 해석하라.\n"
        "다음은 KIBA 일일 회의의 STT 원문입니다. 원장님 보고용 회의록으로 정리하세요.\n"
        "원문에 실제로 나온 내용만 쓰고 추측·창작은 금지합니다. 반드시 JSON 만 출력하세요.\n"
        '형식: {"summary": ["..."], "decisions": ["..."], '
        '"criteria_checks": [{"id":"RSK-02","result":"통과|조건부|보류|해당 없음",'
        '"evidence":"원문의 근거","action":"보완 조치"}], '
        '"todos": ["[ ] 내용 — @담당자 ~YYYY-MM-DD (이슈 #N)"]}\n'
        "- summary: 핵심 3~5개. decisions: 확정된 결정.\n"
        "- todos: 원문에서 '누가 무엇을 언제까지' 형태의 할 일/액션아이템을 모두 추출. "
        "담당자는 @이름, 기한은 ~YYYY-MM-DD, 관련 이슈번호가 있으면 (이슈 #N). 모르면 생략하되 형식은 유지.\n"
        "- criteria_checks: 아래 판단 기준 중 이번 결정과 관련된 것만 평가. 근거 없는 판정은 금지.\n"
        "- 해당 항목이 없으면 빈 배열.\n\n판단 기준:\n" + criteria_text + "\n\n원문:\n" + raw_text
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"[summarize] Gemini 오류 {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        sys.exit(f"[summarize] Gemini 응답 파싱 실패: {json.dumps(data, ensure_ascii=False)[:300]}")
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        sys.exit(f"[summarize] Gemini JSON 파싱 실패: {text[:300]}")
    return {
        "summary": [str(x) for x in out.get("summary", [])],
        "decisions": [str(x) for x in out.get("decisions", [])],
        "criteria_checks": [x for x in out.get("criteria_checks", []) if isinstance(x, dict)],
        "todos": [str(x) for x in out.get("todos", [])],
    }


def summarize(raw_text: str, engine: str = "none"):
    """
    요약 엔진 연동 지점.
    반환: {"summary": [..], "decisions": [..], "todos": [..]} 또는 None.
    None 이면 호출부가 템플릿 골격(빈 자리표시)을 그대로 둔다.

    engine="none"   : 골격만(자동 요약 없음) - 기본값.
    engine="gemini" : Google AI Studio(Gemini)로 자동 요약.
    """
    if engine == "none":
        return None
    if engine == "gemini":
        return _summarize_gemini(raw_text)
    raise NotImplementedError(f"요약 엔진 '{engine}' 미지원. (지원: none, gemini)")


def fill_template(tmpl: str, d: str, raw: Path, sections) -> str:
    rel_raw = raw.relative_to(REPO_ROOT).as_posix() if raw.is_relative_to(REPO_ROOT) else raw.as_posix()
    out = tmpl.replace("YYYY-MM-DD", d)
    out = out.replace("meetings/raw/YYYY-MM-DD_meeting.txt", rel_raw)
    if sections:
        def block(lines):
            return "\n".join(f"- {x}" for x in lines) if lines else "- "
        out = re.sub(r"(## 요약\n).*?(\n\n## )",
                     lambda m: m.group(1) + block(sections.get("summary", [])) + m.group(2),
                     out, count=1, flags=re.DOTALL)
        out = re.sub(r"(## 결정 사항\n).*?(\n\n## )",
                     lambda m: m.group(1) + block(sections.get("decisions", [])) + m.group(2),
                     out, count=1, flags=re.DOTALL)
        criteria_checks = sections.get("criteria_checks", [])
        if criteria_checks:
            rows = ["| 기준 ID | 판정 | 근거 | 보완 조치 |", "| --- | --- | --- | --- |"]
            for item in criteria_checks:
                values = [
                    str(item.get("id", "")).strip(),
                    str(item.get("result", "")).strip(),
                    str(item.get("evidence", "")).strip(),
                    str(item.get("action", "")).strip(),
                ]
                rows.append("| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in values) + " |")
            out = re.sub(
                r"(## 판단 기준 검증\n).*?(\n\n## )",
                lambda m: m.group(1) + "\n".join(rows) + m.group(2),
                out,
                count=1,
                flags=re.DOTALL,
            )
        todos = sections.get("todos", [])
        if todos:
            # 템플릿의 '## 할 일' 자리표시 줄(YYYY-MM-DD 가 이미 날짜로 치환됨)을 정규식으로 교체
            out = re.sub(r"^- \[ \] \(할 일\) —.*$",
                         "\n".join(f"- {t}" for t in todos),
                         out, count=1, flags=re.MULTILINE)
    return out


def main():
    load_env()
    ap = argparse.ArgumentParser(description="STT 원문 → 회의록 요약본 생성")
    ap.add_argument("target", help="YYYY-MM-DD 또는 원문 txt 경로")
    ap.add_argument("--engine", default="none", help="요약 엔진(none|gemini). 기본 none(골격만)")
    ap.add_argument("--force", action="store_true", help="기존 요약본 덮어쓰기")
    args = ap.parse_args()

    raw = resolve_raw(args.target)
    if not raw.exists():
        print(f"원문이 없습니다: {raw}\n  meetings/raw/ 에 <날짜>_meeting.txt 로 STT 결과를 저장하세요.",
              file=sys.stderr)
        sys.exit(2)
    if not TEMPLATE.exists():
        print(f"템플릿이 없습니다: {TEMPLATE}", file=sys.stderr)
        sys.exit(2)

    d = date_of(raw)
    out_path = SUMMARY_DIR / f"{d}_meeting.md"
    if out_path.exists() and not args.force:
        print(f"이미 존재합니다(덮어쓰려면 --force): {out_path}", file=sys.stderr)
        sys.exit(1)

    raw_text = raw.read_text(encoding="utf-8-sig")
    sections = summarize(raw_text, engine=args.engine)
    body = fill_template(TEMPLATE.read_text(encoding="utf-8-sig"), d, raw, sections)

    if sections is None:
        # 골격 모드: 사람이 요약하도록 원문 발췌를 접이식으로 덧붙인다.
        excerpt = raw_text.strip()
        if len(excerpt) > 4000:
            excerpt = excerpt[:4000] + "\n... (원문 일부, 전체는 raw 파일 참고)"
        body += (
            "\n\n---\n\n"
            "<details><summary>원문 발췌 (요약 작성용 — 정리 후 삭제 가능)</summary>\n\n"
            "```\n" + excerpt + "\n```\n</details>\n"
        )

    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")
    print(f"생성: {out_path.relative_to(REPO_ROOT).as_posix()}"
          + ("  (골격 모드 - 요약/결정/할 일을 채우세요)" if sections is None else ""))


if __name__ == "__main__":
    main()
