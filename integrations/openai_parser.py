from __future__ import annotations

import json
import re
from datetime import date, time
from typing import Any

from domain.models import ParseOutcome, RequestConstraints


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


def _build_outcome(data: dict[str, Any], default_duration_minutes: int) -> ParseOutcome:
    weekdays_raw = data.get("weekdays")
    weekdays = frozenset(int(value) for value in weekdays_raw) if weekdays_raw is not None else None
    excluded_raw = data.get("excluded_weekdays")
    excluded_weekdays = (
        frozenset(int(value) for value in excluded_raw) if excluded_raw is not None else None
    )
    duration_minutes = max(15, int(data.get("duration_minutes", default_duration_minutes)))
    duration_min_raw = data.get("duration_min_minutes")
    duration_max_raw = data.get("duration_max_minutes")
    constraints = RequestConstraints(
        date_start=date.fromisoformat(data["date_start"]),
        date_end=date.fromisoformat(data["date_end"]),
        dates=None,
        weekdays=weekdays,
        excluded_weekdays=excluded_weekdays,
        time_start=_parse_time(data.get("time_start")),
        time_end=_parse_time(data.get("time_end")),
        start_time_earliest=_parse_time(data.get("start_time_earliest")),
        start_time_latest=_parse_time(data.get("start_time_latest")),
        duration_minutes=duration_minutes,
        duration_explicit=bool(data.get("duration_explicit", False)),
        duration_min_minutes=(max(15, int(duration_min_raw)) if duration_min_raw is not None else None),
        duration_max_minutes=(max(15, int(duration_max_raw)) if duration_max_raw is not None else None),
        date_context="ai",
    )
    status = str(data.get("status", "resolved"))
    if status not in {"resolved", "needs_clarification", "soft_invitation"}:
        status = "needs_clarification"
    return ParseOutcome(
        constraints=constraints,
        status=status,
        clarification_question=data.get("clarification_question"),
        suggested_reply=data.get("suggested_reply"),
    )


def analyze_request_with_ai(
    message: str,
    today: date,
    default_duration_minutes: int,
    api_key: str,
    model: str,
) -> ParseOutcome:
    """OpenAIを利用し、確定条件または聞き返し判定を返す。"""

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    prompt = f"""
今日は {today.isoformat()}（日本時間）です。
日程調整メッセージから希望条件をJSONだけで抽出してください。
「N日後」は今日からN日後として計算してください。
週は日曜始まり土曜終わりです。週の前半は日・月・火・水、後半は水・木・金・土です。
週明けは月曜・火曜です。
「来月」「Nか月後」は対象月の1日から末日までとして扱い、月の前半は1〜15日、後半は16日〜月末です。
月初・月の初め・月頭は1〜5日、月末・月の終わりは25日〜末日です。
「N時前後」は会う時間全体ではなく、開始時刻の許容幅を前後10分としてください。
「火曜以外」「水曜は無理」などの否定曜日は excluded_weekdays に入れてください。
日付指定がなければ今日から14日後までにしてください。
曖昧な語を勝手に具体化しないでください。
「今度」「近いうち」などで期間が決まらない場合は needs_clarification にしてください。
単なる「また今度行きましょう」のような柔らかい誘いは soft_invitation にしてください。

{{
  "status": "resolved" または "needs_clarification" または "soft_invitation",
  "clarification_question": 聞き返し文または null,
  "suggested_reply": 柔らかい誘いへの返信文または null,
  "date_start": "YYYY-MM-DD",
  "date_end": "YYYY-MM-DD",
  "weekdays": [0,1,2,3,4,5,6] または null,
  "excluded_weekdays": [0,1,2,3,4,5,6] または null,
  "time_start": "HH:MM" または null,
  "time_end": "HH:MM" または null,
  "start_time_earliest": "HH:MM" または null,
  "start_time_latest": "HH:MM" または null,
  "duration_minutes": 整数,
  "duration_explicit": 所要時間の明示があれば true、なければ false,
  "duration_min_minutes": 整数または null,
  "duration_max_minutes": 整数または null
}}
曜日は月曜=0、日曜=6。標準所要時間は {default_duration_minutes} 分。
メッセージ: {message}
""".strip()

    response = client.responses.create(model=model, input=prompt, store=False)
    data = _extract_json(response.output_text)
    return _build_outcome(data, default_duration_minutes)


def parse_request_with_ai(
    message: str,
    today: date,
    default_duration_minutes: int,
    api_key: str,
    model: str,
) -> RequestConstraints:
    """旧コード互換用。AI解析結果の条件部分だけを返す。"""

    return analyze_request_with_ai(
        message,
        today,
        default_duration_minutes,
        api_key,
        model,
    ).constraints
