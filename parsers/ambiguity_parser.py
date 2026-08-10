from __future__ import annotations

import re

from domain.models import RequestConstraints


VAGUE_DATE_TOKENS = ("今度", "近いうち", "そのうち")
SCHEDULING_CUES = ("空いて", "いつ", "何日", "都合", "会える", "どう", "候補")
DAYPART_TOKENS = ("早朝", "朝", "午前", "昼", "午後", "夕方", "夜", "晩", "深夜")


def classify_request(
    message: str,
    constraints: RequestConstraints,
) -> tuple[str, str | None, str | None]:
    """確定解析・聞き返し・柔らかい誘いを安全側に分類する。"""

    has_vague_date = any(token in message for token in VAGUE_DATE_TOKENS)
    if has_vague_date and constraints.date_context == "default":
        if any(cue in message for cue in SCHEDULING_CUES):
            return (
                "needs_clarification",
                "今週・来週・今月のどのあたりを想定していますか？",
                None,
            )
        return (
            "soft_invitation",
            None,
            "ぜひ、また都合の合うときに行きましょう。",
        )

    if "夜まで" in message:
        return (
            "needs_clarification",
            "「夜まで」は、何時までを想定していますか？",
            None,
        )

    bare_clock = re.search(
        r"(?<!\d)(\d{1,2})(?::\d{2}|時(?:\d{1,2}分|半)?)(?!間)", message
    )
    if bare_clock and 1 <= int(bare_clock.group(1)) <= 11:
        if not any(token in message for token in DAYPART_TOKENS):
            return (
                "needs_clarification",
                f"{int(bare_clock.group(1))}時は、午前と午後のどちらですか？",
                None,
            )

    if constraints.weekdays is not None and not constraints.weekdays:
        return (
            "needs_clarification",
            "指定された曜日条件が両立しません。希望する曜日を確認させてください。",
            None,
        )
    if constraints.time_start and constraints.time_end and constraints.time_start >= constraints.time_end:
        return (
            "needs_clarification",
            "開始時刻と終了時刻の前後関係を確認させてください。",
            None,
        )
    if (
        constraints.start_time_earliest
        and constraints.start_time_latest
        and constraints.start_time_earliest > constraints.start_time_latest
    ):
        return (
            "needs_clarification",
            "日付をまたぐ開始時刻の範囲はまだ扱えません。時刻を確認させてください。",
            None,
        )
    return "resolved", None, None
