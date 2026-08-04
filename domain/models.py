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
    time_start: time | None = None
    time_end: time | None = None
    duration_minutes: int = 120
    duration_explicit: bool = False


@dataclass(frozen=True)
class Candidate:
    """条件照合後の候補時間帯。"""

    start: datetime
    end: datetime
    required_duration_minutes: int = 120
    duration_explicit: bool = False
