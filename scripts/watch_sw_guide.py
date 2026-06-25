#!/usr/bin/env python3
"""
watch_sw_guide.py
소프트웨어산업협회 "SW사업대가" 게시판(cbIdx=276)을 모니터링한다.

하는 일
  1) 게시판 목록(1페이지)을 받아 글(bcIdx/제목/등록일/첨부여부) 파싱
  2) scripts/sw_guide_state.json 의 "이미 본 bcIdx" 와 비교해 새 글 감지
  3) 새 글 중 관심 키워드(대가/인건비/가이드/템플릿/단가) 매칭 글이 있으면:
       - data/sw_guide_latest.json 피드 갱신 (GitHub Pages 로 공개 -> quali-fit 가 fetch)
       - GitHub Issue(#3, 대가 산정) 에 코멘트 + 라벨  (GITHUB_TOKEN 있을 때만)
  4) 상태 파일/피드를 항상 최신으로 기록

특징
  - 표준 라이브러리만 사용 (reflect_todo.py 와 동일 패턴)
  - 첫 실행(seeded=false)에는 현재 글을 모두 "본 것"으로 기록하고 알림은 보내지 않음
    (오래된 66건이 한꺼번에 알림으로 터지는 것 방지)

환경변수
  GITHUB_TOKEN       - 이슈 코멘트/라벨용 (없으면 피드만 갱신)
  GITHUB_REPOSITORY  - "owner/repo" (기본 feed-mina/kiba_2026)
  GITHUB_API_URL     - 기본 https://api.github.com
  SW_GUIDE_ISSUE     - 코멘트를 달 이슈 번호 (기본 3)
"""

import html as html_lib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urljoin
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# 설정
# --------------------------------------------------------------------------- #
CB_IDX = 276
BOARD_HOST = "https://www.sw.or.kr"
LIST_URL = f"{BOARD_HOST}/site/sw/ex/board/List.do?cbIdx={CB_IDX}"
LIST_PAGE_URL = f"{LIST_URL}&pageIndex={{page}}"
VIEW_URL = f"{BOARD_HOST}/site/sw/ex/board/View.do?cbIdx={CB_IDX}&bcIdx={{bcIdx}}"

KEYWORDS = ["대가", "인건비", "가이드", "템플릿", "단가", "산정"]

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = REPO_ROOT / "scripts" / "sw_guide_state.json"
FEED_FILE = REPO_ROOT / "data" / "sw_guide_latest.json"
FEED_START_YEAR = 2020
FEED_MAX_PAGES = 7

API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
REPO = os.environ.get("GITHUB_REPOSITORY", "feed-mina/kiba_2026")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
ISSUE_NUMBER = int(os.environ.get("SW_GUIDE_ISSUE", "3"))

LABEL = "대가산정-업데이트"
LABEL_COLOR = "0e8a16"
COMMENT_MARK = "<!-- sw-guide-watch -->"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) kiba-sw-guide-watch"


