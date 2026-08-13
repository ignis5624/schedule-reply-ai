"""旧コードとの互換窓口。

新規実装では domain / parsers / services を直接importしてください。
"""

from domain.models import (
    Availability,
    BusyInterval,
    Candidate,
    CandidateGroup,
    ConstraintGroup,
    ParseOutcome,
    RecurringBusyRule,
    RequestConstraints,
    WeeklyAvailabilityRule,
)
from parsers.compound_parser import analyze_grouped_request
from parsers.request_parser import analyze_request, parse_request
from services.availability_service import build_availabilities, subtract_busy_intervals
from services.candidate_service import find_candidate_groups, find_candidates
from services.reply_service import build_grouped_reply, build_reply, format_candidate

__all__ = [
    "Availability",
    "BusyInterval",
    "Candidate",
    "CandidateGroup",
    "ConstraintGroup",
    "RequestConstraints",
    "ParseOutcome",
    "RecurringBusyRule",
    "WeeklyAvailabilityRule",
    "parse_request",
    "analyze_request",
    "analyze_grouped_request",
    "find_candidates",
    "find_candidate_groups",
    "build_availabilities",
    "subtract_busy_intervals",
    "format_candidate",
    "build_reply",
    "build_grouped_reply",
]
