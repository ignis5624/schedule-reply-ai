from __future__ import annotations

import os
from datetime import date, timedelta
from urllib.parse import urlencode

import streamlit as st

from integrations.google_calendar import (
    GoogleCalendarConfig,
    GoogleCalendarError,
    create_authorization_url,
    exchange_authorization_response,
    fetch_busy_intervals,
)
from integrations.openai_parser import analyze_request_with_ai
from parsers.compound_parser import analyze_grouped_request
from services.availability_service import (
    build_availabilities,
    subtract_busy_from_availabilities,
)
from services.candidate_service import find_candidate_groups
from services.reply_service import (
    build_decline_reply,
    build_grouped_reply,
    build_pending_reply,
    format_candidate,
)
from ui.availability_forms import (
    default_direct_availability,
    default_one_off_busy,
    default_recurring_busy,
    default_weekly_availability,
    read_direct_availabilities,
    read_one_off_busy_intervals,
    read_recurring_busy_rules,
    read_weekly_availability_rules,
)

APP_VERSION = "v4.5-quick-reply-calendar"
DIRECT_SESSION_KEY = "direct_availability_public_v44"
WEEKLY_SESSION_KEY = "weekly_availability_public_v44"
RECURRING_SESSION_KEY = "recurring_busy_public_v44"
ONE_OFF_SESSION_KEY = "one_off_busy_public_v44"
RESULT_SESSION_KEY = "reply_result_public_v45"
EDITED_REPLY_SESSION_KEY = "edited_reply_public_v45"
GOOGLE_CREDENTIALS_KEY = "google_calendar_credentials_v45"
GOOGLE_STATE_KEY = "google_calendar_oauth_state_v45"
GOOGLE_AUTH_URL_KEY = "google_calendar_auth_url_v45"
GOOGLE_NOTICE_KEY = "google_calendar_notice_v45"
MAX_GENERATION_DAYS = 180


def _get_secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return os.getenv(name, default)


def _google_config() -> GoogleCalendarConfig:
    calendar_ids = tuple(
        value.strip()
        for value in _get_secret("GOOGLE_CALENDAR_IDS", "primary").split(",")
        if value.strip()
    )
    return GoogleCalendarConfig(
        client_id=_get_secret("GOOGLE_CLIENT_ID"),
        client_secret=_get_secret("GOOGLE_CLIENT_SECRET"),
        redirect_uri=_get_secret("GOOGLE_REDIRECT_URI"),
        calendar_ids=calendar_ids or ("primary",),
        timezone=_get_secret("GOOGLE_TIME_ZONE", "Asia/Tokyo"),
    )


def _query_value(name: str) -> str:
    value = st.query_params.get(name, "")
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value)


def _handle_google_callback(config: GoogleCalendarConfig) -> None:
    code = _query_value("code")
    returned_state = _query_value("state")
    error = _query_value("error")
    if not code and not error:
        return

    if error:
        st.session_state[GOOGLE_NOTICE_KEY] = "Google Calendarへの接続がキャンセルされました。"
    else:
        query = urlencode({"code": code, "state": returned_state})
        authorization_response = f"{config.redirect_uri}?{query}"
        try:
            credentials_json = exchange_authorization_response(
                config,
                authorization_response,
                st.session_state.get(GOOGLE_STATE_KEY, ""),
            )
            st.session_state[GOOGLE_CREDENTIALS_KEY] = credentials_json
            st.session_state[GOOGLE_NOTICE_KEY] = "Google Calendarを接続しました。"
        except GoogleCalendarError as exc:
            st.session_state[GOOGLE_NOTICE_KEY] = str(exc)
    st.session_state.pop(GOOGLE_AUTH_URL_KEY, None)
    st.session_state.pop(GOOGLE_STATE_KEY, None)
    st.query_params.clear()
    st.rerun()


def _ensure_google_authorization_url(config: GoogleCalendarConfig) -> str:
    existing = st.session_state.get(GOOGLE_AUTH_URL_KEY)
    if existing:
        return str(existing)
    url, state = create_authorization_url(config)
    st.session_state[GOOGLE_AUTH_URL_KEY] = url
    st.session_state[GOOGLE_STATE_KEY] = state
    return url


def _generation_period(outcome: object) -> tuple[date, date, bool]:
    groups = getattr(outcome, "groups", ())
    constraints = [group.constraints for group in groups] if groups else [outcome.constraints]
    start = min(value.date_start for value in constraints)
    requested_end = max(value.date_end for value in constraints)
    maximum_end = start + timedelta(days=MAX_GENERATION_DAYS)
    if requested_end == date.max or requested_end > maximum_end:
        return start, maximum_end, True
    return start, requested_end, False