# --------------------------------------------------------------------------- #
# 게시판 가져오기 / 파싱
# --------------------------------------------------------------------------- #
def fetch_html(url, retries=3, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                ctype = r.headers.get("Content-Type", "")
            break
        except urllib.error.URLError as e:  # DNS/연결 실패 -> 잠깐 쉬고 재시도
            last = e
            print(f"가져오기 시도 {attempt}/{retries} 실패: {e}", file=sys.stderr)
            if attempt < retries:
                time.sleep(3)
    else:
        raise last
    # charset 추정: 헤더 -> meta -> 후보 순서로 디코드 시도
    m = re.search(r"charset=([\w-]+)", ctype, re.I)
    candidates = []
    if m:
        candidates.append(m.group(1))
    head = raw[:2048].decode("ascii", "ignore")
    mm = re.search(r'charset=["\']?([\w-]+)', head, re.I)
    if mm:
        candidates.append(mm.group(1))
    candidates += ["utf-8", "euc-kr", "cp949"]
    for enc in candidates:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


# tbody 안에서 한 행씩: bcIdx, 제목, (중간 셀), 첫 날짜(YYYY-MM-DD)
ROW_RE = re.compile(
    r'bcIdx=(\d+)[^"]*"\s+title="[^"]*"\s*>\s*(.*?)\s*</a>(.*?)<td>\s*(\d{4}-\d{2}-\d{2})\s*</td>',
    re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
ATTACHMENT_RE = re.compile(
    r'<a[^>]+href=["\']([^"\']*/common/board/Download\.do\?[^"\']+)["\'][^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)


def parse_board(html):
    """게시판 목록을 [{bcIdx, title, date, url, attach, relevant}] 로 반환 (최신순)."""
    body = html
    tb = html.find("<tbody")
    if tb >= 0:
        end = html.find("</tbody>", tb)
        body = html[tb:end if end > 0 else len(html)]

    posts = []
    seen = set()
    for bcidx, title_raw, middle, date in ROW_RE.findall(body):
        bcidx = int(bcidx)
        if bcidx in seen:
            continue
        seen.add(bcidx)
        title = TAG_RE.sub("", title_raw)
        title = re.sub(r"\s+", " ", title).strip()
        attach = 'alt="첨부파일"' in middle or "icon_file" in middle
        relevant = any(k in title for k in KEYWORDS)
        posts.append({
            "bcIdx": bcidx,
            "title": title,
            "date": date,
            "url": VIEW_URL.format(bcIdx=bcidx),
            "attach": attach,
            "relevant": relevant,
        })
    return posts


def parse_attachments(html):
    """Return downloadable files exposed by a board detail page."""
    attachments = []
    seen = set()
    for href, label_html in ATTACHMENT_RE.findall(html):
        url = html_lib.unescape(urljoin(BOARD_HOST, href))
        if url in seen:
            continue
        seen.add(url)
        name = TAG_RE.sub("", label_html)
        name = html_lib.unescape(re.sub(r"\s+", " ", name)).strip()
        attachments.append({"name": name or "첨부파일", "url": url})
    return attachments


def fetch_history():
    """Collect and deduplicate notices from 2020 onward."""
    posts_by_id = {}

    def fetch_page(page):
        page_url = LIST_URL if page == 1 else LIST_PAGE_URL.format(page=page)
        return page, parse_board(fetch_html(page_url, retries=1, timeout=15))

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch_page, page) for page in range(1, FEED_MAX_PAGES + 1)]
        page_results = []
        for future in as_completed(futures):
            try:
                page_results.append(future.result())
            except Exception as exc:
                print(f"과거 공지 페이지 확인 실패: {exc}", file=sys.stderr)

    for _, page_posts in sorted(page_results):
        for post in page_posts:
            if int(post["date"][:4]) >= FEED_START_YEAR:
                posts_by_id[post["bcIdx"]] = post
    return list(posts_by_id.values())


def enrich_attachments(posts):
    """Attach direct download links, preserving cached links when available."""
    cached = {}
    if FEED_FILE.exists():
        try:
            old_feed = json.loads(FEED_FILE.read_text(encoding="utf-8"))
            for post in old_feed.get("history", old_feed.get("recent", [])):
                if post.get("attachments"):
                    cached[post["bcIdx"]] = post["attachments"]
        except (ValueError, OSError, KeyError):
            pass

    newest_with_files = {
        post["bcIdx"] for post in sorted(
            (p for p in posts if p["relevant"] and p["attach"]),
            key=lambda p: (p["date"], p["bcIdx"]),
            reverse=True,
        )[:8]
    }

    to_fetch = []
    for post in posts:
        if not (post["relevant"] and post["attach"]):
            post["attachments"] = []
            continue
        if post["bcIdx"] in cached:
            post["attachments"] = cached[post["bcIdx"]]
            continue
        if post["bcIdx"] not in newest_with_files:
            post["attachments"] = []
            continue
        to_fetch.append(post)

    def fetch_post_attachments(post):
        detail = fetch_html(post["url"], retries=1, timeout=10)
        return post["bcIdx"], parse_attachments(detail)

    posts_by_id = {post["bcIdx"]: post for post in to_fetch}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch_post_attachments, post) for post in to_fetch]
        for future in as_completed(futures):
            try:
                bcidx, attachments = future.result()
                posts_by_id[bcidx]["attachments"] = attachments
            except Exception as exc:  # The notice URL remains available as fallback.
                print(f"첨부 링크 확인 실패: {exc}", file=sys.stderr)

    for post in to_fetch:
        post.setdefault("attachments", [])


# --------------------------------------------------------------------------- #
# 상태 / 피드 입출력
# --------------------------------------------------------------------------- #
def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"seeded": False, "seen_bcidx": [], "last_check": None}


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_feed(posts, new_relevant, now_iso):
    # 피드는 등록일 내림차순(같은 날짜면 bcIdx 큰 순)으로 정렬해 최신이 위로 오게 한다.
    relevant_posts = sorted(
        (p for p in posts if p["relevant"]),
        key=lambda p: (p["date"], p["bcIdx"]), reverse=True,
    )
    latest = relevant_posts[0] if relevant_posts else (posts[0] if posts else None)
    feed = {
        "checked_at": now_iso,
        "tracking_since_year": FEED_START_YEAR,
        "board_url": LIST_URL,
        "latest": _slim(latest) if latest else None,
        "recent": [_slim(p) for p in relevant_posts[:8]],
        "history": [_slim(p) for p in relevant_posts],
        "new_since_last_check": [_slim(p) for p in new_relevant],
        "has_update": bool(new_relevant),
    }
    save_json(FEED_FILE, feed)


def _slim(p):
    return {"bcIdx": p["bcIdx"], "title": p["title"], "date": p["date"],
            "url": p["url"], "attach": p["attach"],
            "attachments": p.get("attachments", [])}


