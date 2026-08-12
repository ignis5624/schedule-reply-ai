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
    mode: str = "default"


_DURATION_EXPR = (
    fr"(?:{NUMBER_TOKEN})\s*時間(?:\s*半|\s*(?:{NUMBER_TOKEN})\s*分)?"
    fr"|(?:{NUMBER_TOKEN})\s*分"
)


def _parse_expression(text: str) -> int | None:
    combined = re.fullmatch(
        fr"\s*({NUMBER_TOKEN})\s*時間\s*({NUMBER_TOKEN})\s*分\s*", text
    )
    if combined:
        return max(15, int(parse_number(combined.group(1)) * 60 + parse_number(combined.group(2))))

    half = re.fullmatch(fr"\s*({NUMBER_TOKEN})\s*時間\s*半\s*", text)
    if half:
        return max(30, int(parse_number(half.group(1)) * 60 + 30))

    hours = re.fullmatch(fr"\s*({NUMBER_TOKEN})\s*時間\s*", text)
    if hours:
        return max(30, int(parse_number(hours.group(1)) * 60))

    minutes = re.fullmatch(fr"\s*({NUMBER_TOKEN})\s*分\s*", text)
    if minutes:
        return max(15, int(parse_number(minutes.group(1))))
    return None


def _result_range(first: int, second: int) -> DurationParseResult:
    minimum, maximum = sorted((first, second))
    return DurationParseResult(minimum, True, minimum, maximum, "range")


def extract_duration_details(message: str, default_minutes: int) -> DurationParseResult:
    """所要時間を最小・最大の意味とともに返す。

    「以内」と「以上」を同じ固定時間にせず、候補計算で意味を保持する。
    """

    stay = re.search(fr"({NUMBER_TOKEN})\s*泊\s*({NUMBER_TOKEN})\s*日", message)
    if stay:
        days = max(1, int(parse_number(stay.group(2))))
        value = days * 1440
        return DurationParseResult(value, True, value, value, "exact")

    consecutive_days = re.search(fr"({NUMBER_TOKEN})\s*日間\s*(?:連続)?", message)
    if consecutive_days and not re.search(r"(?:今日|明日|明後日|明々後日)から", message):
        value = max(1, int(parse_number(consecutive_days.group(1)))) * 1440
        return DurationParseResult(value, True, value, value, "exact")

    if re.search(r"丸\s*1\s*日", message):
        return DurationParseResult(1440, True, 1440, 1440, "exact")
    if "半日" in message:
        return DurationParseResult(240, True, 240, 240, "exact")

    same_unit_dash = re.search(
        fr"({NUMBER_TOKEN})\s*(?:〜|～|~|－|-)\s*({NUMBER_TOKEN})\s*時間", message
    )
    if same_unit_dash:
        return _result_range(
            int(parse_number(same_unit_dash.group(1)) * 60),
            int(parse_number(same_unit_dash.group(2)) * 60),
        )

    range_match = re.search(
        fr"({_DURATION_EXPR})\s*(?:〜|～|~|－|-|から)\s*({_DURATION_EXPR})", message
    )
    if range_match:
        first = _parse_expression(range_match.group(1))
        second = _parse_expression(range_match.group(2))
        if first is not None and second is not None:
            return _result_range(first, second)

    same_unit_range = re.search(
        fr"({NUMBER_TOKEN})\s*(?:、|,|か|または)\s*({NUMBER_TOKEN})\s*時間", message
    )
    if same_unit_range:
        return _result_range(
            int(parse_number(same_unit_range.group(1)) * 60),
            int(parse_number(same_unit_range.group(2)) * 60),
        )

    lower_upper = re.search(
        fr"({_DURATION_EXPR})\s*以上\s*({_DURATION_EXPR})\s*以内", message
    )
    if lower_upper:
        first = _parse_expression(lower_upper.group(1))
        second = _parse_expression(lower_upper.group(2))
        if first is not None and second is not None:
            return _result_range(first, second)

    maximum = re.search(
        fr"(?:長くて|最大|最長)?\s*({_DURATION_EXPR})\s*(?:以内|まで)", message
    ) or re.search(fr"(?:長くて|最大|最長)\s*({_DURATION_EXPR})", message)
    if maximum:
        value = _parse_expression(maximum.group(1))
        if value is not None:
            return DurationParseResult(15, True, 15, value, "maximum")

    minimum = re.search(
        fr"(?:最低|少なくとも)\s*({_DURATION_EXPR})", message
    ) or re.search(fr"({_DURATION_EXPR})\s*以上", message)
    if minimum:
        value = _parse_expression(minimum.group(1))
        if value is not None:
            return DurationParseResult(value, True, value, None, "minimum")

    exact = re.search(fr"({_DURATION_EXPR})", message)
    if exact:
        if exact.start() > 0 and message[exact.start() - 1] == "時" and exact.group(1).endswith("分"):
            exact = None
    if exact:
        value = _parse_expression(exact.group(1))
        if value is not None:
            return DurationParseResult(value, True, value, value, "exact")

    latin_hour = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)\b", message, re.IGNORECASE)
    if latin_hour:
        value = max(30, int(float(latin_hour.group(1)) * 60))
        return DurationParseResult(value, True, value, value, "exact")

    return DurationParseResult(default_minutes, False)


def extract_duration(message: str, default_minutes: int) -> tuple[int, bool]:
    """旧コード互換用。所要時間と明示指定かどうかを返す。"""

    result = extract_duration_details(message, default_minutes)
    return result.minutes, result.explicit
