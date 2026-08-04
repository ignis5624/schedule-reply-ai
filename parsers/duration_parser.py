from __future__ import annotations

import re

from .common import parse_number
from .constants import NUMBER_TOKEN


def extract_duration(message: str, default_minutes: int) -> tuple[int, bool]:
    """所要時間と、明示指定かどうかを返す。"""

    combined_match = re.search(fr"({NUMBER_TOKEN})\s*時間\s*({NUMBER_TOKEN})\s*分", message)
    if combined_match:
        hours = parse_number(combined_match.group(1))
        minutes = parse_number(combined_match.group(2))
        return max(15, int(hours * 60 + minutes)), True

    half_match = re.search(fr"({NUMBER_TOKEN})\s*時間\s*半", message)
    if half_match:
        return max(30, int(parse_number(half_match.group(1)) * 60 + 30)), True

    hour_match = re.search(fr"({NUMBER_TOKEN})\s*時間", message)
    if hour_match:
        return max(30, int(parse_number(hour_match.group(1)) * 60)), True

    minute_match = re.search(fr"({NUMBER_TOKEN})\s*分", message)
    if minute_match:
        return max(15, int(parse_number(minute_match.group(1)))), True

    latin_hour = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)\b", message, re.IGNORECASE)
    if latin_hour:
        return max(30, int(float(latin_hour.group(1)) * 60)), True

    if "半日" in message:
        return 240, True
    return default_minutes, False
