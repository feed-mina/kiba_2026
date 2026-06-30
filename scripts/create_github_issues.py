#!/usr/bin/env python3
"""
create_github_issues.py - 신규

회의록 "## 할 일" → GitHub Issues 자동 생성

사용:
  python scripts/create_github_issues.py 2026-06-30
  python scripts/create_github_issues.py 2026-06-30 --project-id 1

필수 환경변수:
  GITHUB_TOKEN
  GITHUB_REPOSITORY (owner/repo)

선택 환경변수:
  GITHUB_PROJECT_ID (Project V2 동기화 시)
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

API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ITEM_RE = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+(.+?)\s*$")


def api(method, path, payload=None):
    """GitHub API 호출"""
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "kiba-create-issues")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return e.code, (json.loads(body) if body else None)


def parse_meeting_actions(text: str) -> list:
    """회의록에서 '## 할 일' 섹션 파싱"""
    m = re.search(r"^##\s+할 일\s*$(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        return []
    
    items = []
    for line in m.group(1).splitlines():
        im = ITEM_RE.match(line)
        if not im:
            continue
        
        raw = im.group(1)
        
        # 템플릿 항목 제외
        if raw.startswith("<!--") or "(할 일)" in raw or "(이슈 #N)" in raw:
            continue
        
        # 메타데이터 파싱
        owner = (re.search(r"@(\S+)", raw) or [None, None])[1]
        due = (re.search(r"~(\d{4}-\d{2}-\d{2})", raw) or [None, None])[1]
        existing_issue = (re.search(r"\(이슈\s*#(\d+)\)", raw) or [None, None])[1]
        
        # 순수 내용 추출 (메타데이터 제거)
        content = re.sub(r"\s*[—-]\s*@\S+", "", raw)
        content = re.sub(r"\s*~\d{4}-\d{2}-\d{2}", "", content)
        content = re.sub(r"\s*\(이슈\s*#\d+\)", "", content).strip(" —-")
        
        items.append({
            "content": content,
            "owner": owner,
            "due": due,
            "existing_issue": int(existing_issue) if existing_issue else None
        })
    
    return items


def create_issue(date: str, item: dict) -> int:
    """GitHub Issue 생성"""
    if not (TOKEN and REPO):
        print(f"❌ GITHUB_TOKEN/GITHUB_REPOSITORY 미설정", file=sys.stderr)
        return None
    
    # 기존 이슈가 있으면 그 번호 반환
    if item["existing_issue"]:
        return item["existing_issue"]
    
    # Issue 본문 작성
    body_lines = [
        f"**회의 일자**: {date}",
        f"**출처**: [회의록](../meetings/summary/{date}_meeting.md)",
        "",
        "## 상세내용",
        item["content"]
    ]
    
    if item["owner"]:
        body_lines.append(f"\n**담당자**: @{item['owner']}")
    
    if item["due"]:
        body_lines.append(f"**마감일**: {item['due']}")
    
    body = "\n".join(body_lines)
    
    # Issue 생성
    payload = {
        "title": item["content"][:80],
        "body": body,
        "labels": ["from-meeting", "todo"],
    }
    
    if item["owner"]:
        payload["assignees"] = [item["owner"]]
    
    status, result = api("POST", f"/repos/{REPO}/issues", payload)
    
    if status in (200, 201):
        return result.get("number")
    else:
        print(f"❌ Issue 생성 실패: {item['content'][:50]}... (상태: {status})", file=sys.stderr)
        return None


def main():
    ap = argparse.ArgumentParser(description="회의록 → GitHub Issues 자동 생성")
    ap.add_argument("date", help="YYYY-MM-DD")
    ap.add_argument("--project-id", help="Git Project V2 ID (선택)")
    ap.add_argument("--dry-run", action="store_true", help="실행 전 미리보기")
    args = ap.parse_args()
    
    # 회의록 파일 확인
    meeting_file = SUMMARY_DIR / f"{args.date}_meeting.md"
    if not meeting_file.exists():
        print(f"❌ 회의록 파일이 없습니다: {meeting_file}", file=sys.stderr)
        sys.exit(1)
    
    # 할 일 파싱
    text = meeting_file.read_text(encoding="utf-8-sig")
    items = parse_meeting_actions(text)
    
    if not items:
        print("⚠️  할 일 항목이 없습니다.")
        return
    
    print(f"\n📋 {args.date} 회의 - {len(items)}개 할 일 항목\n")
    
    created_issues = []
    for i, item in enumerate(items, 1):
        print(f"{i}. {item['content']}")
        if item["owner"]:
            print(f"   담당: @{item['owner']}")
        if item["due"]:
            print(f"   마감: {item['due']}")
        if item["existing_issue"]:
            print(f"   기존: #{item['existing_issue']}")
        
        if not args.dry_run:
            issue_num = create_issue(args.date, item)
            if issue_num:
                print(f"   ✅ Issue #{issue_num} 생성/확인")
                created_issues.append(issue_num)
        
        print()
    
    if args.dry_run:
        print("\n💡 팁: --dry-run 제거하고 실행하면 실제 Issues가 생성됩니다.")
    else:
        print(f"\n✅ 완료: {len(created_issues)}/{len(items)} Issues 생성")
        if args.project_id and created_issues:
            print(f"\n📌 다음 단계: Project {args.project_id}에 Issues 추가")
            print(f"   python scripts/sync_project.py --issues {','.join(map(str, created_issues))}")


if __name__ == "__main__":
    main()