def _render_schedule_settings(availability_mode: str) -> tuple[object, object, object]:
    if availability_mode == "通常時間から予定を差し引く":
        weekly_tab, recurring_tab, one_off_tab = st.tabs(
            ["通常対応時間", "仕事・学校", "単発予定"]
        )
        with weekly_tab:
            st.caption("候補を探す母体の時間です。終了00:00は翌日0時として扱います。")
            weekly_edited = st.data_editor(
                st.session_state[WEEKLY_SESSION_KEY],
                num_rows="dynamic",
                width="stretch",
                column_config={
                    "対象曜日": st.column_config.TextColumn("対象曜日", required=True),
                    "開始": st.column_config.TimeColumn("開始", required=True, step=1800),
                    "終了": st.column_config.TimeColumn("終了", required=True, step=1800),
                    "有効": st.column_config.CheckboxColumn("有効"),
                },
                hide_index=True,
                key="weekly_availability_editor_v44",
            )
            st.session_state[WEEKLY_SESSION_KEY] = weekly_edited
        with recurring_tab:
            st.caption("仕事・学校・アルバイトなど、毎週繰り返す予定です。")
            recurring_edited = st.data_editor(
                st.session_state[RECURRING_SESSION_KEY],
                num_rows="dynamic",
                width="stretch",
                column_config={
                    "予定名": st.column_config.TextColumn("予定名"),
                    "対象曜日": st.column_config.TextColumn("対象曜日", required=True),
                    "開始": st.column_config.TimeColumn("開始", required=True, step=1800),
                    "終了": st.column_config.TimeColumn("終了", required=True, step=1800),
                    "適用開始日": st.column_config.DateColumn("適用開始日"),
                    "適用終了日": st.column_config.DateColumn("適用終了日"),
                    "有効": st.column_config.CheckboxColumn("有効"),
                },
                hide_index=True,
                key="recurring_busy_editor_v44",
            )
            st.session_state[RECURRING_SESSION_KEY] = recurring_edited
        with one_off_tab:
            st.caption("一度だけの予定です。Google連携時はカレンダーのbusy時間も自動で加わります。")
            one_off_edited = st.data_editor(
                st.session_state[ONE_OFF_SESSION_KEY],
                num_rows="dynamic",
                width="stretch",
                column_config={
                    "予定名": st.column_config.TextColumn("予定名"),
                    "開始日": st.column_config.DateColumn("開始日", required=True),
                    "開始": st.column_config.TimeColumn("開始", required=True, step=1800),
                    "終了日": st.column_config.DateColumn("終了日", required=True),
                    "終了": st.column_config.TimeColumn("終了", required=True, step=1800),
                    "有効": st.column_config.CheckboxColumn("有効"),
                },
                hide_index=True,
                key="one_off_busy_editor_v44",
            )
            st.session_state[ONE_OFF_SESSION_KEY] = one_off_edited
        return weekly_edited, recurring_edited, one_off_edited

    st.caption("従来方式です。終了日を翌日以降にすると日付またぎで登録できます。")
    direct_edited = st.data_editor(
        st.session_state[DIRECT_SESSION_KEY],
        num_rows="dynamic",
        width="stretch",
        column_config={
            "開始日": st.column_config.DateColumn("開始日", required=True),
            "開始": st.column_config.TimeColumn("開始", required=True, step=1800),
            "終了日": st.column_config.DateColumn("終了日", required=True),
            "終了": st.column_config.TimeColumn("終了", required=True, step=1800),
        },
        hide_index=True,
        key="direct_availability_editor_v44",
    )
    st.session_state[DIRECT_SESSION_KEY] = direct_edited
    return direct_edited, None, None


