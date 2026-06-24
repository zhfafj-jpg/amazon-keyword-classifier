from __future__ import annotations

import re
from typing import Any

import pandas as pd

from .scorer import classify_priority, click_conversion_efficiency, demand_score, extract_aba_metrics
from .translator import translate_keyword
from .utils import clamp, compact_join, match_terms, split_terms, yes_no


OUTPUT_COLUMNS = [
    "原搜索词",
    "中文翻译",
    "搜索频率排名",
    "点击占比",
    "转化份额",
    "转化优势",
    "需求评分",
    "点击转化效率",
    "相关性评分",
    "分类结果",
    "推广优先级",
    "建议动作",
    "命中的规则",
    "是否品牌词",
    "是否配件词",
    "是否否词候选",
    "备注",
]


def _rules_list(rules: dict[str, Any], key: str) -> list[str]:
    return split_terms(rules.get(key, []))


def _extract_sizes(text: str, configured_sizes: list[str]) -> list[str]:
    found = set(match_terms(text, configured_sizes))
    for match in re.findall(r"\b\d{2}\s?inch\b|\b\d{2}x\d{2}x\d{1,2}\b", text.lower()):
        found.add(match.replace(" ", " "))
    return list(found)


def compact_terms(terms: list[str]) -> list[str]:
    output: list[str] = []
    for term in split_terms(terms):
        if term not in output:
            output.append(term)
    return output


def build_product_profile(
    product_info: str,
    core_terms: str,
    color_terms: str,
    size_terms: str,
    irrelevant_terms: str,
    brand_terms: str,
    rules: dict[str, Any],
) -> dict[str, list[str]]:
    product_text = product_info or ""
    configured_core = _rules_list(rules, "core_candidate_terms")
    configured_colors = _rules_list(rules, "color_terms")
    configured_sizes = _rules_list(rules, "size_terms")
    configured_functions = _rules_list(rules, "functional_terms")
    configured_scenes = _rules_list(rules, "scene_terms")
    configured_materials = _rules_list(rules, "material_terms")

    profile = {
        "core_terms": split_terms(core_terms) or match_terms(product_text, configured_core),
        "color_terms": split_terms(color_terms) or match_terms(product_text, configured_colors),
        "size_terms": split_terms(size_terms) or _extract_sizes(product_text, configured_sizes),
        "irrelevant_terms": split_terms(irrelevant_terms),
        "brand_terms": split_terms(brand_terms),
        "functional_terms": match_terms(product_text, configured_functions),
        "scene_terms": match_terms(product_text, configured_scenes),
        "material_terms": match_terms(product_text, configured_materials),
    }

    if not profile["core_terms"]:
        profile["core_terms"] = match_terms(product_text, ["luggage", "suitcase", "carry on", "checked luggage"])

    return profile


def _keyword_flags(keyword: str, profile: dict[str, list[str]], rules: dict[str, Any]) -> dict[str, Any]:
    brand_terms = compact_terms(_rules_list(rules, "brand_terms") + profile.get("brand_terms", []))
    accessory_terms = _rules_list(rules, "accessory_terms")
    different_category_terms = _rules_list(rules, "different_category_terms")
    functional_terms = compact_terms(_rules_list(rules, "functional_terms") + profile.get("functional_terms", []))
    scene_terms = compact_terms(_rules_list(rules, "scene_terms") + profile.get("scene_terms", []))
    material_terms = compact_terms(_rules_list(rules, "material_terms") + profile.get("material_terms", []))

    hits = {
        "core": match_terms(keyword, profile.get("core_terms", [])),
        "size": match_terms(keyword, profile.get("size_terms", [])),
        "color": match_terms(keyword, profile.get("color_terms", [])),
        "function": match_terms(keyword, functional_terms),
        "scene": match_terms(keyword, scene_terms),
        "material": match_terms(keyword, material_terms),
        "irrelevant": match_terms(keyword, profile.get("irrelevant_terms", [])),
        "brand": match_terms(keyword, brand_terms),
        "accessory": match_terms(keyword, accessory_terms),
        "different_category": match_terms(keyword, different_category_terms),
    }

    return {
        "hits": hits,
        "is_brand": bool(hits["brand"]),
        "is_accessory": bool(hits["accessory"]),
        "is_irrelevant": bool(hits["irrelevant"]),
        "is_different_category": bool(hits["different_category"]),
        "has_attribute_intent": bool(
            hits["size"] or hits["color"] or hits["function"] or hits["scene"] or hits["material"]
        ),
    }


