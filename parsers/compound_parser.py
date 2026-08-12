from __future__ import annotations

import re
from dataclasses import replace
from datetime import date

from domain.models import ConstraintGroup, ParseOutcome, RequestConstraints

from .common import normalize_message
from .request_parser import analyze_request


_CONDITION_START = (
    r"(?:今日|本日|明日|明後日|明々後日|今週|来週|再来週|再々来週|"
    r"今月|来月|再来月|再々来月|月初|月末|週明け|"
    r"[月火水木金土日]曜?|平日|土日|週末|午前|午後|朝|昼|夕方|夜|深夜|\d)"
)


def _clean_clause(text: str) -> str:
    cleaned = text.strip(" 、,。.　")
    cleaned = re.sub(r"^(?:できれば|なるべく|希望としては)", "", cleaned)
    cleaned = re.sub(r"^(?:無理なら|むりなら|だめなら|ダメなら|難しければ)", "", cleaned)
    cleaned = re.sub(r"^(?:第?[一二三123]希望)(?:は|が)?", "", cleaned)
    cleaned = re.sub(r"(?:がいい|がよい|を希望)(?:けど|ですが|ものの)?$", "", cleaned)
    cleaned = re.sub(r"(?:けど|ですが|ものの)$", "", cleaned)
    return cleaned.strip(" 、,。.　")


def _split_explicit_priorities(message: str) -> list[tuple[str, int]] | None:
    markers = list(
        re.finditer(r"(?:第)?([一二三123])(?:希望|候補)(?:は|が)?", message)
    )
    if len(markers) < 2:
        return None

    number_map = {"一": 1, "二": 2, "三": 3, "1": 1, "2": 2, "3": 3}
    results: list[tuple[str, int]] = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(message)
        clause = _clean_clause(message[marker.end() : end])
        if clause:
            results.append((clause, number_map[marker.group(1)]))
    return results if len(results) >= 2 else None


def _split_fallback_priorities(message: str) -> list[tuple[str, int]] | None:
    markers = list(re.finditer(
        r"(?:無理なら|むりなら|だめなら|ダメなら|難しければ|"
        r"それが無理なら|それも無理なら|次に|次点で)", message
    ))
    if not markers:
        return None
    results: list[tuple[str, int]] = []
    first = _clean_clause(message[: markers[0].start()])
    if first:
        results.append((first, 1))
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(message)
        clause = _clean_clause(message[marker.end() : end])
        if clause:
            results.append((clause, len(results) + 1))
    return results if len(results) >= 2 else None


def _looks_like_condition(text: str) -> bool:
    return bool(
        re.search(
            r"(?:今日|明日|明後日|今週|来週|再来週|今月|来月|再来月|"
            r"[月火水木金土日]曜?|平日|土日|週末|月初|月末|週明け|"
            r"午前|午後|朝|昼|夕方|夜|深夜|\d{1,4}[年月日時])",
            text,
        )
    )


def _split_alternatives(message: str) -> list[tuple[str, int]] | None:
    explicit = re.split(r"\s*(?:または|又は|もしくは|あるいは|それか|\bor\b|／|/)\s*", message, flags=re.IGNORECASE)
    if len(explicit) >= 2 and all(_looks_like_condition(part) for part in explicit):
        return [(_clean_clause(part), 1) for part in explicit]

    conditional_parts = [_clean_clause(part) for part in re.split(r"[、,]", message)]
    conditional_parts = [part for part in conditional_parts if part]
    if (
        len(conditional_parts) >= 2
        and any(re.search(r"(?:なら|だったら|の場合)", part) for part in conditional_parts)
        and all(_looks_like_condition(part) for part in conditional_parts)
    ):
        return [(part, 1) for part in conditional_parts]

    has_choice_suffix = bool(re.search(r"の?(?:どちらか|いずれか)$", message))
    if has_choice_suffix:
        choice_text = re.sub(r"の?(?:どちらか|いずれか)$", "", message)
        choice_parts = [_clean_clause(part) for part in re.split(r"[、,]|と(?=[月火水木金土日])", choice_text)]
        if len(choice_parts) >= 2 and all(_looks_like_condition(part) for part in choice_parts):
            return [(part, 1) for part in choice_parts]

    paired_parts = [_clean_clause(part) for part in re.split(r"[、,]", message)]
    if len(paired_parts) >= 2 and all(
        re.search(r"(?:[月火水木金土日]曜|平日|土日|週末)", part)
        and re.search(r"(?:午前|午後|朝|昼|夕方|夜|深夜|\d{1,2}時)", part)
        for part in paired_parts
    ):
        return [(part, 1) for part in paired_parts]

    split_pattern = rf"\s*か[、,]?(?={_CONDITION_START})\s*"
    alternatives = re.split(split_pattern, message)
    if len(alternatives) >= 2 and all(_looks_like_condition(part) for part in alternatives):
        return [(_clean_clause(part), 1) for part in alternatives]
    return None


