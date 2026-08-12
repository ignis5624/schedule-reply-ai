from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from domain.models import (
    Availability,
    Candidate,
    CandidateGroup,
    ConstraintGroup,
    ParseOutcome,
    RequestConstraints,
)


def _merge_windows(windows: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not windows:
        return []

    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(windows):
        if not merged:
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        if start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def _merge_windows_within_day(
    windows: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """開始時刻指定では日ごとの候補を残し、同日内のみ結合する。"""

    grouped: dict[object, list[tuple[datetime, datetime]]] = {}
    for start, end in windows:
        grouped.setdefault(start.date(), []).append((start, end))
    results: list[tuple[datetime, datetime]] = []
    for day in sorted(grouped):
        results.extend(_merge_windows(grouped[day]))
    return results


def find_candidates(
    availabilities: Iterable[Availability],
    constraints: RequestConstraints,
    limit: int = 5,
) -> list[Candidate]:
    """登録された空き時間と解析条件を厳密に照合する。"""

    minimum_minutes = constraints.duration_min_minutes or constraints.duration_minutes
    duration = timedelta(minutes=minimum_minutes)
    duration_ceiling = timedelta(
        minutes=constraints.duration_max_minutes or minimum_minutes
    )
    usable_windows: list[tuple[datetime, datetime]] = []

    for slot in sorted(availabilities, key=lambda item: item.start_datetime):
        first_day = max(slot.start_datetime.date(), constraints.date_start)
        last_slot_day = (slot.end_datetime - timedelta(microseconds=1)).date()
        last_day = min(last_slot_day, constraints.date_end)
        if first_day > last_day:
            continue

        day = first_day
        while day <= last_day:
            is_allowed = not (
                (constraints.dates is not None and day not in constraints.dates)
                or (constraints.weekdays is not None and day.weekday() not in constraints.weekdays)
                or (
                    constraints.excluded_weekdays is not None
                    and day.weekday() in constraints.excluded_weekdays
                )
            )
            if is_allowed:
                day_start = datetime.combine(day, datetime.min.time())
                next_day_start = day_start + timedelta(days=1)
                if constraints.time_spans_next_day and constraints.time_start is not None:
                    requested_start = datetime.combine(day, constraints.time_start)
                    requested_end = datetime.combine(
                        day + timedelta(days=1),
                        constraints.time_end or constraints.time_start,
                    )
                else:
                    requested_start = (
                        datetime.combine(day, constraints.time_start)
                        if constraints.time_start is not None
                        else day_start
                    )
                    requested_end = (
                        datetime.combine(day, constraints.time_end)
                        if constraints.time_end is not None
                        else next_day_start
                    )
                    if constraints.time_start is not None and constraints.time_end is None:
                        requested_end += duration_ceiling
                    if constraints.start_time_earliest is not None:
                        requested_end += duration_ceiling
                window_start = max(slot.start_datetime, requested_start)
                window_end = min(slot.end_datetime, requested_end)
                if window_start < window_end:
                    usable_windows.append((window_start, window_end))
            day += timedelta(days=1)

    candidates: list[Candidate] = []
    merged_windows = (
        _merge_windows_within_day(usable_windows)
        if constraints.start_time_earliest is not None
        else _merge_windows(usable_windows)
    )
    for window_start, window_end in merged_windows:
        if window_end - window_start < duration:
            continue

        latest_start: datetime | None = None
        candidate_start = window_start
        candidate_end = window_end
        if constraints.start_time_earliest is not None:
            requested_day = window_start.date()
            requested_latest = datetime.combine(
                requested_day,
                constraints.start_time_latest or constraints.start_time_earliest,
            )
            requested_earliest = datetime.combine(requested_day, constraints.start_time_earliest)
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
                duration_mode=constraints.duration_mode,
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


def find_candidate_groups(
    availabilities: Iterable[Availability],
    outcome: ParseOutcome,
    limit_per_group: int = 3,
) -> list[CandidateGroup]:
    """条件グループを混ぜず、優先順位順に候補を計算する。"""

    slots = list(availabilities)
    groups = outcome.groups or (
        ConstraintGroup(constraints=outcome.constraints, priority=1),
    )
    results: list[CandidateGroup] = []
    for group in sorted(enumerate(groups), key=lambda item: (item[1].priority, item[0])):
        _, value = group
        candidates = find_candidates(slots, value.constraints, limit=limit_per_group)
        results.append(
            CandidateGroup(
                priority=value.priority,
                label=value.label,
                source_text=value.source_text,
                candidates=tuple(candidates),
            )
        )
    return results
