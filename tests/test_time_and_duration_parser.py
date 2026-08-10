import unittest
from datetime import date, time

from parsers.request_parser import analyze_request, parse_request


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

    def test_japanese_clock_and_around_start(self) -> None:
        half = parse_request("明日18時半", self.today)
        self.assertEqual(half.start_time_earliest, time(18, 30))
        self.assertEqual(half.start_time_latest, time(18, 30))

        minute_clock = parse_request("明日18時30分", self.today)
        self.assertEqual(minute_clock.start_time_earliest, time(18, 30))
        self.assertFalse(minute_clock.duration_explicit)

        around = parse_request("明日19時前後", self.today)
        self.assertEqual(around.start_time_earliest, time(18, 50))
        self.assertEqual(around.start_time_latest, time(19, 10))

    def test_start_time_and_duration_are_not_misread_as_range(self) -> None:
        parsed = parse_request("18時から2時間", self.today)
        self.assertEqual(parsed.time_start, time(18, 0))
        self.assertIsNone(parsed.time_end)
        self.assertEqual(parsed.duration_minutes, 120)

    def test_duration_range_is_not_a_clock_range(self) -> None:
        parsed = parse_request("1〜2時間", self.today)
        self.assertIsNone(parsed.time_start)
        self.assertIsNone(parsed.time_end)
        self.assertEqual(parsed.duration_min_minutes, 60)
        self.assertEqual(parsed.duration_max_minutes, 120)

    def test_ambiguous_bare_hour_asks_am_or_pm(self) -> None:
        outcome = analyze_request("来週6時", self.today)
        self.assertEqual(outcome.status, "needs_clarification")
        self.assertIn("午前と午後", outcome.clarification_question or "")


if __name__ == "__main__":
    unittest.main()