def _render_result(result: dict[str, object]) -> None:
    st.divider()
    st.subheader("返信案")
    st.text_area(
        "必要なら送る前に編集できます",
        height=120,
        key=EDITED_REPLY_SESSION_KEY,
    )
    st.caption("右上のコピーアイコンからコピーできます。")
    st.code(st.session_state[EDITED_REPLY_SESSION_KEY], language=None, wrap_lines=True)

    tone = str(result["tone"])
    with st.expander("今すぐ日程を決められない／今回は断る"):
        st.write("**少し待ってもらう**")
        st.code(build_pending_reply(tone), language=None, wrap_lines=True)
        st.write("**今回は断る**")
        st.code(build_decline_reply(tone), language=None, wrap_lines=True)

    outcome = result["outcome"]
    candidate_groups = result["candidate_groups"]
    availabilities = result["availabilities"]
    with st.expander("判定内容を確認"):
        st.write(f"アプリ版：{APP_VERSION}")
        st.write(f"解析方法：{result['parser_label']}")
        constraints = outcome.constraints
        if constraints.date_end == date.max:
            st.write(f"対象期間：{constraints.date_start} 以降")
        else:
            st.write(f"対象期間：{constraints.date_start} 〜 {constraints.date_end}")
        st.write(f"所要時間：{constraints.duration_minutes}分")
        st.write(f"空き時間の作成：{result['availability_mode']}")
        if result["google_busy_count"]:
            st.write(f"Google Calendarから反映したbusy：{result['google_busy_count']}件")
        if outcome.status != "resolved":
            st.write(f"判定：{outcome.status}")
        elif any(group.candidates for group in candidate_groups):
            st.write("候補：")
            for index, group in enumerate(candidate_groups, start=1):
                if not group.candidates:
                    continue
                heading = group.label or f"条件{index}"
                if group.source_text:
                    heading += f"（{group.source_text}）"
                st.write(f"**{heading}**")
                for candidate in group.candidates:
                    st.write(f"- {format_candidate(candidate)}")
        else:
            st.write("候補はありません。")
        if availabilities and result["generation_capped"]:
            st.info(f"無期限または長期間の指定のため、最初の{MAX_GENERATION_DAYS}日分を計算しました。")


