#!/usr/bin/env python3
"""
reflect_todo.py
Todo/*.md 를 읽어 두 가지를 반영한다.
  1) 파일당 GitHub Issue 를 멱등(idempotent) 생성/갱신
     - 라벨 'todo'
     - 본문에 숨은 마커 <!-- todo-file: <상대경로> --> 로 같은 파일의 이슈를 식별
       => 매번 새 이슈를 만들지 않고 기존 이슈를 갱신
  2) index.html 의 <!-- TODO-AUTO:START --> ~ <!-- TODO-AUTO:END --> 블록을
     현재 Todo 목록으로 재생성 (수작업 보드는 건드리지 않음)

환경변수(GitHub Actions 에서 자동 주입):
  GITHUB_TOKEN       - 이슈 생성/수정 + 라벨용 토큰
  GITHUB_REPOSITORY  - "owner/repo"
  GITHUB_API_URL     - 기본 https://api.github.com (선택)
로컬에서 HTML 갱신만 테스트하려면 토큰 없이 --html-only 로 실행.
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from html import escape

REPO_ROOT = Path(__file__).resolve().parent.parent
TODO_DIR = REPO_ROOT / "Todo"
INDEX_HTML = REPO_ROOT / "index.html"
LABEL = "todo"
LABEL_COLOR = "d97706"
MARK_START = "<!-- TODO-AUTO:START -->"
MARK_END = "<!-- TODO-AUTO:END -->"

API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "")


# --------------------------------------------------------------------------- #
# GitHub REST helpers (stdlib only)
# --------------------------------------------------------------------------- #
def api(method, path, payload=None):
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "kiba-todo-reflect")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body else None), r.headers
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return e.code, (json.loads(body) if body else None), e.headers


def ensure_label():
    status, _, _ = api("GET", f"/repos/{REPO}/labels/{LABEL}")
    if status == 404:
        api("POST", f"/repos/{REPO}/labels",
            {"name": LABEL, "color": LABEL_COLOR,
             "description": "Todo/*.md 에서 자동 생성된 항목"})


def list_todo_issues():
    """라벨 todo 가 붙은 모든 이슈(열림/닫힘)를 마커->이슈 로 매핑."""
    by_marker = {}
    page = 1
    while True:
        status, items, _ = api(
            "GET",
            f"/repos/{REPO}/issues?labels={LABEL}&state=all&per_page=100&page={page}",
        )
        if status != 200 or not items:
            break
        for it in items:
            if "pull_request" in it:  # /issues 는 PR 도 포함 -> 제외
                continue
            body = it.get("body") or ""
            m = re.search(r"<!--\s*todo-file:\s*(.+?)\s*-->", body)
            if m:
                by_marker[m.group(1).strip()] = it
        if len(items) < 100:
            break
        page += 1
    return by_marker


# --------------------------------------------------------------------------- #
# Todo parsing
# --------------------------------------------------------------------------- #
def parse_todo(path: Path):
    text = path.read_text(encoding="utf-8-sig")  # BOM 제거
    rel = path.relative_to(REPO_ROOT).as_posix()
    # 제목: 첫 H1, 없으면 파일명
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = m.group(1).strip() if m else path.stem
    # 날짜: 파일명 앞 YYYY-MM-DD
    dm = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
    date = dm.group(1) if dm else ""
    # 체크리스트 진행도
    done = len(re.findall(r"^\s*[-*]\s+\[[xX]\]", text, re.MULTILINE))
    open_ = len(re.findall(r"^\s*[-*]\s+\[ \]", text, re.MULTILINE))
    total = done + open_
    # 항목 제목들 (## N. ...)
    sections = re.findall(r"^##\s+(.+)$", text, re.MULTILINE)
    return {
        "path": path, "rel": rel, "title": title, "date": date,
        "done": done, "total": total, "sections": sections, "text": text,
    }


def issue_body(item):
    marker = f"<!-- todo-file: {item['rel']} -->"
    note = (f"> 이 이슈는 `{item['rel']}` 에서 자동 생성/갱신됩니다. "
            f"직접 편집하면 다음 동기화 때 덮어써질 수 있습니다.\n\n")
    return f"{marker}\n{note}{item['text']}"


# --------------------------------------------------------------------------- #
# Issue upsert
# --------------------------------------------------------------------------- #
def upsert_issues(items):
    ensure_label()
    existing = list_todo_issues()
    result = {}  # rel -> issue number
    for it in items:
        body = issue_body(it)
        cur = existing.get(it["rel"])
        if cur:
            num = cur["number"]
            need = (cur.get("title") != it["title"]) or ((cur.get("body") or "") != body)
            if need:
                api("PATCH", f"/repos/{REPO}/issues/{num}",
                    {"title": it["title"], "body": body})
                print(f"updated issue #{num}  <- {it['rel']}")
            else:
                print(f"unchanged issue #{num}  <- {it['rel']}")
            result[it["rel"]] = num
        else:
            status, data, _ = api("POST", f"/repos/{REPO}/issues",
                                   {"title": it["title"], "body": body,
                                    "labels": [LABEL]})
            if status in (200, 201) and data:
                result[it["rel"]] = data["number"]
                print(f"created issue #{data['number']}  <- {it['rel']}")
            else:
                print(f"FAILED to create issue for {it['rel']}: {status} {data}",
                      file=sys.stderr)
    return result


# --------------------------------------------------------------------------- #
# index.html block
# --------------------------------------------------------------------------- #
def build_html(items, issue_map):
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    cards = []
    for it in sorted(items, key=lambda x: x["rel"], reverse=True):
        num = issue_map.get(it["rel"])
        if num and REPO:
            link = f'<a href="https://github.com/{REPO}/issues/{num}">Issue #{num} 보기</a>'
        else:
            link = ""
        prog = f'{it["done"]}/{it["total"]} 완료' if it["total"] else "체크리스트 없음"
        secs = "".join(f"<li>{escape(s)}</li>" for s in it["sections"][:6])
        issue_attr = f' data-issue="{num}"' if num else ""
        cards.append(
            f'<article class="card task-card" data-source="todo" data-repo="{escape(REPO)}"{issue_attr} data-title="{escape(it["title"])}">'
            f'<div class="card-head"><h4>{escape(it["title"])}</h4></div>'
            f'<p class="note">{escape(it["date"])} · {escape(prog)}</p>'
            f'<ul class="todo-auto-list">{secs}</ul>'
            f'<div class="tagline">{link}</div>'
            '</article>'
        )
    if not cards:
        cards.append('<p class="note">등록된 Todo 파일이 없습니다.</p>')
    inner = (
        '\n      <section class="panel" aria-labelledby="todo-auto-title">\n'
        '        <h2 class="panel-title" id="todo-auto-title">일일 Todo 기록 (자동)</h2>\n'
        f'        <p class="panel-copy">`Todo/` 폴더의 기록을 자동으로 반영합니다. '
        f'마지막 갱신: {now}</p>\n'
        '        <div class="board" style="grid-template-columns:repeat(auto-fill,minmax(260px,1fr))">\n'
        '          ' + "\n          ".join(cards) + '\n'
        '        </div>\n'
        '      </section>\n      '
    )
    return inner


def update_index(items, issue_map):
    if not INDEX_HTML.exists():
        print("index.html not found; skip HTML", file=sys.stderr)
        return False
    html = INDEX_HTML.read_text(encoding="utf-8")
    if MARK_START not in html or MARK_END not in html:
        print("TODO-AUTO markers not found in index.html; skip HTML", file=sys.stderr)
        return False
    inner = build_html(items, issue_map)
    new = re.sub(
        re.escape(MARK_START) + r".*?" + re.escape(MARK_END),
        MARK_START + inner + MARK_END,
        html, flags=re.DOTALL,
    )
    if new != html:
        INDEX_HTML.write_text(new, encoding="utf-8")
        print("index.html updated")
        return True
    print("index.html unchanged")
    return False


# --------------------------------------------------------------------------- #
def main():
    html_only = "--html-only" in sys.argv
    items = [parse_todo(p) for p in sorted(TODO_DIR.glob("*.md"))]
    print(f"found {len(items)} Todo file(s)")

    issue_map = {}
    if not html_only:
        if not (TOKEN and REPO):
            print("GITHUB_TOKEN/GITHUB_REPOSITORY not set; run with --html-only "
                  "for HTML-only, or provide env.", file=sys.stderr)
            sys.exit(2)
        issue_map = upsert_issues(items)

    update_index(items, issue_map)


if __name__ == "__main__":
    main()
