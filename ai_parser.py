from __future__ import annotations

import json
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
    model: str,
) -> RequestConstraints:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    prompt = f"""
今日は {today.isoformat()}（日本時間）です。
日程調整メッセージから希望条件をJSONだけで抽出してください。
「N日後」は今日からN日後として計算してください。
週は日曜始まり土曜終わりです。週の前半は日・月・火・水、後半は水・木・金・土です。
「来月」「Nか月後」は対象月の1日から末日までとして扱い、月の前半は1〜15日、後半は16日〜月末です。
日付指定がなければ今日から14日後までにしてください。

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
        dates=None,
        weekdays=weekdays,
        time_start=_parse_time(data.get("time_start")),
        time_end=_parse_time(data.get("time_end")),
        duration_minutes=max(15, int(data.get("duration_minutes", default_duration_minutes))),
        duration_explicit=bool(data.get("duration_explicit", False)),
    )
