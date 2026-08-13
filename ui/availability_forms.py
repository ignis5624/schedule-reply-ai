from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd

from domain.models import (
    Availability,
    BusyInterval,
    RecurringBusyRule,
    WeeklyAvailabilityRule,
)
from parsers.weekday_parser import extract_weekday_constraints


def default_direct_availability() -> pd.DataFrame:
    today = date.today()
    rows = []
    for offset in range(1, 15):
        day = today + timedelta(days=offset)
        if day.weekday() < 5:
            rows.append({"開始日": day, "開始": time(18), "終了日": day, "終了": time(22)})
        else:
            rows.append({"開始日": day, "開始": time(10), "終了日": day, "終了": time(20)})
    return pd.DataFrame(rows)


def default_weekly_availability() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"対象曜日": "平日", "開始": time(6), "終了": time(0), "有効": True},
            {"対象曜日": "土日", "開始": time(6), "終了": time(0), "有効": True},
        ]
    )


def default_recurring_busy() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "予定名": "仕事（例）",
                "対象曜日": "平日",
                "開始": time(9),
                "終了": time(18),
                "適用開始日": None,
                "適用終了日": None,
                "有効": False,
            }
        ]
    )


def default_one_off_busy() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["予定名", "開始日", "開始", "終了日", "終了", "有効"]
    )


def _is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _normalize_day(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "date") and not _is_missing(value):
        return value.date()
    raise ValueError("日付として解釈できません。")


def _optional_day(value: object) -> date | None:
    return None if value is None or _is_missing(value) else _normalize_day(value)


def _row_enabled(row: pd.Series) -> bool:
    value = row.get("有効", True)
    return True if _is_missing(value) else bool(value)


def parse_weekdays(value: object) -> frozenset[int]:
    if value is None or _is_missing(value):
        raise ValueError("対象曜日が未入力です。")
    text = str(value).strip()
    if not text:
        raise ValueError("対象曜日が未入力です。")
    if any(token in text for token in ("毎日", "全日", "月〜日", "月-日")):
        return frozenset(range(7))
    weekdays, excluded = extract_weekday_constraints(text)
    if weekdays is None:
        raise ValueError("曜日は「平日」「土日」「月〜金」「月・水・金」などで入力してください。")
    if excluded:
        weekdays = frozenset(set(weekdays) - set(excluded))
    if not weekdays:
        raise ValueError("対象にできる曜日がありません。")
    return weekdays


def read_direct_availabilities(
    edited: pd.DataFrame,
) -> tuple[list[Availability], list[str]]:
    availabilities: list[Availability] = []
    errors: list[str] = []
    for index, row in edited.iterrows():
        try:
            day_value = _normalize_day(row["開始日"])
            end_day_value = _normalize_day(row["終了日"])
            start_value = row["開始"]
            end_value = row["終了"]
            if end_day_value < day_value:
                raise ValueError("終了日は開始日以降にしてください。")
            if end_day_value == day_value and start_value >= end_value:
                end_day_value += timedelta(days=1)
            availabilities.append(
                Availability(day_value, start_value, end_value, end_day_value)
            )
        except Exception as exc:
            errors.append(f"{index + 1}行目：{exc}")
    return availabilities, errors


def read_weekly_availability_rules(
    edited: pd.DataFrame,
) -> tuple[list[WeeklyAvailabilityRule], list[str]]:
    rules: list[WeeklyAvailabilityRule] = []
    errors: list[str] = []
    for index, row in edited.iterrows():
        if not _row_enabled(row):
            continue
        try:
            rules.append(
                WeeklyAvailabilityRule(
                    weekdays=parse_weekdays(row.get("対象曜日")),
                    start=row["開始"],
                    end=row["終了"],
                )
            )
        except Exception as exc:
            errors.append(f"通常時間 {index + 1}行目：{exc}")
    if not rules and not errors:
        errors.append("有効な通常対応可能時間を1件以上登録してください。")
    return rules, errors


def read_recurring_busy_rules(
    edited: pd.DataFrame,
) -> tuple[list[RecurringBusyRule], list[str]]:
    rules: list[RecurringBusyRule] = []
    errors: list[str] = []
    for index, row in edited.iterrows():
        if not _row_enabled(row):
            continue
        try:
            label_value = row.get("予定名", "固定予定")
            label = "固定予定" if _is_missing(label_value) else str(label_value).strip()
            rules.append(
                RecurringBusyRule(
                    weekdays=parse_weekdays(row.get("対象曜日")),
                    start=row["開始"],
                    end=row["終了"],
                    label=label or "固定予定",
                    effective_start=_optional_day(row.get("適用開始日")),
                    effective_end=_optional_day(row.get("適用終了日")),
                )
            )
        except Exception as exc:
            errors.append(f"固定予定 {index + 1}行目：{exc}")
    return rules, errors


def read_one_off_busy_intervals(
    edited: pd.DataFrame,
) -> tuple[list[BusyInterval], list[str]]:
    intervals: list[BusyInterval] = []
    errors: list[str] = []
    for index, row in edited.iterrows():
        if not _row_enabled(row):
            continue
        try:
            start_day = _normalize_day(row["開始日"])
            end_day = _normalize_day(row["終了日"])
            start = datetime.combine(start_day, row["開始"])
            end = datetime.combine(end_day, row["終了"])
            if end_day == start_day and row["終了"] <= row["開始"]:
                end += timedelta(days=1)
            label_value = row.get("予定名", "単発予定")
            label = "単発予定" if _is_missing(label_value) else str(label_value).strip()
            intervals.append(BusyInterval(start, end, label or "単発予定"))
        except Exception as exc:
            errors.append(f"単発予定 {index + 1}行目：{exc}")
    return intervals, errors
