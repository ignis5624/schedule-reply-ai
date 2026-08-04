from datetime import time

WEEKDAYS_JA = {"月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日": 6}
WEEKDAY_LABELS = "月火水木金土日"

# ユーザー指定の固定ルール
WEEK_FIRST_HALF = frozenset({6, 0, 1, 2})  # 日・月・火・水
WEEK_SECOND_HALF = frozenset({2, 3, 4, 5})  # 水・木・金・土

NAMED_TIME_WINDOWS: tuple[tuple[tuple[str, ...], time, time], ...] = (
    (("早朝",), time(5, 0), time(8, 0)),
    (("朝", "朝方"), time(6, 0), time(10, 0)),
    (("午前", "午前中"), time(6, 0), time(12, 0)),
    (("昼", "お昼", "昼時", "ランチ", "昼休み"), time(11, 0), time(14, 0)),
    (("午後", "昼過ぎ"), time(12, 0), time(18, 0)),
    (("夕方", "夕刻"), time(16, 0), time(19, 0)),
    (("夜", "夜間", "晩", "夜の時間"), time(18, 0), time(23, 0)),
    (("深夜", "夜遅く", "遅い時間"), time(21, 0), time(23, 59)),
)

KANJI_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
KANJI_UNITS = {"十": 10, "百": 100, "千": 1000}
NUMBER_TOKEN = r"(?:\d+(?:\.\d+)?|[零〇一二三四五六七八九十百千]+)"
