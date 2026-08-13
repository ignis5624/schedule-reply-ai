import unittest
from datetime import date, datetime, time

from domain.models import Availability, BusyInterval, RecurringBusyRule, WeeklyAvailabilityRule
from parsers.request_parser import parse_request
from services.availability_service import (
    build_availabilities,
    subtract_busy_from_availabilities,
)
from services.candidate_service import find_candidates


class AvailabilityServiceTests(unittest.TestCase):
    def test_calendar_busy_can_be_subtracted_from_direct_availability(self) -> None:
        slots = [Availability(date(2026, 8, 20), time(18), time(22))]
        busy = [
            BusyInterval(
                datetime(2026, 8, 20, 19),
                datetime(2026, 8, 20, 20),
                source="google_calendar",
            )
        ]

        actual = subtract_busy_from_availabilities(slots, busy)

        self.assertEqual(
            [(value.start, value.end) for value in actual],
            [(time(18), time(19)), (time(20), time(22))],
        )

    def test_work_is_subtracted_from_normal_hours(self) -> None:
        day = date(2026, 8, 10)  # 月曜日
        actual = build_availabilities(
            [WeeklyAvailabilityRule(frozenset({0}), time(6), time(0))],
            recurring_busy_rules=[
                RecurringBusyRule(frozenset({0}), time(9), time(18), label="仕事")
            ],
            date_start=day,
            date_end=day,
        )
        self.assertEqual(
            [(value.start_datetime, value.end_datetime) for value in actual],
            [
                (datetime(2026, 8, 10, 6), datetime(2026, 8, 10, 9)),
                (datetime(2026, 8, 10, 18), datetime(2026, 8, 11, 0)),
            ],
        )

    def test_overlapping_busy_rules_are_merged_before_subtraction(self) -> None:
        day = date(2026, 8, 10)
        actual = build_availabilities(
            [WeeklyAvailabilityRule(frozenset({0}), time(8), time(22))],
            recurring_busy_rules=[
                RecurringBusyRule(frozenset({0}), time(9), time(15), label="学校"),
                RecurringBusyRule(frozenset({0}), time(14), time(18), label="仕事"),
            ],
            date_start=day,
            date_end=day,
        )
        self.assertEqual(
            [(value.start, value.end) for value in actual],
            [(time(8), time(9)), (time(18), time(22))],
        )

    def test_one_off_busy_uses_the_same_subtraction_path_as_calendar_busy(self) -> None:
        day = date(2026, 8, 10)
        actual = build_availabilities(
            [WeeklyAvailabilityRule(frozenset({0}), time(18), time(23))],
            busy_intervals=[
                BusyInterval(
                    datetime(2026, 8, 10, 19),
                    datetime(2026, 8, 10, 20, 30),
                    label="食事",
                    source="google_calendar",
                )
            ],
            date_start=day,
            date_end=day,
        )
        self.assertEqual(
            [(value.start_datetime, value.end_datetime) for value in actual],
            [
                (datetime(2026, 8, 10, 18), datetime(2026, 8, 10, 19)),
                (datetime(2026, 8, 10, 20, 30), datetime(2026, 8, 10, 23)),
            ],
        )

    def test_previous_day_overnight_busy_affects_period_start(self) -> None:
        monday = date(2026, 8, 10)
        actual = build_availabilities(
            [WeeklyAvailabilityRule(frozenset({0}), time(0), time(6))],
            recurring_busy_rules=[
                RecurringBusyRule(frozenset({6}), time(22), time(2), label="夜勤")
            ],
            date_start=monday,
            date_end=monday,
        )
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0].start_datetime, datetime(2026, 8, 10, 2))
        self.assertEqual(actual[0].end_datetime, datetime(2026, 8, 10, 6))

    def test_effective_dates_and_disabled_rules_are_respected(self) -> None:
        actual = build_availabilities(
            [WeeklyAvailabilityRule(frozenset({0, 1}), time(18), time(22))],
            recurring_busy_rules=[
                RecurringBusyRule(
                    frozenset({0, 1}),
                    time(18),
                    time(20),
                    label="夏期講習",
                    effective_start=date(2026, 8, 11),
                    effective_end=date(2026, 8, 11),
                ),
                RecurringBusyRule(
                    frozenset({0, 1}),
                    time(20),
                    time(22),
                    enabled=False,
                ),
            ],
            date_start=date(2026, 8, 10),
            date_end=date(2026, 8, 11),
        )
        self.assertEqual(
            [(value.start_datetime, value.end_datetime) for value in actual],
            [
                (datetime(2026, 8, 10, 18), datetime(2026, 8, 10, 22)),
                (datetime(2026, 8, 11, 20), datetime(2026, 8, 11, 22)),
            ],
        )

    def test_fully_busy_window_produces_no_availability(self) -> None:
        day = date(2026, 8, 10)
        actual = build_availabilities(
            [WeeklyAvailabilityRule(frozenset({0}), time(9), time(18))],
            recurring_busy_rules=[
                RecurringBusyRule(frozenset({0}), time(8), time(20))
            ],
            date_start=day,
            date_end=day,
        )
        self.assertEqual(actual, [])

    def test_generated_availability_flows_into_existing_candidate_service(self) -> None:
        today = date(2026, 8, 9)
        monday = date(2026, 8, 10)
        actual = build_availabilities(
            [WeeklyAvailabilityRule(frozenset({0}), time(6), time(0))],
            recurring_busy_rules=[
                RecurringBusyRule(frozenset({0}), time(9), time(18), label="仕事")
            ],
            date_start=monday,
            date_end=monday,
        )
        candidates = find_candidates(actual, parse_request("明日の夜に2時間", today))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].start, datetime(2026, 8, 10, 18))
        self.assertEqual(candidates[0].end, datetime(2026, 8, 10, 23))


if __name__ == "__main__":
    unittest.main()
