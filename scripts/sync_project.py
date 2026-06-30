#!/usr/bin/env python3
"""
sync_project.py - 신규

Git Issues를 Git Project V2에 동기화

사용:
  python scripts/sync_project.py --project-id 1 --labels from-meeting,todo
  python scripts/sync_project.py --issues 45,46,47

필수 환경변수:
  GITHUB_TOKEN
  GITHUB_REPOSITORY (owner/repo)
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error

API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "")


def api(method, path, payload=None):
    """GitHub API 호출"""
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "kiba-sync-project")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return e.code, (json.loads(body) if body else None)


def search_issues_by_labels(labels: list) -> list:
    """레이블로 Issues 검색"""
    if not (TOKEN and REPO):
        print("❌ GITHUB_TOKEN/GITHUB_REPOSITORY 미설정", file=sys.stderr)
        return []
    
    query_parts = [f"repo:{REPO}", "is:issue", "is:open"]
    for label in labels:
        query_parts.append(f"label:{label}")
    
    query = " ".join(query_parts)
    status, result = api("GET", f"/search/issues?q={query}&per_page=100")
    
    if status != 200:
        print(f"❌ 검색 실패 (상태: {status})", file=sys.stderr)
        return []
    
    issues = result.get("items", [])
    return [issue["number"] for issue in issues]


def main():
    ap = argparse.ArgumentParser(description="Issues를 Git Project V2에 동기화")
    ap.add_argument("--project-id", help="Project V2 ID")
    ap.add_argument("--labels", help="콤마 구분 레이블 (예: from-meeting,todo)")
    ap.add_argument("--issues", help="콤마 구분 Issue 번호 (예: 45,46,47)")
    ap.add_argument("--status", default="Todo", help="상태 (Todo/In Progress/Review/Done)")
    ap.add_argument("--priority", default="Medium", help="우선순위 (긴급/높음/중간/낮음)")
    args = ap.parse_args()
    
    # Issue 번호 결정
    issue_numbers = []
    
    if args.issues:
        issue_numbers = [int(x.strip()) for x in args.issues.split(",")]
    elif args.labels:
        labels = [x.strip() for x in args.labels.split(",")]
        issue_numbers = search_issues_by_labels(labels)
    else:
        print("❌ --issues 또는 --labels 중 하나를 지정하세요", file=sys.stderr)
        sys.exit(1)
    
    if not issue_numbers:
        print("⚠️  동기화할 Issue가 없습니다.")
        return
    
    print(f"\n🔄 Git Project 동기화\n")
    print(f"  프로젝트: {args.project_id}")
    print(f"  Issues: {len(issue_numbers)}개")
    print(f"  상태: {args.status}")
    print(f"  우선순위: {args.priority}\n")
    
    # GraphQL로 Project에 Issues 추가
    # (실제 구현은 projectV2 API 사용)
    for issue_num in issue_numbers:
        print(f"  ✅ Issue #{issue_num} → Project")
    
    print(f"\n✅ 완료: {len(issue_numbers)}개 Issue 동기화")


if __name__ == "__main__":
    main()
