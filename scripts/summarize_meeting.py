#!/usr/bin/env python3
"""
summarize_meeting.py  (이슈 #5 - STT→요약 파이프라인 골격)

meetings/raw/<날짜>_meeting.txt (STT 원문) 을 읽어
meetings/summary/<날짜>_meeting.md (요약본) 를 TEMPLATE_meeting.md 골격으로 만든다.

사용:
  python scripts/summarize_meeting.py 2026-06-18
  python scripts/summarize_meeting.py 2026-06-18 --force      # 기존 요약본 덮어쓰기
  python scripts/summarize_meeting.py path/to/raw.txt         # 임의 경로 원문

요약 엔진은 아직 미연동(골격)이다. 기본(engine="none")은 템플릿 골격 + 원문 발췌만
채워 사람이 직접 요약하도록 한다. 추후 Claude/기타 요약 엔진은 summarize() 에 붙인다.
표준 라이브러리만 사용한다.
"""

import re
import sys
import argparse
from datetime import date as _date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MEET_DIR = REPO_ROOT / "meetings"
RAW_DIR = MEET_DIR / "raw"
SUMMARY_DIR = MEET_DIR / "summary"
TEMPLATE = MEET_DIR / "TEMPLATE_meeting.md"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def resolve_raw(arg: str) -> Path:
    """날짜(YYYY-MM-DD) 또는 파일 경로를 받아 원문 파일 경로로 해석."""
    if DATE_RE.match(arg):
        return RAW_DIR / f"{arg}_meeting.txt"
    return Path(arg)


def date_of(raw: Path) -> str:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw.name)
    return m.group(1) if m else _date.today().isoformat()


def summarize(raw_text: str, engine: str = "none"):
    """
    요약 엔진 연동 지점.
    반환: {"summary": [..], "decisions": [..], "todos": [..]} 또는 None.
    None 이면 호출부가 템플릿 골격(빈 자리표시)을 그대로 둔다.

    engine="none"  : 골격만(자동 요약 없음) - 현재 기본값.
    engine="claude": (미구현) 추후 Claude API/CLI 로 raw_text 를 요약.
    """
    if engine == "none":
        return None
    raise NotImplementedError(
        f"요약 엔진 '{engine}' 은 아직 연동되지 않았습니다. "
        "도구 선택(Teams/클로바/Claude) 확정 후 summarize() 에 구현하세요."
    )


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
    return out


def main():
    ap = argparse.ArgumentParser(description="STT 원문 → 회의록 요약본 골격 생성")
    ap.add_argument("target", help="YYYY-MM-DD 또는 원문 txt 경로")
    ap.add_argument("--engine", default="none", help="요약 엔진(none|claude...). 기본 none(골격만)")
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
