import unittest
from datetime import date, time

from parsers.request_parser import parse_request


class TimeAndDurationParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today = date(2026, 7, 29)

    def test_time_windows(self) -> None:
        night = parse_request("来週の夜", self.today)
        self.assertEqual(night.time_start, time(18, 0))
        self.assertEqual(night.time_end, time(23, 0))

        after = parse_request("18時以降", self.today)
        self.assertEqual(after.time_start, time(18, 0))
        self.assertIsNone(after.time_end)

        exact_range = parse_request("18:30〜22:00", self.today)
        self.assertEqual(exact_range.time_start, time(18, 30))
        self.assertEqual(exact_range.time_end, time(22, 0))

    def test_durations(self) -> None:
        self.assertEqual(parse_request("二時間半", self.today).duration_minutes, 150)
        self.assertEqual(parse_request("1時間30分", self.today).duration_minutes, 90)
        self.assertEqual(parse_request("1.5h", self.today).duration_minutes, 90)


if __name__ == "__main__":
    unittest.main()
