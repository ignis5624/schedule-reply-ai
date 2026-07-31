from __future__ import annotations

import json
import os
import re
from datetime import date, time
from typing import Any

from scheduler import RequestConstraints


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
    model: str = "gpt-5-mini",
) -> RequestConstraints:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    prompt = f"""
今日は {today.isoformat()}（日本時間）です。
日程調整メッセージから、希望条件をJSONだけで抽出してください。
曖昧な条件を勝手に狭めないでください。日付指定がなければ今日から14日後までにしてください。

JSON形式:
{{
  "date_start": "YYYY-MM-DD",
  "date_end": "YYYY-MM-DD",
  "weekdays": [0,1,2,3,4,5,6] または null,
  "time_start": "HH:MM" または null,
  "time_end": "HH:MM" または null,
  "duration_minutes": 整数
}}
曜日は月曜=0、日曜=6です。標準所要時間は {default_duration_minutes} 分です。

メッセージ:
{message}
""".strip()

    response = client.responses.create(
        model=model,
        input=prompt,
        store=False,
    )
    data = _extract_json(response.output_text)
    weekdays_raw = data.get("weekdays")
    weekdays = frozenset(int(value) for value in weekdays_raw) if weekdays_raw is not None else None

    return RequestConstraints(
        date_start=date.fromisoformat(data["date_start"]),
        date_end=date.fromisoformat(data["date_end"]),
        weekdays=weekdays,
        time_start=_parse_time(data.get("time_start")),
        time_end=_parse_time(data.get("time_end")),
        duration_minutes=max(15, int(data.get("duration_minutes", default_duration_minutes))),
    )
