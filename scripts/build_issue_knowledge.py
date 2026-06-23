from __future__ import annotations

import os
import re
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parents[1]
TODO_DIR = REPO_ROOT / "Todo"
ASK_DIR = REPO_ROOT / "ASK"
DOCS_DIR = REPO_ROOT / "docs"
OUT_ISSUES = REPO_ROOT / "Knowledge" / "Issues"
OUT_DASH = REPO_ROOT / "Knowledge" / "Dashboards"
OUT_SOURCES = REPO_ROOT / "Knowledge" / "Sources"
REPO = "feed-mina/kiba_2026"
API_BASE = "https://kiba.kibayerin.workers.dev"
INDEX_HTML = REPO_ROOT / "index.html"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def obsidian_link(path: Path, label: str | None = None, heading: str | None = None) -> str:
    rel = path.relative_to(REPO_ROOT).as_posix()
    target = rel[:-3] if rel.endswith(".md") else rel
    if heading:
        target += f"#{heading}"
    return f"[[{target}|{label or heading or path.stem}]]"


def md_link(label: str, url: str) -> str:
    return f"[{label}]({url})"


def file_link(path: Path, label: str | None = None, from_dir: Path | None = None) -> str:
    # 머신 절대경로(file:///C:/...) 대신 노트 위치 기준 상대경로를 쓴다.
    # 폴더 이동·다른 PC(데스크톱/노트북)에서도 링크가 깨지지 않게 하기 위함.
    # from_dir: 링크가 들어갈 노트가 위치한 폴더(없으면 repo root 기준).
    try:
        if from_dir is not None:
            rel = os.path.relpath(path.resolve(), from_dir.resolve()).replace("\\", "/")
        else:
            rel = path.resolve().relative_to(REPO_ROOT).as_posix()
        href = quote(rel, safe="/")
    except ValueError:
        href = path.as_posix()
    return md_link(label or path.name, href)


def safe_filename(value: str, max_len: int = 90) -> str:
    value = re.sub(r'[\\/:*?"<>|]+', " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:max_len].rstrip() or "Untitled"


def github_issue_link(issue: str) -> str:
    return f"https://github.com/{REPO}/issues/{issue}"


def github_issue_link_for(repo: str, issue: str) -> str:
    return f"https://github.com/{repo}/issues/{issue}"


def issue_key(repo: str, issue: str) -> str:
    return f"{repo}#{issue}"


def repo_label(repo: str) -> str:
    return repo.split("/", 1)[1] if "/" in repo else repo


def worker_docs_list_link(issue: str) -> str:
    return f"{API_BASE}/docs/list?repo={quote(REPO, safe='')}&issue={quote(str(issue))}"


def worker_download_link(r2_key: str) -> str:
    return f"{API_BASE}/docs/download?repo={quote(REPO, safe='')}&key={quote(r2_key, safe='')}"


def checklist_counts(text: str) -> tuple[int, int]:
    open_count = len(re.findall(r"(?m)^-\s+\[\s\]\s+", text))
    done_count = len(re.findall(r"(?m)^-\s+\[[xX]\]\s+", text))
    return open_count, done_count


def extract_title(text: str, fallback: str) -> str:
    match = re.search(r"(?m)^#\s+(.+)", text)
    return match.group(1).strip() if match else fallback


def extract_issue_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    preferred_patterns = [
        r"대표\s*이슈\s*:\s*#(\d+)",
        r"GitHub\s*Issue\s*#(\d+)",
        r"\(Issue\s*#(\d+)",
        r"Issue\s*#(\d+)",
    ]
    for pattern in preferred_patterns:
        for match in re.finditer(pattern, text, re.I):
            issue = match.group(1)
            if issue not in candidates:
                candidates.append(issue)
    for match in re.finditer(r"#(\d+)", text):
        issue = match.group(1)
        if issue not in candidates:
            candidates.append(issue)
    return candidates


def extract_sections(text: str) -> list[str]:
    sections = []
    for match in re.finditer(r"(?m)^##\s+(.+)", text):
        title = re.sub(r"^\d+\.\s*", "", match.group(1).strip())
        sections.append(title)
    return sections


def extract_next_actions(text: str, limit: int = 8) -> list[str]:
    actions = []
    for match in re.finditer(r"(?m)^-\s+\[\s\]\s+(.+)", text):
        actions.append(match.group(1).strip())
        if len(actions) >= limit:
            break
    return actions


def extract_date_lines(text: str, limit: int = 12) -> list[str]:
    lines = []
    for line in text.splitlines():
        if re.search(r"\d{4}-\d{2}-\d{2}", line):
            cleaned = line.strip()
            if cleaned and cleaned not in lines:
                lines.append(cleaned)
        if len(lines) >= limit:
            break
    return lines


def extract_doc_refs(text: str) -> list[str]:
    refs: list[str] = []
    for match in re.finditer(r"`(docs/[^`]+)`", text):
        refs.append(match.group(1))
    for match in re.finditer(r"docs/[^\s)]+", text):
        candidate = match.group(0).strip(".,)")
        if candidate not in refs:
            refs.append(candidate)
    return refs


def normalize_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title)
    return title.strip().lower()


class BoardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.cards: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.capture: str | None = None
        self.buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k: v or "" for k, v in attrs}
        if tag == "article" and "task-card" in attrs_dict.get("class", ""):
            self.current = dict(attrs_dict)
            self.current["h4"] = ""
            self.current["note"] = ""
            return
        if not self.current:
            return
        if tag == "h4":
            self.capture = "h4"
            self.buffer = []
        elif tag == "p" and "note" in attrs_dict.get("class", ""):
            self.capture = "note"
            self.buffer = []

    def handle_data(self, data: str) -> None:
        if self.current and self.capture:
            self.buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.current and self.capture and tag in {"h4", "p"}:
            text = re.sub(r"\s+", " ", "".join(self.buffer)).strip()
            self.current[self.capture] = text
            self.capture = None
            self.buffer = []
        if tag == "article" and self.current:
            self.cards.append(self.current)
            self.current = None


def parse_board_cards() -> list[dict[str, str]]:
    if not INDEX_HTML.exists():
        return []
    parser = BoardParser()
    parser.feed(read_text(INDEX_HTML))
    cards = []
    for card in parser.cards:
        title = card.get("data-title") or card.get("h4") or "Untitled"
        issue = card.get("data-issue", "")
        ref = card.get("data-ref", "")
        repo = card.get("data-repo", REPO) or REPO
        if not issue and "github.com" in ref:
            match = re.search(r"github\.com/([^/]+/[^/]+)/issues/(\d+)", ref)
            if match:
                repo = match.group(1)
                issue = match.group(2)
        cards.append(
            {
                "title": title,
                "issue": issue,
                "note": card.get("note", ""),
                "repo": repo,
                "source": card.get("data-source", ""),
                "done": card.get("data-done", ""),
                "ref": ref,
            }
        )
    return cards


