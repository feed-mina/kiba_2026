#!/usr/bin/env python3
"""
transcribe_clova.py  (이슈 #5 - 녹음 → STT 원문 자동화)

녹음 파일을 Naver CLOVA Speech Recognition(CSR)으로 전사해
meetings/raw/<날짜>_meeting.txt 로 저장한다(= summarize_meeting.py 의 입력).

사용:
  python scripts/transcribe_clova.py --audio rec.m4a                 # 오늘 날짜
  python scripts/transcribe_clova.py --audio rec.m4a --date 2026-06-28
  python scripts/transcribe_clova.py --audio rec.m4a --force         # 기존 raw 덮어쓰기

환경변수(.env): CLOVA_CSR_CLIENT_ID, CLOVA_CSR_CLIENT_SECRET  (AI·NAVER API CSR)

주의: CSR(AI·NAVER API)은 **짧은 음성(약 60초/파일 크기 제한)**용이다. 긴 회의는
클로바노트로 내보내 raw/ 에 직접 저장하거나, CLOVA Speech(긴 문장) 제품으로 후속 연동한다.
표준 라이브러리만 사용한다.
"""

import os
import sys
import argparse
import urllib.request
import urllib.error
from datetime import date as _date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "meetings" / "raw"
CSR_URL = "https://naveropenapi.apigw.ntruss.com/recog/v1/stt"


def load_env() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        sys.exit(f"[clova] 환경변수 {name} 가 필요합니다 (.env 또는 셸).")
    return val


def transcribe(audio: Path, lang: str) -> str:
    cid = require("CLOVA_CSR_CLIENT_ID")
    secret = require("CLOVA_CSR_CLIENT_SECRET")
    if not audio.exists():
        sys.exit(f"[clova] 오디오 파일 없음: {audio}")
    data = audio.read_bytes()
    req = urllib.request.Request(
        f"{CSR_URL}?lang={lang}",
        data=data,
        method="POST",
        headers={
            "X-NCP-APIGW-API-KEY-ID": cid,
            "X-NCP-APIGW-API-KEY": secret,
            "Content-Type": "application/octet-stream",
        },
    )
    print(f"[clova] CSR 전사 중… ({audio.name}, {len(data)//1024} KB)")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            import json
            out = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"[clova] CSR 오류 {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")
    text = (out.get("text") or "").strip()
    if not text:
        sys.exit(f"[clova] 전사 결과가 비어 있습니다: {out}")
    return text


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description="녹음 → CLOVA CSR → meetings/raw/<날짜>_meeting.txt")
    ap.add_argument("--audio", required=True, type=Path, help="녹음 파일")
    ap.add_argument("--date", default=_date.today().isoformat(), help="YYYY-MM-DD (기본 오늘)")
    ap.add_argument("--lang", default="Kor", help="언어 코드(기본 Kor)")
    ap.add_argument("--force", action="store_true", help="기존 raw 덮어쓰기")
    args = ap.parse_args()

    out_path = RAW_DIR / f"{args.date}_meeting.txt"
    if out_path.exists() and not args.force:
        sys.exit(f"[clova] 이미 존재(덮어쓰려면 --force): {out_path}")

    text = transcribe(args.audio, args.lang)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text + "\n", encoding="utf-8")
    print(f"[clova] 저장(로컬 전용): {out_path.relative_to(REPO_ROOT).as_posix()}")
    print(f"[clova] 다음: python scripts/summarize_meeting.py {args.date} --engine gemini")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
