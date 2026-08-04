from __future__ import annotations

from datetime import date

from domain.models import RequestConstraints

from .common import normalize_message
from .date_parser import parse_date_constraints
from .duration_parser import extract_duration
from .time_parser import extract_time_window
from .weekday_parser import combine_week_segment, extract_weekdays


def parse_request(
    message: str,
    today: date,
    default_duration_minutes: int = 120,
) -> RequestConstraints:
    """各専門解析器を束ね、最終的な条件オブジェクトを返す。"""

    normalized = normalize_message(message)
    date_result = parse_date_constraints(normalized, today)
    weekdays = extract_weekdays(normalized)
    weekdays = combine_week_segment(
        normalized,
        weekdays,
        is_week_context=date_result.context == "week",
    )
    time_start, time_end = extract_time_window(normalized)
    duration_minutes, duration_explicit = extract_duration(normalized, default_duration_minutes)

    return RequestConstraints(
        date_start=date_result.date_start,
        date_end=date_result.date_end,
        dates=date_result.dates,
        weekdays=weekdays,
        time_start=time_start,
        time_end=time_end,
        duration_minutes=duration_minutes,
        duration_explicit=duration_explicit,
    )
