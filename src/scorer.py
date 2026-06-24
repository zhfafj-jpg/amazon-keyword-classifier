from __future__ import annotations

from typing import Any

from .utils import parse_number, parse_percent


def get_value(row: Any, column: str | None):
    if not column:
        return None
    try:
        value = row[column]
    except Exception:
        return None
    return None if str(value).lower() == "nan" else value


def extract_metrics(row: Any, detected_columns: dict[str, str]) -> dict[str, Any]:
    aba_rank = parse_number(get_value(row, detected_columns.get("aba_rank")))
    click_share = parse_percent(get_value(row, detected_columns.get("click_share")))
    conversion_share = parse_percent(get_value(row, detected_columns.get("conversion_share")))
    clicks = parse_number(get_value(row, detected_columns.get("clicks")))
    spend = parse_number(get_value(row, detected_columns.get("spend")))
    orders = parse_number(get_value(row, detected_columns.get("orders")))
    sales = parse_number(get_value(row, detected_columns.get("sales")))
    acos = parse_percent(get_value(row, detected_columns.get("acos")))
    ctr = parse_percent(get_value(row, detected_columns.get("ctr")))
    cpc = parse_number(get_value(row, detected_columns.get("cpc")))
    return {
        "aba_rank": aba_rank,
        "click_share": click_share,
        "conversion_share": conversion_share,
        "clicks": clicks,
        "spend": spend,
        "orders": orders,
        "sales": sales,
        "acos": acos,
        "ctr": ctr,
        "cpc": cpc,
    }


def has_aba_data(metrics: dict[str, Any]) -> bool:
    return any(metrics.get(key) is not None for key in ["aba_rank", "click_share", "conversion_share"])


def has_ad_data(metrics: dict[str, Any]) -> bool:
    return any(metrics.get(key) is not None for key in ["clicks", "spend", "orders", "sales", "acos", "ctr", "cpc"])


def aba_category(metrics: dict[str, Any], basic: dict[str, Any]) -> tuple[str | None, str | None]:
    if not has_aba_data(metrics):
        return None, None
    if basic["is_brand"]:
        return "品牌词/竞品词", "ABA：命中品牌词库，需单独按竞品词策略处理。"
    if not basic["is_product_related"]:
        if basic["is_accessory"]:
            return "词组否定建议", "ABA：配件/不相关词，建议词组否定。"
        return "精准否定建议", "ABA：产品线不相关，建议精准否定。"

    rank = metrics.get("aba_rank")
    click_share = metrics.get("click_share")
    conversion_share = metrics.get("conversion_share")

    rank_good = rank is not None and rank <= 20000
    conversion_ok = conversion_share is not None and click_share is not None and conversion_share >= click_share
    click_high_conversion_low = (
        click_share is not None
        and click_share >= 0.08
        and conversion_share is not None
        and conversion_share < click_share
    )

    if rank_good and conversion_ok:
        return "核心主推词", "ABA：排名靠前且转化份额不低于点击占比。"
    if click_high_conversion_low:
        return "低价测试词", "ABA：点击占比较高但转化份额偏低。"
    if basic["has_function_or_attribute"]:
        return "Listing埋词", "ABA：相关的功能/属性词，适合埋词。"
    return "待人工确认", "ABA：数据不足或表现不够明确。"


def ad_action(metrics: dict[str, Any], basic: dict[str, Any]) -> tuple[str, str | None, str | None]:
    if not has_ad_data(metrics):
        return "", None, None

    if basic["is_brand"]:
        return "建议单独竞品词策略/谨慎投放", "品牌词/竞品词", "广告：命中品牌词库，不进入普通主推词。"

    clicks = metrics.get("clicks") or 0
    orders = metrics.get("orders") or 0
    acos = metrics.get("acos")

    if basic["is_accessory"] or basic["is_unsuitable"]:
        category = "词组否定建议" if basic["is_accessory"] else "精准否定建议"
        return "建议词组否定或精准否定", category, "广告：明显配件/不相关词。"

    if orders >= 1 and acos is not None and acos <= 0.25:
        return "建议拉精准/保留/小幅加价", "核心主推词", "广告：有订单且 ACOS <= 25%。"
    if clicks >= 20 and orders == 0 and basic["is_product_related"]:
        return "建议小幅降价/继续观察", "低价测试词", "广告：点击量较高未出单但产品相关。"
    if clicks >= 15 and orders == 0 and not basic["is_product_related"]:
        return "建议精准否定", "精准否定建议", "广告：点击量较高未出单且产品不相关。"
    return "待人工确认", "待人工确认", "广告：数据不足或动作不明确。"


def choose_final_category(
    basic: dict[str, Any],
    metrics: dict[str, Any],
    analysis_mode: str,
) -> tuple[str, str, list[str]]:
    notes: list[str] = []
    action = ""
    final_category = basic["base_category"]

    if basic["is_brand"]:
        notes.append("命中品牌词库，保留为品牌词/竞品词。")
        return "品牌词/竞品词", "建议单独竞品词策略/谨慎投放", notes

    if analysis_mode in {"ABA选词", "综合分析"}:
        category, note = aba_category(metrics, basic)
        if category:
            final_category = category
        if note:
            notes.append(note)

    if analysis_mode in {"广告搜索词", "综合分析"}:
        ad_suggestion, category, note = ad_action(metrics, basic)
        if ad_suggestion:
            action = ad_suggestion
        if category:
            final_category = category
        if note:
            notes.append(note)

    if not action:
        if final_category in {"词组否定建议", "精准否定建议", "不相关词"}:
            action = "建议否定/排除"
        elif final_category == "核心主推词":
            action = "建议加入核心投放/重点埋词"
        elif final_category == "低价测试词":
            action = "建议低竞价测试"
        elif final_category == "Listing埋词":
            action = "建议用于标题/五点/后台搜索词评估"
        else:
            action = "待人工确认"

    return final_category, action, notes
