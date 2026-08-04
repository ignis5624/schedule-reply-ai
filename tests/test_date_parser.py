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


if __name__ == "__main__":
    unittest.main()
