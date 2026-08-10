"""旧コードとの互換窓口。新規実装はintegrations.openai_parserを使用。"""

from integrations.openai_parser import analyze_request_with_ai, parse_request_with_ai

__all__ = ["parse_request_with_ai", "analyze_request_with_ai"]
