from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable

WEEKDAYS_JA = {"月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日": 6}
WEEKDAY_LABELS = "月火水木金土日"

# ユーザー指定の固定ルール
WEEK_FIRST_HALF = frozenset({6, 0, 1, 2})  # 日・月・火・水
WEEK_SECOND_HALF = frozenset({2, 3, 4, 5})  # 水・木・金・土

NAMED_TIME_WINDOWS: tuple[tuple[tuple[str, ...], time, time], ...] = (
    (("早朝",), time(5, 0), time(8, 0)),
    (("朝", "朝方"), time(6, 0), time(10, 0)),
    (("午前", "午前中"), time(6, 0), time(12, 0)),
    (("昼", "お昼", "昼時", "ランチ", "昼休み"), time(11, 0), time(14, 0)),
    (("午後", "昼過ぎ"), time(12, 0), time(18, 0)),
    (("夕方", "夕刻"), time(16, 0), time(19, 0)),
    (("夜", "夜間", "晩", "夜の時間"), time(18, 0), time(23, 0)),
    (("深夜", "夜遅く", "遅い時間"), time(21, 0), time(23, 59)),
)

KANJI_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
KANJI_UNITS = {"十": 10, "百": 100, "千": 1000}
NUMBER_TOKEN = r"(?:\d+(?:\.\d+)?|[零〇一二三四五六七八九十百千]+)"


@dataclass(frozen=True)
class Availability:
    day: date
    start: time
    end: time


@dataclass(frozen=True)
class RequestConstraints:
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
    start: datetime
    end: datetime
    required_duration_minutes: int = 120
    duration_explicit: bool = False


def _parse_number(text: str) -> float:
    text = unicodedata.normalize("NFKC", text.strip())
    try:
        return float(text)
    except ValueError:
        pass

    # 「二〇二六」のように位取り記号がない場合は各桁として読む。
    if text and all(char in KANJI_DIGITS for char in text):
        return float("".join(str(KANJI_DIGITS[char]) for char in text))

    # 「二十三」「百二十」程度の一般的な漢数字に対応。
    total = 0
    current = 0
    for char in text:
        if char in KANJI_DIGITS:
            current = KANJI_DIGITS[char]
        elif char in KANJI_UNITS:
            unit = KANJI_UNITS[char]
            total += (current or 1) * unit
            current = 0
        else:
            raise ValueError(f"数値として解釈できません: {text}")
    return float(total + current)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _week_bounds(base: date, offset_weeks: int) -> tuple[date, date]:
    """週は日曜始まり・土曜終わり。"""
    days_since_sunday = (base.weekday() + 1) % 7
    sunday = base - timedelta(days=days_since_sunday) + timedelta(weeks=offset_weeks)
    return sunday, sunday + timedelta(days=6)


def _shift_year_month(base: date, offset_months: int) -> tuple[int, int]:
    total_months = base.year * 12 + (base.month - 1) + offset_months
    year, month_index = divmod(total_months, 12)
    return year, month_index + 1


