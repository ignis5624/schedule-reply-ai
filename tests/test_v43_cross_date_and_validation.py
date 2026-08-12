import unittest
from datetime import date, datetime, time

from domain.models import Availability
from parsers.compound_parser import analyze_grouped_request
from parsers.request_parser import analyze_request, parse_request
from services.candidate_service import find_candidates
from services.reply_service import format_candidate


class CrossDateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today = date(2026, 8, 10)

    def test_availability_keeps_legacy_constructor_and_supports_overnight(self) -> None:
        legacy = Availability(date(2026, 8, 11), time(22, 0), time(2, 0))
        self.assertEqual(legacy.end_datetime, datetime(2026, 8, 12, 2, 0))

        multi_day = Availability(
            date(2026, 8, 11),
            time(9, 0),
            time(18, 0),
            date(2026, 8, 13),
        )
        self.assertEqual(multi_day.end_datetime, datetime(2026, 8, 13, 18, 0))

    def test_invalid_explicit_end_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Availability(
                date(2026, 8, 11),
                time(22, 0),
                time(2, 0),
                date(2026, 8, 11),
            )

    def test_overnight_request_and_reply(self) -> None:
        constraints = parse_request("明日22時から翌1時", self.today, 120)
        self.assertTrue(constraints.time_spans_next_day)
        slots = [Availability(date(2026, 8, 11), time(21, 0), time(2, 0))]
        candidates = find_candidates(slots, constraints)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(format_candidate(candidates[0]), "8/11（火）22:00〜翌01:00")

    def test_multi_day_duration_uses_one_continuous_window(self) -> None:
        slots = [
            Availability(
                date(2026, 8, 10),
                time(9, 0),
                time(18, 0),
                date(2026, 8, 13),
            )
        ]
        candidates = find_candidates(slots, parse_request("3日間連続", self.today))
        self.assertEqual(len(candidates), 1)
        self.assertIn("間で3日間", format_candidate(candidates[0]))

    def test_exact_start_can_continue_past_midnight(self) -> None:
        slots = [Availability(date(2026, 8, 11), time(22, 0), time(2, 0))]
        candidates = find_candidates(slots, parse_request("明日23時開始で2時間", self.today))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].end, datetime(2026, 8, 12, 1, 0))


class ExpandedExpressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today = date(2026, 8, 10)

    def test_relative_period_date_list_and_dot_date(self) -> None:
        period = parse_request("明日から3日間", self.today)
        self.assertEqual((period.date_start, period.date_end), (date(2026, 8, 11), date(2026, 8, 13)))

        within = parse_request("3日以内", self.today)
        self.assertEqual((within.date_start, within.date_end), (self.today, date(2026, 8, 13)))

        listed = parse_request("8月15、16、18日", self.today)
        self.assertEqual(
            listed.dates,
            frozenset({date(2026, 8, 15), date(2026, 8, 16), date(2026, 8, 18)}),
        )
        self.assertEqual(parse_request("2026.8.20", self.today).date_start, date(2026, 8, 20))

    def test_named_dates_and_month_week(self) -> None:
        self.assertEqual(parse_request("今夜", self.today).date_start, self.today)
        self.assertEqual(parse_request("明朝", self.today).date_start, date(2026, 8, 11))
        second_week = parse_request("来月第2週", self.today)
        self.assertEqual((second_week.date_start, second_week.date_end), (date(2026, 9, 6), date(2026, 9, 12)))
        second_saturday = parse_request("来月第2土曜", self.today)
        self.assertEqual((second_saturday.date_start, second_saturday.date_end), (date(2026, 9, 12), date(2026, 9, 12)))

    def test_duration_qualifiers_and_multi_day_duration(self) -> None:
        maximum = parse_request("1時間以内", self.today)
        self.assertEqual((maximum.duration_min_minutes, maximum.duration_max_minutes), (15, 60))
        self.assertEqual(maximum.duration_mode, "maximum")

        minimum = parse_request("1時間以上", self.today)
        self.assertEqual((minimum.duration_min_minutes, minimum.duration_max_minutes), (60, None))
        self.assertEqual(minimum.duration_mode, "minimum")

        duration_range = parse_request("1時間半〜2時間半", self.today)
        self.assertEqual((duration_range.duration_min_minutes, duration_range.duration_max_minutes), (90, 150))
        self.assertEqual(parse_request("2泊3日", self.today).duration_minutes, 4320)
        self.assertEqual(parse_request("丸1日", self.today).duration_minutes, 1440)

    def test_time_variants(self) -> None:
        before = parse_request("18時前", self.today)
        self.assertEqual(before.time_end, time(18, 0))
        self.assertEqual((parse_request("昼前", self.today).time_start, parse_request("昼前", self.today).time_end), (time(10), time(12)))
        self.assertEqual((parse_request("午後イチ", self.today).time_start, parse_request("午後イチ", self.today).time_end), (time(12), time(14)))
        deep_night = parse_request("深夜1時", self.today)
        self.assertEqual(deep_night.start_time_earliest, time(1, 0))
        next_morning = parse_request("22時から翌朝1時", self.today)
        self.assertEqual((next_morning.time_start, next_morning.time_end), (time(22), time(1)))
        self.assertTrue(next_morning.time_spans_next_day)

    def test_multiple_excluded_weekdays(self) -> None:
        parsed = parse_request("火曜と木曜以外", self.today)
        self.assertIsNone(parsed.weekdays)
        self.assertEqual(parsed.excluded_weekdays, frozenset({1, 3}))


class ValidationAndGroupingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today = date(2026, 8, 10)

    def test_unrecognized_or_unsupported_expressions_ask(self) -> None:
        for message in ("仕事終わり", "数時間", "祝日以外", "適当な時間", "1時間弱"):
            with self.subTest(message=message):
                self.assertEqual(analyze_request(message, self.today).status, "needs_clarification")

    def test_soft_invitation_and_contradiction(self) -> None:
        self.assertEqual(analyze_request("またいつか", self.today).status, "soft_invitation")
        mismatch = analyze_request("2026年8月11日水曜", self.today)
        self.assertEqual(mismatch.status, "needs_clarification")
        self.assertIn("一致しません", mismatch.clarification_question or "")
        past = analyze_request("2025年8月11日", self.today)
        self.assertEqual(past.status, "needs_clarification")
        self.assertIn("過去", past.clarification_question or "")

    def test_alternative_spellings_and_shared_suffix(self) -> None:
        for message in ("火曜の夜又は水曜の午前", "火曜の夜 or 水曜の午前", "火曜の夜、水曜の午前"):
            with self.subTest(message=message):
                outcome = analyze_grouped_request(message, self.today)
                self.assertEqual(outcome.status, "resolved")
                self.assertEqual(len(outcome.groups), 2)

        shared = analyze_grouped_request("来週か再来週、平日の夜", self.today)
        self.assertEqual(len(shared.groups), 2)
        self.assertTrue(all(group.constraints.weekdays == frozenset(range(5)) for group in shared.groups))

    def test_three_priorities_are_preserved(self) -> None:
        outcome = analyze_grouped_request(
            "第一候補は火曜、第二候補は水曜、第三候補は木曜", self.today
        )
        self.assertEqual(outcome.relation, "preference")
        self.assertEqual([group.priority for group in outcome.groups], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