def _condition_kind(text: str) -> str:
    if re.search(r"(?:今日|本日|明日|明後日|明々後日|\d+日後)", text):
        return "relative_date"
    if re.search(r"[月火水木金土日]曜?|平日|土日|週末", text):
        return "weekday"
    if re.search(r"(?:今週|来週|再来週|再々来週|週明け)", text):
        return "week_period"
    if re.search(r"(?:今月|来月|再来月|再々来月|月初|月末|上旬|中旬|下旬)", text):
        return "month_period"
    if re.search(r"(?:\d{1,2}月\s*)?\d{1,2}日", text):
        return "explicit_date"
    return "other"


def _has_time(constraints: RequestConstraints) -> bool:
    return any(
        value is not None
        for value in (
            constraints.time_start,
            constraints.time_end,
            constraints.start_time_earliest,
            constraints.start_time_latest,
        )
    )


def _copy_time(source: RequestConstraints, target: RequestConstraints) -> RequestConstraints:
    return replace(
        target,
        time_start=source.time_start,
        time_end=source.time_end,
        time_spans_next_day=source.time_spans_next_day,
        start_time_earliest=source.start_time_earliest,
        start_time_latest=source.start_time_latest,
    )


def _copy_duration(source: RequestConstraints, target: RequestConstraints) -> RequestConstraints:
    return replace(
        target,
        duration_minutes=source.duration_minutes,
        duration_explicit=source.duration_explicit,
        duration_min_minutes=source.duration_min_minutes,
        duration_max_minutes=source.duration_max_minutes,
        duration_mode=source.duration_mode,
    )


def _priority_label(priority: int) -> str:
    labels = {1: "第一希望", 2: "第二希望", 3: "第三希望"}
    return labels.get(priority, f"第{priority}希望")


