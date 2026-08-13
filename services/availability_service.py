from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

from domain.models import (
    Availability,
    BusyInterval,
    RecurringBusyRule,
    WeeklyAvailabilityRule,
)


DatetimeInterval = tuple[datetime, datetime]


def _merge_intervals(intervals: Iterable[DatetimeInterval]) -> list[DatetimeInterval]:
    """重複・連続する区間を1つにまとめる。"""

    merged: list[DatetimeInterval] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        merged[-1] = previous_start, max(previous_end, end)
    return merged


def subtract_busy_intervals(
    base_intervals: Iterable[DatetimeInterval],
    busy_intervals: Iterable[DatetimeInterval],
) -> list[DatetimeInterval]:
    """対応可能区間からbusy区間を差し引く。"""

    bases = _merge_intervals(base_intervals)
    busy = _merge_intervals(busy_intervals)
    available: list[DatetimeInterval] = []

    for base_start, base_end in bases:
        cursor = base_start
        for busy_start, busy_end in busy:
            if busy_end <= cursor:
                continue
            if busy_start >= base_end:
                break
            if busy_start > cursor:
                available.append((cursor, min(busy_start, base_end)))
            cursor = max(cursor, busy_end)
            if cursor >= base_end:
                break
        if cursor < base_end:
            available.append((cursor, base_end))
    return available


def subtract_busy_from_availabilities(
    availabilities: Iterable[Availability],
    busy_intervals: Iterable[BusyInterval],
) -> list[Availability]:
    """従来の直接登録方式にも、外部カレンダー等のbusyを適用する。"""

    actual_windows = subtract_busy_intervals(
        ((slot.start_datetime, slot.end_datetime) for slot in availabilities),
        ((interval.start, interval.end) for interval in busy_intervals),
    )
    return [
        Availability(
            day=start.date(),
            start=start.time(),
            end=end.time(),
            end_day=end.date(),
        )
        for start, end in actual_windows
    ]


def build_availabilities(
    weekly_rules: Iterable[WeeklyAvailabilityRule],
    *,
    recurring_busy_rules: Iterable[RecurringBusyRule] = (),
    busy_intervals: Iterable[BusyInterval] = (),
    date_start: date,
    date_end: date,
) -> list[Availability]:
    """通常対応時間から固定・単発busyを差し引き、実際の空き時間を返す。"""

    if date_start > date_end:
        raise ValueError("生成期間の開始日は終了日以前にしてください。")

    weekly = tuple(weekly_rules)
    recurring = tuple(recurring_busy_rules)
    one_off = tuple(busy_intervals)

    base_windows: list[DatetimeInterval] = []
    day = date_start
    while day <= date_end:
        base_windows.extend(rule.interval_on(day) for rule in weekly if rule.applies_on(day))
        day += timedelta(days=1)

    busy_windows: list[DatetimeInterval] = [
        (interval.start, interval.end) for interval in one_off
    ]
    # 前日開始の日付またぎbusyが期間初日にかかる場合も含める。
    day = date_start - timedelta(days=1)
    while day <= date_end:
        busy_windows.extend(rule.interval_on(day) for rule in recurring if rule.applies_on(day))
        day += timedelta(days=1)

    actual_windows = subtract_busy_intervals(base_windows, busy_windows)
    return [
        Availability(
            day=start.date(),
            start=start.time(),
            end=end.time(),
            end_day=end.date(),
        )
        for start, end in actual_windows
    ]