def _month_bounds_from_year_month(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    return first, last


def _month_bounds(base: date, offset_months: int) -> tuple[date, date]:
    year, month = _shift_year_month(base, offset_months)
    return _month_bounds_from_year_month(year, month)


def _add_months_clamped(base: date, offset_months: int) -> date:
    year, month = _shift_year_month(base, offset_months)
    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _add_years_clamped(base: date, offset_years: int) -> date:
    year = base.year + offset_years
    day = min(base.day, calendar.monthrange(year, base.month)[1])
    return date(year, base.month, day)


def _normalize_message(message: str) -> str:
    normalized = unicodedata.normalize("NFKC", message.strip())
    replacements = {
        "あした": "明日",
        "あす": "明日",
        "あさって": "明後日",
        "しあさって": "明々後日",
        "明明後日": "明々後日",
        "こんしゅう": "今週",
        "らいしゅう": "来週",
        "さらいしゅう": "再来週",
        "こんげつ": "今月",
        "らいげつ": "来月",
        "さらいげつ": "再来月",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)

    # 八月十五日、二時間半、三週間後などを算用数字へ寄せる。
    kanji_number = r"[零〇一二三四五六七八九十百千]+"
    normalized = re.sub(
        fr"({kanji_number})(?=(?:年|月|日|週間|週|時間|分|時))",
        lambda match: str(int(_parse_number(match.group(1)))),
        normalized,
    )
    return normalized


def _extract_explicit_date_range(message: str, today: date) -> tuple[date, date] | None:
    # 2026/8/1〜2026/8/5、2026-8-1から2026-8-5
    full_range = re.search(
        r"(?<!\d)(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?\s*"
        r"(?:から|〜|～|~|－|-)\s*"
        r"(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?",
        message,
    )
    if full_range:
        y1, m1, d1, y2, m2, d2 = map(int, full_range.groups())
        start, end = _safe_date(y1, m1, d1), _safe_date(y2, m2, d2)
        if start and end:
            return (start, end) if start <= end else (end, start)

    # 8/1〜8/5、8月1日から8月5日
    month_day_range = re.search(
        r"(?<!\d)(\d{1,2})(?:月|/)\s*(\d{1,2})日?\s*"
        r"(?:から|〜|～|~|－|-)\s*"
        r"(\d{1,2})(?:月|/)\s*(\d{1,2})日?",
        message,
    )
    if month_day_range:
        m1, d1, m2, d2 = map(int, month_day_range.groups())
        y1 = today.year
        start = _safe_date(y1, m1, d1)
        if start is None:
            return None
        if start < today:
            start = _safe_date(y1 + 1, m1, d1)
        if start is None:
            return None
        y2 = start.year + (1 if m2 < m1 else 0)
        end = _safe_date(y2, m2, d2)
        if end:
            return start, end

    # 8月1日から5日、来月1日〜5日（後者は月コンテキスト側でも扱う）
    same_month_range = re.search(
        r"(?<!\d)(\d{1,2})月\s*(\d{1,2})日\s*(?:から|〜|～|~|－|-)\s*(\d{1,2})日",
        message,
    )
    if same_month_range:
        month, d1, d2 = map(int, same_month_range.groups())
        year = today.year + (1 if month < today.month else 0)
        start, end = _safe_date(year, month, d1), _safe_date(year, month, d2)
        if start and end:
            return (start, end) if start <= end else (end, start)
    return None


def _extract_explicit_dates(message: str, today: date) -> list[date]:
    results: list[date] = []

    full_patterns = (
        r"(?<!\d)(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日",
        r"(?<!\d)(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?!\d)",
    )
    for pattern in full_patterns:
        for year_text, month_text, day_text in re.findall(pattern, message):
            parsed = _safe_date(int(year_text), int(month_text), int(day_text))
            if parsed:
                results.append(parsed)

    # 年のない日付。過去なら翌年として扱う。
    short_patterns = (
        r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)",
        r"(?<!\d)(\d{1,2})月\s*(\d{1,2})日",
    )
    for pattern in short_patterns:
        for month_text, day_text in re.findall(pattern, message):
            month, day = int(month_text), int(day_text)
            parsed = _safe_date(today.year, month, day)
            if parsed is None:
                continue
            if parsed < today:
                parsed = _safe_date(today.year + 1, month, day)
            if parsed:
                results.append(parsed)

    return sorted(set(results))


def _extract_relative_dates(message: str, today: date) -> list[date]:
    results: set[date] = set()
    aliases = (
        (("明々後日",), 3),
        (("明後日",), 2),
        (("明日",), 1),
        (("今日", "本日"), 0),
    )
    for tokens, offset in aliases:
        if any(token in message for token in tokens):
            results.add(today + timedelta(days=offset))

    for number_text in re.findall(
        fr"(?<![\d一二三四五六七八九十百千])({NUMBER_TOKEN})\s*日後", message
    ):
        results.add(today + timedelta(days=int(_parse_number(number_text))))

    for number_text in re.findall(
        fr"(?<![\d一二三四五六七八九十百千])({NUMBER_TOKEN})\s*(?:週間|週)後", message
    ):
        results.add(today + timedelta(days=7 * int(_parse_number(number_text))))

    for number_text in re.findall(
        fr"(?<![\d一二三四五六七八九十百千])({NUMBER_TOKEN})\s*年後", message
    ):
        results.add(_add_years_clamped(today, int(_parse_number(number_text))))
    return sorted(results)


