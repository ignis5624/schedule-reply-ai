from __future__ import annotations

import re
from dataclasses import dataclass

from .common import parse_number
from .constants import NUMBER_TOKEN


@dataclass(frozen=True)
class DurationParseResult:
    minutes: int
    explicit: bool
    minimum_minutes: int | None = None
    maximum_minutes: int | None = None


def extract_duration_details(message: str, default_minutes: int) -> DurationParseResult:
    """所要時間を、必要に応じて最小・最大の幅付きで返す。"""

    range_match = re.search(
        fr"({NUMBER_TOKEN})\s*(?:時間\s*)?(?:〜|～|~|－|-)\s*({NUMBER_TOKEN})\s*時間",
        message,
    )
    if range_match:
        first = max(30, int(parse_number(range_match.group(1)) * 60))
        second = max(30, int(parse_number(range_match.group(2)) * 60))
        minimum, maximum = sorted((first, second))
        return DurationParseResult(minimum, True, minimum, maximum)

    combined_match = re.search(fr"({NUMBER_TOKEN})\s*時間\s*({NUMBER_TOKEN})\s*分", message)
    if combined_match:
        hours = parse_number(combined_match.group(1))
        minutes = parse_number(combined_match.group(2))
        value = max(15, int(hours * 60 + minutes))
        return DurationParseResult(value, True, value, value)

    half_match = re.search(fr"({NUMBER_TOKEN})\s*時間\s*半", message)
    if half_match:
        value = max(30, int(parse_number(half_match.group(1)) * 60 + 30))
        return DurationParseResult(value, True, value, value)

    hour_match = re.search(fr"({NUMBER_TOKEN})\s*時間", message)
    if hour_match:
        value = max(30, int(parse_number(hour_match.group(1)) * 60))
        return DurationParseResult(value, True, value, value)

    minute_match = re.search(fr"(?<![\d時])({NUMBER_TOKEN})\s*分", message)
    if minute_match:
        value = max(15, int(parse_number(minute_match.group(1))))
        return DurationParseResult(value, True, value, value)

    latin_hour = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)\b", message, re.IGNORECASE)
    if latin_hour:
        value = max(30, int(float(latin_hour.group(1)) * 60))
        return DurationParseResult(value, True, value, value)

    if "半日" in message:
        return DurationParseResult(240, True, 240, 240)
    return DurationParseResult(default_minutes, False)


def extract_duration(message: str, default_minutes: int) -> tuple[int, bool]:
    """旧コード互換用。所要時間と明示指定かどうかを返す。"""

    result = extract_duration_details(message, default_minutes)
    return result.minutes, result.explicit
