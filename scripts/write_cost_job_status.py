#!/usr/bin/env python3
"""Write a small, deterministic R2 status document for a cost generation job."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status", choices=("processing", "ready", "failed"), required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--message", default="")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--filename", default="")
    args = parser.parse_args()

    payload = {
        "ok": args.status != "failed",
        "status": args.status,
        "requestId": args.request_id,
        "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if args.message:
        payload["message"] = args.message
    if args.run_url:
        payload["runUrl"] = args.run_url
    if args.filename:
        payload["filename"] = args.filename

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
