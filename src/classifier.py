from __future__ import annotations

from typing import Any

import pandas as pd

from .scorer import choose_final_category, extract_metrics
from .utils import (
    ALL_COLOR_WORDS,
    compact_join,
    contains_term,
    format_percent,
    match_terms,
    split_terms,
    yes_no,
)


RESULT_COLUMNS = [
    "原关键词",
    "产品线",
    "分类结果",
    "标签",
    "匹配到的规则",
    "是否颜色匹配",
    "是否尺寸匹配",
    "是否品牌词",
    "是否配件词",
    "ABA排名",
    "点击占比",
    "转化份额",
    "点击量",
    "花费",
    "订单",
    "ACOS",
    "建议动作",
    "备注",
]


def _global_terms(rules: dict[str, Any], key: str) -> list[str]:
    return split_terms(rules.get("global_terms", {}).get(key, []))


def classify_keyword(keyword: str, product_line: str, rules: dict[str, Any]) -> dict[str, Any]:
    product_rules = rules["product_lines"][product_line]
    colors = split_terms(product_rules.get("colors", []))
    sizes = split_terms(product_rules.get("sizes", []))
    core_terms = split_terms(product_rules.get("core_terms", []))
    unsuitable_terms = split_terms(product_rules.get("unsuitable_terms", []))
    brand_terms = _global_terms(rules, "brand_terms")
    accessory_terms = _global_terms(rules, "accessory_terms")
    functional_terms = _global_terms(rules, "functional_terms")
    scene_terms = _global_terms(rules, "scene_terms")
    low_price_terms = _global_terms(rules, "low_price_terms")

    matched_brand = match_terms(keyword, brand_terms)
    matched_accessory = match_terms(keyword, accessory_terms)
    matched_core = match_terms(keyword, core_terms)
    matched_color = match_terms(keyword, colors)
    matched_size = match_terms(keyword, sizes)
    matched_unsuitable = match_terms(keyword, unsuitable_terms)
    matched_function = match_terms(keyword, functional_terms)
    matched_scene = match_terms(keyword, scene_terms)
    matched_low_price = match_terms(keyword, low_price_terms)

    all_allowed_colors = set(colors)
    color_conflicts = [
        color for color in ALL_COLOR_WORDS
        if color not in all_allowed_colors and contains_term(keyword, color)
    ]

    tags: list[str] = []
    matched_rules: list[str] = []
    notes: list[str] = []

    if matched_core:
        tags.append("核心主推词")
        matched_rules.append(f"核心词: {', '.join(matched_core)}")
    if matched_color:
        tags.append("颜色词")
        matched_rules.append(f"颜色: {', '.join(matched_color)}")
    if matched_size:
        tags.append("尺寸词")
        matched_rules.append(f"尺寸: {', '.join(matched_size)}")
    if matched_function:
        tags.append("功能词")
        matched_rules.append(f"功能: {', '.join(matched_function)}")
    if matched_scene:
        tags.append("场景词")
        matched_rules.append(f"场景: {', '.join(matched_scene)}")
    if matched_low_price:
        tags.append("低价测试词")
        matched_rules.append(f"价格词: {', '.join(matched_low_price)}")
    if matched_brand:
        tags.extend(["品牌词", "竞品词"])
        matched_rules.append(f"品牌词: {', '.join(matched_brand)}")
        notes.append("命中内置品牌词库，不进入普通主推词。")
    if matched_accessory:
        tags.append("配件词")
        matched_rules.append(f"配件/不相关: {', '.join(matched_accessory)}")
    if matched_unsuitable:
        tags.append("不相关词")
        matched_rules.append(f"产品线不适合: {', '.join(matched_unsuitable)}")
    if color_conflicts:
        tags.append("不相关词")
        matched_rules.append(f"产品线未配置颜色: {', '.join(color_conflicts)}")

    is_brand = bool(matched_brand)
    is_accessory = bool(matched_accessory)
    is_unsuitable = bool(matched_unsuitable or color_conflicts)
    has_function_or_attribute = bool(matched_color or matched_size or matched_function or matched_scene)
    has_basic_relevance = bool(matched_core or matched_color or matched_size or matched_function or matched_scene)
    is_product_related = has_basic_relevance and not is_accessory and not is_unsuitable and not is_brand

    if is_brand:
        base_category = "品牌词/竞品词"
    elif is_accessory:
        base_category = "词组否定建议"
        tags.append("词组否定建议")
    elif is_unsuitable:
        base_category = "精准否定建议"
        tags.append("精准否定建议")
    elif matched_core:
        base_category = "核心主推词"
    elif matched_low_price and has_basic_relevance:
        base_category = "低价测试词"
    elif has_function_or_attribute:
        base_category = "Listing埋词"
    else:
        base_category = "待人工确认"
        tags.append("待人工确认")

    return {
        "base_category": base_category,
        "tags": tags,
        "matched_rules": matched_rules,
        "notes": notes,
        "is_color_match": bool(matched_color),
        "is_size_match": bool(matched_size),
        "is_brand": is_brand,
        "is_accessory": is_accessory,
        "is_unsuitable": is_unsuitable,
        "is_product_related": is_product_related,
        "has_function_or_attribute": has_function_or_attribute,
    }


