from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from domain.models import BusyInterval


FREEBUSY_SCOPE = "https://www.googleapis.com/auth/calendar.freebusy"
TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"


class GoogleCalendarError(RuntimeError):
    """Google Calendar連携を利用者向けに扱える例外。"""


@dataclass(frozen=True)
class GoogleCalendarConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    calendar_ids: tuple[str, ...] = ("primary",)
    timezone: str = "Asia/Tokyo"

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    def client_config(self) -> dict[str, dict[str, object]]:
        return {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": AUTH_URI,
                "token_uri": TOKEN_URI,
                "redirect_uris": [self.redirect_uri],
            }
        }


def create_authorization_url(config: GoogleCalendarConfig) -> tuple[str, str]:
    """認可URLとCSRF検証用stateを作る。Googleライブラリは利用時だけ読む。"""

    if not config.configured:
        raise GoogleCalendarError("Google CalendarのOAuth設定が不足しています。")

    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(config.client_config(), scopes=[FREEBUSY_SCOPE])
    flow.redirect_uri = config.redirect_uri
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return authorization_url, state


def exchange_authorization_response(
    config: GoogleCalendarConfig,
    authorization_response: str,
    expected_state: str,
) -> str:
    """OAuthコールバックを検証し、セッション保存用credentials JSONを返す。"""

    if not config.configured:
        raise GoogleCalendarError("Google CalendarのOAuth設定が不足しています。")

    query = parse_qs(urlparse(authorization_response).query)
    returned_state = query.get("state", [""])[0]
    if not expected_state or returned_state != expected_state:
        raise GoogleCalendarError("Google連携の確認情報が一致しません。もう一度接続してください。")

    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(
        config.client_config(),
        scopes=[FREEBUSY_SCOPE],
        state=expected_state,
    )
    flow.redirect_uri = config.redirect_uri
    try:
        flow.fetch_token(authorization_response=authorization_response)
    except Exception as exc:
        raise GoogleCalendarError("Google Calendarの認証を完了できませんでした。") from exc
    return flow.credentials.to_json()


def _parse_google_datetime(value: str, timezone: ZoneInfo) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone).replace(tzinfo=None)


def parse_freebusy_response(
    response: dict[str, Any],
    *,
    calendar_ids: Iterable[str],
    timezone_name: str = "Asia/Tokyo",
) -> list[BusyInterval]:
    """freeBusy応答を、既存の日程計算が扱うbusy区間へ変換する。"""

    timezone = ZoneInfo(timezone_name)
    calendars = response.get("calendars", {})
    intervals: list[BusyInterval] = []
    for calendar_id in calendar_ids:
        calendar = calendars.get(calendar_id, {})
        errors = calendar.get("errors", [])
        if errors:
            reason = errors[0].get("reason", "unknown")
            raise GoogleCalendarError(f"カレンダーの空き状況を取得できませんでした（{reason}）。")
        for busy in calendar.get("busy", []):
            try:
                start = _parse_google_datetime(busy["start"], timezone)
                end = _parse_google_datetime(busy["end"], timezone)
                intervals.append(
                    BusyInterval(
                        start=start,
                        end=end,
                        label="Google Calendarの予定",
                        source="google_calendar",
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise GoogleCalendarError("Google Calendarの応答形式を解釈できませんでした。") from exc
    return intervals


def fetch_busy_intervals(
    credentials_json: str,
    config: GoogleCalendarConfig,
    *,
    date_start: date,
    date_end: date,
    service: object | None = None,
) -> tuple[list[BusyInterval], str]:
    """予定の題名や内容を取得せず、指定期間のbusy時間だけを取得する。

    戻り値の2要素目は、アクセストークン更新後のcredentials JSON。
    """

    if date_start > date_end:
        raise ValueError("取得期間の開始日は終了日以前にしてください。")
    if not config.calendar_ids:
        return [], credentials_json

    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    try:
        credentials_data = json.loads(credentials_json)
        credentials = Credentials.from_authorized_user_info(
            credentials_data,
            scopes=[FREEBUSY_SCOPE],
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        if not credentials.valid:
            raise GoogleCalendarError("Google Calendarの接続期限が切れました。再接続してください。")
    except GoogleCalendarError:
        raise
    except Exception as exc:
        raise GoogleCalendarError("Google Calendarの接続情報を読み込めませんでした。") from exc

    if service is None:
        from googleapiclient.discovery import build

        service = build("calendar", "v3", credentials=credentials, cache_discovery=False)

    timezone = ZoneInfo(config.timezone)
    time_min = datetime.combine(date_start, time.min, tzinfo=timezone)
    time_max = datetime.combine(date_end + timedelta(days=1), time.min, tzinfo=timezone)
    body = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "timeZone": config.timezone,
        "items": [{"id": calendar_id} for calendar_id in config.calendar_ids],
    }
    try:
        response = service.freebusy().query(body=body).execute()
    except Exception as exc:
        raise GoogleCalendarError("Google Calendarから空き状況を取得できませんでした。") from exc

    intervals = parse_freebusy_response(
        response,
        calendar_ids=config.calendar_ids,
        timezone_name=config.timezone,
    )
    return intervals, credentials.to_json()
