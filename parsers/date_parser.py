from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

from .common import parse_number
from .constants import NUMBER_TOKEN
from .weekday_parser import extract_weekdays


@dataclass(frozen=True)
class DateParseResult:
    date_start: date
    date_end: date
    dates: frozenset[date] | None
    context: str


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _week_bounds(base: date, offset_weeks: int) -> tuple[date, date]:
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


def _add_years_clamped(base: date, offset_years: int) -> date:
    year = base.year + offset_years
    day = min(base.day, calendar.monthrange(year, base.month)[1])
    return date(year, base.month, day)


def _extract_explicit_date_range(message: str, today: date) -> tuple[date, date] | None:
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

    month_day_range = re.search(
        r"(?<!\d)(\d{1,2})(?:月|/)\s*(\d{1,2})日?\s*"
        r"(?:から|〜|～|~|－|-)\s*"
        r"(\d{1,2})(?:月|/)\s*(\d{1,2})日?",
        message,
    )
    if month_day_range:
        m1, d1, m2, d2 = map(int, month_day_range.groups())
        start = _safe_date(today.year, m1, d1)
        if start is None:
            return None
        if start < today:
            start = _safe_date(today.year + 1, m1, d1)
        if start is None:
            return None
        y2 = start.year + (1 if m2 < m1 else 0)
        end = _safe_date(y2, m2, d2)
        if end:
            return start, end

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

    day_only_range = re.search(
        r"(?<![\d年月])(\d{1,2})日\s*(?:から|〜|～|~|－|-)\s*(\d{1,2})日",
        message,
    )
    if day_only_range:
        d1, d2 = map(int, day_only_range.groups())
        year, month = today.year, today.month
        start = _safe_date(year, month, d1)
        if start is None or start < today:
            year, month = _shift_year_month(today, 1)
            start = _safe_date(year, month, d1)
        end = _safe_date(year, month, d2)
        if start and end:
            return (start, end) if start <= end else (end, start)
    return None


