import unittest
from datetime import date, time

from scheduler import Availability, find_candidates, format_candidate, parse_request


class SchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today = date(2026, 7, 29)  # 水曜日

    def test_relative_days_and_aliases(self) -> None:
        expected = date(2026, 7, 30)
        for text in ("明日", "あした", "あす"):
            self.assertEqual(parse_request(text, self.today).date_start, expected)
        self.assertEqual(parse_request("明後日", self.today).date_start, date(2026, 7, 31))
        self.assertEqual(parse_request("明々後日", self.today).date_start, date(2026, 8, 1))
        self.assertEqual(parse_request("三日後", self.today).date_start, date(2026, 8, 1))
        self.assertEqual(parse_request("10日後", self.today).date_start, date(2026, 8, 8))
        self.assertEqual(parse_request("二週間後", self.today).date_start, date(2026, 8, 12))

    def test_week_is_sunday_to_saturday(self) -> None:
        this_week = parse_request("今週", self.today)
        self.assertEqual(this_week.date_start, self.today)
        self.assertEqual(this_week.date_end, date(2026, 8, 1))

        next_week = parse_request("来週", self.today)
        self.assertEqual(next_week.date_start, date(2026, 8, 2))
        self.assertEqual(next_week.date_end, date(2026, 8, 8))

    def test_week_first_and_second_half(self) -> None:
        first = parse_request("来週前半", self.today)
        second = parse_request("来週後半", self.today)
        self.assertEqual(first.weekdays, frozenset({6, 0, 1, 2}))
        self.assertEqual(second.weekdays, frozenset({2, 3, 4, 5}))

    def test_week_half_intersects_explicit_weekdays(self) -> None:
        parsed = parse_request("来週前半の月曜か木曜", self.today)
        self.assertEqual(parsed.weekdays, frozenset({0}))

    def test_relative_months_and_month_segments(self) -> None:
        next_month = parse_request("来月", self.today)
        self.assertEqual(next_month.date_start, date(2026, 8, 1))
        self.assertEqual(next_month.date_end, date(2026, 8, 31))

        first_half = parse_request("来月前半", self.today)
        self.assertEqual(first_half.date_start, date(2026, 8, 1))
        self.assertEqual(first_half.date_end, date(2026, 8, 15))

        second_half = parse_request("来月後半", self.today)
        self.assertEqual(second_half.date_start, date(2026, 8, 16))
        self.assertEqual(second_half.date_end, date(2026, 8, 31))

        middle = parse_request("3か月後の中旬", self.today)
        self.assertEqual(middle.date_start, date(2026, 10, 11))
        self.assertEqual(middle.date_end, date(2026, 10, 20))

    def test_explicit_month_and_dates(self) -> None:
        august = parse_request("8月後半", self.today)
        self.assertEqual(august.date_start, date(2026, 8, 16))
        self.assertEqual(august.date_end, date(2026, 8, 31))

        exact = parse_request("8月15日", self.today)
        self.assertEqual(exact.date_start, date(2026, 8, 15))
        self.assertEqual(exact.date_end, date(2026, 8, 15))

        date_range = parse_request("8月1日から5日", self.today)
        self.assertEqual(date_range.date_start, date(2026, 8, 1))
        self.assertEqual(date_range.date_end, date(2026, 8, 5))

    def test_nearest_weekday(self) -> None:
        parsed = parse_request("次の月曜日", self.today)
        self.assertEqual(parsed.date_start, date(2026, 8, 3))
        self.assertEqual(parsed.date_end, date(2026, 8, 3))

    def test_weekday_groups_and_ranges(self) -> None:
        self.assertEqual(parse_request("月水金", self.today).weekdays, frozenset({0, 2, 4}))
        self.assertEqual(parse_request("月曜から水曜", self.today).weekdays, frozenset({0, 1, 2}))
        self.assertEqual(parse_request("土日", self.today).weekdays, frozenset({5, 6}))
        self.assertEqual(parse_request("平日", self.today).weekdays, frozenset({0, 1, 2, 3, 4}))

    def test_time_windows(self) -> None:
        night = parse_request("来週の夜", self.today)
        self.assertEqual(night.time_start, time(18, 0))
        self.assertEqual(night.time_end, time(23, 0))

        after = parse_request("18時以降", self.today)
        self.assertEqual(after.time_start, time(18, 0))
        self.assertIsNone(after.time_end)

        afternoon_range = parse_request("午後3時から午後7時", self.today)
        self.assertEqual(afternoon_range.time_start, time(15, 0))
        self.assertEqual(afternoon_range.time_end, time(19, 0))

    def test_durations(self) -> None:
        self.assertEqual(parse_request("二時間半", self.today).duration_minutes, 150)
        self.assertEqual(parse_request("1時間30分", self.today).duration_minutes, 90)
        self.assertEqual(parse_request("90分", self.today).duration_minutes, 90)
        self.assertEqual(parse_request("1.5h", self.today).duration_minutes, 90)

    def test_multiple_specific_dates_do_not_include_days_between(self) -> None:
        parsed = parse_request("8月1日か8月3日", self.today)
        self.assertEqual(parsed.dates, frozenset({date(2026, 8, 1), date(2026, 8, 3)}))
        slots = [
            Availability(date(2026, 8, 1), time(18, 0), time(22, 0)),
            Availability(date(2026, 8, 2), time(18, 0), time(22, 0)),
            Availability(date(2026, 8, 3), time(18, 0), time(22, 0)),
        ]
        candidates = find_candidates(slots, parsed)
        self.assertEqual([candidate.start.date() for candidate in candidates], [date(2026, 8, 1), date(2026, 8, 3)])

    def test_multiple_relative_dates(self) -> None:
        parsed = parse_request("明日か明後日", self.today)
        self.assertEqual(parsed.dates, frozenset({date(2026, 7, 30), date(2026, 7, 31)}))

    def test_colon_time_range(self) -> None:
        parsed = parse_request("18:30〜22:00", self.today)
        self.assertEqual(parsed.time_start, time(18, 30))
        self.assertEqual(parsed.time_end, time(22, 0))

    def test_kanji_explicit_date(self) -> None:
        parsed = parse_request("八月十五日", self.today)
        self.assertEqual(parsed.date_start, date(2026, 8, 15))

    def test_merge_contiguous_slots(self) -> None:
        day = date(2026, 7, 30)
        slots = [
            Availability(day, time(18, 0), time(20, 0)),
            Availability(day, time(20, 0), time(22, 0)),
        ]
        constraints = parse_request("明日2時間", self.today)
        candidates = find_candidates(slots, constraints)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(format_candidate(candidates[0]), "7/30（木）18:00〜22:00の間で2時間")


if __name__ == "__main__":
    unittest.main()
