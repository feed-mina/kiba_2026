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
이때 기존 index.html 의 이슈 번호/저장소 링크를 보존한다.
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from html import escape, unescape

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


def attr_value(tag: str, name: str):
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    return unescape(m.group(1)) if m else None


def repo_from_index():
    """HTML-only 실행 때 data-repo/link 가 비지 않도록 기존 설정을 재사용한다."""
    if not INDEX_HTML.exists():
        return ""
    html = INDEX_HTML.read_text(encoding="utf-8")
    m = re.search(r'defaultRepo:\s*"([^"]+)"', html)
    if m:
        return m.group(1).strip()
    m = re.search(r'data-repo="([^"]+)"', html)
    return m.group(1).strip() if m else ""


def issue_map_from_index(items):
    """기존 자동 보드에서 Todo 파일 -> GitHub Issue 번호 매핑을 복구한다.

    GitHub 토큰 없이 --html-only 로 실행하면 API에서 이슈 번호를 조회할 수 없다.
    대신 기존 index.html 의 자동 보드 카드에 남아 있는 data-todo-rel 또는 data-title
    정보를 사용해 data-issue/link 를 보존한다.
    """
    if not INDEX_HTML.exists():
        return {}
    html = INDEX_HTML.read_text(encoding="utf-8")
    by_title = {it["title"]: it["rel"] for it in items}
    result = {}
    for m in re.finditer(r'<article\b(?=[^>]*\bdata-source="todo")[^>]*>', html):
        tag = m.group(0)
        issue = attr_value(tag, "data-issue")
        if not issue or not issue.isdigit():
            continue
        rel = attr_value(tag, "data-todo-rel")
        title = attr_value(tag, "data-title")
        if not rel and title:
            rel = by_title.get(title)
        if rel:
            result[rel] = int(issue)
    return result


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
    # 다른 이슈로 통합(병합)된 파일은 보드/이슈 동기화에서 제외한다.
    #   파일 상단에 <!-- merged-into: #13 --> 마커를 넣으면 자동으로 숨김.
    mg = re.search(r"<!--\s*merged-into:\s*#?(\d+)\s*-->", text)
    merged_into = mg.group(1) if mg else None
    return {
        "path": path, "rel": rel, "title": title, "date": date,
        "done": done, "total": total, "sections": sections, "text": text,
        "merged_into": merged_into,
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
def is_done(it):
    """체크리스트가 있고 전부 체크되면 완료(끝난 일)로 본다."""
    return it["total"] > 0 and it["done"] >= it["total"]


def is_not_started(it):
    """체크리스트가 있으나 아무것도 완료 안 됨 = '다음에 할 일'.
    일일 Todo 보드(자동)에서는 제외하고 GitHub Issue로만 추적한다."""
    return it["total"] > 0 and it["done"] == 0


def render_card(it, issue_map):
    num = issue_map.get(it["rel"])
    if num and REPO:
        link = f'<a href="https://github.com/{REPO}/issues/{num}">Issue #{num} 보기</a>'
    else:
        link = ""
    prog = f'{it["done"]}/{it["total"]} 완료' if it["total"] else "체크리스트 없음"
    secs = "".join(f"<li>{escape(s)}</li>" for s in it["sections"][:6])
    issue_attr = f' data-issue="{num}"' if num else ""
    status_attr = ' data-status="done"' if is_done(it) else ' data-status="active"'
    return (
        f'<article class="card task-card" data-source="todo" data-repo="{escape(REPO)}"'
        f' data-todo-rel="{escape(it["rel"])}"{issue_attr}{status_attr}'
        f' data-progress-done="{it["done"]}" data-progress-total="{it["total"]}"'
        f' data-title="{escape(it["title"])}">'
        f'<div class="card-head"><h4>{escape(it["title"])}</h4></div>'
        f'<p class="note">{escape(it["date"])} · {escape(prog)}</p>'
        f'<ul class="todo-auto-list">{secs}</ul>'
        f'<div class="tagline">{link}</div>'
        '</article>'
    )


def build_html(items, issue_map):
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    ordered = sorted(items, key=lambda x: x["rel"], reverse=True)
    # 일일 Todo 보드는 완료되지 않은 작업을 모두 보여준다.
    # 끝난 일(is_done)만 접이식 아코디언으로 분리(기본 숨김)한다.
    active = [it for it in ordered if not is_done(it)]
    done = [it for it in ordered if is_done(it)]

    active_cards = [render_card(it, issue_map) for it in active]
    if not active_cards:
        active_cards.append('<p class="note">열린 Todo가 없습니다.</p>')

    inner = (
        '\n      <section class="panel" aria-labelledby="todo-auto-title">\n'
        '        <h2 class="panel-title" id="todo-auto-title">일일 Todo 기록 (자동)</h2>\n'
        f'        <p class="panel-copy">`Todo/` 폴더의 열린 작업을 표시합니다. '
        f'완료된 작업은 접어서 보관합니다. 마지막 갱신: {now}</p>\n'
        '        <div class="board" style="grid-template-columns:repeat(auto-fill,minmax(260px,1fr))">\n'
        '          ' + "\n          ".join(active_cards) + '\n'
        '        </div>\n'
    )

    # 완료된 항목은 활성 보드에서 빼고 "끝난 일" 아코디언으로 접어 둔다.
    if done:
        done_cards = [render_card(it, issue_map) for it in done]
        inner += (
            '        <details class="fold" style="margin-top:18px">\n'
            f'          <summary>✅ 끝난 일 ({len(done)})</summary>\n'
            '          <div class="fold-body">\n'
            '            <div class="board" style="grid-template-columns:repeat(auto-fill,minmax(260px,1fr))">\n'
            '              ' + "\n              ".join(done_cards) + '\n'
            '            </div>\n'
            '          </div>\n'
            '        </details>\n'
        )

    inner += '      </section>\n      '
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
    global REPO
    html_only = "--html-only" in sys.argv
    all_items = [parse_todo(p) for p in sorted(TODO_DIR.glob("*.md"))]
    # merged-into 마커가 있는 통합 파일은 보드·이슈 동기화에서 제외(자동 숨김)
    items = [it for it in all_items if not it["merged_into"]]
    merged = [it for it in all_items if it["merged_into"]]
    print(f"found {len(all_items)} Todo file(s); 활성 {len(items)}, 통합 제외 {len(merged)}")
    for it in merged:
        print(f"  merged → #{it['merged_into']} (제외): {it['rel']}")

    issue_map = {}
    if not html_only:
        if not (TOKEN and REPO):
            print("GITHUB_TOKEN/GITHUB_REPOSITORY not set; run with --html-only "
                  "for HTML-only, or provide env.", file=sys.stderr)
            sys.exit(2)
        issue_map = upsert_issues(items)
    else:
        if not REPO:
            REPO = repo_from_index()
        issue_map = issue_map_from_index(items)
        print(f"html-only: preserved {len(issue_map)} issue link(s) from index.html")

    update_index(items, issue_map)


if __name__ == "__main__":
    main()