def parse_todos(board_by_title: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    items = []
    for path in sorted(TODO_DIR.glob("*.md")):
        text = read_text(path)
        title = extract_title(text, path.stem)
        board = board_by_title.get(normalize_title(title), {})
        issues = extract_issue_candidates(text)
        issue = board.get("issue") or (issues[0] if issues else "")
        open_count, done_count = checklist_counts(text)
        merged = bool(re.search(r"merged-into:\s*#\d+", text))
        if merged:
            status = "merged"
        elif done_count and open_count == 0:
            status = "done"
        elif open_count:
            status = "active"
        else:
            status = "reference"
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
        items.append(
            {
                "path": path,
                "title": title,
                "issue": issue,
                "repo": REPO,
                "all_issues": issues,
                "status": status,
                "date": date_match.group(1) if date_match else "",
                "open": open_count,
                "done": done_count,
                "sections": extract_sections(text),
                "next_actions": extract_next_actions(text),
                "date_lines": extract_date_lines(text),
                "doc_refs": extract_doc_refs(text),
                "board": board,
            }
        )
    return items


def parse_asks() -> list[dict[str, object]]:
    """ASK 일일 로그에서 명시적으로 언급된 이슈를 찾아 ASK<->Issue 그래프 연결에 사용."""
    items: list[dict[str, object]] = []
    for path in sorted(ASK_DIR.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        text = read_text(path)
        # 보수적으로 'Issue #N' / '이슈 #N' / '(Issue #N' 만 매칭(체크리스트 번호 오인 방지).
        issues: list[str] = []
        for match in re.finditer(r"(?:Issue|이슈)\s*#(\d+)", text, re.I):
            if match.group(1) not in issues:
                issues.append(match.group(1))
        if not issues:
            continue
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
        items.append(
            {
                "path": path,
                "title": extract_title(text, path.stem),
                "issues": issues,
                "date": date_match.group(1) if date_match else "",
            }
        )
    return items


def doc_issue_from_rel(rel: str) -> str:
    patterns = [
        r"(?:^|/)issue-(\d+)(?:/|$)",
        r"^docs/feed-mina__kiba_2026/(\d+)(?:/|$)",
        r"^issues/issue-(\d+)(?:/|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, rel)
        if match:
            return match.group(1)
    return ""


def scan_docs() -> list[dict[str, str]]:
    docs = []
    if not DOCS_DIR.exists():
        return docs
    for path in sorted(p for p in DOCS_DIR.rglob("*") if p.is_file()):
        rel_under_docs = path.relative_to(DOCS_DIR).as_posix()
        rel_repo = path.relative_to(REPO_ROOT).as_posix()
        issue = doc_issue_from_rel(rel_under_docs)
        r2_key = ""
        cloud_link = ""
        if rel_under_docs.startswith("docs/feed-mina__kiba_2026/"):
            r2_key = rel_under_docs
            cloud_link = worker_download_link(r2_key)
        elif issue:
            cloud_link = worker_docs_list_link(issue)
        docs.append(
            {
                "path": path,
                "rel": rel_repo,
                "under_docs": rel_under_docs,
                "name": path.name,
                "issue": issue,
                "size": str(path.stat().st_size),
                "local_link": file_link(path, from_dir=OUT_ISSUES),
                "cloud_link": cloud_link,
                "r2_key": r2_key,
            }
        )
    return docs


def issue_note_name(issue: str, title: str) -> str:
    suffix = safe_filename(title)
    return f"Issue {issue} - {suffix}.md" if issue else f"No Issue - {suffix}.md"


def issue_note_filename(repo: str, issue: str, title: str) -> str:
    prefix = f"Issue {issue}" if repo == REPO else f"{repo_label(repo)} Issue {issue}"
    return f"{prefix} - {safe_filename(title)}.md"


def build_issue_notes(todos: list[dict[str, object]], board_cards: list[dict[str, str]], docs: list[dict[str, str]], asks: list[dict[str, object]] | None = None) -> dict[str, str]:
    asks = asks or []
    for old_note in OUT_ISSUES.glob("Issue *.md"):
        old_note.unlink()
    for old_note in OUT_ISSUES.glob("* Issue *.md"):
        old_note.unlink()

    by_issue: dict[str, dict[str, object]] = {}

    for card in board_cards:
        issue = card.get("issue", "")
        if not issue:
            continue
        key = issue_key(card.get("repo", REPO), issue)
        by_issue.setdefault(key, {"cards": [], "todos": [], "docs": [], "asks": [], "repo": card.get("repo", REPO), "issue": issue})
        by_issue[key]["cards"].append(card)

    for todo in todos:
        issue = str(todo.get("issue") or "")
        if not issue:
            continue
        key = issue_key(str(todo.get("repo") or REPO), issue)
        by_issue.setdefault(key, {"cards": [], "todos": [], "docs": [], "asks": [], "repo": str(todo.get("repo") or REPO), "issue": issue})
        by_issue[key]["todos"].append(todo)

    for doc in docs:
        issue = doc.get("issue", "")
        if not issue:
            continue
        key = issue_key(REPO, issue)
        by_issue.setdefault(key, {"cards": [], "todos": [], "docs": [], "asks": [], "repo": REPO, "issue": issue})
        by_issue[key]["docs"].append(doc)

    for ask in asks:
        for issue in ask["issues"]:  # type: ignore[union-attr]
            key = issue_key(REPO, str(issue))
            by_issue.setdefault(key, {"cards": [], "todos": [], "docs": [], "asks": [], "repo": REPO, "issue": str(issue)})
            by_issue[key]["asks"].append(ask)

    note_by_issue = {}
    def sort_key(item: tuple[str, dict[str, object]]) -> tuple[str, int]:
        bucket = item[1]
        issue = str(bucket.get("issue") or "0")
        return (str(bucket.get("repo") or REPO), int(issue) if issue.isdigit() else 9999)

    for key, bucket in sorted(by_issue.items(), key=sort_key):
        repo = str(bucket.get("repo") or REPO)
        issue = str(bucket.get("issue") or "")
        cards = bucket["cards"]
        issue_todos = bucket["todos"]
        issue_docs = bucket["docs"]
        issue_asks = bucket["asks"]
        active_todos = [todo for todo in issue_todos if todo.get("status") == "active"]
        if cards:
            title = cards[0].get("title", "")
        elif active_todos:
            title = str(active_todos[0]["title"])
        elif issue_todos:
            title = str(issue_todos[0]["title"])
        else:
            title = f"Issue #{issue}"

        path = OUT_ISSUES / issue_note_filename(repo, issue, title)
        note_by_issue[key] = path.stem
        status = "reference"
        if any(t["status"] == "active" for t in issue_todos):
            status = "active"
        elif issue_todos and all(t["status"] in {"done", "merged"} for t in issue_todos):
            status = "done"
        elif any(card.get("done") for card in cards):
            status = "done"

        open_total = sum(int(t["open"]) for t in issue_todos)
        done_total = sum(int(t["done"]) for t in issue_todos)

        lines = [
            "---",
            f"repo: {repo}",
            f"issue: {issue}",
            f"status: {status}",
            f"github: {github_issue_link_for(repo, issue)}",
            "tags:",
            "  - issue",
            f"  - issue-{issue}",
            "  - project-status",
            "---",
            "",
            f"# Issue {issue} - {title}",
            "",
            "## 현재 상태",
            "",
            f"- 상태: `{status}`",
            f"- 체크리스트: `{done_total}/{done_total + open_total}` 완료",
            f"- GitHub: {md_link(f'{repo} Issue #{issue}', github_issue_link_for(repo, issue))}",
            f"- 현황판: {file_link(INDEX_HTML, 'index.html', from_dir=OUT_ISSUES)}",
        ]
        if cards:
            card = cards[0]
            if card.get("note"):
                lines.append(f"- index.html 표시: {card['note']}")
            if card.get("ref"):
                lines.append(f"- 외부 참조: {md_link(card['ref'], card['ref'])}")

        lines.extend(["", "## 다음 행동", ""])
        actions = [a for todo in issue_todos for a in todo["next_actions"]]
        if actions:
            lines.extend([f"- [ ] {action}" for action in actions[:12]])
        else:
            lines.append("- [ ] 다음 점검 시 Todo 또는 GitHub Issue에서 후속 행동을 확인")

        lines.extend(["", "## 날짜 기록", ""])
        if issue_todos:
            for todo in issue_todos:
                lines.append(f"### {todo['date'] or '날짜 미상'} - {todo['title']}")
                lines.append(f"- 원본: {obsidian_link(todo['path'], todo['path'].name)}")
                if todo["date_lines"]:
                    for date_line in todo["date_lines"][:6]:
                        lines.append(f"- {date_line}")
                else:
                    lines.append("- 날짜 세부 기록 없음")
                lines.append("")
        else:
            lines.append("- 연결된 Todo 파일 없음")

        lines.extend(["## 관련 Todo", ""])
        if issue_todos:
            for todo in issue_todos:
                lines.append(
                    f"- {obsidian_link(todo['path'], todo['title'])} - `{todo['status']}` `{todo['done']}/{int(todo['done']) + int(todo['open'])}`"
                )
        else:
            lines.append("- 없음")

        lines.extend(["", "## 관련 ASK", ""])
        if issue_asks:
            seen_ask: set[str] = set()
            for ask in issue_asks:
                ask_path = ask["path"]  # type: ignore[index]
                stem = ask_path.stem  # type: ignore[union-attr]
                if stem in seen_ask:
                    continue
                seen_ask.add(stem)
                label = f"{ask['date'] or stem} - {ask['title']}"  # type: ignore[index]
                lines.append(f"- {obsidian_link(ask_path, label)}")
        else:
            lines.append("- 연결된 ASK 기록 없음")

        lines.extend(["", "## 관련 docs / Cloud 링크", ""])
        if issue_docs:
            lines.append("> Cloud 링크는 Worker의 비밀번호 보호 엔드포인트입니다. 접근 시 `DOCS_PASSWORD`가 필요할 수 있습니다.")
            lines.append("")
            lines.append("| 파일 | 로컬 | Cloud/R2 |")
            lines.append("|---|---|---|")
            for doc in issue_docs[:40]:
                cloud = md_link("Cloud 링크", doc["cloud_link"]) if doc["cloud_link"] else ""
                lines.append(f"| {doc['name']} | {doc['local_link']} | {cloud} |")
        else:
            lines.append(f"- 이슈 자료 목록 후보: {md_link('Cloud docs list', worker_docs_list_link(issue))}")

        lines.extend(["", "## 관련 index.html 카드", ""])
        if cards:
            for card in cards:
                lines.append(f"- {card.get('title', '')} / source `{card.get('source', '')}` / repo `{card.get('repo', '')}`")
        else:
            lines.append("- index.html 카드 없음")

        lines.extend(["", "#issue #project-status", ""])
        write_text(path, "\n".join(lines))

    return note_by_issue


def issue_note_link(issue: str, note_by_issue: dict[str, str], repo: str = REPO) -> str:
    key = issue_key(repo, issue)
    stem = note_by_issue.get(key)
    label = f"Issue #{issue}" if repo == REPO else f"{repo_label(repo)} #{issue}"
    return f"[[Knowledge/Issues/{stem}|{label}]]" if stem else label


def build_docs_index(docs: list[dict[str, str]]) -> None:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for doc in docs:
        grouped[doc.get("issue") or "unassigned"].append(doc)
    lines = [
        "# Docs Index",
        "",
        "> 원문은 복사하지 않고 파일명, 이슈, 로컬 링크, Cloud/R2 링크만 관리합니다.",
        "> Cloud 링크는 Worker 비밀번호 보호 엔드포인트라 브라우저 직접 접근에는 비밀번호 헤더가 필요할 수 있습니다.",
        "",
    ]
    for issue, items in sorted(grouped.items(), key=lambda kv: (kv[0] == "unassigned", int(kv[0]) if kv[0].isdigit() else 9999)):
        heading = f"Issue #{issue}" if issue != "unassigned" else "Unassigned"
        lines.extend([f"## {heading}", ""])
        lines.append("| 파일 | 로컬 | Cloud/R2 |")
        lines.append("|---|---|---|")
        for doc in items:
            cloud = md_link("Cloud 링크", doc["cloud_link"]) if doc["cloud_link"] else ""
            lines.append(f"| {doc['name']} | {doc['local_link']} | {cloud} |")
        lines.append("")
    write_text(OUT_SOURCES / "Docs Index.md", "\n".join(lines))


def build_board_source(board_cards: list[dict[str, str]], note_by_issue: dict[str, str]) -> None:
    lines = [
        "# index.html Board Source",
        "",
        f"- 로컬 현황판: {file_link(INDEX_HTML, from_dir=OUT_SOURCES)}",
        "- 이 노트는 `index.html`의 task-card를 읽어 만든 현황 소스 인덱스입니다.",
        "",
        "| 이슈 | 제목 | 표시 상태 | 원천 |",
        "|---|---|---|---|",
    ]
    for card in board_cards:
        issue = card.get("issue", "")
        issue_cell = issue_note_link(issue, note_by_issue, card.get("repo", REPO)) if issue else ""
        title = card.get("title", "")
        note = card.get("note", "")
        source = card.get("source", "")
        lines.append(f"| {issue_cell} | {title} | {note} | {source} |")
    write_text(OUT_SOURCES / "index.html Board Source.md", "\n".join(lines))


def build_dashboards(todos: list[dict[str, object]], note_by_issue: dict[str, str]) -> None:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for todo in todos:
        grouped[str(todo["status"])].append(todo)

    status_order = ["active", "reference", "merged", "done"]
    lines = [
        "# 프로젝트 현황",
        "",
        f"- 현황판: {file_link(INDEX_HTML, 'index.html', from_dir=OUT_DASH)}",
        "- 기준: GitHub Issue 중심, Obsidian은 이슈별 지식/날짜 기록 계층",
        "",
    ]
    for status in status_order:
        items = grouped.get(status, [])
        lines.extend([f"## {status}", ""])
        if not items:
            lines.append("- 없음")
        for todo in items:
            issue = str(todo.get("issue") or "")
            issue_part = issue_note_link(issue, note_by_issue, str(todo.get("repo") or REPO)) if issue else "이슈 미지정"
            lines.append(
                f"- {issue_part} - {obsidian_link(todo['path'], str(todo['title']))} `{todo['done']}/{int(todo['done']) + int(todo['open'])}`"
            )
        lines.append("")
    write_text(OUT_DASH / "프로젝트 현황.md", "\n".join(lines))

    timeline: dict[str, list[dict[str, object]]] = defaultdict(list)
    for todo in todos:
        timeline[str(todo.get("date") or "unknown")].append(todo)
    lines = [
        "# 날짜별 진행 로그",
        "",
        "- 이슈별 상태에 날짜 기록을 더한 뷰입니다.",
        "",
    ]
    for date in sorted(timeline.keys(), reverse=True):
        lines.extend([f"## {date}", ""])
        for todo in timeline[date]:
            issue = str(todo.get("issue") or "")
            issue_part = issue_note_link(issue, note_by_issue, str(todo.get("repo") or REPO)) if issue else "이슈 미지정"
            lines.append(f"- {issue_part} - {obsidian_link(todo['path'], str(todo['title']))}")
            for date_line in todo["date_lines"][:3]:
                lines.append(f"  - {date_line}")
        lines.append("")
    write_text(OUT_DASH / "날짜별 진행 로그.md", "\n".join(lines))


def build_home(note_by_issue: dict[str, str]) -> None:
    lines = [
        "# 이슈 중심 프로젝트 지식관리",
        "",
        "GitHub Issue를 진행 상태의 기준으로 두고, Obsidian에는 이슈별 맥락, 날짜 기록, docs 링크를 모읍니다.",
        "",
        "## 바로가기",
        "",
        "- [[Knowledge/이슈 보드.base|이슈 보드 (Bases 관계형 표)]]",
        "- [[Knowledge/Dashboards/프로젝트 현황|프로젝트 현황]]",
        "- [[Knowledge/Dashboards/날짜별 진행 로그|날짜별 진행 로그]]",
        "- [[Knowledge/Sources/Docs Index|Docs Index]]",
        "- [[Knowledge/Sources/index.html Board Source|index.html Board Source]]",
        "- [[Knowledge/Workstations/데스크톱-노트북 작업 이어가기|데스크톱-노트북 작업 이어가기]]",
        "- [[Knowledge/Codex/코덱스 지식관리 홈|코덱스 지식관리 홈]]",
        "- [[Knowledge/Claude/클로드 지식관리 홈|클로드 지식관리 홈]]",
        "",
        "## 운영 원칙",
        "",
        "- GitHub Issue: 실행과 상태의 기준",
        "- `index.html`: 한눈에 보는 현재 상태",
        "- Obsidian: 결정, 맥락, 날짜별 흐름, docs 링크",
        "- `docs/`: 원문 보관. Obsidian에는 원문 복사 없이 메타데이터와 링크만 유지",
        "",
        "## 갱신",
        "",
        "```powershell",
        "python .\\scripts\\build_issue_knowledge.py",
        "```",
        "",
        f"- 생성된 이슈 노트: {len(note_by_issue)}개",
        "",
        "#project-status #issue",
        "",
    ]
    write_text(REPO_ROOT / "Knowledge" / "이슈 중심 프로젝트 지식관리.md", "\n".join(lines))


def main() -> None:
    for directory in [OUT_ISSUES, OUT_DASH, OUT_SOURCES]:
        directory.mkdir(parents=True, exist_ok=True)
    board_cards = parse_board_cards()
    board_by_title = {normalize_title(card["title"]): card for card in board_cards}
    todos = parse_todos(board_by_title)
    docs = scan_docs()
    asks = parse_asks()
    note_by_issue = build_issue_notes(todos, board_cards, docs, asks)
    build_docs_index(docs)
    build_board_source(board_cards, note_by_issue)
    build_dashboards(todos, note_by_issue)
    build_home(note_by_issue)
    print(f"Wrote issue knowledge: {len(note_by_issue)} issue notes, {len(docs)} docs, {len(board_cards)} board cards")


if __name__ == "__main__":
    main()
