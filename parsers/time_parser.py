from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from .constants import NAMED_TIME_WINDOWS


def _to_time(hour: int, minute: int = 0, *, as_end: bool = False) -> time:
    if hour == 24 and minute == 0:
        return time(23, 59)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("時刻の範囲が不正です。")
    return time(hour, minute)


def _clock_from_groups(
    period: str | None,
    hour_text: str,
    minute_text: str | None,
    *,
    as_end: bool = False,
) -> time:
    hour = int(hour_text)
    minute = int(minute_text or 0)
    if period == "午後" and hour < 12:
        hour += 12
    elif period == "午前" and hour == 12:
        hour = 0
    return _to_time(hour, minute, as_end=as_end)


def extract_time_window(message: str) -> tuple[time | None, time | None]:
    """時間帯・時刻範囲を抽出する。"""

    colon_range = re.search(
        r"(?<!\d)(\d{1,2}):(\d{2})\s*(?:-|－|〜|～|~|から)\s*(\d{1,2}):(\d{2})(?!\d)",
        message,
    )
    if colon_range:
        h1, m1, h2, m2 = map(int, colon_range.groups())
        return _to_time(h1, m1), _to_time(h2, m2, as_end=True)

    range_match = re.search(
        r"(?:(午前|午後)\s*)?(\d{1,2})(?::(\d{2}))?時?\s*"
        r"(?:-|－|〜|～|~|から)\s*"
        r"(?:(午前|午後)\s*)?(\d{1,2})(?::(\d{2}))?時",
        message,
    )
    if range_match:
        p1, h1, m1, p2, h2, m2 = range_match.groups()
        return _clock_from_groups(p1, h1, m1), _clock_from_groups(p2 or p1, h2, m2, as_end=True)

    after_match = re.search(
        r"(?:(午前|午後)\s*)?(\d{1,2})(?::(\d{2}))?時\s*(?:以降|以後|から|より後|以降なら|以降で)",
        message,
    )
    before_match = re.search(
        r"(?:(午前|午後)\s*)?(\d{1,2})(?::(\d{2}))?時\s*(?:まで|以前|より前|までなら|までで)",
        message,
    )
    if after_match or before_match:
        start = _clock_from_groups(*after_match.groups()) if after_match else None
        end = _clock_from_groups(*before_match.groups(), as_end=True) if before_match else None
        return start, end

    hour_block = re.search(r"(?:(午前|午後)\s*)?(\d{1,2})時台", message)
    if hour_block:
        start = _clock_from_groups(hour_block.group(1), hour_block.group(2), None)
        end = (datetime.combine(date.today(), start) + timedelta(hours=1)).time()
        return start, end

    exact_start = re.search(
        r"(?:(午前|午後)\s*)?(\d{1,2})(?::(\d{2}))?時\s*(?:に|集合|開始|スタート|からなら|からで)?(?:\s|$)",
        message,
    )
    if exact_start:
        return _clock_from_groups(*exact_start.groups()), None

    if "正午" in message:
        return time(12, 0), time(13, 0)

    named_matches: list[tuple[int, time, time]] = []
    for tokens, start, end in NAMED_TIME_WINDOWS:
        for token in tokens:
            if token in message:
                named_matches.append((len(token), start, end))
    if named_matches:
        _, start, end = max(named_matches, key=lambda item: item[0])
        return start, end
    return None, None
