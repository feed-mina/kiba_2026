#!/usr/bin/env python3
"""
sync_meeting_to_notebooklm.py  (이슈 #5 - 회의록 요약본 → NotebookLM 자동 반영 골격)

meetings/summary/<날짜>_meeting.md 를 NotebookLM 소스로 자동 반영한다.
경로는 둘(Google 측 자격증명이 있어야 실제 동작):

  --via enterprise   NotebookLM Enterprise API (Gemini Enterprise/Google Cloud 조직)
                     notebooks.sources.batchCreate 로 요약본을 소스로 직접 추가.
                     필요 env: GOOGLE_ACCESS_TOKEN, NOTEBOOKLM_PROJECT, NOTEBOOKLM_NOTEBOOK_ID
                     문서: https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/api-notebooks-sources

  --via drive        Google Drive 폴더에 요약본을 Google Doc 으로 업로드.
                     NotebookLM 에서 그 폴더/문서를 소스로 1회 연결한 뒤 동기화.
                     필요 env: GOOGLE_ACCESS_TOKEN, DRIVE_FOLDER_ID

GOOGLE_ACCESS_TOKEN 은 적절한 scope(Drive: drive.file / Enterprise: cloud-platform)의
OAuth access token 이다(토큰 발급은 운영자 몫 - gcloud auth print-access-token 등).

사용:
  python scripts/sync_meeting_to_notebooklm.py 2026-06-18              # dry-run(계획만 출력)
  python scripts/sync_meeting_to_notebooklm.py 2026-06-18 --via drive --confirm
표준 라이브러리만 사용한다.
"""

import os
import re
import sys
import json
import uuid
import argparse
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SUMMARY_DIR = REPO_ROOT / "meetings" / "summary"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def resolve_summary(arg: str) -> Path:
    if DATE_RE.match(arg):
        return SUMMARY_DIR / f"{arg}_meeting.md"
    return Path(arg).resolve()


def rel(p: Path) -> str:
    try:
        return p.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _http(method, url, headers, body=None):
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def drive_upload(summary_path: Path, folder_id: str, token: str, title: str):
    """요약본 텍스트를 Drive 폴더에 Google Doc 으로 변환 업로드(multipart)."""
    text = summary_path.read_text(encoding="utf-8-sig")
    boundary = uuid.uuid4().hex
    metadata = {
        "name": title,
        "parents": [folder_id],
        "mimeType": "application/vnd.google-apps.document",  # 변환 업로드
    }
    parts = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\nContent-Type: text/markdown; charset=UTF-8\r\n\r\n"
        f"{text}\r\n--{boundary}--\r\n"
    ).encode("utf-8")
    status, resp = _http(
        "POST",
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,webViewLink",
        {"Authorization": f"Bearer {token}",
         "Content-Type": f"multipart/related; boundary={boundary}"},
        parts,
    )
    if status in (200, 201):
        d = json.loads(resp)
        print(f"Drive 업로드 성공: {d.get('name')}  {d.get('webViewLink','')}")
        print("→ NotebookLM 에서 이 Drive 폴더를 소스로 (최초 1회) 연결한 뒤, 소스 동기화로 반영하세요.")
        return True
    print(f"Drive 업로드 실패: {status} {resp}", file=sys.stderr)
    return False


def enterprise_add_source(summary_path: Path, project: str, notebook: str, token: str, title: str):
    """
    NotebookLM Enterprise: notebooks.sources.batchCreate.
    엔드포인트/페이로드 정확한 형태는 조직 프로젝트 기준으로 검증 필요(아래는 문서 기반 초안).
    """
    raise NotImplementedError(
        "Enterprise 경로는 조직의 NotebookLM Enterprise 프로젝트에서 엔드포인트/페이로드를 "
        "검증한 뒤 활성화하세요(batchCreate 소스 형식·리전·권한 확인 필요).\n"
        "문서: https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/api-notebooks-sources\n"
        f"  대상 notebook={notebook}, project={project}, source title={title}"
    )


def main():
    ap = argparse.ArgumentParser(description="회의록 요약본 → NotebookLM 자동 반영")
    ap.add_argument("target", help="YYYY-MM-DD 또는 요약본 md 경로")
    ap.add_argument("--via", choices=["enterprise", "drive"], help="반영 경로")
    ap.add_argument("--confirm", action="store_true", help="실제 호출(미지정 시 dry-run)")
    args = ap.parse_args()

    path = resolve_summary(args.target)
    if not path.exists():
        print(f"요약본이 없습니다: {path}", file=sys.stderr)
        sys.exit(2)
    title = path.stem  # 예: 2026-06-18_meeting
    token = os.environ.get("GOOGLE_ACCESS_TOKEN", "")

    if not args.via:
        print("경로(--via enterprise|drive)를 지정하세요. README 'NotebookLM 자동 반영' 참고.")
        print(f"대상 요약본: {rel(path)}")
        return

    if not args.confirm:
        need = ("GOOGLE_ACCESS_TOKEN, DRIVE_FOLDER_ID" if args.via == "drive"
                else "GOOGLE_ACCESS_TOKEN, NOTEBOOKLM_PROJECT, NOTEBOOKLM_NOTEBOOK_ID")
        print(f"(dry-run) via={args.via}, 대상={path.name}\n  필요 env: {need}\n  실제 반영하려면 --confirm")
        return

    if not token:
        print("GOOGLE_ACCESS_TOKEN 미설정 — 발급 후 재시도(예: gcloud auth print-access-token).", file=sys.stderr)
        sys.exit(2)

    if args.via == "drive":
        folder = os.environ.get("DRIVE_FOLDER_ID", "")
        if not folder:
            print("DRIVE_FOLDER_ID 미설정.", file=sys.stderr); sys.exit(2)
        ok = drive_upload(path, folder, token, title)
        sys.exit(0 if ok else 1)
    else:
        enterprise_add_source(path, os.environ.get("NOTEBOOKLM_PROJECT", ""),
                              os.environ.get("NOTEBOOKLM_NOTEBOOK_ID", ""), token, title)


if __name__ == "__main__":
    main()
