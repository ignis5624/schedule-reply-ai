from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from ai_parser import parse_request_with_ai
from scheduler import Availability, build_reply, find_candidates, format_candidate, parse_request

st.set_page_config(page_title="予定返信AI・試作版", page_icon="📅", layout="wide")


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


if "availability" not in st.session_state:
    st.session_state.availability = default_availability()

st.title("予定返信AI・試作版")
st.caption("登録した空き時間から候補を探し、相手への返信文を作ります。予定の確定は行いません。")

with st.sidebar:
    st.header("基本設定")
    name = st.text_input("予定を持つ人の名前", value="山田")
    duration = st.selectbox("標準の所要時間", options=[60, 90, 120, 180, 240], index=2, format_func=lambda x: f"{x}分")
    api_key = get_secret("OPENAI_API_KEY")
    model = get_secret("OPENAI_MODEL", "gpt-5-mini")
    use_ai = st.toggle("AIで文章を解析", value=bool(api_key), disabled=not bool(api_key))
    if not api_key:
        st.info("APIキー未設定のため、現在はルール解析です。試作品の基本動作は確認できます。")

left, right = st.columns([1.15, 1])

with left:
    st.subheader("1. 空いている時間を登録")
    edited = st.data_editor(
        st.session_state.availability,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "日付": st.column_config.DateColumn("日付", required=True),
            "開始": st.column_config.TimeColumn("開始", required=True, step=1800),
            "終了": st.column_config.TimeColumn("終了", required=True, step=1800),
        },
        hide_index=True,
        key="availability_editor",
    )
    st.session_state.availability = edited

with right:
    st.subheader("2. 相手のメッセージを入力")
    message = st.text_area(
        "受信したメッセージ",
        value="来週の平日夜に2時間くらいご飯行ける？",
        height=130,
    )
    analyze = st.button("返信候補を作る", type="primary", use_container_width=True)

if analyze:
    errors: list[str] = []
    availabilities: list[Availability] = []
    for index, row in edited.iterrows():
        try:
            day_value = row["日付"]
            if isinstance(day_value, datetime):
                day_value = day_value.date()
            start_value = row["開始"]
            end_value = row["終了"]
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
                constraints = parse_request_with_ai(
                    message=message,
                    today=date.today(),
                    default_duration_minutes=duration,
                    api_key=api_key,
                    model=model,
                )
                parser_label = f"AI解析（{model}）"
            else:
                constraints = parse_request(message, date.today(), duration)
                parser_label = "ルール解析"

            candidates = find_candidates(availabilities, constraints, limit=5)
            reply = build_reply(name, candidates, message)

            st.divider()
            st.subheader("3. 結果")
            st.text_area("そのまま送れる返信候補", value=reply, height=120)

            with st.expander("判定内容を確認"):
                st.write(f"解析方法：{parser_label}")
                st.write(f"対象期間：{constraints.date_start} 〜 {constraints.date_end}")
                st.write(f"所要時間：{constraints.duration_minutes}分")
                if constraints.weekdays is not None:
                    labels = "・".join("月火水木金土日"[day] for day in sorted(constraints.weekdays))
                    st.write(f"曜日：{labels}")
                if constraints.time_start or constraints.time_end:
                    start_label = constraints.time_start.strftime("%H:%M") if constraints.time_start else "指定なし"
                    end_label = constraints.time_end.strftime("%H:%M") if constraints.time_end else "指定なし"
                    st.write(f"時間帯：{start_label} 〜 {end_label}")

                if candidates:
                    st.write("候補：")
                    for candidate in candidates:
                        st.write(f"- {format_candidate(candidate)}")
                else:
                    st.write("候補はありません。")
        except Exception as exc:
            st.error(f"解析に失敗しました：{exc}")
            st.caption("AI解析で失敗した場合は、サイドバーのAI解析をオフにするとルール解析で試せます。")

st.divider()
st.caption("次段階：Google Calendarの空き時間取得 → 本人承認 → LINE公式アカウントのグループ返信")