def _extract_nearest_weekday_dates(message: str, today: date) -> list[date]:
    if not re.search(r"(?:次の|今度の|直近の|一番近い)", message):
        return []
    weekdays = _extract_weekdays(message)
    if not weekdays:
        return []
    results: list[date] = []
    for target in sorted(weekdays):
        days_ahead = (target - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        results.append(today + timedelta(days=days_ahead))
    return sorted(set(results))


def _extract_week_range(message: str, today: date) -> tuple[date, date] | None:
    aliases = (
        (("再々来週",), 3),
        (("再来週", "翌々週"), 2),
        (("来週", "次週", "翌週"), 1),
        (("今週", "今週中", "今週内"), 0),
    )
    for tokens, offset in aliases:
        if any(token in message for token in tokens):
            start, end = _week_bounds(today, offset)
            if offset == 0:
                start = max(start, today)
            return start, end
    return None


def _extract_month_range(message: str, today: date) -> tuple[date, date] | None:
    aliases = (
        (("再々来月",), 3),
        (("再来月", "翌々月"), 2),
        (("来月", "翌月"), 1),
        (("今月", "今月中", "今月内"), 0),
    )
    offset: int | None = None
    matched_token: str | None = None

    for tokens, value in aliases:
        for token in tokens:
            if token in message:
                offset = value
                matched_token = token
                break
        if offset is not None:
            break

    if offset is None:
        match = re.search(fr"(?<![\d一二三四五六七八九十百千])({NUMBER_TOKEN})\s*(?:か月|ヶ月|ヵ月|カ月|ケ月|箇月)後", message)
        if match:
            offset = int(_parse_number(match.group(1)))
            matched_token = match.group(0)

    if offset is not None:
        first, last = _month_bounds(today, offset)
        if matched_token:
            range_match = re.search(
                re.escape(matched_token) + r"(?:の)?\s*(\d{1,2})日\s*(?:から|〜|～|~|－|-)\s*(\d{1,2})日",
                message,
            )
            if range_match:
                start = _safe_date(first.year, first.month, int(range_match.group(1)))
                end = _safe_date(first.year, first.month, int(range_match.group(2)))
                if start and end:
                    return (start, end) if start <= end else (end, start)
            day_match = re.search(re.escape(matched_token) + r"(?:の)?\s*(\d{1,2})日", message)
            if day_match:
                exact = _safe_date(first.year, first.month, int(day_match.group(1)))
                return (exact, exact) if exact else (first, last)
        return first, last

    # 2026年8月、8月。日付まで書かれている表現は除外。
    explicit_month = re.search(r"(?<!\d)(?:(\d{4})年\s*)?(\d{1,2})月(?!\s*\d{1,2}日)", message)
    if explicit_month:
        year_text, month_text = explicit_month.groups()
        month = int(month_text)
        if not 1 <= month <= 12:
            return None
        if year_text:
            year = int(year_text)
        else:
            year = today.year + (1 if month < today.month else 0)
        first, last = _month_bounds_from_year_month(year, month)
        return first, last
    return None


def _apply_month_segment(message: str, start: date, end: date) -> tuple[date, date]:
    year, month = start.year, start.month
    month_last = calendar.monthrange(year, month)[1]

    if any(token in message for token in ("前半", "前半頃", "前半あたり")):
        segment_start, segment_end = date(year, month, 1), date(year, month, 15)
    elif any(token in message for token in ("後半", "後半頃", "後半あたり")):
        segment_start, segment_end = date(year, month, 16), date(year, month, month_last)
    elif "上旬" in message:
        segment_start, segment_end = date(year, month, 1), date(year, month, 10)
    elif "中旬" in message:
        segment_start, segment_end = date(year, month, 11), date(year, month, 20)
    elif "下旬" in message:
        segment_start, segment_end = date(year, month, 21), date(year, month, month_last)
    else:
        return start, end

    return max(start, segment_start), min(end, segment_end)


def _weekday_range(start_label: str, end_label: str) -> set[int]:
    start = WEEKDAYS_JA[start_label]
    end = WEEKDAYS_JA[end_label]
    values = {start}
    cursor = start
    while cursor != end:
        cursor = (cursor + 1) % 7
        values.add(cursor)
    return values


def _extract_weekdays(message: str) -> frozenset[int] | None:
    if any(token in message for token in ("毎日", "全日", "曜日問わず", "何曜日でも")):
        return None

    found: set[int] = set()
    if any(token in message for token in ("平日", "ウィークデー")):
        found.update(range(5))
    if any(token in message for token in ("土日", "週末", "土・日", "土、日")):
        found.update({5, 6})

    # 月曜から水曜、月〜水
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

    # 月曜日、火曜
    for label in re.findall(r"([月火水木金土日])曜(?:日)?", message):
        found.add(WEEKDAYS_JA[label])

    # 月・水・金、月水金、月か火
    compact_groups = re.findall(
        r"(?<![\d年月])([月火水木金土日](?:(?:[・、,/かと]|または)?[月火水木金土日])+)(?![年月日])",
        message,
    )
    for group in compact_groups:
        for label in re.findall(r"[月火水木金土日]", group):
            found.add(WEEKDAYS_JA[label])

    return frozenset(found) if found else None


def _combine_week_segment(message: str, weekdays: frozenset[int] | None, is_week_context: bool) -> frozenset[int] | None:
    if not is_week_context:
        return weekdays
    segment: frozenset[int] | None = None
    if "前半" in message:
        segment = WEEK_FIRST_HALF
    elif "後半" in message:
        segment = WEEK_SECOND_HALF
    if segment is None:
        return weekdays
    if weekdays is None:
        return segment
    return frozenset(set(weekdays) & set(segment))


def _to_time(hour: int, minute: int = 0, *, as_end: bool = False) -> time:
    if hour == 24 and minute == 0:
        return time(23, 59) if as_end else time(23, 59)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("時刻の範囲が不正です。")
    return time(hour, minute)


def _clock_from_groups(period: str | None, hour_text: str, minute_text: str | None, *, as_end: bool = False) -> time:
    hour = int(hour_text)
    minute = int(minute_text or 0)
    if period == "午後" and hour < 12:
        hour += 12
    elif period == "午前" and hour == 12:
        hour = 0
    return _to_time(hour, minute, as_end=as_end)


def _extract_time_window(message: str) -> tuple[time | None, time | None]:
    # 18:30〜22:00
    colon_range = re.search(
        r"(?<!\d)(\d{1,2}):(\d{2})\s*(?:-|－|〜|～|~|から)\s*(\d{1,2}):(\d{2})(?!\d)",
        message,
    )
    if colon_range:
        h1, m1, h2, m2 = map(int, colon_range.groups())
        return _to_time(h1, m1), _to_time(h2, m2, as_end=True)

    # 午後6時から午後10時、18時〜22時
    range_match = re.search(
        r"(?:(午前|午後)\s*)?(\d{1,2})(?::(\d{2}))?時?\s*"
        r"(?:-|－|〜|～|~|から)\s*"
        r"(?:(午前|午後)\s*)?(\d{1,2})(?::(\d{2}))?時",
        message,
    )
    if range_match:
        p1, h1, m1, p2, h2, m2 = range_match.groups()
        return _clock_from_groups(p1, h1, m1), _clock_from_groups(p2 or p1, h2, m2, as_end=True)

    # 18時以降、午後6時から／22時まで、午後10時以前
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

    # 18時台
    hour_block = re.search(r"(?:(午前|午後)\s*)?(\d{1,2})時台", message)
    if hour_block:
        start = _clock_from_groups(hour_block.group(1), hour_block.group(2), None)
        start_dt = datetime.combine(date.today(), start)
        end_dt = start_dt + timedelta(hours=1)
        return start, end_dt.time()

    # 午後3時に、18時集合、18時スタート、18時だけ
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


def _extract_duration(message: str, default_minutes: int) -> tuple[int, bool]:
    # 2時間30分、二時間半、1.5時間
    combined_match = re.search(fr"({NUMBER_TOKEN})\s*時間\s*({NUMBER_TOKEN})\s*分", message)
    if combined_match:
        hours = _parse_number(combined_match.group(1))
        minutes = _parse_number(combined_match.group(2))
        return max(15, int(hours * 60 + minutes)), True

    half_match = re.search(fr"({NUMBER_TOKEN})\s*時間\s*半", message)
    if half_match:
        return max(30, int(_parse_number(half_match.group(1)) * 60 + 30)), True

    hour_match = re.search(fr"({NUMBER_TOKEN})\s*時間", message)
    if hour_match:
        return max(30, int(_parse_number(hour_match.group(1)) * 60)), True

    minute_match = re.search(fr"({NUMBER_TOKEN})\s*分", message)
    if minute_match:
        return max(15, int(_parse_number(minute_match.group(1)))), True

    latin_hour = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)\b", message, re.IGNORECASE)
    if latin_hour:
        return max(30, int(float(latin_hour.group(1)) * 60)), True

    if "半日" in message:
        return 240, True
    return default_minutes, False


