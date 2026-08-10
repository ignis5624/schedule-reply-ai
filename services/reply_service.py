from __future__ import annotations

from domain.models import Candidate
from parsers.constants import WEEKDAY_LABELS


def _format_duration(minutes: int) -> str:
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours}時間{remainder}分"
    if hours:
        return f"{hours}時間"
    return f"{remainder}分"


def _format_requested_duration(candidate: Candidate) -> str:
    minimum = candidate.required_duration_minutes
    maximum = candidate.maximum_duration_minutes
    if maximum is not None and maximum > minimum:
        return f"{_format_duration(minimum)}〜{_format_duration(maximum)}"
    return _format_duration(minimum)


def format_candidate(candidate: Candidate) -> str:
    """候補を利用者向けの日本語へ整形する。"""

    start, end = candidate.start, candidate.end
    weekday = WEEKDAY_LABELS[start.weekday()]
    if candidate.latest_start is not None:
        duration_label = _format_requested_duration(candidate)
        if candidate.latest_start == start:
            return f"{start.month}/{start.day}（{weekday}）{start:%H:%M}開始で{duration_label}"
        return (
            f"{start.month}/{start.day}（{weekday}）"
            f"{start:%H:%M}〜{candidate.latest_start:%H:%M}開始で{duration_label}"
        )

    base = f"{start.month}/{start.day}（{weekday}）{start:%H:%M}〜{end:%H:%M}"
    available_minutes = int((end - start).total_seconds() // 60)
    if candidate.maximum_duration_minutes is not None:
        return f"{base}の間で{_format_requested_duration(candidate)}"
    if candidate.duration_explicit and available_minutes > candidate.required_duration_minutes:
        return f"{base}の間で{_format_requested_duration(candidate)}"
    return base


def build_reply(name: str, candidates: list[Candidate]) -> str:
    """候補一覧から送信用の返信文を作る。"""

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
