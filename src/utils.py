from __future__ import annotations

import re
from typing import Iterable, Optional


KEYWORD_ALIASES = [
    "search term",
    "search terms",
    "customer search term",
    "search query",
    "query",
    "keyword",
    "keywords",
    "term",
    "搜索词",
    "关键词",
    "客户搜索词",
]

COLUMN_ALIASES = {
    "aba_rank": ["search frequency rank", "搜索频率排名", "sfr", "rank", "aba rank"],
    "click_share": ["click share", "点击占比", "点击份额"],
    "conversion_share": ["conversion share", "转化份额", "转化占比"],
    "clicks": ["clicks", "click", "点击量", "点击次数"],
    "spend": ["spend", "cost", "花费", "广告花费"],
    "orders": ["orders", "order", "purchases", "订单", "订单量"],
    "sales": ["sales", "销售额", "销售"],
    "acos": ["acos", "a cos", "广告成本销售比"],
    "ctr": ["ctr", "点击率"],
    "cpc": ["cpc", "平均点击花费", "单次点击成本"],
}

ALL_COLOR_WORDS = {
    "black",
    "green",
    "brown",
    "purple",
    "beige",
    "blue",
    "pink",
    "white",
    "silver",
    "red",
    "grey",
    "gray",
    "gold",
    "yellow",
    "orange",
}


def normalize_text(value: object) -> str:
    text = str(value or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[’']", "'", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_column_name(value: object) -> str:
    text = str(value or "").lower().strip()
    text = text.replace("\ufeff", "")
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
    raw = str(value)
    if "%" in raw or number > 1:
        return number / 100
    return number


def format_percent(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:.2%}"


def yes_no(value: bool) -> str:
    return "是" if value else "否"


def compact_join(items: Iterable[str]) -> str:
    unique: list[str] = []
    for item in items:
        if item and item not in unique:
            unique.append(item)
    return "、".join(unique)


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
