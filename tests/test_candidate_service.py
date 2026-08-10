import unittest
from datetime import date, time

from domain.models import Availability
from parsers.request_parser import parse_request
from services.candidate_service import find_candidates
from services.reply_service import format_candidate


class CandidateServiceTests(unittest.TestCase):
    def test_merge_contiguous_slots(self) -> None:
        today = date(2026, 7, 29)
        day = date(2026, 7, 30)
        slots = [
            Availability(day, time(18, 0), time(20, 0)),
            Availability(day, time(20, 0), time(22, 0)),
        ]
        candidates = find_candidates(slots, parse_request("明日2時間", today))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(format_candidate(candidates[0]), "7/30（木）18:00〜22:00の間で2時間")

    def test_excludes_unselected_date(self) -> None:
        today = date(2026, 7, 29)
        slots = [
            Availability(date(2026, 8, 1), time(18, 0), time(22, 0)),
            Availability(date(2026, 8, 2), time(18, 0), time(22, 0)),
            Availability(date(2026, 8, 3), time(18, 0), time(22, 0)),
        ]
        candidates = find_candidates(slots, parse_request("8月1日か8月3日", today))
        self.assertEqual(
            [candidate.start.date() for candidate in candidates],
            [date(2026, 8, 1), date(2026, 8, 3)],
        )

    def test_negative_weekday_is_excluded(self) -> None:
        today = date(2026, 8, 10)
        slots = [
            Availability(date(2026, 8, 11), time(18, 0), time(22, 0)),
            Availability(date(2026, 8, 12), time(18, 0), time(22, 0)),
        ]
        candidates = find_candidates(slots, parse_request("水曜は無理", today))
        self.assertEqual([candidate.start.date() for candidate in candidates], [date(2026, 8, 11)])

    def test_around_time_is_a_start_window(self) -> None:
        today = date(2026, 8, 10)
        slots = [Availability(date(2026, 8, 11), time(18, 0), time(22, 0))]
        candidates = find_candidates(slots, parse_request("明日19時前後", today))
        self.assertEqual(
            format_candidate(candidates[0]),
            "8/11（火）18:50〜19:10開始で2時間",
        )

    def test_duration_range_is_preserved_in_reply(self) -> None:
        today = date(2026, 8, 10)
        slots = [Availability(date(2026, 8, 11), time(18, 0), time(22, 0))]
        candidates = find_candidates(slots, parse_request("明日1〜2時間", today))
        self.assertEqual(
            format_candidate(candidates[0]),
            "8/11（火）18:00〜22:00の間で1時間〜2時間",
        )


if __name__ == "__main__":
    unittest.main()