def analyze_keywords(
    df: pd.DataFrame,
    keyword_column: str,
    product_line: str,
    rules: dict[str, Any],
    analysis_mode: str,
    detected_columns: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    output_rows: list[dict[str, Any]] = []
    hit_rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        keyword = str(row.get(keyword_column, "")).strip()
        if not keyword or keyword.lower() == "nan":
            continue

        basic = classify_keyword(keyword, product_line, rules)
        metrics = extract_metrics(row, detected_columns)
        final_category, action, scoring_notes = choose_final_category(basic, metrics, analysis_mode)

        tags = list(basic["tags"])
        if final_category not in tags and final_category != "品牌词/竞品词":
            tags.insert(0, final_category)
        if final_category == "品牌词/竞品词":
            tags.extend(["品牌词", "竞品词"])
        if final_category in {"品牌词/竞品词", "词组否定建议", "精准否定建议", "不相关词"}:
            tags = [tag for tag in tags if tag not in {"核心主推词", "低价测试词", "Listing埋词"}]

        row_notes = [*basic["notes"], *scoring_notes]
        result = {
            "原关键词": keyword,
            "产品线": product_line,
            "分类结果": final_category,
            "标签": compact_join(tags),
            "匹配到的规则": compact_join(basic["matched_rules"]),
            "是否颜色匹配": yes_no(basic["is_color_match"]),
            "是否尺寸匹配": yes_no(basic["is_size_match"]),
            "是否品牌词": yes_no(basic["is_brand"]),
            "是否配件词": yes_no(basic["is_accessory"]),
            "ABA排名": "" if metrics["aba_rank"] is None else int(metrics["aba_rank"]),
            "点击占比": format_percent(metrics["click_share"]),
            "转化份额": format_percent(metrics["conversion_share"]),
            "点击量": "" if metrics["clicks"] is None else int(metrics["clicks"]),
            "花费": "" if metrics["spend"] is None else metrics["spend"],
            "订单": "" if metrics["orders"] is None else int(metrics["orders"]),
            "ACOS": format_percent(metrics["acos"]),
            "建议动作": action,
            "备注": compact_join(row_notes),
        }

        for original_column in df.columns:
            if original_column not in result:
                result[f"原表_{original_column}"] = row.get(original_column, "")

        output_rows.append(result)
        hit_rows.append(
            {
                "原关键词": keyword,
                "产品线": product_line,
                "基础分类": basic["base_category"],
                "最终分类": final_category,
                "是否产品相关": yes_no(basic["is_product_related"]),
                "命中标签": compact_join(tags),
                "规则命中说明": compact_join(basic["matched_rules"]) or "未命中明确规则",
                "评分/动作说明": compact_join(row_notes),
            }
        )

    result_df = pd.DataFrame(output_rows)
    hit_df = pd.DataFrame(hit_rows)
    if not result_df.empty:
        leading = [column for column in RESULT_COLUMNS if column in result_df.columns]
        trailing = [column for column in result_df.columns if column not in leading]
        result_df = result_df[leading + trailing]
    return result_df, hit_df
