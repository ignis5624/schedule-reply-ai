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

    minimum_minutes = constraints.duration_min_minutes or constraints.duration_minutes
    duration = timedelta(minutes=minimum_minutes)
    usable_windows: list[tuple[datetime, datetime]] = []

    for slot in sorted(availabilities, key=lambda item: (item.day, item.start)):
        if not (constraints.date_start <= slot.day <= constraints.date_end):
            continue
        if constraints.dates is not None and slot.day not in constraints.dates:
            continue
        if constraints.weekdays is not None and slot.day.weekday() not in constraints.weekdays:
            continue
        if constraints.excluded_weekdays is not None and slot.day.weekday() in constraints.excluded_weekdays:
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

        latest_start: datetime | None = None
        candidate_start = window_start
        candidate_end = window_end
        if constraints.start_time_earliest is not None:
            requested_earliest = datetime.combine(window_start.date(), constraints.start_time_earliest)
            requested_latest = datetime.combine(
                window_start.date(),
                constraints.start_time_latest or constraints.start_time_earliest,
            )
            candidate_start = max(window_start, requested_earliest)
            latest_start = min(window_end - duration, requested_latest)
            if candidate_start > latest_start:
                continue
            candidate_end = latest_start + duration

        maximum_duration: int | None = None
        if (
            constraints.duration_max_minutes is not None
            and constraints.duration_max_minutes > minimum_minutes
        ):
            feasible_minutes = int((window_end - candidate_start).total_seconds() // 60)
            maximum_duration = min(constraints.duration_max_minutes, feasible_minutes)

        candidates.append(
            Candidate(
                start=candidate_start,
                end=candidate_end,
                required_duration_minutes=minimum_minutes,
                duration_explicit=constraints.duration_explicit,
                latest_start=latest_start,
                maximum_duration_minutes=maximum_duration,
            )
        )
        if len(candidates) >= limit:
            break
    return candidates