def analyze_grouped_request(
    message: str,
    today: date,
    default_duration_minutes: int = 120,
) -> ParseOutcome:
    """複合条件を独立したグループとして解析し、優先順位を保持する。"""

    normalized = normalize_message(message)
    single = analyze_request(normalized, today, default_duration_minutes)

    if "ただし" in normalized:
        return replace(
            single,
            status="needs_clarification",
            clarification_question="「ただし」以降の条件は、どの候補に適用しますか？",
        )

    if any(token in normalized for token in ("両方", "それぞれ", "1回ずつ", "一回ずつ", "連続で")):
        return replace(
            single,
            status="needs_clarification",
            clarification_question=(
                "複数の候補から一つを選びますか？それとも複数回または連続した予定ですか？"
            ),
        )

    shared_suffix = ""
    suffix_match = re.search(
        r"[、,]\s*((?:(?:平日|土日|週末)(?:の)?\s*)?"
        r"(?:早朝|朝|午前|昼|午後|夕方|夜|深夜)"
        r"(?:\s*(?:\d+(?:\.\d+)?時間|\d+分))?)$",
        normalized,
    )
    split_source = normalized
    if suffix_match and re.search(r"(?:か|または|又は|もしくは|あるいは)", normalized[:suffix_match.start()]):
        shared_suffix = suffix_match.group(1)
        split_source = normalized[:suffix_match.start()]

    clauses = _split_explicit_priorities(split_source)
    relation = "preference" if clauses else "alternative"
    if clauses is None:
        clauses = _split_fallback_priorities(split_source)
        if clauses:
            relation = "preference"
    if clauses is None:
        relation = "alternative"
        clauses = _split_alternatives(split_source)
    if not clauses or len(clauses) < 2:
        return single

    shared_period_match = re.search(
        r"(?:再々来週|再来週|来週|今週|再々来月|再来月|来月|今月)",
        clauses[0][0],
    )
    shared_period = shared_period_match.group(0) if shared_period_match else None

    parsed: list[tuple[str, int, ParseOutcome]] = []
    for index, (clause, priority) in enumerate(clauses):
        parse_text = f"{clause}{shared_suffix}"
        if index > 0 and shared_period and _condition_kind(clause) == "weekday":
            parse_text = f"{shared_period}{clause}"
        outcome = analyze_request(parse_text, today, default_duration_minutes)
        if outcome.status != "resolved":
            return replace(
                single,
                status=outcome.status,
                clarification_question=outcome.clarification_question,
                suggested_reply=outcome.suggested_reply,
            )
        parsed.append((clause, priority, outcome))

    kinds = [_condition_kind(clause) for clause, _, _ in parsed]
    same_kind = len(set(kinds)) == 1
    has_comma = bool(re.search(r"[、,]", normalized))
    shared_marker = any(token in normalized for token in ("どちらも", "両日とも", "ともに"))

    time_flags = [_has_time(outcome.constraints) for _, _, outcome in parsed]
    duration_flags = [outcome.constraints.duration_explicit for _, _, outcome in parsed]

    if not shared_marker:
        if len(set(time_flags)) > 1:
            if same_kind and time_flags[-1] and not has_comma:
                source = parsed[-1][2].constraints
                parsed = [
                    (clause, priority, replace(outcome, constraints=_copy_time(source, outcome.constraints)))
                    if not _has_time(outcome.constraints)
                    else (clause, priority, outcome)
                    for clause, priority, outcome in parsed
                ]
            elif (
                same_kind
                and time_flags[0]
                and not has_comma
                and re.search(
                    r"(?:今週|来週|再来週|再々来週).*(?:朝|午前|昼|午後|夕方|夜|深夜)の[月火水木金土日]",
                    normalized,
                )
            ):
                source = parsed[0][2].constraints
                parsed = [
                    (clause, priority, replace(outcome, constraints=_copy_time(source, outcome.constraints)))
                    if not _has_time(outcome.constraints)
                    else (clause, priority, outcome)
                    for clause, priority, outcome in parsed
                ]
            else:
                return replace(
                    single,
                    status="needs_clarification",
                    clarification_question="時間指定は、どの候補に適用しますか？",
                )
        if len(set(duration_flags)) > 1:
            if same_kind and duration_flags[-1] and not has_comma:
                source = parsed[-1][2].constraints
                parsed = [
                    (clause, priority, replace(outcome, constraints=_copy_duration(source, outcome.constraints)))
                    if not outcome.constraints.duration_explicit
                    else (clause, priority, outcome)
                    for clause, priority, outcome in parsed
                ]
            else:
                return replace(
                    single,
                    status="needs_clarification",
                    clarification_question="所要時間は、どの候補に適用しますか？",
                )
    else:
        whole = single.constraints
        inherited: list[tuple[str, int, ParseOutcome]] = []
        for clause, priority, outcome in parsed:
            constraints = outcome.constraints
            if not _has_time(constraints) and _has_time(whole):
                constraints = _copy_time(whole, constraints)
            if not constraints.duration_explicit and whole.duration_explicit:
                constraints = _copy_duration(whole, constraints)
            inherited.append((clause, priority, replace(outcome, constraints=constraints)))
        parsed = inherited

    groups = tuple(
        ConstraintGroup(
            constraints=outcome.constraints,
            priority=priority,
            label=_priority_label(priority) if relation == "preference" else None,
            source_text=clause,
        )
        for clause, priority, outcome in parsed
    )
    return ParseOutcome(
        constraints=groups[0].constraints,
        status="resolved",
        groups=groups,
        relation=relation,
        recognized_fields=frozenset().union(*(outcome.recognized_fields for _, _, outcome in parsed)),
    )