# --------------------------------------------------------------------------- #
# GitHub REST (stdlib only) - reflect_todo.py 패턴
# --------------------------------------------------------------------------- #
def api(method, path, payload=None):
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "kiba-sw-guide-watch")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return e.code, (json.loads(body) if body else None)


def ensure_label():
    # 라벨 이름이 한글이므로 URL 경로에 넣을 때 퍼센트 인코딩 필수
    status, _ = api("GET", f"/repos/{REPO}/labels/{quote(LABEL)}")
    if status == 404:
        api("POST", f"/repos/{REPO}/labels",
            {"name": LABEL, "color": LABEL_COLOR,
             "description": "SW 대가 산정 가이드 게시판 업데이트 감지"})


def notify_issue(new_relevant, now_iso):
    if not (TOKEN and REPO):
        print("GITHUB_TOKEN/REPO 없음 -> 이슈 코멘트 생략 (피드만 갱신)")
        return
    ensure_label()
    lines = [
        COMMENT_MARK,
        "### 🔔 SW 대가 산정 가이드 게시판에 새 글이 올라왔습니다",
        "",
        f"- 출처: [{LIST_URL}]({LIST_URL})",
        f"- 감지 시각: {now_iso}",
        "",
    ]
    for p in new_relevant:
        flag = " 📎" if p["attach"] else ""
        lines.append(f"- **{p['title']}** ({p['date']}){flag} — [바로가기]({p['url']})")
    lines += ["", "_이 메모는 watch_sw_guide.py 가 자동으로 남깁니다._"]
    status, data = api("POST", f"/repos/{REPO}/issues/{ISSUE_NUMBER}/comments",
                       {"body": "\n".join(lines)})
    if status in (200, 201):
        print(f"이슈 #{ISSUE_NUMBER} 코멘트 등록")
        api("POST", f"/repos/{REPO}/issues/{ISSUE_NUMBER}/labels",
            {"labels": [LABEL]})
    else:
        print(f"이슈 코멘트 실패: {status} {data}", file=sys.stderr)


# --------------------------------------------------------------------------- #
def main():
    # Windows 콘솔(cp949)에서도 한글 로그가 깨지지 않게 stdout/stderr 를 UTF-8 로.
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    now_iso = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    try:
        posts = fetch_history()
    except urllib.error.URLError as e:
        # 사이트 접속 불가(DNS/지오 차단 등)는 코드 오류가 아니므로 조용히 통과(exit 0).
        # 한국 IP인 사무실 PC(주 수집기)가 처리하고, 해외 IP인 GitHub Actions(보조)는
        # 접속이 막히면 빨간 X 대신 경고만 남긴다.
        print(f"게시판 접속 불가 — 이번 회차 건너뜀 (정상): {e}", file=sys.stderr)
        sys.exit(0)
    except Exception as e:  # noqa: BLE001  그 외 예외는 실패로 표시
        print(f"게시판 가져오기 실패: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"파싱된 글 {len(posts)}건 (관심 {sum(p['relevant'] for p in posts)}건)")
    if not posts:
        print("행을 하나도 못 찾음 — 게시판 구조가 바뀌었을 수 있습니다.", file=sys.stderr)
        sys.exit(1)

    enrich_attachments(posts)

    state = load_state()
    seen = set(state.get("seen_bcidx", []))
    current = {p["bcIdx"] for p in posts}

    if not state.get("seeded"):
        # 첫 실행: 현재 글을 모두 본 것으로 기록, 알림 없음
        state.update({"seeded": True, "seen_bcidx": sorted(current),
                      "last_check": now_iso})
        save_json(STATE_FILE, state)
        write_feed(posts, [], now_iso)
        print(f"시드 완료: 현재 {len(current)}건을 기준선으로 기록 (알림 없음)")
        return

    # A history backfill must not produce a burst of old notifications.
    last_check_date = str(state.get("last_check") or "")[:10]
    new_posts = [
        p for p in posts
        if p["bcIdx"] not in seen and (not last_check_date or p["date"] >= last_check_date)
    ]
    new_relevant = [p for p in new_posts if p["relevant"]]
    print(f"새 글 {len(new_posts)}건, 관심 새 글 {len(new_relevant)}건")

    # 본 목록은 새 글 전체를 누적 (관심 없는 글도 다시 안 보게)
    state["seen_bcidx"] = sorted(seen | current)
    state["last_check"] = now_iso
    save_json(STATE_FILE, state)

    write_feed(posts, new_relevant, now_iso)

    if new_relevant:
        for p in new_relevant:
            print(f"  + #{p['bcIdx']} {p['title']} ({p['date']})")
        notify_issue(new_relevant, now_iso)
    else:
        print("관심 새 글 없음 — 피드 checked_at 만 갱신")


if __name__ == "__main__":
    main()
