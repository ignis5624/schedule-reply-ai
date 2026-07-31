from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable

WEEKDAYS_JA = {"月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日": 6}
WEEKDAY_LABELS = "月火水木金土日"


@dataclass(frozen=True)
class Availability:
    day: date
    start: time
    end: time


@dataclass(frozen=True)
class RequestConstraints:
    date_start: date
    date_end: date
    weekdays: frozenset[int] | None = None
    time_start: time | None = None
    time_end: time | None = None
    duration_minutes: int = 120


@dataclass(frozen=True)
class Candidate:
    start: datetime
    end: datetime


def _week_bounds(base: date, offset_weeks: int) -> tuple[date, date]:
    monday = base - timedelta(days=base.weekday()) + timedelta(weeks=offset_weeks)
    return monday, monday + timedelta(days=6)


def _extract_explicit_dates(message: str, today: date) -> list[date]:
    results: list[date] = []
    # 7/31, 7月31日
    patterns = [r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)", r"(\d{1,2})月\s*(\d{1,2})日"]
    for pattern in patterns:
        for month_text, day_text in re.findall(pattern, message):
            month, day = int(month_text), int(day_text)
            year = today.year
            try:
                parsed = date(year, month, day)
            except ValueError:
                continue
            # 年末に翌年1月を指定した場合などを軽く補正
            if parsed < today - timedelta(days=60):
                try:
                    parsed = date(year + 1, month, day)
                except ValueError:
                    continue
            results.append(parsed)
    return sorted(set(results))


def _extract_weekdays(message: str) -> frozenset[int] | None:
    if "平日" in message:
        return frozenset(range(5))
    if any(token in message for token in ("土日", "週末")):
        return frozenset({5, 6})

    # 曜日として明示された表現だけを拾う。
    # 「明日」「31日」「7月」の「日」「月」を曜日と誤認しないようにする。
    found: set[int] = set()
    for label, value in WEEKDAYS_JA.items():
        if re.search(fr"{label}曜(?:日)?", message):
            found.add(value)
    return frozenset(found) if found else None


def _extract_time_window(message: str) -> tuple[time | None, time | None]:
    # 「18時以降」「19時まで」「18-21時」「18時から21時」
    range_match = re.search(r"(\d{1,2})(?::(\d{2}))?時?\s*(?:-|〜|～|から)\s*(\d{1,2})(?::(\d{2}))?時", message)
    if range_match:
        sh, sm, eh, em = range_match.groups()
        return time(int(sh), int(sm or 0)), time(int(eh), int(em or 0))

    after_match = re.search(r"(\d{1,2})(?::(\d{2}))?時\s*(?:以降|から)", message)
    before_match = re.search(r"(\d{1,2})(?::(\d{2}))?時\s*(?:まで|以前)", message)
    if after_match or before_match:
        start = time(int(after_match.group(1)), int(after_match.group(2) or 0)) if after_match else None
        end = time(int(before_match.group(1)), int(before_match.group(2) or 0)) if before_match else None
        return start, end

    named_windows = [
        ("朝", time(7, 0), time(12, 0)),
        ("昼", time(11, 0), time(15, 0)),
        ("午後", time(12, 0), time(18, 0)),
        ("夕方", time(16, 0), time(20, 0)),
        ("夜", time(18, 0), time(23, 0)),
    ]
    for token, start, end in named_windows:
        if token in message:
            return start, end
    return None, None


def _extract_duration(message: str, default_minutes: int) -> int:
    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*時間", message)
    if hour_match:
        return max(30, int(float(hour_match.group(1)) * 60))
    minute_match = re.search(r"(\d+)\s*分", message)
    if minute_match:
        return max(15, int(minute_match.group(1)))
    if "半日" in message:
        return 240
    return default_minutes


def parse_request(message: str, today: date, default_duration_minutes: int = 120) -> RequestConstraints:
    normalized = message.strip()
    explicit_dates = _extract_explicit_dates(normalized, today)

    if explicit_dates:
        date_start, date_end = min(explicit_dates), max(explicit_dates)
    elif "明後日" in normalized:
        date_start = date_end = today + timedelta(days=2)
    elif "明日" in normalized:
        date_start = date_end = today + timedelta(days=1)
    elif "今日" in normalized:
        date_start = date_end = today
    elif "再来週" in normalized:
        date_start, date_end = _week_bounds(today, 2)
    elif "来週" in normalized:
        date_start, date_end = _week_bounds(today, 1)
    elif "今週" in normalized:
        _, sunday = _week_bounds(today, 0)
        date_start, date_end = today, sunday
    else:
        date_start, date_end = today, today + timedelta(days=14)

    weekdays = _extract_weekdays(normalized)
    time_start, time_end = _extract_time_window(normalized)
    duration_minutes = _extract_duration(normalized, default_duration_minutes)

    return RequestConstraints(
        date_start=date_start,
        date_end=date_end,
        weekdays=weekdays,
        time_start=time_start,
        time_end=time_end,
        duration_minutes=duration_minutes,
    )


def find_candidates(
    availabilities: Iterable[Availability],
    constraints: RequestConstraints,
    limit: int = 5,
    step_minutes: int = 30,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    duration = timedelta(minutes=constraints.duration_minutes)

    for slot in sorted(availabilities, key=lambda item: (item.day, item.start)):
        if not (constraints.date_start <= slot.day <= constraints.date_end):
            continue
        if constraints.weekdays is not None and slot.day.weekday() not in constraints.weekdays:
            continue

        window_start = datetime.combine(slot.day, slot.start)
        window_end = datetime.combine(slot.day, slot.end)
        if constraints.time_start is not None:
            window_start = max(window_start, datetime.combine(slot.day, constraints.time_start))
        if constraints.time_end is not None:
            window_end = min(window_end, datetime.combine(slot.day, constraints.time_end))

        cursor = window_start
        # 30分単位に切り上げ
        if cursor.minute % step_minutes:
            cursor += timedelta(minutes=step_minutes - cursor.minute % step_minutes)
            cursor = cursor.replace(second=0, microsecond=0)

        while cursor + duration <= window_end:
            candidates.append(Candidate(start=cursor, end=cursor + duration))
            if len(candidates) >= limit:
                return candidates
            # 同じ空き枠から候補を出しすぎない
            cursor += timedelta(minutes=max(step_minutes, constraints.duration_minutes))

    return candidates


def format_candidate(candidate: Candidate) -> str:
    start = candidate.start
    end = candidate.end
    weekday = WEEKDAY_LABELS[start.weekday()]
    return f"{start.month}/{start.day}（{weekday}）{start:%H:%M}〜{end:%H:%M}"


def build_reply(name: str, candidates: list[Candidate], request_message: str) -> str:
    if not candidates:
        return (
            f"確認しましたが、{name}さんの登録済みの予定では条件に合う時間が見つかりませんでした。"
            "別の期間または時間帯も候補にできますか？"
        )

    labels = [format_candidate(candidate) for candidate in candidates[:3]]
    if len(labels) == 1:
        options = labels[0]
    else:
        options = "、".join(labels[:-1]) + "、または" + labels[-1]

    return (
        f"{name}さんは、{options}なら予定を合わせられそうです。"
        "この中で都合のよい時間はありますか？確定前に本人へ確認します。"
    )
