from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

import pandas as pd
import streamlit as st

APP_VERSION = "v2.2"
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
    duration_explicit: bool = False


@dataclass(frozen=True)
class Candidate:
    start: datetime
    end: datetime
    required_duration_minutes: int = 120
    duration_explicit: bool = False


def _week_bounds(base: date, offset_weeks: int) -> tuple[date, date]:
    monday = base - timedelta(days=base.weekday()) + timedelta(weeks=offset_weeks)
    return monday, monday + timedelta(days=6)


def _shift_year_month(base: date, offset_months: int) -> tuple[int, int]:
    total_months = base.year * 12 + (base.month - 1) + offset_months
    year, month_index = divmod(total_months, 12)
    return year, month_index + 1


def _month_bounds(base: date, offset_months: int) -> tuple[date, date]:
    year, month = _shift_year_month(base, offset_months)
    first = date(year, month, 1)
    next_year, next_month = _shift_year_month(first, 1)
    last = date(next_year, next_month, 1) - timedelta(days=1)
    return first, last


def _extract_relative_month_range(message: str, today: date) -> tuple[date, date] | None:
    # Longer aliases must be checked first because 「再来月」 contains 「来月」.
    aliases = (("再来月", 2), ("来月", 1), ("今月", 0))
    offset: int | None = None
    matched_token: str | None = None
    for token, value in aliases:
        if token in message:
            offset = value
            matched_token = token
            break

    if offset is None:
        match = re.search(r"(?<!\d)(\d{1,3})\s*(?:か月|ヶ月|ヵ月|カ月|ケ月|箇月)後", message)
        if match:
            offset = int(match.group(1))
            matched_token = match.group(0)

    if offset is None:
        return None

    first, last = _month_bounds(today, offset)

    # 「来月15日」「3か月後の15日」のように日まで指定された場合はその日だけに絞る。
    if matched_token is not None:
        token_pattern = re.escape(matched_token)
        day_match = re.search(token_pattern + r"(?:の)?\s*(\d{1,2})日", message)
        if day_match:
            day_number = int(day_match.group(1))
            try:
                exact = date(first.year, first.month, day_number)
            except ValueError:
                return first, last
            return exact, exact

    return first, last


def _extract_explicit_dates(message: str, today: date) -> list[date]:
    results: list[date] = []
    patterns = [
        r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)",
        r"(\d{1,2})月\s*(\d{1,2})日",
    ]
    for pattern in patterns:
        for month_text, day_text in re.findall(pattern, message):
            month, day = int(month_text), int(day_text)
            try:
                parsed = date(today.year, month, day)
            except ValueError:
                continue
            if parsed < today - timedelta(days=60):
                try:
                    parsed = date(today.year + 1, month, day)
                except ValueError:
                    continue
            results.append(parsed)
    return sorted(set(results))


def _extract_relative_date(message: str, today: date) -> date | None:
    aliases = (
        ("明々後日", 3),
        ("明明後日", 3),
        ("しあさって", 3),
        ("明後日", 2),
        ("明日", 1),
        ("今日", 0),
    )
    for token, offset in aliases:
        if token in message:
            return today + timedelta(days=offset)

    match = re.search(r"(?<!\d)(\d{1,4})\s*日後", message)
    if match:
        return today + timedelta(days=int(match.group(1)))
    return None


def _extract_weekdays(message: str) -> frozenset[int] | None:
    if "平日" in message:
        return frozenset(range(5))
    if any(token in message for token in ("土日", "週末")):
        return frozenset({5, 6})

    found: set[int] = set()
    for label, value in WEEKDAYS_JA.items():
        if re.search(fr"{label}曜(?:日)?", message):
            found.add(value)
    return frozenset(found) if found else None


def _extract_time_window(message: str) -> tuple[time | None, time | None]:
    range_match = re.search(
        r"(\d{1,2})(?::(\d{2}))?時?\s*(?:-|〜|～|から)\s*(\d{1,2})(?::(\d{2}))?時",
        message,
    )
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


def _extract_duration(message: str, default_minutes: int) -> tuple[int, bool]:
    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*時間", message)
    if hour_match:
        return max(30, int(float(hour_match.group(1)) * 60)), True
    minute_match = re.search(r"(\d+)\s*分", message)
    if minute_match:
        return max(15, int(minute_match.group(1))), True
    if "半日" in message:
        return 240, True
    return default_minutes, False