def calculate_relevance(flags: dict[str, Any]) -> int:
    hits = flags["hits"]
    score = 0
    if hits["core"]:
        score += 40
    if hits["size"]:
        score += 15
    if hits["color"]:
        score += 10
    if hits["function"]:
        score += 20
    if hits["scene"]:
        score += 10
    if hits["material"]:
        score += 10
    if hits["irrelevant"]:
        score -= 50
    if hits["accessory"]:
        score -= 40
    if hits["different_category"]:
        score -= 60
    return clamp(score)


def build_rule_hit_text(flags: dict[str, Any]) -> str:
    labels = {
        "core": "核心词",
        "size": "尺寸词",
        "color": "颜色词",
        "function": "功能词",
        "scene": "场景词",
        "material": "材质/属性词",
        "irrelevant": "用户不相关词",
        "brand": "品牌/竞品词",
        "accessory": "配件词",
        "different_category": "不同品类词",
    }
    parts: list[str] = []
    for key, label in labels.items():
        values = flags["hits"].get(key, [])
        if values:
            parts.append(f"{label}: {', '.join(values)}")
    return compact_join(parts)


def _is_negative_candidate(category: str, flags: dict[str, Any], relevance: int) -> bool:
    return (
        category == "D级不相关/否词"
        or flags["is_accessory"]
        or flags["is_irrelevant"]
        or flags["is_different_category"]
        or relevance < 40
    )


def analyze_aba_keywords(
    df: pd.DataFrame,
    keyword_column: str,
    detected_columns: dict[str, str],
    product_profile: dict[str, list[str]],
    rules: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    output_rows: list[dict[str, Any]] = []
    rule_rows: list[dict[str, Any]] = []
    translation_terms = rules.get("translation_terms", {})

    for _, row in df.iterrows():
        keyword = str(row.get(keyword_column, "")).strip()
        if not keyword or keyword.lower() == "nan":
            continue

        translation, translation_note = translate_keyword(keyword, translation_terms)
        flags = _keyword_flags(keyword, product_profile, rules)
        relevance = calculate_relevance(flags)
        metrics = extract_aba_metrics(row, detected_columns)
        click_eff = click_conversion_efficiency(metrics["click_share"], metrics["conversion_share"])
        demand = demand_score(metrics["search_frequency_rank"])
        category, priority, action = classify_priority(relevance, metrics, flags, click_eff)
        conversion_advantage = None
        if metrics["click_share"] is not None and metrics["conversion_share"] is not None:
            conversion_advantage = metrics["conversion_share"] - metrics["click_share"]

        negative_candidate = _is_negative_candidate(category, flags, relevance)
        rule_hit_text = build_rule_hit_text(flags)
        notes = []
        if translation_note:
            notes.append(translation_note)
        if category == "待人工确认":
            notes.append("数据不足或相关性处于中间状态")
        if flags["is_brand"]:
            notes.append("命中品牌词库，不进入普通主推词")
        if flags["is_accessory"]:
            notes.append("命中配件词库")
        if flags["is_irrelevant"] or flags["is_different_category"]:
            notes.append("命中不相关/不同品类规则")

        result = {
            "原搜索词": keyword,
            "中文翻译": translation,
            "搜索频率排名": metrics["search_frequency_rank"],
            "点击占比": metrics["click_share"],
            "转化份额": metrics["conversion_share"],
            "转化优势": conversion_advantage,
            "需求评分": demand,
            "点击转化效率": click_eff,
            "相关性评分": relevance,
            "分类结果": category,
            "推广优先级": priority,
            "建议动作": action,
            "命中的规则": rule_hit_text,
            "是否品牌词": yes_no(flags["is_brand"]),
            "是否配件词": yes_no(flags["is_accessory"]),
            "是否否词候选": yes_no(negative_candidate),
            "备注": compact_join(notes),
        }

        for original_column in df.columns:
            if original_column == keyword_column:
                continue
            output_name = f"原表_{original_column}"
            if output_name not in result:
                result[output_name] = row.get(original_column, "")

        output_rows.append(result)
        rule_rows.append(
            {
                "原搜索词": keyword,
                "分类结果": category,
                "推广优先级": priority,
                "相关性评分": relevance,
                "是否否词候选": yes_no(negative_candidate),
                "命中的规则": rule_hit_text or "未命中明确规则",
                "备注": result["备注"],
            }
        )

    result_df = pd.DataFrame(output_rows)
    rules_df = pd.DataFrame(rule_rows)
    if not result_df.empty:
        leading = [column for column in OUTPUT_COLUMNS if column in result_df.columns]
        trailing = [column for column in result_df.columns if column not in leading]
        result_df = result_df[leading + trailing]
    return result_df, rules_df
