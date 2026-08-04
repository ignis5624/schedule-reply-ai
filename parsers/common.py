from __future__ import annotations

import re
import unicodedata

from .constants import KANJI_DIGITS, KANJI_UNITS


def parse_number(text: str) -> float:
    """算用数字・一般的な漢数字を数値へ変換する。"""

    text = unicodedata.normalize("NFKC", text.strip())
    try:
        return float(text)
    except ValueError:
        pass

    if text and all(char in KANJI_DIGITS for char in text):
        return float("".join(str(KANJI_DIGITS[char]) for char in text))

    total = 0
    current = 0
    for char in text:
        if char in KANJI_DIGITS:
            current = KANJI_DIGITS[char]
        elif char in KANJI_UNITS:
            unit = KANJI_UNITS[char]
            total += (current or 1) * unit
            current = 0
        else:
            raise ValueError(f"数値として解釈できません: {text}")
    return float(total + current)


def normalize_message(message: str) -> str:
    """表記ゆれと漢数字を、各解析器が扱いやすい形へ寄せる。"""

    normalized = unicodedata.normalize("NFKC", message.strip())
    replacements = {
        "あした": "明日",
        "あす": "明日",
        "あさって": "明後日",
        "しあさって": "明々後日",
        "明明後日": "明々後日",
        "こんしゅう": "今週",
        "らいしゅう": "来週",
        "さらいしゅう": "再来週",
        "こんげつ": "今月",
        "らいげつ": "来月",
        "さらいげつ": "再来月",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)

    kanji_number = r"[零〇一二三四五六七八九十百千]+"
    normalized = re.sub(
        fr"({kanji_number})(?=(?:年|月|日|週間|週|時間|分|時))",
        lambda match: str(int(parse_number(match.group(1)))),
        normalized,
    )
    return normalized
