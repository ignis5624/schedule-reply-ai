from __future__ import annotations

import re
from datetime import date

from domain.models import RequestConstraints


VAGUE_DATE_TOKENS = ("今度", "近いうち", "そのうち", "いつか")
SCHEDULING_CUES = ("空いて", "予定", "何日", "都合", "会える", "候補", "日程")
DAYPART_TOKENS = ("早朝", "朝", "午前", "昼", "午後", "夕方", "夜", "晩", "深夜")


def _clarification(question: str) -> tuple[str, str, None]:
    return "needs_clarification", question, None


def classify_request(
    message: str,
    constraints: RequestConstraints,
    *,
    today: date | None = None,
    recognized_fields: frozenset[str] = frozenset(),
) -> tuple[str, str | None, str | None]:
    """確定解析・聞き返し・柔らかい誘いを安全側に分類する。"""

    has_vague_date = any(token in message for token in VAGUE_DATE_TOKENS)
    if has_vague_date and constraints.date_context == "default":
        if any(cue in message for cue in SCHEDULING_CUES) or "いつ空いて" in message:
            return _clarification("今週・来週・今月のどのあたりを想定していますか？")
        return "soft_invitation", None, "ぜひ、また都合の合うときに行きましょう。"

    unsupported_questions = (
        (("仕事終わり", "仕事後", "学校終わり", "授業後"),
         "「仕事・学校終わり」は何時頃ですか？"),
        (("数時間",), "何時間くらい必要ですか？"),
        (("祝日",), "祝日を含めますか？現在は祝日判定を自動できません。"),
        (("週半ば", "週の真ん中", "月半ば", "月の真ん中", "終盤"),
         "希望する日付や曜日の範囲をもう少し具体的に教えてください。"),
    )
    for tokens, question in unsupported_questions:
        if any(token in message for token in tokens):
            return _clarification(question)

    if re.search(r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十]+)\s*時間\s*(?:弱|強)", message):
        return _clarification("「時間弱・時間強」は幅があるため、最小と最大の所要時間を教えてください。")
    if re.search(r"第?[1-5]\s*[月火水木金土日]曜", message) and constraints.date_context != "exact":
        return _clarification("第何曜日かは、対象の月も教えてください。")
    if re.search(r"(?<!\d)24(?::00|時)", message) and not constraints.time_spans_next_day:
        return _clarification("「24時」は、指定日の翌日0時としてよいですか？")

    if "夜まで" in message:
        return _clarification("「夜まで」は、何時までを想定していますか？")

    if today is not None and constraints.date_end < today:
        return _clarification("指定された日付は過去です。年または日付を確認させてください。")
    if constraints.date_start > constraints.date_end:
        return _clarification("開始日と終了日の前後関係を確認させてください。")

    exact_dates = constraints.dates
    if exact_dates is None and constraints.date_start == constraints.date_end:
        exact_dates = frozenset({constraints.date_start})
    if exact_dates and constraints.weekdays is not None:
        if not any(day.weekday() in constraints.weekdays for day in exact_dates):
            return _clarification("日付と曜日が一致しません。どちらを優先しますか？")

    bare_clock = re.search(r"(?<!\d)(\d{1,2})(?::\d{2}|時(?:\d{1,2}分|半)?)(?!間)", message)
    if bare_clock and 1 <= int(bare_clock.group(1)) <= 11:
        if not any(token in message for token in DAYPART_TOKENS) and "翌" not in message:
            return _clarification(f"{int(bare_clock.group(1))}時は、午前と午後のどちらですか？")

    if constraints.weekdays is not None and not constraints.weekdays:
        return _clarification("指定された曜日条件が両立しません。希望する曜日を確認させてください。")
    if (
        constraints.time_start
        and constraints.time_end
        and constraints.time_start >= constraints.time_end
        and not constraints.time_spans_next_day
    ):
        return _clarification("開始時刻と終了時刻の前後関係を確認させてください。")
    if (
        constraints.start_time_earliest
        and constraints.start_time_latest
        and constraints.start_time_earliest > constraints.start_time_latest
    ):
        return _clarification("日付をまたぐ開始時刻の範囲はまだ扱えません。時刻を確認させてください。")

    if not recognized_fields:
        has_schedule_intent = any(cue in message for cue in SCHEDULING_CUES) or "いつ空いて" in message
        if not has_schedule_intent:
            return _clarification("日付・曜日・時間帯のいずれかを教えてください。")
    return "resolved", None, None
