from __future__ import annotations

from datetime import timedelta

from domain.models import Candidate, CandidateGroup
from parsers.constants import WEEKDAY_LABELS


def _format_duration(minutes: int) -> str:
    if minutes >= 1440 and minutes % 1440 == 0:
        return f"{minutes // 1440}日間"
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
        if candidate.duration_mode == "maximum":
            return f"最大{_format_duration(maximum)}"
        return f"{_format_duration(minimum)}〜{_format_duration(maximum)}"
    if candidate.duration_mode == "minimum":
        return f"{_format_duration(minimum)}以上"
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

    if end.date() == start.date():
        end_label = f"{end:%H:%M}"
    elif end.date() == start.date() + timedelta(days=1):
        end_label = f"翌{end:%H:%M}"
    else:
        end_weekday = WEEKDAY_LABELS[end.weekday()]
        end_label = f"{end.month}/{end.day}（{end_weekday}）{end:%H:%M}"
    base = f"{start.month}/{start.day}（{weekday}）{start:%H:%M}〜{end_label}"
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


def _join_options(labels: list[str]) -> str:
    if len(labels) == 1:
        return labels[0]
    return "、".join(labels[:-1]) + "、または" + labels[-1]


def build_grouped_reply(
    name: str,
    candidate_groups: list[CandidateGroup],
    *,
    relation: str,
) -> str:
    """グループの対応関係と優先順位を保った返信文を作る。"""

    available_groups = [group for group in candidate_groups if group.candidates]
    if not available_groups:
        return build_reply(name, [])

    if relation != "preference":
        labels: list[str] = []
        candidate_index = 0
        while len(labels) < 3:
            added = False
            for group in available_groups:
                if candidate_index < len(group.candidates):
                    labels.append(format_candidate(group.candidates[candidate_index]))
                    added = True
                    if len(labels) >= 3:
                        break
            if not added:
                break
            candidate_index += 1
        return (
            f"{name}さんは、{_join_options(labels)}なら予定を合わせられそうです。"
            "この中で都合のよい時間はありますか？確定前に本人へ確認します。"
        )

    segments: list[str] = []
    for group in available_groups:
        label = group.label or f"第{group.priority}希望"
        options = _join_options(
            [format_candidate(candidate) for candidate in group.candidates[:2]]
        )
        segments.append(f"{label}では{options}")

    unavailable_priorities = {
        group.priority for group in candidate_groups if not group.candidates
    }
    prefix = ""
    if 1 in unavailable_priorities and available_groups[0].priority > 1:
        prefix = "第一希望では条件に合う時間が見つかりませんでしたが、"
    return (
        f"{name}さんは、{prefix}{'、'.join(segments)}なら予定を合わせられそうです。"
        "希望順に確認できますが、どの時間がよいですか？確定前に本人へ確認します。"
    )
