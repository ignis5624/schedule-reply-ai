"""旧コードとの互換窓口。新規実装はintegrations.openai_parserを使用。"""

from integrations.openai_parser import parse_request_with_ai

__all__ = ["parse_request_with_ai"]
