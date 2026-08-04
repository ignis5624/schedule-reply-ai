from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from domain.models import Availability, Candidate, RequestConstraints


def _merge_windows(windows: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not windows:
        return []

    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(windows):
        if not merged:
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        if start.date() == previous_start.date() and start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def find_candidates(
    availabilities: Iterable[Availability],
    constraints: RequestConstraints,
    limit: int = 5,
) -> list[Candidate]:
    """登録された空き時間と解析条件を厳密に照合する。"""

    duration = timedelta(minutes=constraints.duration_minutes)
    usable_windows: list[tuple[datetime, datetime]] = []

    for slot in sorted(availabilities, key=lambda item: (item.day, item.start)):
        if not (constraints.date_start <= slot.day <= constraints.date_end):
            continue
        if constraints.dates is not None and slot.day not in constraints.dates:
            continue
        if constraints.weekdays is not None and slot.day.weekday() not in constraints.weekdays:
            continue

        window_start = datetime.combine(slot.day, slot.start)
        window_end = datetime.combine(slot.day, slot.end)
        if constraints.time_start is not None:
            window_start = max(window_start, datetime.combine(slot.day, constraints.time_start))
        if constraints.time_end is not None:
            window_end = min(window_end, datetime.combine(slot.day, constraints.time_end))
        if window_start < window_end:
            usable_windows.append((window_start, window_end))

    candidates: list[Candidate] = []
    for window_start, window_end in _merge_windows(usable_windows):
        if window_end - window_start < duration:
            continue
        candidates.append(
            Candidate(
                start=window_start,
                end=window_end,
                required_duration_minutes=constraints.duration_minutes,
                duration_explicit=constraints.duration_explicit,
            )
        )
        if len(candidates) >= limit:
            break
    return candidates
