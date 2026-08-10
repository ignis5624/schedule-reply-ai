import unittest
from datetime import date

from parsers.request_parser import parse_request


class DateParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today = date(2026, 7, 29)

    def test_relative_days_and_aliases(self) -> None:
        self.assertEqual(parse_request("明日", self.today).date_start, date(2026, 7, 30))
        self.assertEqual(parse_request("あした", self.today).date_start, date(2026, 7, 30))
        self.assertEqual(parse_request("明々後日", self.today).date_start, date(2026, 8, 1))
        self.assertEqual(parse_request("三日後", self.today).date_start, date(2026, 8, 1))
        self.assertEqual(parse_request("二週間後", self.today).date_start, date(2026, 8, 12))

    def test_week_rules(self) -> None:
        parsed = parse_request("来週前半", self.today)
        self.assertEqual(parsed.date_start, date(2026, 8, 2))
        self.assertEqual(parsed.date_end, date(2026, 8, 8))
        self.assertEqual(parsed.weekdays, frozenset({6, 0, 1, 2}))

    def test_month_rules(self) -> None:
        self.assertEqual(parse_request("来月前半", self.today).date_end, date(2026, 8, 15))
        self.assertEqual(parse_request("3か月後の中旬", self.today).date_start, date(2026, 10, 11))

    def test_multiple_dates_do_not_include_between(self) -> None:
        parsed = parse_request("8月1日か8月3日", self.today)
        self.assertEqual(parsed.dates, frozenset({date(2026, 8, 1), date(2026, 8, 3)}))

    def test_week_beginning_is_monday_and_tuesday(self) -> None:
        parsed = parse_request("来週明け", self.today)
        self.assertEqual(parsed.date_start, date(2026, 8, 2))
        self.assertEqual(parsed.date_end, date(2026, 8, 8))
        self.assertEqual(parsed.weekdays, frozenset({0, 1}))

    def test_month_beginning_and_end_rules(self) -> None:
        beginning = parse_request("来月の月初", self.today)
        self.assertEqual(beginning.date_start, date(2026, 8, 1))
        self.assertEqual(beginning.date_end, date(2026, 8, 5))

        ending = parse_request("来月末", self.today)
        self.assertEqual(ending.date_start, date(2026, 8, 25))
        self.assertEqual(ending.date_end, date(2026, 8, 31))

        final_week = parse_request("来月の最終週", self.today)
        self.assertEqual(final_week.date_start, date(2026, 8, 30))
        self.assertEqual(final_week.date_end, date(2026, 8, 31))

    def test_day_without_month_and_open_ended_date(self) -> None:
        self.assertEqual(parse_request("30日", self.today).date_start, date(2026, 7, 30))
        after = parse_request("明日以降", self.today)
        self.assertEqual(after.date_start, date(2026, 7, 30))
        self.assertEqual(after.date_end, date.max)

        until = parse_request("明日まで", self.today)
        self.assertEqual(until.date_start, self.today)
        self.assertEqual(until.date_end, date(2026, 7, 30))


if __name__ == "__main__":
    unittest.main()
