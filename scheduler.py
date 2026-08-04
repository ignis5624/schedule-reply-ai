"""旧コードとの互換窓口。

新規実装では domain / parsers / services を直接importしてください。
"""

from domain.models import Availability, Candidate, RequestConstraints
from parsers.request_parser import parse_request
from services.candidate_service import find_candidates
from services.reply_service import build_reply, format_candidate

__all__ = [
    "Availability",
    "Candidate",
    "RequestConstraints",
    "parse_request",
    "find_candidates",
    "format_candidate",
    "build_reply",
]
