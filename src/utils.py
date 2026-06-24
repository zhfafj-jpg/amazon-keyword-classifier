from __future__ import annotations

import re
from typing import Iterable, Optional


KEYWORD_ALIASES = [
    "搜索词",
    "搜索查询",
    "搜索词组",
    "Search Term",
    "Search Query",
    "Keyword",
]

ABA_COLUMN_ALIASES = {
    "keyword": KEYWORD_ALIASES,
    "search_frequency_rank": ["搜索频率排名", "Search Frequency Rank", "SFR"],
    "click_share": ["点击占比", "点击份额", "Click Share"],
    "conversion_share": ["转化份额", "转化占比", "Conversion Share"],
    "product_title": ["商品标题", "Product Title"],
    "brand": ["品牌", "Brand"],
    "asin": ["ASIN"],
}

ABA_HEADER_HINTS = [
    alias
    for aliases in ABA_COLUMN_ALIASES.values()
    for alias in aliases
]


def normalize_text(value: object) -> str:
    text = str(value or "").lower().replace("\ufeff", "")
    text = text.replace("&", " and ")
    text = re.sub(r"[’']", "'", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_column_name(value: object) -> str:
    text = str(value or "").lower().strip().replace("\ufeff", "")
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)


def split_terms(value: object) -> list[str]:
    if isinstance(value, list):
        raw_terms = value
    else:
        raw_terms = re.split(r"[,;，；\n\r]+", str(value or ""))

    terms: list[str] = []
    for item in raw_terms:
        term = normalize_text(item)
        if term and term not in terms:
            terms.append(term)
    return terms


def compact_join(items: Iterable[str], separator: str = "、") -> str:
    values: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in values:
            values.append(text)
    return separator.join(values)


def contains_term(text: str, term: str) -> bool:
    normalized_text = normalize_text(text)
    normalized_term = normalize_text(term)
    if not normalized_term:
        return False
    if " " in normalized_term:
        return normalized_term in normalized_text
    return re.search(rf"(^|\s){re.escape(normalized_term)}(\s|$)", normalized_text) is not None


def match_terms(text: str, terms: Iterable[str]) -> list[str]:
    return [term for term in split_terms(list(terms)) if contains_term(text, term)]


def find_best_column(columns: Iterable[str], aliases: Iterable[str]) -> Optional[str]:
    normalized_columns = {normalize_column_name(column): column for column in columns}
    normalized_aliases = [normalize_column_name(alias) for alias in aliases]

    for alias in normalized_aliases:
        if alias in normalized_columns:
            return normalized_columns[alias]

    for alias in normalized_aliases:
        for normalized_column, original_column in normalized_columns.items():
            if alias and (alias in normalized_column or normalized_column in alias):
                return original_column
    return None


def parse_number(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "-", "--"}:
        return None
    cleaned = re.sub(r"[$,\s]", "", text).replace("%", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_percent(value: object) -> Optional[float]:
    number = parse_number(value)
    if number is None:
        return None
    if "%" in str(value) or number > 1:
        return number / 100
    return number


def clamp(value: int | float, low: int = 0, high: int = 100) -> int:
    return int(max(low, min(high, round(value))))


def yes_no(value: bool) -> str:
    return "是" if value else "否"
