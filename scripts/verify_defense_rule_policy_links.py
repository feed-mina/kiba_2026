#!/usr/bin/env python3
"""Verify generated defense-rule policy links against article and policy seeds."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "defense_cost_rule_db"
DOMAIN_PATH = REPO_ROOT / "data" / "sample_ver1_cost_db" / "ver2" / "domain_tables.json"
OUT_PATH = DATA_DIR / "policy_link_check.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    articles = load_json(DATA_DIR / "legal_articles.json")["articles"]
    policy_links = load_json(DATA_DIR / "policy_article_links.json")
    domain = load_json(DOMAIN_PATH)

    article_nos = {
        row["article_no"]
        for row in articles
        if not row.get("is_supplementary") and not row.get("is_deleted")
    }
    policy_codes = {
        row["policy_code"]
        for row in domain.get("calculation_policy", {}).get("rows", [])
    }

    problems: list[str] = []
    for row in policy_links["links"]:
        if row["article_no"] not in article_nos:
            problems.append(f"missing article: {row['article_no']} for {row['source_policy_code']}")
        if row["source_policy_code"] not in policy_codes:
            problems.append(f"missing source policy: {row['source_policy_code']}")
    for row in policy_links["skipped"]:
        if row["source_policy_code"] not in policy_codes:
            problems.append(f"missing skipped source policy: {row['source_policy_code']}")

    result = {
        "passed": not problems,
        "linked_policy_count": len(policy_links["links"]),
        "skipped_policy_count": len(policy_links["skipped"]),
        "known_article_count": len(article_nos),
        "known_policy_count": len(policy_codes),
        "problems": problems,
    }
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
