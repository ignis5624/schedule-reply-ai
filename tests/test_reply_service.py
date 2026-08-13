import unittest
from datetime import date, time

from domain.models import Availability
from parsers.compound_parser import analyze_grouped_request
from services.candidate_service import find_candidate_groups
from services.reply_service import (
    build_decline_reply,
    build_grouped_reply,
    build_pending_reply,
)


class ReplyServiceTests(unittest.TestCase):
    def test_casual_reply_is_first_person_and_short(self) -> None:
        today = date(2026, 8, 13)
        outcome = analyze_grouped_request("来週の火曜夜に2時間", today)
        groups = find_candidate_groups(
            [Availability(date(2026, 8, 18), time(18), time(22))],
            outcome,
        )

        reply = build_grouped_reply("山田", groups, relation=outcome.relation)

        self.assertIn("空いてる", reply)
        self.assertNotIn("山田さんは", reply)
        self.assertNotIn("本人へ確認", reply)

    def test_tone_can_be_changed_without_changing_candidates(self) -> None:
        today = date(2026, 8, 13)
        outcome = analyze_grouped_request("来週の火曜夜", today)
        groups = find_candidate_groups(
            [Availability(date(2026, 8, 18), time(18), time(22))],
            outcome,
        )

        polite = build_grouped_reply(
            "",
            groups,
            relation=outcome.relation,
            tone="polite",
        )

        self.assertIn("空いています", polite)
        self.assertIn("ご都合", polite)

    def test_pending_and_decline_replies_are_available(self) -> None:
        self.assertIn("また連絡", build_pending_reply())
        self.assertIn("今回は", build_decline_reply())


if __name__ == "__main__":
    unittest.main()
