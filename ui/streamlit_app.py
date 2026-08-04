from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from domain.models import Availability
from integrations.openai_parser import parse_request_with_ai
from parsers.request_parser import parse_request
from services.candidate_service import find_candidates
from services.reply_service import build_reply, format_candidate

APP_VERSION = "v4.0-modular"
SESSION_KEY = "availability_public_v40"


def _get_secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return os.getenv(name, default)


def _default_availability() -> pd.DataFrame:
    today = date.today()
    rows = []
    for offset in range(1, 15):
        day = today + timedelta(days=offset)
        if day.weekday() < 5:
            rows.append({"日付": day, "開始": time(18, 0), "終了": time(22, 0)})
        else:
            rows.append({"日付": day, "開始": time(10, 0), "終了": time(20, 0)})
    return pd.DataFrame(rows)


def _normalize_day(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    raise ValueError("日付として解釈できません。")


def _read_availabilities(edited: pd.DataFrame) -> tuple[list[Availability], list[str]]:
    availabilities: list[Availability] = []
    errors: list[str] = []
    for index, row in edited.iterrows():
        try:
            day_value = _normalize_day(row["日付"])
            start_value = row["開始"]
            end_value = row["終了"]
            if start_value >= end_value:
                errors.append(f"{index + 1}行目：終了時刻は開始時刻より後にしてください。")
                continue
            availabilities.append(Availability(day=day_value, start=start_value, end=end_value))
        except Exception:
            errors.append(f"{index + 1}行目：日付・開始・終了をすべて入力してください。")
    return availabilities, errors


def run_app() -> None:
    st.set_page_config(page_title="予定返信AI", page_icon="📅", layout="wide")

    if SESSION_KEY not in st.session_state:
        st.session_state[SESSION_KEY] = _default_availability()

    st.title("予定返信AI")
    st.caption("空き時間と相手のメッセージから返信候補を作ります。予定は確定せず、候補の提示まで行います。")

    with st.sidebar:
        st.header("基本設定")
        name = st.text_input("予定を持つ人の名前", value="山田")
        duration = st.selectbox(
            "標準の所要時間",
            [60, 90, 120, 180, 240],
            index=2,
            format_func=lambda value: f"{value}分",
        )
        api_key = _get_secret("OPENAI_API_KEY")
        model = _get_secret("OPENAI_MODEL", "gpt-5-mini")
        use_ai = st.toggle("AIで文章を解析", value=False, disabled=not bool(api_key))
        if not api_key:
            st.info("現在はルール解析です。APIキーを設定するとAI解析も選べます。")

    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("1. 空いている時間を登録")
        edited = st.data_editor(
            st.session_state[SESSION_KEY],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "日付": st.column_config.DateColumn("日付", required=True),
                "開始": st.column_config.TimeColumn("開始", required=True, step=1800),
                "終了": st.column_config.TimeColumn("終了", required=True, step=1800),
            },
            hide_index=True,
            key="availability_editor_public_v40",
        )
        st.session_state[SESSION_KEY] = edited

    with right:
        st.subheader("2. 相手のメッセージを入力")
        message = st.text_area(
            "受信したメッセージ",
            value="来週の平日夜に2時間くらい会える？",
            height=130,
        )
        analyze = st.button("返信候補を作る", type="primary", use_container_width=True)

    if analyze:
        availabilities, errors = _read_availabilities(edited)
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
    with st.expander("対応している表現と固定ルール"):
        st.markdown(
            """
- 日付：今日・明日・明後日・明々後日、N日後、N週間後、具体的な日付・期間
- 週：今週・来週・再来週・再々来週、次の曜日、平日、土日、曜日の列挙・範囲
- 月：今月・来月・再来月・Nか月後、具体的な月、前半・後半・上旬・中旬・下旬
- 時間：朝・午前・昼・午後・夕方・夜・深夜、時刻範囲、N時以降・N時まで
- 所要時間：N時間、N時間半、N時間N分、N分

**週の前半は日・月・火・水、後半は水・木・金・土です。**  
**月の前半は1〜15日、後半は16日〜月末です。**
            """
        )
    st.caption("連続する空き時間は一つにまとめます。未対応表現への聞き返しは次の段階で追加します。")
