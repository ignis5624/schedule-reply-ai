import unittest
from datetime import date, datetime, time

import pandas as pd

from ui.availability_forms import (
    default_recurring_busy,
    parse_weekdays,
    read_direct_availabilities,
    read_one_off_busy_intervals,
    read_recurring_busy_rules,
    read_weekly_availability_rules,
)


class AvailabilityFormTests(unittest.TestCase):
    def test_weekday_input_variants(self) -> None:
        self.assertEqual(parse_weekdays("平日"), frozenset(range(5)))
        self.assertEqual(parse_weekdays("土日"), frozenset({5, 6}))
        self.assertEqual(parse_weekdays("月・水・金"), frozenset({0, 2, 4}))
        self.assertEqual(parse_weekdays("月〜日"), frozenset(range(7)))

    def test_disabled_example_work_does_not_create_a_rule(self) -> None:
        rules, errors = read_recurring_busy_rules(default_recurring_busy())
        self.assertEqual(rules, [])
        self.assertEqual(errors, [])

    def test_recurring_rule_reads_effective_period(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "予定名": "学校",
                    "対象曜日": "月〜金",
                    "開始": time(9),
                    "終了": time(17),
                    "適用開始日": date(2026, 9, 1),
                    "適用終了日": date(2027, 3, 31),
                    "有効": True,
                }
            ]
        )
        rules, errors = read_recurring_busy_rules(frame)
        self.assertEqual(errors, [])
        self.assertEqual(rules[0].weekdays, frozenset(range(5)))
        self.assertEqual(rules[0].effective_start, date(2026, 9, 1))
        self.assertEqual(rules[0].effective_end, date(2027, 3, 31))

    def test_one_off_same_day_end_before_start_becomes_overnight(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "予定名": "夜行バス",
                    "開始日": date(2026, 8, 10),
                    "開始": time(23),
                    "終了日": date(2026, 8, 10),
                    "終了": time(6),
                    "有効": True,
                }
            ]
        )
        intervals, errors = read_one_off_busy_intervals(frame)
        self.assertEqual(errors, [])
        self.assertEqual(intervals[0].start, datetime(2026, 8, 10, 23))
        self.assertEqual(intervals[0].end, datetime(2026, 8, 11, 6))

    def test_legacy_direct_input_still_supports_overnight(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "開始日": date(2026, 8, 10),
                    "開始": time(22),
                    "終了日": date(2026, 8, 10),
                    "終了": time(2),
                }
            ]
        )
        intervals, errors = read_direct_availabilities(frame)
        self.assertEqual(errors, [])
        self.assertEqual(intervals[0].end_datetime, datetime(2026, 8, 11, 2))

    def test_invalid_weekday_and_reversed_period_return_row_errors(self) -> None:
        weekly = pd.DataFrame(
            [{"対象曜日": "休日", "開始": time(9), "終了": time(18), "有効": True}]
        )
        rules, errors = read_weekly_availability_rules(weekly)
        self.assertEqual(rules, [])
        self.assertTrue(errors)

        recurring = pd.DataFrame(
            [
                {
                    "予定名": "学校",
                    "対象曜日": "月",
                    "開始": time(9),
                    "終了": time(18),
                    "適用開始日": date(2026, 9, 2),
                    "適用終了日": date(2026, 9, 1),
                    "有効": True,
                }
            ]
        )
        rules, errors = read_recurring_busy_rules(recurring)
        self.assertEqual(rules, [])
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