def _extract_explicit_dates(message: str, today: date) -> list[date]:
    results: list[date] = []
    full_patterns = (
        r"(?<!\d)(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日",
        r"(?<!\d)(\d{4})[./-](\d{1,2})[./-](\d{1,2})(?!\d)",
    )
    for pattern in full_patterns:
        for year_text, month_text, day_text in re.findall(pattern, message):
            parsed = _safe_date(int(year_text), int(month_text), int(day_text))
            if parsed:
                results.append(parsed)

    short_patterns = (
        r"(?<![\d/])(\d{1,2})\s*/\s*(\d{1,2})(?!\d)",
        r"(?<![\d年])(\d{1,2})月\s*(\d{1,2})日",
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

    for list_match in re.finditer(
        r"(?<!\d)(\d{1,2})月\s*((?:\d{1,2}\s*(?:日)?\s*(?:、|,|・|と|または)\s*)+\d{1,2})日?",
        message,
    ):
        month = int(list_match.group(1))
        for day_text in re.findall(r"\d{1,2}", list_match.group(2)):
            parsed = _safe_date(today.year, month, int(day_text))
            if parsed and parsed < today:
                parsed = _safe_date(today.year + 1, month, int(day_text))
            if parsed:
                results.append(parsed)

    for day_text in re.findall(r"(?<![\d年月丸中泊])(\d{1,2})日(?!後|間|以内|連続)", message):
        day = int(day_text)
        parsed = _safe_date(today.year, today.month, day)
        if parsed is None or parsed < today:
            year, month = _shift_year_month(today, 1)
            parsed = _safe_date(year, month, day)
        if parsed:
            results.append(parsed)
    return sorted(set(results))


def _extract_relative_period(message: str, today: date) -> tuple[date, date] | None:
    aliases = {"今日": 0, "本日": 0, "明日": 1, "明後日": 2, "明々後日": 3}
    start_match = re.search(
        fr"(明々後日|明後日|明日|今日|本日)から\s*({NUMBER_TOKEN})\s*日間", message
    )
    if start_match:
        start = today + timedelta(days=aliases[start_match.group(1)])
        days = max(1, int(parse_number(start_match.group(2))))
        return start, start + timedelta(days=days - 1)

    within_match = re.search(fr"({NUMBER_TOKEN})\s*日以内", message)
    if within_match:
        days = max(0, int(parse_number(within_match.group(1))))
        return today, today + timedelta(days=days)
    return None


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
        results.add(today + timedelta(days=int(parse_number(number_text))))
    for number_text in re.findall(
        fr"(?<![\d一二三四五六七八九十百千])({NUMBER_TOKEN})\s*(?:週間|週)後", message
    ):
        results.add(today + timedelta(days=7 * int(parse_number(number_text))))
    for number_text in re.findall(
        fr"(?<![\d一二三四五六七八九十百千])({NUMBER_TOKEN})\s*年後", message
    ):
        results.add(_add_years_clamped(today, int(parse_number(number_text))))
    return sorted(results)


def _extract_nearest_weekday_dates(message: str, today: date) -> list[date]:
    if not re.search(r"(?:次の|今度の|直近の|一番近い)", message):
        return []
    weekdays = extract_weekdays(message)
    if not weekdays:
        return []
    results: list[date] = []
    for target in sorted(weekdays):
        days_ahead = (target - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        results.append(today + timedelta(days=days_ahead))
    return sorted(set(results))


def _extract_bare_week_beginning(message: str, today: date) -> tuple[date, date] | None:
    if "週明け" not in message:
        return None
    if any(token in message for token in ("今週", "来週", "再来週", "再々来週")):
        return None

    if today.weekday() == 0:
        monday = today
    elif today.weekday() == 1:
        return today, today
    else:
        monday = today + timedelta(days=(7 - today.weekday()))
    return monday, monday + timedelta(days=1)


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
        match = re.search(
            fr"(?<![\d一二三四五六七八九十百千])({NUMBER_TOKEN})\s*(?:か月|ヶ月|ヵ月|カ月|ケ月|箇月)後",
            message,
        )
        if match:
            offset = int(parse_number(match.group(1)))
            matched_token = match.group(0)

    if offset is not None:
        first, last = _month_bounds(today, offset)
        if matched_token:
            range_match = re.search(
                re.escape(matched_token)
                + r"(?:の)?\s*(\d{1,2})日\s*(?:から|〜|～|~|－|-)\s*(\d{1,2})日",
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

    explicit_month = re.search(r"(?<!\d)(?:(\d{4})年\s*)?(\d{1,2})月(?!\s*\d{1,2}日)", message)
    if explicit_month:
        year_text, month_text = explicit_month.groups()
        month = int(month_text)
        if not 1 <= month <= 12:
            return None
        year = int(year_text) if year_text else today.year + (1 if month < today.month else 0)
        return _month_bounds_from_year_month(year, month)
    return None


def _extract_bare_month_segment(message: str, today: date) -> tuple[date, date] | None:
    month_start_tokens = ("月初", "月初め", "月の初め", "月はじめ", "月頭")
    month_end_tokens = ("月末", "月の終わり", "月終わり")
    if any(token in message for token in month_start_tokens):
        if today.day <= 5:
            year, month = today.year, today.month
        else:
            year, month = _shift_year_month(today, 1)
        return date(year, month, 1), date(year, month, 5)
    if any(token in message for token in month_end_tokens):
        last = calendar.monthrange(today.year, today.month)[1]
        return max(today, date(today.year, today.month, 25)), date(today.year, today.month, last)
    if "最終週" in message:
        last_day = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
        start, end = _week_bounds(last_day, 0)
        return max(today, start, date(today.year, today.month, 1)), min(end, last_day)
    return None


def _apply_month_segment(message: str, start: date, end: date) -> tuple[date, date]:
    year, month = start.year, start.month
    month_last = calendar.monthrange(year, month)[1]

    nth_week = re.search(r"第?([1-5])週", message)
    if nth_week:
        first_day = date(year, month, 1)
        first_week_start, _ = _week_bounds(first_day, 0)
        segment_start = first_week_start + timedelta(weeks=int(nth_week.group(1)) - 1)
        segment_end = segment_start + timedelta(days=6)
        segment_start = max(segment_start, first_day)
        segment_end = min(segment_end, date(year, month, month_last))
    elif any(token in message for token in ("月初", "月初め", "月の初め", "月はじめ", "月頭")):
        segment_start, segment_end = date(year, month, 1), date(year, month, 5)
    elif any(token in message for token in ("月末", "月の終わり", "月終わり")):
        segment_start, segment_end = date(year, month, 25), date(year, month, month_last)
    elif "最終週" in message:
        last_day = date(year, month, month_last)
        segment_start, segment_end = _week_bounds(last_day, 0)
        segment_start = max(segment_start, date(year, month, 1))
        segment_end = min(segment_end, last_day)
    elif any(token in message for token in ("前半", "前半頃", "前半あたり")):
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


def parse_date_constraints(message: str, today: date) -> DateParseResult:
    """日付・週・月に関する条件を1か所で決定する。"""

    relative_period = _extract_relative_period(message, today)
    explicit_range = _extract_explicit_date_range(message, today)
    explicit_dates = _extract_explicit_dates(message, today)
    relative_dates = _extract_relative_dates(message, today)
    nearest_weekday_dates = _extract_nearest_weekday_dates(message, today)
    bare_week_beginning = _extract_bare_week_beginning(message, today)
    month_range = _extract_month_range(message, today)
    bare_month_segment = _extract_bare_month_segment(message, today)
    week_range = _extract_week_range(message, today)

    context = "default"
    allowed_dates: frozenset[date] | None = None
    if relative_period is not None:
        date_start, date_end = relative_period
        context = "period"
    elif explicit_range is not None:
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
    elif bare_week_beginning is not None:
        date_start, date_end = bare_week_beginning
        context = "exact"
    elif month_range is not None:
        date_start, date_end = month_range
        context = "month"
    elif bare_month_segment is not None:
        date_start, date_end = bare_month_segment
        context = "month"
    elif week_range is not None:
        date_start, date_end = week_range
        context = "week"
    else:
        date_start, date_end = today, today + timedelta(days=14)

    if context == "month":
        date_start, date_end = _apply_month_segment(message, date_start, date_end)
        nth_weekday = re.search(r"第?([1-5])\s*([月火水木金土日])曜(?:日)?", message)
        if nth_weekday:
            ordinal = int(nth_weekday.group(1))
            target_weekday = "月火水木金土日".index(nth_weekday.group(2))
            first = date(date_start.year, date_start.month, 1)
            day_number = 1 + (target_weekday - first.weekday()) % 7 + 7 * (ordinal - 1)
            exact = _safe_date(first.year, first.month, day_number)
            if exact is not None:
                date_start = date_end = exact
                allowed_dates = None
                context = "exact"

    if week_range is not None and re.search(r"(?:今週|来週|再来週|再々来週)(?:の)?以降", message):
        date_end = date.max
    elif week_range is not None and re.search(r"(?:今週|来週|再来週|再々来週)(?:の)?まで", message):
        date_start = today
    if month_range is not None and re.search(r"(?:今月|来月|再来月|再々来月)(?:の)?以降", message):
        date_end = date.max
    elif month_range is not None and re.search(r"(?:今月|来月|再来月|再々来月)(?:の)?まで", message):
        date_start = today

    if context in ("exact", "explicit") and date_start == date_end:
        if re.search(r"(?:今日|本日|明日|明後日|明々後日|\d{1,2}日)\s*(?:以降|から)", message):
            allowed_dates = None
            date_end = date.max
        elif re.search(r"(?:今日|本日|明日|明後日|明々後日|\d{1,2}日)\s*まで", message):
            allowed_dates = None
            date_start = today

    return DateParseResult(date_start, date_end, allowed_dates, context)
