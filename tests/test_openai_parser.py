import unittest

from integrations.openai_parser import _build_outcome


class OpenAIParserTests(unittest.TestCase):
    def test_ai_outcome_can_request_clarification(self) -> None:
        outcome = _build_outcome(
            {
                "status": "needs_clarification",
                "clarification_question": "希望する期間はいつですか？",
                "suggested_reply": None,
                "date_start": "2026-08-10",
                "date_end": "2026-08-24",
                "weekdays": None,
                "excluded_weekdays": None,
                "time_start": None,
                "time_end": None,
                "start_time_earliest": None,
                "start_time_latest": None,
                "duration_minutes": 120,
                "duration_explicit": False,
                "duration_min_minutes": None,
                "duration_max_minutes": None,
            },
            120,
        )
        self.assertEqual(outcome.status, "needs_clarification")
        self.assertEqual(outcome.clarification_question, "希望する期間はいつですか？")

    def test_ai_outcome_preserves_exclusions_and_start_range(self) -> None:
        outcome = _build_outcome(
            {
                "status": "resolved",
                "date_start": "2026-08-10",
                "date_end": "2026-08-24",
                "weekdays": [0, 1, 2, 3, 4],
                "excluded_weekdays": [2],
                "time_start": None,
                "time_end": None,
                "start_time_earliest": "18:50",
                "start_time_latest": "19:10",
                "duration_minutes": 60,
                "duration_explicit": True,
                "duration_min_minutes": 60,
                "duration_max_minutes": 120,
            },
            120,
        )
        self.assertEqual(outcome.constraints.excluded_weekdays, frozenset({2}))
        self.assertEqual(outcome.constraints.start_time_earliest.isoformat(), "18:50:00")
        self.assertEqual(outcome.constraints.duration_max_minutes, 120)


if __name__ == "__main__":
    unittest.main()
