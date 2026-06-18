#!/usr/bin/env python3
"""
reflect_meeting.py  (이슈 #5 - 회의록 → Todo/GitHub Issue 반영 골격)

meetings/summary/<날짜>_meeting.md 의 "## 할 일" 체크리스트를 파싱해
  1) --to-todo   : Todo/<날짜>_meeting_actions.md 를 생성/갱신 (reflect_todo.py 가 보드/이슈로 반영)
  2) --to-issues : 항목에 (이슈 #N) 이 있으면 해당 이슈에 멱등 코멘트로 적재

사용:
  python scripts/reflect_meeting.py 2026-06-18                 # dry-run (파싱 결과만 출력)
  python scripts/reflect_meeting.py 2026-06-18 --to-todo
  python scripts/reflect_meeting.py 2026-06-18 --to-issues     # GITHUB_TOKEN/GITHUB_REPOSITORY 필요

할 일 항목 형식:
  - [ ] 내용 — @담당자 ~2026-06-20 (이슈 #5)
  (@담당자, ~기한, (이슈 #N) 은 모두 선택)

표준 라이브러리만 사용한다. GitHub 호출 패턴은 reflect_todo.py 와 동일.
"""

import os
import re
import sys
import json
import argparse
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SUMMARY_DIR = REPO_ROOT / "meetings" / "summary"
TODO_DIR = REPO_ROOT / "Todo"

API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# - [ ] 내용 — @담당자 ~2026-06-20 (이슈 #5)
ITEM_RE = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+(.+?)\s*$")


def api(method, path, payload=None):
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "kiba-meeting-reflect")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return e.code, (json.loads(body) if body else None)


def resolve_summary(arg: str) -> Path:
    if DATE_RE.match(arg):
        return SUMMARY_DIR / f"{arg}_meeting.md"
    return Path(arg)


def parse_actions(text: str):
    """'## 할 일' 섹션의 체크리스트만 파싱."""
    m = re.search(r"^##\s+할 일\s*$(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        return []
    items = []
    for line in m.group(1).splitlines():
        im = ITEM_RE.match(line)
        if not im:
            continue
        raw = im.group(1)
        # 템플릿 자리표시 줄만 건너뜀(실제 담당자명이 '담당자'로 시작해도 안전하게)
        if raw.startswith("<!--") or "(할 일)" in raw or "(이슈 #N)" in raw:
            continue
        owner = (re.search(r"@(\S+)", raw) or [None, None])[1]
        due = (re.search(r"~(\d{4}-\d{2}-\d{2})", raw) or [None, None])[1]
        issue = (re.search(r"\(이슈\s*#(\d+)\)", raw) or [None, None])[1]
        # 메타데이터 토큰을 제거한 순수 내용
        content = re.sub(r"\s*[—-]\s*@\S+", "", raw)
        content = re.sub(r"\s*~\d{4}-\d{2}-\d{2}", "", content)
        content = re.sub(r"\s*\(이슈\s*#\d+\)", "", content).strip(" —-")
        items.append({"content": content, "owner": owner, "due": due,
                      "issue": int(issue) if issue else None})
    return items


def write_todo(date: str, items):
    out = TODO_DIR / f"{date}_meeting_actions.md"
    lines = [f"# {date} 회의 후속 할 일", "",
             f"> [meetings/summary/{date}_meeting.md](../meetings/summary/{date}_meeting.md) 에서 자동 추출. "
             "회의에서 정한 할 일을 추적합니다.", "", "## 후속 작업", "", "**체크리스트:**"]
    for it in items:
        meta = []
        if it["owner"]: meta.append(f"@{it['owner']}")
        if it["due"]: meta.append(f"~{it['due']}")
        if it["issue"]: meta.append(f"(이슈 #{it['issue']})")
        suffix = (" — " + " ".join(meta)) if meta else ""
        lines.append(f"- [ ] {it['content']}{suffix}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"작성: {out.relative_to(REPO_ROOT).as_posix()}  ({len(items)}개 항목)")


def post_issue_comments(date: str, items):
    if not (TOKEN and REPO):
        print("GITHUB_TOKEN/GITHUB_REPOSITORY 미설정 — --to-issues 불가", file=sys.stderr)
        sys.exit(2)
    by_issue = {}
    for it in items:
        if it["issue"]:
            by_issue.setdefault(it["issue"], []).append(it)
    if not by_issue:
        print("(이슈 #N) 표시가 있는 항목이 없어 코멘트할 대상이 없습니다.")
        return
    marker = f"<!-- meeting-actions: {date} -->"
    for num, its in by_issue.items():
        bullets = []
        for it in its:
            meta = []
            if it["owner"]: meta.append(f"담당 @{it['owner']}")
            if it["due"]: meta.append(f"기한 {it['due']}")
            tail = (" — " + ", ".join(meta)) if meta else ""
            bullets.append(f"- [ ] {it['content']}{tail}")
        body = (f"{marker}\n### {date} 회의 후속 할 일\n" + "\n".join(bullets) +
                f"\n\n_출처: meetings/summary/{date}_meeting.md_")
        # 같은 날짜 마커의 기존 코멘트가 있으면 갱신(멱등)
        st, comments = api("GET", f"/repos/{REPO}/issues/{num}/comments?per_page=100")
        existing = None
        if st == 200 and comments:
            existing = next((c for c in comments if marker in (c.get("body") or "")), None)
        if existing:
            api("PATCH", f"/repos/{REPO}/issues/comments/{existing['id']}", {"body": body})
            print(f"이슈 #{num} 코멘트 갱신({len(its)}개 항목)")
        else:
            st2, _ = api("POST", f"/repos/{REPO}/issues/{num}/comments", {"body": body})
            print(f"이슈 #{num} 코멘트 {'생성' if st2 in (200,201) else '실패('+str(st2)+')'}({len(its)}개 항목)")


def main():
    ap = argparse.ArgumentParser(description="회의록 할 일 → Todo/GitHub Issue 반영")
    ap.add_argument("target", help="YYYY-MM-DD 또는 요약본 md 경로")
    ap.add_argument("--to-todo", action="store_true", help="Todo/<날짜>_meeting_actions.md 생성")
    ap.add_argument("--to-issues", action="store_true", help="(이슈 #N) 항목을 해당 이슈에 코멘트")
    args = ap.parse_args()

    path = resolve_summary(args.target)
    if not path.exists():
        print(f"요약본이 없습니다: {path}", file=sys.stderr)
        sys.exit(2)
    m = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
    date = m.group(1) if m else "unknown"

    items = parse_actions(path.read_text(encoding="utf-8-sig"))
    if not items:
        print("'## 할 일' 섹션에서 추출할 항목이 없습니다(템플릿 자리표시 제외).")
        return

    print(f"추출된 할 일 {len(items)}개:")
    for it in items:
        print(f"  - {it['content']}"
              + (f"  @{it['owner']}" if it['owner'] else "")
              + (f"  ~{it['due']}" if it['due'] else "")
              + (f"  (#{it['issue']})" if it['issue'] else ""))

    if args.to_todo:
        write_todo(date, items)
    if args.to_issues:
        post_issue_comments(date, items)
    if not (args.to_todo or args.to_issues):
        print("\n(dry-run) --to-todo / --to-issues 로 실제 반영하세요.")


if __name__ == "__main__":
    main()
