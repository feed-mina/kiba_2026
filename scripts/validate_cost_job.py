#!/usr/bin/env python3
"""Validate the hidden cost-job payload from a trusted GitHub issue comment."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


REPO = "feed-mina/kiba_2026"
ISSUE = 42
MARKER = re.compile(r"<!--\s*kiba-cost-job\s*(\{.*?\})\s*-->", re.DOTALL)
REQUEST_ID = re.compile(r"^[0-9A-Za-z-]{20,120}$")
TEMPLATE_KEYS = {
    "ver1": "원가계산보고서샘플/(E)sample_원가계산보고서ver1.xlsx.xlsx",
    "ver2": "원가계산보고서샘플/(E)sample_원가계산보고서ver2.xlsx.xlsx",
}
INPUT_PREFIXES = {
    "priceComparison": "priceComparison__",
    "unitCost": "unitCost__",
    "detail": "detail__",
}


def parse_job(comment: str) -> dict[str, Any]:
    match = MARKER.search(comment)
    if not match:
        raise ValueError("missing kiba-cost-job marker")
    job = json.loads(match.group(1))
    if not isinstance(job, dict) or job.get("version") != 1:
        raise ValueError("unsupported job payload")
    if job.get("repo") != REPO or job.get("issue") != ISSUE:
        raise ValueError("job repository or issue mismatch")

    request_id = str(job.get("requestId") or "")
    if not REQUEST_ID.fullmatch(request_id):
        raise ValueError("invalid requestId")
    template_version = str(job.get("templateVersion") or "")
    if job.get("templateKey") != TEMPLATE_KEYS.get(template_version):
        raise ValueError("invalid template key")

    prefix = f"cost-requests/feed-mina__kiba_2026/{ISSUE}/{request_id}"
    input_keys = job.get("inputKeys")
    if not isinstance(input_keys, dict) or set(input_keys) != set(INPUT_PREFIXES):
        raise ValueError("input key set mismatch")
    for role, filename_prefix in INPUT_PREFIXES.items():
        key = str(input_keys[role])
        if not key.startswith(f"{prefix}/{filename_prefix}") or ".." in key:
            raise ValueError(f"invalid input key: {role}")

    expected_output = f"{prefix}/result__원가계산서.xlsx"
    expected_status = f"{prefix}/status.json"
    if job.get("outputKey") != expected_output or job.get("statusKey") != expected_status:
        raise ValueError("output key mismatch")
    return job


def write_github_output(path: Path, job: dict[str, Any]) -> None:
    values = {
        "repo": job["repo"],
        "issue": str(job["issue"]),
        "request_id": job["requestId"],
        "template_version": job["templateVersion"],
        "template_key": job["templateKey"],
        "price_comparison_key": job["inputKeys"]["priceComparison"],
        "unit_cost_key": job["inputKeys"]["unitCost"],
        "detail_key": job["inputKeys"]["detail"],
        "output_key": job["outputKey"],
        "status_key": job["statusKey"],
    }
    with path.open("a", encoding="utf-8", newline="\n") as output:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise ValueError(f"newline in output: {key}")
            output.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    comment = os.environ.get("COST_COMMENT_BODY", "")
    write_github_output(args.github_output, parse_job(comment))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