def parse_request(message: str, today: date, default_duration_minutes: int = 120) -> RequestConstraints:
    normalized = _normalize_message(message)

    explicit_range = _extract_explicit_date_range(normalized, today)
    explicit_dates = _extract_explicit_dates(normalized, today)
    relative_dates = _extract_relative_dates(normalized, today)
    nearest_weekday_dates = _extract_nearest_weekday_dates(normalized, today)
    month_range = _extract_month_range(normalized, today)
    week_range = _extract_week_range(normalized, today)

    context = "default"
    allowed_dates: frozenset[date] | None = None
    if explicit_range is not None:
        date_start, date_end = explicit_range
        context = "explicit"
    elif explicit_dates:
        date_start, date_end = min(explicit_dates), max(explicit_dates)
        allowed_dates = frozenset(explicit_dates) if len(explicit_dates) > 1 else None
        context = "explicit"
    elif relative_dates:
        date_start, date_end = min(relative_dates), max(relative_dates)
        allowed_dates = frozenset(relative_dates) if len(relative_dates) > 1 else None
        context = "exact"
    elif nearest_weekday_dates:
        date_start, date_end = min(nearest_weekday_dates), max(nearest_weekday_dates)
        allowed_dates = frozenset(nearest_weekday_dates) if len(nearest_weekday_dates) > 1 else None
        context = "exact"
    elif month_range is not None:
        date_start, date_end = month_range
        context = "month"
    elif week_range is not None:
        date_start, date_end = week_range
        context = "week"
    else:
        date_start, date_end = today, today + timedelta(days=14)

    if context == "month":
        date_start, date_end = _apply_month_segment(normalized, date_start, date_end)

    weekdays = _extract_weekdays(normalized)
    weekdays = _combine_week_segment(normalized, weekdays, context == "week")
    time_start, time_end = _extract_time_window(normalized)
    duration_minutes, duration_explicit = _extract_duration(normalized, default_duration_minutes)

    return RequestConstraints(
        date_start=date_start,
        date_end=date_end,
        dates=allowed_dates,
        weekdays=weekdays,
        time_start=time_start,
        time_end=time_end,
        duration_minutes=duration_minutes,
        duration_explicit=duration_explicit,
    )