def parse_request(message: str, today: date, default_duration_minutes: int = 120) -> RequestConstraints:
    normalized = unicodedata.normalize("NFKC", message.strip())
    explicit_dates = _extract_explicit_dates(normalized, today)
    relative_date = _extract_relative_date(normalized, today)
    relative_month_range = _extract_relative_month_range(normalized, today)

    if explicit_dates:
        date_start, date_end = min(explicit_dates), max(explicit_dates)
    elif relative_date is not None:
        date_start = date_end = relative_date
    elif relative_month_range is not None:
        date_start, date_end = relative_month_range
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
    duration_minutes, duration_explicit = _extract_duration(normalized, default_duration_minutes)

    return RequestConstraints(
        date_start=date_start,
        date_end=date_end,
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


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("AIの応答にJSONがありません。")
    return json.loads(cleaned[start : end + 1])


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    hour, minute = map(int, value.split(":"))
    return time(hour, minute)


def parse_request_with_ai(
    message: str,
    today: date,
    default_duration_minutes: int,
    api_key: str,
    model: str,
) -> RequestConstraints:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    prompt = f"""
今日は {today.isoformat()}（日本時間）です。
日程調整メッセージから希望条件をJSONだけで抽出してください。
「N日後」は今日からN日後として計算してください。「来月」「Nか月後」は対象月の1日から末日までとして扱い、日まで指定されていればその日だけにしてください。日付指定がなければ今日から14日後までにしてください。

{{
  "date_start": "YYYY-MM-DD",
  "date_end": "YYYY-MM-DD",
  "weekdays": [0,1,2,3,4,5,6] または null,
  "time_start": "HH:MM" または null,
  "time_end": "HH:MM" または null,
  "duration_minutes": 整数,
  "duration_explicit": 所要時間の明示があれば true、なければ false
}}
曜日は月曜=0、日曜=6。標準所要時間は {default_duration_minutes} 分。
メッセージ: {message}
""".strip()

    response = client.responses.create(model=model, input=prompt, store=False)
    data = _extract_json(response.output_text)
    weekdays_raw = data.get("weekdays")
    weekdays = frozenset(int(v) for v in weekdays_raw) if weekdays_raw is not None else None
    return RequestConstraints(
        date_start=date.fromisoformat(data["date_start"]),
        date_end=date.fromisoformat(data["date_end"]),
        weekdays=weekdays,
        time_start=_parse_time(data.get("time_start")),
        time_end=_parse_time(data.get("time_end")),
        duration_minutes=max(15, int(data.get("duration_minutes", default_duration_minutes))),
        duration_explicit=bool(data.get("duration_explicit", False)),
    )


def get_secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return os.getenv(name, default)


def default_availability() -> pd.DataFrame:
    today = date.today()
    rows = []
    for offset in range(1, 8):
        day = today + timedelta(days=offset)
        if day.weekday() < 5:
            rows.append({"日付": day, "開始": time(18, 0), "終了": time(22, 0)})
        else:
            rows.append({"日付": day, "開始": time(10, 0), "終了": time(20, 0)})
    return pd.DataFrame(rows)


st.set_page_config(page_title=f"予定返信AI {APP_VERSION}", page_icon="📅", layout="wide")
if "availability_v22" not in st.session_state:
    st.session_state.availability_v22 = default_availability()

st.title(f"予定返信AI・試作版 {APP_VERSION}")
st.caption("N日後・来月・Nか月後の解析と、連続する空き時間の一括表示に対応した版です。予定の確定は行いません。")

with st.sidebar:
    st.header("基本設定")
    name = st.text_input("予定を持つ人の名前", value="山田")
    duration = st.selectbox("標準の所要時間", [60, 90, 120, 180, 240], index=2, format_func=lambda x: f"{x}分")
    api_key = get_secret("OPENAI_API_KEY")
    model = get_secret("OPENAI_MODEL", "gpt-5-mini")
    use_ai = st.toggle("AIで文章を解析", value=bool(api_key), disabled=not bool(api_key))
    if not api_key:
        st.info("APIキー未設定のため、現在はルール解析です。")

left, right = st.columns([1.15, 1])
with left:
    st.subheader("1. 空いている時間を登録")
    edited = st.data_editor(
        st.session_state.availability_v22,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "日付": st.column_config.DateColumn("日付", required=True),
            "開始": st.column_config.TimeColumn("開始", required=True, step=1800),
            "終了": st.column_config.TimeColumn("終了", required=True, step=1800),
        },
        hide_index=True,
        key="availability_editor_v22",
    )
    st.session_state.availability_v22 = edited

with right:
    st.subheader("2. 相手のメッセージを入力")
    message = st.text_area("受信したメッセージ", value="来月の平日夜に2時間くらい会える？", height=130)
    analyze = st.button("返信候補を作る", type="primary", use_container_width=True)

if analyze:
    errors: list[str] = []
    availabilities: list[Availability] = []
    for index, row in edited.iterrows():
        try:
            day_value = row["日付"]
            if isinstance(day_value, datetime):
                day_value = day_value.date()
            start_value, end_value = row["開始"], row["終了"]
            if start_value >= end_value:
                errors.append(f"{index + 1}行目：終了時刻は開始時刻より後にしてください。")
                continue
            availabilities.append(Availability(day=day_value, start=start_value, end=end_value))
        except Exception:
            errors.append(f"{index + 1}行目：日付・開始・終了をすべて入力してください。")

    if not message.strip():
        errors.append("相手のメッセージを入力してください。")

    if errors:
        for error in errors:
            st.error(error)
    else:
        try:
            if use_ai:
                constraints = parse_request_with_ai(message, date.today(), duration, api_key, model)
                parser_label = f"AI解析（{model}）"
            else:
                constraints = parse_request(message, date.today(), duration)
                parser_label = "ルール解析"

            candidates = find_candidates(availabilities, constraints, limit=5)
            reply = build_reply(name, candidates)

            st.divider()
            st.subheader("3. 結果")
            st.text_area("そのまま送れる返信候補", value=reply, height=120)
            with st.expander("判定内容を確認"):
                st.write(f"アプリ版：{APP_VERSION}")
                st.write(f"解析方法：{parser_label}")
                st.write(f"対象期間：{constraints.date_start} 〜 {constraints.date_end}")
                st.write(f"所要時間：{constraints.duration_minutes}分")
                if candidates:
                    st.write("候補：")
                    for candidate in candidates:
                        st.write(f"- {format_candidate(candidate)}")
                else:
                    st.write("候補はありません。")
        except Exception as exc:
            st.error(f"解析に失敗しました：{exc}")

st.divider()
st.caption("対応例：『来月』『再来月』『3か月後』『来月15日』。18:00〜22:00が空きで『2時間』なら、分割せず『18:00〜22:00の間で2時間』と表示します。")
