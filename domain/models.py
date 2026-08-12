from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


@dataclass(frozen=True)
class Availability:
    """利用者が空いている1つの時間帯。終了日は省略時に自動決定する。"""

    day: date
    start: time
    end: time
    end_day: date | None = None

    def __post_init__(self) -> None:
        if self.end_day is not None and self.end_datetime <= self.start_datetime:
            raise ValueError("空き時間の終了は開始より後にしてください。")

    @property
    def start_datetime(self) -> datetime:
        return datetime.combine(self.day, self.start)

    @property
    def end_datetime(self) -> datetime:
        resolved_day = self.end_day
        if resolved_day is None:
            resolved_day = self.day + timedelta(days=1) if self.end <= self.start else self.day
        return datetime.combine(resolved_day, self.end)


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
    time_spans_next_day: bool = False
    start_time_earliest: time | None = None
    start_time_latest: time | None = None
    duration_minutes: int = 120
    duration_explicit: bool = False
    duration_min_minutes: int | None = None
    duration_max_minutes: int | None = None
    duration_mode: str = "default"
    date_context: str = "default"


@dataclass(frozen=True)
class ConstraintGroup:
    """一緒に適用すべき日付・時刻条件のまとまり。"""

    constraints: RequestConstraints
    priority: int = 1
    label: str | None = None
    source_text: str = ""


@dataclass(frozen=True)
class ParseOutcome:
    """解析結果と、返信前に必要な確認をまとめたもの。"""

    constraints: RequestConstraints
    status: str = "resolved"
    clarification_question: str | None = None
    suggested_reply: str | None = None
    groups: tuple[ConstraintGroup, ...] = ()
    relation: str = "single"
    recognized_fields: frozenset[str] = frozenset()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Candidate:
    """条件照合後の候補時間帯。"""

    start: datetime
    end: datetime
    required_duration_minutes: int = 120
    duration_explicit: bool = False
    latest_start: datetime | None = None
    maximum_duration_minutes: int | None = None
    duration_mode: str = "default"


@dataclass(frozen=True)
class CandidateGroup:
    """一つの条件グループから得られた候補一覧。"""

    priority: int
    label: str | None
    source_text: str
    candidates: tuple[Candidate, ...]
