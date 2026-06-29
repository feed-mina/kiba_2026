#!/usr/bin/env python3

from __future__ import annotations

import json
import unittest

from validate_cost_job import ISSUE, REPO, TEMPLATE_KEYS, parse_job


class ValidateCostJobTest(unittest.TestCase):
    def make_comment(self) -> str:
        request_id = "2026-06-29T01-02-03-000Z-123e4567-e89b-12d3-a456-426614174000"
        prefix = f"cost-requests/feed-mina__kiba_2026/{ISSUE}/{request_id}"
        job = {
            "version": 1,
            "repo": REPO,
            "issue": ISSUE,
            "requestId": request_id,
            "templateVersion": "ver1",
            "templateKey": TEMPLATE_KEYS["ver1"],
            "inputKeys": {
                "priceComparison": f"{prefix}/priceComparison__price.xlsx",
                "unitCost": f"{prefix}/unitCost__unit.xlsx",
                "detail": f"{prefix}/detail__detail.xlsx",
            },
            "outputKey": f"{prefix}/result__원가계산서.xlsx",
            "statusKey": f"{prefix}/status.json",
        }
        return f"before\n<!-- kiba-cost-job\n{json.dumps(job, ensure_ascii=False)}\n-->\nafter"

    def test_accepts_expected_payload(self) -> None:
        job = parse_job(self.make_comment())
        self.assertEqual(job["issue"], ISSUE)
        self.assertEqual(job["templateVersion"], "ver1")

    def test_rejects_path_traversal(self) -> None:
        comment = self.make_comment().replace("priceComparison__price.xlsx", "priceComparison__../secret")
        with self.assertRaisesRegex(ValueError, "invalid input key"):
            parse_job(comment)

    def test_rejects_wrong_issue(self) -> None:
        comment = self.make_comment().replace('"issue": 42', '"issue": 41')
        with self.assertRaisesRegex(ValueError, "mismatch"):
            parse_job(comment)


if __name__ == "__main__":
    unittest.main()
