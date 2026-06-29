#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path

from reflect_meeting import parse_actions
from summarize_meeting import DECISION_CRITERIA, TEMPLATE, fill_template


class MeetingPipelineTest(unittest.TestCase):
    def test_decision_manual_has_25_criteria(self) -> None:
        text = DECISION_CRITERIA.read_text(encoding="utf-8")
        rows = [line for line in text.splitlines() if line.startswith("| ") and not line.startswith("| ---")]
        criteria_rows = [line for line in rows if any(prefix in line for prefix in ("OBJ-", "VAL-", "RSK-", "EXE-", "QUA-"))]
        self.assertEqual(len(criteria_rows), 25)

    def test_summary_renders_criteria_and_actions(self) -> None:
        sections = {
            "summary": ["핵심 요약"],
            "decisions": ["비공개 저장소를 사용한다."],
            "criteria_checks": [
                {"id": "RSK-02", "result": "통과", "evidence": "비공개 저장", "action": ""},
            ],
            "todos": ["[ ] Drive 연결 — @담당자 ~2026-07-01 (이슈 #45)"],
        }
        body = fill_template(
            TEMPLATE.read_text(encoding="utf-8"),
            "2026-06-29",
            Path("meetings/raw/2026-06-29_meeting.txt"),
            sections,
        )
        self.assertIn("| RSK-02 | 통과 | 비공개 저장 |", body)
        actions = parse_actions(body)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["issue"], 45)
        self.assertEqual(actions[0]["owner"], "담당자")


if __name__ == "__main__":
    unittest.main()
