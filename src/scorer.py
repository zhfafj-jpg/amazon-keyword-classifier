from __future__ import annotations

from typing import Any

from .utils import clamp, parse_number, parse_percent_points


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
    click_share = first_available_share(row, detected_columns, ["click_share", "click_share_2", "click_share_3"])
    conversion_share = first_available_share(
        row,
        detected_columns,
        ["conversion_share", "conversion_share_2", "conversion_share_3"],
    )
    return {
        "search_frequency_rank": parse_number(get_row_value(row, detected_columns.get("search_frequency_rank"))),
        "click_share": click_share,
        "conversion_share": conversion_share,
    }


def first_available_share(row: Any, detected_columns: dict[str, str], canonical_keys: list[str]) -> float | None:
    for key in canonical_keys:
        column = detected_columns.get(key)
        value = parse_percent_points(get_row_value(row, column))
        if value is not None:
            return value
    return None


def demand_score(rank: float | None) -> int | None:
    if rank is None:
        return None
    if rank <= 1000:
        return 100
    if rank <= 10000:
        return 90
    if rank <= 50000:
        return 75
    if rank <= 150000:
        return 60
    if rank <= 300000:
        return 40
    return 20


def demand_level(rank: float | None) -> str:
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


def conversion_advantage(click_share: float | None, conversion_share: float | None) -> float | None:
    if click_share is None or conversion_share is None:
        return None
    return round(conversion_share - click_share, 4)


def click_conversion_efficiency(click_share: float | None, conversion_share: float | None) -> str:
    if click_share is None or conversion_share is None:
        return "数据不足"
    advantage = conversion_advantage(click_share, conversion_share)
    if advantage is None:
        return "数据不足"
    if advantage > 0.5:
        return "成交效率强"
    if abs(advantage) <= 0.5:
        return "正常"
    if click_share >= 8 and conversion_share < click_share:
        return "点击强但成交弱"
    if click_share < 3 and conversion_share < 3:
        return "弱"
    return "成交偏弱"


def click_conversion_efficiency_score(click_share: float | None, conversion_share: float | None) -> int | None:
    if click_share is None or conversion_share is None:
        return None
    advantage = conversion_share - click_share
    if advantage >= 3:
        return 95
    if advantage > 0.5:
        return 82
    if abs(advantage) <= 0.5:
        return 65
    if click_share >= 8 and conversion_share < click_share:
        return 35
    if click_share < 3 and conversion_share < 3:
        return 45
    return 50


def risk_score(flags: dict[str, Any], relevance_score: int) -> int:
    score = 0
    if flags.get("is_brand"):
        score += 45
    if flags.get("is_accessory"):
        score += 80
    if flags.get("is_set_mismatch"):
        score += 85
    elif flags.get("is_set_term"):
        score += 25
    if flags.get("is_different_category"):
        score += 80
    if flags.get("is_irrelevant"):
        score += 75
    if flags.get("is_generic"):
        score += 15
    if relevance_score < 40:
        score += 30
    return clamp(score)


def composite_priority_score(
    relevance_score: int,
    demand_score_value: int | None,
    click_efficiency_score: int | None,
    risk_score_value: int,
) -> int:
    demand = demand_score_value if demand_score_value is not None else 45
    click = click_efficiency_score if click_efficiency_score is not None else 55
    raw = relevance_score * 0.55 + demand * 0.25 + click * 0.2 - risk_score_value * 0.45
    return clamp(raw)


def classify_priority(
    relevance_score: int,
    scores: dict[str, int | None],
    flags: dict[str, Any],
    keyword_intent: str,
    click_efficiency: str,
) -> tuple[str, str, str, str]:
    demand = scores.get("demand_score") or 0
    risk = scores.get("risk_score") or 0
    click_score = scores.get("click_efficiency_score")

    if flags.get("is_brand"):
        if relevance_score >= 50 and not (flags.get("is_accessory") or flags.get("is_different_category")):
            return "品牌/竞品词", "品牌/竞品", "单独品牌词测试或竞品分析，不进入普通主推词", "品牌词，产品相关，建议单独测试"
        return "品牌/竞品词", "品牌/竞品", "不投放 / 仅做竞品观察", "品牌词但与当前产品相关性不足"

    if flags.get("is_accessory"):
        return "D级不相关/否词", "D", "不投放 / 否词候选", "命中配件词，不适合作为当前产品投放词"

    if flags.get("is_set_mismatch"):
        return "D级不相关/否词", "D", "不投放 / 否词候选", "命中套装词，但当前产品不是套装"

    if flags.get("is_different_category"):
        return "D级不相关/否词", "D", "不投放 / 否词候选", "命中不同品类词"

    if flags.get("is_irrelevant") or relevance_score < 40:
        return "D级不相关/否词", "D", "不投放 / 否词候选", "产品相关性低或命中不相关词"

    if flags.get("is_generic"):
        if demand >= 60:
            return "B级低价测试词", "B", "Broad / Phrase 低价测试，不进主预算", "泛类目词，不建议新品主预算"
        return "待人工确认", "待确认", "待人工确认", "泛类目词且需求数据不强"

    click_ok_for_core = click_score is None or click_score >= 55
    if (
        relevance_score >= 85
        and demand >= 60
        and risk <= 25
        and keyword_intent in {"核心类目词", "精准长尾词"}
        and click_ok_for_core
    ):
        return "S级核心主推词", "S", "Exact / Phrase 主推，标题和主图重点承接", "产品高度匹配，需求较好，风险低"

    if relevance_score >= 75 and demand >= 50 and risk <= 35 and keyword_intent in {"核心类目词", "精准长尾词", "尺寸词", "颜色词"}:
        return "A级重点词", "A", "Phrase / Exact 测试，适合重点广告组", "产品匹配度高，适合重点测试"

    if relevance_score >= 45 and keyword_intent in {"功能词", "场景词", "尺寸词", "颜色词"} and risk <= 35:
        return "C级Listing埋词", "C", "标题、五点、A+、Search Terms 埋词", "产品相关，偏功能/属性/场景"

    if 50 <= relevance_score < 75 or demand >= 75 or click_efficiency == "点击强但成交弱":
        return "B级低价测试词", "B", "Broad / Phrase 低价测试，不进主预算", "有测试价值，但不适合主预算"

    return "待人工确认", "待确认", "待人工确认", "相关性和数据表现处于中间状态"
