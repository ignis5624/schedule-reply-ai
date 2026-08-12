import unittest
from datetime import date, time

from domain.models import Availability
from parsers.compound_parser import analyze_grouped_request
from services.candidate_service import find_candidate_groups
from services.reply_service import build_grouped_reply, format_candidate


class CompoundParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today = date(2026, 8, 10)

    def test_paired_weekday_and_time_are_separate_groups(self) -> None:
        outcome = analyze_grouped_request("火曜の夜か水曜の午前", self.today)
        self.assertEqual(outcome.status, "resolved")
        self.assertEqual(outcome.relation, "alternative")
        self.assertEqual(len(outcome.groups), 2)
        self.assertEqual(outcome.groups[0].constraints.weekdays, frozenset({1}))
        self.assertEqual(outcome.groups[0].constraints.time_start, time(18, 0))
        self.assertEqual(outcome.groups[1].constraints.weekdays, frozenset({2}))
        self.assertEqual(outcome.groups[1].constraints.time_end, time(12, 0))

    def test_tail_time_is_shared_between_same_kind_alternatives(self) -> None:
        outcome = analyze_grouped_request("火曜か水曜の夜", self.today)
        self.assertEqual(outcome.status, "resolved")
        self.assertEqual(len(outcome.groups), 2)
        self.assertTrue(all(group.constraints.time_start == time(18, 0) for group in outcome.groups))

    def test_shared_week_context_is_inherited(self) -> None:
        outcome = analyze_grouped_request("来週火曜か水曜の夜", self.today)
        self.assertEqual(outcome.status, "resolved")
        self.assertEqual(outcome.groups[0].constraints.date_start, date(2026, 8, 16))
        self.assertEqual(outcome.groups[1].constraints.date_start, date(2026, 8, 16))

    def test_scope_ambiguity_asks_question(self) -> None:
        outcome = analyze_grouped_request("火曜の夜か水曜", self.today)
        self.assertEqual(outcome.status, "needs_clarification")
        self.assertIn("時間指定", outcome.clarification_question or "")

        mixed = analyze_grouped_request("明日か金曜の19時", self.today)
        self.assertEqual(mixed.status, "needs_clarification")

    def test_conditional_clauses_keep_their_own_times(self) -> None:
        outcome = analyze_grouped_request(
            "月曜なら18時以降、火曜なら20時以降",
            self.today,
        )
        self.assertEqual(len(outcome.groups), 2)
        self.assertEqual(outcome.groups[0].constraints.time_start, time(18, 0))
        self.assertEqual(outcome.groups[1].constraints.time_start, time(20, 0))

    def test_shared_time_does_not_overwrite_group_durations(self) -> None:
        outcome = analyze_grouped_request(
            "火曜1時間または木曜2時間、どちらも18時以降",
            self.today,
        )
        self.assertEqual(outcome.groups[0].constraints.duration_minutes, 60)
        self.assertEqual(outcome.groups[1].constraints.duration_minutes, 120)
        self.assertTrue(all(group.constraints.time_start == time(18, 0) for group in outcome.groups))

    def test_priority_and_fallback_are_preserved(self) -> None:
        outcome = analyze_grouped_request("できれば火曜、無理なら水曜", self.today)
        self.assertEqual(outcome.relation, "preference")
        self.assertEqual([group.priority for group in outcome.groups], [1, 2])
        self.assertEqual([group.label for group in outcome.groups], ["第一希望", "第二希望"])

        explicit = analyze_grouped_request(
            "第一希望は金曜の夜、第二希望は土曜の午後",
            self.today,
        )
        self.assertEqual([group.priority for group in explicit.groups], [1, 2])

    def test_multiple_required_schedule_asks_question(self) -> None:
        outcome = analyze_grouped_request("火曜と水曜の両方", self.today)
        self.assertEqual(outcome.status, "needs_clarification")
        self.assertIn("複数回", outcome.clarification_question or "")

    def test_candidates_do_not_cross_mix_group_conditions(self) -> None:
        outcome = analyze_grouped_request("火曜の夜か水曜の午前", self.today)
        slots = [
            Availability(date(2026, 8, 11), time(9, 0), time(12, 0)),
            Availability(date(2026, 8, 11), time(18, 0), time(22, 0)),
            Availability(date(2026, 8, 12), time(9, 0), time(12, 0)),
            Availability(date(2026, 8, 12), time(18, 0), time(22, 0)),
        ]
        groups = find_candidate_groups(slots, outcome)
        self.assertEqual(
            [format_candidate(candidate) for candidate in groups[0].candidates],
            ["8/11（火）18:00〜22:00"],
        )
        self.assertEqual(
            [format_candidate(candidate) for candidate in groups[1].candidates],
            ["8/12（水）09:00〜12:00"],
        )
        reply = build_grouped_reply("山田", groups, relation=outcome.relation)
        self.assertIn("8/11", reply)
        self.assertIn("8/12", reply)

    def test_reply_lists_preferred_group_first(self) -> None:
        outcome = analyze_grouped_request("できれば火曜、無理なら水曜", self.today)
        slots = [
            Availability(date(2026, 8, 11), time(18, 0), time(22, 0)),
            Availability(date(2026, 8, 12), time(18, 0), time(22, 0)),
        ]
        groups = find_candidate_groups(slots, outcome)
        reply = build_grouped_reply("山田", groups, relation=outcome.relation)
        self.assertLess(reply.index("第一希望"), reply.index("第二希望"))

        fallback_only = find_candidate_groups(
            [Availability(date(2026, 8, 12), time(18, 0), time(22, 0))],
            outcome,
        )
        fallback_reply = build_grouped_reply(
            "山田",
            fallback_only,
            relation=outcome.relation,
        )
        self.assertIn("第一希望では条件に合う時間が見つかりません", fallback_reply)


if __name__ == "__main__":
    unittest.main()
