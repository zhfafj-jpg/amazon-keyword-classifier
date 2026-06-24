from __future__ import annotations

from typing import Any

from .utils import parse_number, parse_percent


def get_row_value(row: Any, column: str | None):
    if not column:
        return None
    try:
        value = row[column]
    except Exception:
        return None
    if str(value).strip().lower() in {"", "nan", "none"}:
        return None
    return value


def extract_aba_metrics(row: Any, detected_columns: dict[str, str]) -> dict[str, float | None]:
    return {
        "search_frequency_rank": parse_number(get_row_value(row, detected_columns.get("search_frequency_rank"))),
        "click_share": parse_percent(get_row_value(row, detected_columns.get("click_share"))),
        "conversion_share": parse_percent(get_row_value(row, detected_columns.get("conversion_share"))),
    }


def demand_score(rank: float | None) -> str:
    if rank is None:
        return "数据不足"
    if rank <= 10000:
        return "高"
    if rank <= 50000:
        return "中高"
    if rank <= 150000:
        return "中"
    if rank <= 300000:
        return "偏低"
    return "低"


def click_conversion_efficiency(click_share: float | None, conversion_share: float | None) -> str:
    if click_share is None or conversion_share is None:
        return "数据不足"
    advantage = conversion_share - click_share
    if advantage > 0.005:
        return "成交效率强"
    if abs(advantage) <= 0.005:
        return "正常"
    if click_share >= 0.08 and conversion_share < click_share:
        return "点击强但成交弱"
    if click_share < 0.03 and conversion_share < 0.03:
        return "弱"
    return "成交偏弱"


def has_good_rank(rank: float | None) -> bool:
    return rank is not None and rank <= 50000


def has_search_volume(rank: float | None) -> bool:
    return rank is not None and rank <= 150000


def conversion_not_bad(click_share: float | None, conversion_share: float | None) -> bool:
    if click_share is None or conversion_share is None:
        return False
    return conversion_share >= click_share - 0.01


def conversion_strong(click_share: float | None, conversion_share: float | None) -> bool:
    if click_share is None or conversion_share is None:
        return False
    return conversion_share >= click_share


def classify_priority(
    relevance_score: int,
    metrics: dict[str, float | None],
    flags: dict[str, bool],
    click_efficiency: str,
) -> tuple[str, str, str]:
    rank = metrics.get("search_frequency_rank")
    click_share = metrics.get("click_share")
    conversion_share = metrics.get("conversion_share")

    if flags["is_brand"]:
        return "品牌/竞品词", "品牌/竞品", "单独品牌词测试或竞品分析，不进入普通主推词"

    if flags["is_accessory"] or flags["is_irrelevant"] or flags["is_different_category"] or relevance_score < 40:
        return "D级不相关/否词", "D", "不投放 / 否词候选"

    if (
        relevance_score >= 80
        and has_good_rank(rank)
        and conversion_strong(click_share, conversion_share)
        and not flags["is_accessory"]
        and not flags["is_irrelevant"]
    ):
        return "S级核心主推词", "S", "Exact / Phrase 主推，标题和图片重点承接"

    if relevance_score >= 70 and has_search_volume(rank) and conversion_not_bad(click_share, conversion_share):
        return "A级重点词", "A", "Phrase / Exact 测试，适合重点广告组"

    if 50 <= relevance_score < 70 and (click_efficiency == "点击强但成交弱" or has_search_volume(rank)):
        return "B级低价测试词", "B", "Broad / Phrase 低价测试"

    if relevance_score >= 40 and flags["has_attribute_intent"]:
        return "C级Listing埋词", "C", "放入标题、五点、A+、Search Terms"

    return "待人工确认", "待确认", "待人工确认"
