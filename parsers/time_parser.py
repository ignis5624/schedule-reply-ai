from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .constants import NAMED_TIME_WINDOWS


@dataclass(frozen=True)
class TimeParseResult:
    time_start: time | None = None
    time_end: time | None = None
    start_time_earliest: time | None = None
    start_time_latest: time | None = None


def _to_time(hour: int, minute: int = 0, *, as_end: bool = False) -> time:
    if hour == 24 and minute == 0:
        return time(23, 59)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("時刻の範囲が不正です。")
    return time(hour, minute)


def _infer_period(message: str, period: str | None) -> str | None:
    if period is not None:
        return period
    if any(token in message for token in ("夜", "晩", "夕方", "午後")):
        return "午後"
    if any(token in message for token in ("朝", "午前", "早朝")):
        return "午前"
    return None


def _clock_from_parts(
    message: str,
    period: str | None,
    hour_text: str,
    colon_minute: str | None = None,
    japanese_minute: str | None = None,
    half: str | None = None,
    *,
    as_end: bool = False,
) -> time:
    hour = int(hour_text)
    minute = int(colon_minute or japanese_minute or (30 if half else 0))
    period = _infer_period(message, period)
    if period == "午後" and hour < 12:
        hour += 12
    elif period == "午前" and hour == 12:
        hour = 0
    return _to_time(hour, minute, as_end=as_end)


def _shift_minutes(value: time, minutes: int) -> time:
    return (datetime.combine(date(2000, 1, 1), value) + timedelta(minutes=minutes)).time()


def _named_window(message: str) -> tuple[time, time] | None:
    matches: list[tuple[int, time, time]] = []
    for tokens, start, end in NAMED_TIME_WINDOWS:
        for token in tokens:
            if token in message:
                matches.append((len(token), start, end))
    if not matches:
        return None
    _, start, end = max(matches, key=lambda item: item[0])
    return start, end


def extract_time_constraints(message: str) -> TimeParseResult:
    """時間帯と、開始時刻の固定・許容幅を区別して抽出する。"""

    colon_range = re.search(
        r"(?<!\d)(\d{1,2}):(\d{2})\s*(?:-|－|〜|～|~|から)\s*(\d{1,2}):(\d{2})(?!\d)",
        message,
    )
    if colon_range:
        h1, m1, h2, m2 = map(int, colon_range.groups())
        return TimeParseResult(_to_time(h1, m1), _to_time(h2, m2, as_end=True))

    japanese_range = re.search(
        r"(?:(午前|午後)\s*)?(\d{1,2})時(?:(\d{1,2})分|(半))?\s*"
        r"(?:-|－|〜|～|~|から)\s*"
        r"(?:(午前|午後)\s*)?(\d{1,2})時(?:(\d{1,2})分|(半))?(?!間)",
        message,
    )
    if japanese_range:
        p1, h1, m1, half1, p2, h2, m2, half2 = japanese_range.groups()
        start = _clock_from_parts(message, p1, h1, japanese_minute=m1, half=half1)
        end = _clock_from_parts(message, p2 or p1, h2, japanese_minute=m2, half=half2, as_end=True)
        return TimeParseResult(start, end)

    shorthand_range = re.search(
        r"(?<!\d)(\d{1,2})\s*(?:-|－|〜|～|~)\s*(\d{1,2})時(?!間)", message
    )
    if shorthand_range:
        h1, h2 = shorthand_range.groups()
        return TimeParseResult(
            _clock_from_parts(message, None, h1),
            _clock_from_parts(message, None, h2, as_end=True),
        )

    after_match = re.search(
        r"(?:(午前|午後)\s*)?(\d{1,2})(?::(\d{2})|時(?:(\d{1,2})分|(半))?)\s*"
        r"(?:以降なら|以降で|以降|以後|から|より後|〜|～|~)\s*",
        message,
    )
    before_match = re.search(
        r"(?:(午前|午後)\s*)?(\d{1,2})(?::(\d{2})|時(?:(\d{1,2})分|(半))?)\s*"
        r"(?:まで|以前|より前|までなら|までで)",
        message,
    )
    leading_before = re.search(
        r"(?:〜|～|~)\s*(?:(午前|午後)\s*)?(\d{1,2})(?::(\d{2})|時(?:(\d{1,2})分|(半))?)(?!間)",
        message,
    )
    if after_match or before_match or leading_before:
        start = None
        end = None
        if after_match:
            start = _clock_from_parts(message, *after_match.groups())
        end_source = before_match or leading_before
        if end_source:
            end = _clock_from_parts(message, *end_source.groups(), as_end=True)
        return TimeParseResult(start, end)

    named = _named_window(message)
    if named:
        for tokens, start, _ in NAMED_TIME_WINDOWS:
            if any(f"{token}以降" in message or f"{token}から" in message for token in tokens):
                return TimeParseResult(time_start=start)

    around_match = re.search(
        r"(?:(午前|午後)\s*)?(\d{1,2})(?::(\d{2})|時(?:(\d{1,2})分|(半))?)\s*"
        r"(?:ごろ|頃|前後)",
        message,
    )
    if around_match:
        center = _clock_from_parts(message, *around_match.groups())
        return TimeParseResult(
            start_time_earliest=_shift_minutes(center, -10),
            start_time_latest=_shift_minutes(center, 10),
        )

    hour_block = re.search(r"(?:(午前|午後)\s*)?(\d{1,2})時台", message)
    if hour_block:
        start = _clock_from_parts(message, hour_block.group(1), hour_block.group(2))
        end = (datetime.combine(date.today(), start) + timedelta(hours=1)).time()
        return TimeParseResult(start, end)

    exact_start = re.search(
        r"(?:(午前|午後)\s*)?(\d{1,2})(?::(\d{2})|時(?:(\d{1,2})分|(半))?)"
        r"(?!間)(?:\s*(?:に|集合|開始|スタート|からなら|からで))?(?:\s|$)",
        message,
    )
    if exact_start:
        exact = _clock_from_parts(message, *exact_start.groups())
        return TimeParseResult(start_time_earliest=exact, start_time_latest=exact)

    if "正午" in message:
        return TimeParseResult(time(12, 0), time(13, 0))

    if named:
        return TimeParseResult(*named)
    return TimeParseResult()


def extract_time_window(message: str) -> tuple[time | None, time | None]:
    """旧コード互換用。時間帯の開始・終了だけを返す。"""

    result = extract_time_constraints(message)
    return result.time_start, result.time_end
