from __future__ import annotations

from datetime import date

from domain.models import ParseOutcome, RequestConstraints

from .ambiguity_parser import classify_request
from .common import normalize_message
from .date_parser import parse_date_constraints
from .duration_parser import extract_duration_details
from .time_parser import extract_time_constraints
from .weekday_parser import combine_week_segment, extract_weekday_constraints


def parse_request(
    message: str,
    today: date,
    default_duration_minutes: int = 120,
) -> RequestConstraints:
    """各専門解析器を束ね、最終的な条件オブジェクトを返す。"""

    normalized = normalize_message(message)
    date_result = parse_date_constraints(normalized, today)
    weekdays, excluded_weekdays = extract_weekday_constraints(normalized)
    weekdays = combine_week_segment(
        normalized,
        weekdays,
        is_week_context=date_result.context == "week",
    )
    time_result = extract_time_constraints(normalized)
    duration_result = extract_duration_details(normalized, default_duration_minutes)

    return RequestConstraints(
        date_start=date_result.date_start,
        date_end=date_result.date_end,
        dates=date_result.dates,
        weekdays=weekdays,
        excluded_weekdays=excluded_weekdays,
        time_start=time_result.time_start,
        time_end=time_result.time_end,
        start_time_earliest=time_result.start_time_earliest,
        start_time_latest=time_result.start_time_latest,
        duration_minutes=duration_result.minutes,
        duration_explicit=duration_result.explicit,
        duration_min_minutes=duration_result.minimum_minutes,
        duration_max_minutes=duration_result.maximum_minutes,
        date_context=date_result.context,
    )


def analyze_request(
    message: str,
    today: date,
    default_duration_minutes: int = 120,
) -> ParseOutcome:
    """通常解析に、曖昧さと会話意図の判定を加える。"""

    normalized = normalize_message(message)
    constraints = parse_request(normalized, today, default_duration_minutes)
    status, question, suggested_reply = classify_request(normalized, constraints)
    return ParseOutcome(
        constraints=constraints,
        status=status,
        clarification_question=question,
        suggested_reply=suggested_reply,
    )
