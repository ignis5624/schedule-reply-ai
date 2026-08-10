import unittest
from datetime import date

from parsers.request_parser import analyze_request


class AmbiguityParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today = date(2026, 8, 10)

    def test_vague_scheduling_request_asks_for_period(self) -> None:
        outcome = analyze_request("近いうち空いてる？", self.today)
        self.assertEqual(outcome.status, "needs_clarification")
        self.assertIn("今週・来週・今月", outcome.clarification_question or "")

    def test_soft_invitation_does_not_generate_dates(self) -> None:
        outcome = analyze_request("また今度ご飯に行きましょう", self.today)
        self.assertEqual(outcome.status, "soft_invitation")
        self.assertIsNotNone(outcome.suggested_reply)

    def test_concrete_date_overrides_vague_word(self) -> None:
        outcome = analyze_request("今度、来週火曜の夜はどう？", self.today)
        self.assertEqual(outcome.status, "resolved")

    def test_night_until_asks_for_exact_end(self) -> None:
        outcome = analyze_request("来週は夜までなら大丈夫", self.today)
        self.assertEqual(outcome.status, "needs_clarification")
        self.assertIn("何時まで", outcome.clarification_question or "")


if __name__ == "__main__":
    unittest.main()