def run_app() -> None:
    st.set_page_config(page_title="予定返信AI", page_icon="📅", layout="centered")

    defaults = (
        (DIRECT_SESSION_KEY, default_direct_availability),
        (WEEKLY_SESSION_KEY, default_weekly_availability),
        (RECURRING_SESSION_KEY, default_recurring_busy),
        (ONE_OFF_SESSION_KEY, default_one_off_busy),
    )
    for key, factory in defaults:
        if key not in st.session_state:
            st.session_state[key] = factory()

    google_config = _google_config()
    _handle_google_callback(google_config)

    st.title("予定返信AI")
    st.caption("届いたメッセージを貼るだけで、空いている候補と返信文を作ります。")
    notice = st.session_state.pop(GOOGLE_NOTICE_KEY, None)
    if notice:
        st.info(notice)

    with st.sidebar:
        st.header("設定")
        duration = st.selectbox(
            "標準の所要時間",
            [60, 90, 120, 180, 240],
            index=2,
            format_func=lambda value: f"{value}分",
        )
        tone_label = st.selectbox("返信の雰囲気", ["友人向け", "ふつう", "丁寧"])
        tone = {"友人向け": "casual", "ふつう": "neutral", "丁寧": "polite"}[tone_label]
        api_key = _get_secret("OPENAI_API_KEY")
        model = _get_secret("OPENAI_MODEL", "gpt-5-mini")
        use_ai = st.toggle("AIで文章を解析", value=False, disabled=not bool(api_key))
        availability_mode = st.radio(
            "空き時間の作り方",
            ("通常時間から予定を差し引く", "空き時間を直接登録"),
            help="通常時間から、仕事・学校・単発予定・Google Calendarの予定を差し引けます。",
        )

        st.divider()
        st.subheader("Google Calendar")
        google_connected = bool(st.session_state.get(GOOGLE_CREDENTIALS_KEY))
        if google_connected:
            st.success("接続済み（予定内容は取得しません）")
            if st.button("接続を解除", width="stretch"):
                st.session_state.pop(GOOGLE_CREDENTIALS_KEY, None)
                st.session_state.pop(GOOGLE_AUTH_URL_KEY, None)
                st.rerun()
        elif google_config.configured:
            try:
                st.link_button(
                    "Google Calendarを接続",
                    _ensure_google_authorization_url(google_config),
                    width="stretch",
                )
            except GoogleCalendarError as exc:
                st.error(str(exc))
        else:
            st.caption("公開環境のOAuth設定後に接続ボタンが表示されます。")
        use_google = st.toggle(
            "Googleの予定を候補から除外",
            value=google_connected,
            disabled=not google_connected,
        )
        if not api_key:
            st.caption("AI未設定でもルール解析で動作します。")

    st.subheader("1. 相手のメッセージを貼る")
    message = st.text_area(
        "受信したメッセージ",
        value="来週の平日夜に2時間くらい会える？",
        height=120,
        label_visibility="collapsed",
    )

    with st.expander("2. 空き時間・仕事・学校を設定", expanded=False):
        edited_values = _render_schedule_settings(availability_mode)

    analyze = st.button("返信を作る", type="primary", width="stretch")
    if analyze:
        errors: list[str] = []
        weekly_rules = []
        recurring_rules = []
        one_off_busy = []
        if availability_mode == "通常時間から予定を差し引く":
            weekly_rules, weekly_errors = read_weekly_availability_rules(edited_values[0])
            recurring_rules, recurring_errors = read_recurring_busy_rules(edited_values[1])
            one_off_busy, one_off_errors = read_one_off_busy_intervals(edited_values[2])
            errors.extend(weekly_errors + recurring_errors + one_off_errors)
            availabilities = []
        else:
            availabilities, direct_errors = read_direct_availabilities(edited_values[0])
            errors.extend(direct_errors)
        if not message.strip():
            errors.append("相手のメッセージを入力してください。")

        if errors:
            for error in errors:
                st.error(error)
        else:
            try:
                rule_outcome = analyze_grouped_request(message, date.today(), duration)
                if rule_outcome.status == "resolved" and use_ai and len(rule_outcome.groups) <= 1:
                    outcome = analyze_request_with_ai(
                        message, date.today(), duration, api_key, model
                    )
                    parser_label = f"AI解析（{model}）"
                else:
                    outcome = rule_outcome
                    parser_label = "ルール解析"

                candidate_groups = []
                generation_capped = False
                google_busy_count = 0
                if outcome.status == "needs_clarification":
                    reply = outcome.clarification_question or "希望条件を確認させてください。"
                    parser_label += "（聞き返し）"
                elif outcome.status == "soft_invitation":
                    reply = outcome.suggested_reply or "ぜひ、また都合の合うときに行きましょう。"
                    parser_label += "（柔らかい誘い）"
                else:
                    generation_start, generation_end, generation_capped = _generation_period(outcome)
                    google_busy = []
                    if use_google:
                        credentials_json = str(st.session_state[GOOGLE_CREDENTIALS_KEY])
                        google_busy, refreshed_credentials = fetch_busy_intervals(
                            credentials_json,
                            google_config,
                            date_start=generation_start,
                            date_end=generation_end,
                        )
                        st.session_state[GOOGLE_CREDENTIALS_KEY] = refreshed_credentials
                        google_busy_count = len(google_busy)

                    if availability_mode == "通常時間から予定を差し引く":
                        availabilities = build_availabilities(
                            weekly_rules,
                            recurring_busy_rules=recurring_rules,
                            busy_intervals=[*one_off_busy, *google_busy],
                            date_start=generation_start,
                            date_end=generation_end,
                        )
                    elif google_busy:
                        availabilities = subtract_busy_from_availabilities(
                            availabilities,
                            google_busy,
                        )
                    candidate_groups = find_candidate_groups(
                        availabilities,
                        outcome,
                        limit_per_group=3,
                    )
                    reply = build_grouped_reply(
                        "",
                        candidate_groups,
                        relation=outcome.relation,
                        tone=tone,
                    )

                result = {
                    "reply": reply,
                    "tone": tone,
                    "outcome": outcome,
                    "candidate_groups": candidate_groups,
                    "parser_label": parser_label,
                    "availability_mode": availability_mode,
                    "availabilities": availabilities,
                    "generation_capped": generation_capped,
                    "google_busy_count": google_busy_count,
                }
                st.session_state[RESULT_SESSION_KEY] = result
                st.session_state[EDITED_REPLY_SESSION_KEY] = reply
            except GoogleCalendarError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"解析に失敗しました：{exc}")

    result = st.session_state.get(RESULT_SESSION_KEY)
    if result:
        _render_result(result)

    st.divider()
    with st.expander("対応している表現と固定ルール"):
        st.markdown(
            """
- 日付：今日・明日・N日後、今週・来週、今月・来月、具体的な日付・期間
- 時間：午前・午後・夕方・夜、N時以降・N時まで・N時前後、日付またぎ
- 所要時間：N分・N時間・範囲・以上・以内・N泊N日
- 条件：除外曜日、複合条件、第一希望〜第三希望
- 空き時間：通常対応時間から、仕事・学校・単発予定・Google Calendarのbusyを差し引き

**週明けは月・火、月初は1〜5日、月末は25日〜末日です。**  
**曖昧な条件は無理に推測せず、必要な内容を聞き返します。**
            """
        )


if __name__ == "__main__":
    run_app()