def _merge_windows(windows: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not windows:
        return []

    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(windows):
        if not merged:
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        if start.date() == previous_start.date() and start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def find_candidates(
    availabilities: Iterable[Availability],
    constraints: RequestConstraints,
    limit: int = 5,
) -> list[Candidate]:
    duration = timedelta(minutes=constraints.duration_minutes)
    usable_windows: list[tuple[datetime, datetime]] = []

    for slot in sorted(availabilities, key=lambda item: (item.day, item.start)):
        if not (constraints.date_start <= slot.day <= constraints.date_end):
            continue
        if constraints.dates is not None and slot.day not in constraints.dates:
            continue
        if constraints.weekdays is not None and slot.day.weekday() not in constraints.weekdays:
            continue

        window_start = datetime.combine(slot.day, slot.start)
        window_end = datetime.combine(slot.day, slot.end)
        if constraints.time_start is not None:
            window_start = max(window_start, datetime.combine(slot.day, constraints.time_start))
        if constraints.time_end is not None:
            window_end = min(window_end, datetime.combine(slot.day, constraints.time_end))
        if window_start < window_end:
            usable_windows.append((window_start, window_end))

    candidates: list[Candidate] = []
    for window_start, window_end in _merge_windows(usable_windows):
        if window_end - window_start < duration:
            continue
        candidates.append(
            Candidate(
                start=window_start,
                end=window_end,
                required_duration_minutes=constraints.duration_minutes,
                duration_explicit=constraints.duration_explicit,
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


def _format_duration(minutes: int) -> str:
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours}時間{remainder}分"
    if hours:
        return f"{hours}時間"
    return f"{remainder}分"


def format_candidate(candidate: Candidate) -> str:
    start, end = candidate.start, candidate.end
    weekday = WEEKDAY_LABELS[start.weekday()]
    base = f"{start.month}/{start.day}（{weekday}）{start:%H:%M}〜{end:%H:%M}"
    available_minutes = int((end - start).total_seconds() // 60)
    if candidate.duration_explicit and available_minutes > candidate.required_duration_minutes:
        return f"{base}の間で{_format_duration(candidate.required_duration_minutes)}"
    return base


def build_reply(name: str, candidates: list[Candidate]) -> str:
    if not candidates:
        return (
            f"確認しましたが、{name}さんの登録済みの予定では条件に合う時間が見つかりませんでした。"
            "別の期間または時間帯も候補にできますか？"
        )

    labels = [format_candidate(candidate) for candidate in candidates[:3]]
    options = labels[0] if len(labels) == 1 else "、".join(labels[:-1]) + "、または" + labels[-1]
    return (
        f"{name}さんは、{options}なら予定を合わせられそうです。"
        "この中で都合のよい時間はありますか？確定前に本人へ確認します。"
    )
