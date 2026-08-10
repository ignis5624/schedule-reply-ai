from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass(frozen=True)
class Availability:
    """利用者が空いている1つの時間帯。"""

    day: date
    start: time
    end: time


@dataclass(frozen=True)
class RequestConstraints:
    """メッセージから抽出した日程条件。"""

    date_start: date
    date_end: date
    dates: frozenset[date] | None = None
    weekdays: frozenset[int] | None = None
    excluded_weekdays: frozenset[int] | None = None
    time_start: time | None = None
    time_end: time | None = None
    start_time_earliest: time | None = None
    start_time_latest: time | None = None
    duration_minutes: int = 120
    duration_explicit: bool = False
    duration_min_minutes: int | None = None
    duration_max_minutes: int | None = None
    date_context: str = "default"


@dataclass(frozen=True)
class ParseOutcome:
    """解析結果と、返信前に必要な確認をまとめたもの。"""

    constraints: RequestConstraints
    status: str = "resolved"
    clarification_question: str | None = None
    suggested_reply: str | None = None


@dataclass(frozen=True)
class Candidate:
    """条件照合後の候補時間帯。"""

    start: datetime
    end: datetime
    required_duration_minutes: int = 120
    duration_explicit: bool = False
    latest_start: datetime | None = None
    maximum_duration_minutes: int | None = None
