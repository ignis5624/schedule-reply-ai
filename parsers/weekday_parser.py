from __future__ import annotations

import re

from .constants import WEEKDAYS_JA, WEEK_FIRST_HALF, WEEK_SECOND_HALF


def _weekday_range(start_label: str, end_label: str) -> set[int]:
    start = WEEKDAYS_JA[start_label]
    end = WEEKDAYS_JA[end_label]
    values = {start}
    cursor = start
    while cursor != end:
        cursor = (cursor + 1) % 7
        values.add(cursor)
    return values


def _extract_excluded_weekdays(message: str) -> frozenset[int] | None:
    excluded: set[int] = set()
    if re.search(r"(?:土日|週末)\s*(?:以外|を除いて|除く)", message):
        excluded.update({5, 6})
    if re.search(r"平日\s*(?:以外|を除いて|除く)", message):
        excluded.update(range(5))

    for group in re.findall(
        r"((?:[月火水木金土日]曜?(?:日)?\s*(?:、|,|・|と)\s*)+"
        r"[月火水木金土日]曜?(?:日)?)\s*(?:以外|を除いて|除く)",
        message,
    ):
        excluded.update(
            WEEKDAYS_JA[label] for label in re.findall(r"[月火水木金土日]", group)
        )

    for label in re.findall(
        r"([月火水木金土日])曜(?:日)?\s*(?:は)?\s*(?:以外|無理|むり|ダメ|だめ|NG|不可|を除いて|除く)",
        message,
        flags=re.IGNORECASE,
    ):
        excluded.add(WEEKDAYS_JA[label])
    return frozenset(excluded) if excluded else None


def extract_weekday_constraints(
    message: str,
) -> tuple[frozenset[int] | None, frozenset[int] | None]:
    """指定曜日と除外曜日を分離して返す。"""

    if any(token in message for token in ("毎日", "全日", "曜日問わず", "何曜日でも")):
        return None, _extract_excluded_weekdays(message)

    found: set[int] = set()
    if any(token in message for token in ("平日", "ウィークデー")):
        found.update(range(5))
    if any(token in message for token in ("土日", "週末", "土・日", "土、日")):
        found.update({5, 6})
    if "週明け" in message:
        found.update({0, 1})

    for start_label, end_label in re.findall(
        r"([月火水木金土日])曜(?:日)?\s*(?:から|〜|～|~|－|-)\s*([月火水木金土日])曜?(?:日)?",
        message,
    ):
        found.update(_weekday_range(start_label, end_label))
    for start_label, end_label in re.findall(
        r"(?<![\d年月])([月火水木金土日])\s*(?:〜|～|~|－|-)\s*([月火水木金土日])(?![年月日])",
        message,
    ):
        found.update(_weekday_range(start_label, end_label))

    for label in re.findall(r"([月火水木金土日])曜(?:日)?", message):
        found.add(WEEKDAYS_JA[label])

    compact_groups = re.findall(
        r"(?<![明平祝\d年月])"
        r"([月火水木金土日](?:(?:[・、,/かと]|または)[月火水木金土日])+)(?![年月日])",
        message,
    )
    compact_groups += re.findall(
        r"(?<![明平祝\d年月])([月火水木金土日]{2,7})(?=(?:曜|の|で|なら|が|は|、|,|\s|$))",
        message,
    )
    for group in compact_groups:
        for label in re.findall(r"[月火水木金土日]", group):
            found.add(WEEKDAYS_JA[label])

    excluded = _extract_excluded_weekdays(message)
    if excluded:
        found.difference_update(excluded)
    return (frozenset(found) if found else None), excluded


def extract_weekdays(message: str) -> frozenset[int] | None:
    """旧コード互換用。肯定指定された曜日だけを返す。"""

    weekdays, _ = extract_weekday_constraints(message)
    return weekdays


def combine_week_segment(
    message: str,
    weekdays: frozenset[int] | None,
    *,
    is_week_context: bool,
) -> frozenset[int] | None:
    """来週前半・後半の固定ルールを曜日条件へ合成する。"""

    if not is_week_context:
        return weekdays

    segment: frozenset[int] | None = None
    if "前半" in message:
        segment = WEEK_FIRST_HALF
    elif "後半" in message:
        segment = WEEK_SECOND_HALF
    elif "週明け" in message:
        segment = frozenset({0, 1})

    if segment is None:
        return weekdays
    if weekdays is None:
        return segment
    return frozenset(set(weekdays) & set(segment))
