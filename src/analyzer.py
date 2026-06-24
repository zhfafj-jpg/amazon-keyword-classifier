from __future__ import annotations

import re
from typing import Any

import pandas as pd

from .scorer import (
    classify_priority,
    click_conversion_efficiency,
    click_conversion_efficiency_score,
    composite_priority_score,
    conversion_advantage,
    demand_level,
    demand_score,
    extract_aba_metrics,
    risk_score,
)
from .translator import translate_keyword
from .utils import clamp, compact_join, contains_term, match_terms, split_terms, yes_no


PRODUCT_TYPE_OPTIONS = [
    "carry_on_luggage",
    "checked_luggage",
    "trunk_luggage",
    "front_pocket_luggage",
    "luggage_set",
    "accessory",
    "unknown",
]


OUTPUT_COLUMNS = [
    "原搜索词",
    "中文翻译",
    "词意图类型",
    "搜索频率排名",
    "Top1点击份额",
    "Top1转化份额",
    "转化优势",
    "需求评分",
    "需求等级",
    "点击转化效率",
    "点击转化效率评分",
    "产品相关性评分",
    "相关性评分",
    "风险评分",
    "综合优先级评分",
    "分类结果",
    "推广优先级",
    "建议动作",
    "命中的规则",
    "为什么这样分类",
    "是否品牌词",
    "是否配件词",
    "是否否词候选",
    "是否进入关键词库",
    "词库类型",
    "备注",
]


def compact_terms(terms: list[str] | object) -> list[str]:
    output: list[str] = []
    for term in split_terms(terms):
        if term not in output:
            output.append(term)
    return output


def _rules_list(rules: dict[str, Any], key: str) -> list[str]:
    return compact_terms(rules.get(key, []))


def _extract_sizes(text: str, configured_sizes: list[str]) -> list[str]:
    found = set(match_terms(text, configured_sizes))
    for match in re.findall(r"\b\d{2}\s?inch\b|\b\d{2}x\d{2}x\d{1,2}\b", text.lower()):
        found.add(match.replace(" ", ""))
    return sorted(found)


def _has_any(text: str, terms: list[str]) -> bool:
    return bool(match_terms(text, terms))


def infer_product_type(text: str, core_terms: list[str], rules: dict[str, Any]) -> str:
    source = " ".join([text, *core_terms])
    if _has_any(source, ["front pocket", "laptop compartment"]):
        return "front_pocket_luggage"
    if _has_any(source, ["trunk luggage", "trunk suitcase", "trunk style", "deep compartment", "3 7 split"]):
        return "trunk_luggage"
    if _has_any(source, ["checked luggage", "checked suitcase", "large checked", "medium checked", "26 inch", "28 inch", "30 inch"]):
        return "checked_luggage"
    if _has_any(source, ["carry on luggage", "carry on suitcase", "carry on", "22x14x9", "20 inch"]):
        return "carry_on_luggage"
    if _has_any(source, _rules_list(rules, "set_terms")):
        return "luggage_set"
    if _has_any(source, ["luggage cover", "luggage tag", "weight scale", "replacement wheel", "packing cubes"]):
        return "accessory"
    return "unknown"


def build_product_profile(
    product_info: str,
    core_terms: str,
    color_terms: str,
    size_terms: str,
    irrelevant_terms: str,
    brand_terms: str,
    rules: dict[str, Any],
) -> dict[str, Any]:
    product_text = product_info or ""
    configured_core = _rules_list(rules, "core_candidate_terms")
    configured_colors = _rules_list(rules, "color_terms")
    configured_sizes = _rules_list(rules, "size_terms")
    configured_features = _rules_list(rules, "functional_terms")
    configured_scenarios = _rules_list(rules, "scene_terms")

    detected_core = compact_terms(split_terms(core_terms) or match_terms(product_text, configured_core))
    product_type = infer_product_type(product_text, detected_core, rules)
    is_luggage_set = product_type == "luggage_set"
    is_accessory = product_type == "accessory"
    is_front_pocket = product_type == "front_pocket_luggage" or _has_any(product_text, ["front pocket", "laptop compartment"])
    is_trunk_style = product_type == "trunk_luggage" or _has_any(product_text, ["trunk", "deep compartment", "3 7 split"])
    is_carry_on = product_type in {"carry_on_luggage", "front_pocket_luggage"} or _has_any(product_text, ["carry on", "22x14x9", "20 inch"])
    is_checked = product_type == "checked_luggage" or _has_any(product_text, ["checked luggage", "26 inch", "28 inch", "30 inch"])

    if not detected_core:
        detected_core = match_terms(product_text, ["carry on luggage", "checked luggage", "trunk luggage", "luggage", "suitcase"])
    if is_carry_on and "carry on luggage" not in detected_core:
        detected_core.append("carry on luggage")
    if is_checked and "checked luggage" not in detected_core:
        detected_core.append("checked luggage")
    if is_front_pocket and "front pocket carry on luggage" not in detected_core:
        detected_core.append("front pocket carry on luggage")
    if is_trunk_style and "trunk luggage" not in detected_core:
        detected_core.append("trunk luggage")

    return {
        "product_type": product_type,
        "core_terms": compact_terms(detected_core),
        "size_terms": compact_terms(split_terms(size_terms) or _extract_sizes(product_text, configured_sizes)),
        "color_terms": compact_terms(split_terms(color_terms) or match_terms(product_text, configured_colors)),
        "feature_terms": compact_terms(match_terms(product_text, configured_features)),
        "scenario_terms": compact_terms(match_terms(product_text, configured_scenarios)),
        "exclude_terms": compact_terms(split_terms(irrelevant_terms)),
        "accessory_terms": _rules_list(rules, "accessory_terms"),
        "brand_terms": compact_terms(_rules_list(rules, "brand_terms") + split_terms(brand_terms)),
        "is_single_luggage": not is_luggage_set and not is_accessory,
        "is_luggage_set": is_luggage_set,
        "is_front_pocket": is_front_pocket,
        "is_trunk_style": is_trunk_style,
        "is_carry_on": is_carry_on,
        "is_checked": is_checked,
    }


def normalize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(profile)
    for key in [
        "core_terms",
        "size_terms",
        "color_terms",
        "feature_terms",
        "scenario_terms",
        "exclude_terms",
        "accessory_terms",
        "brand_terms",
    ]:
        normalized[key] = compact_terms(normalized.get(key, []))
    normalized["product_type"] = normalized.get("product_type") if normalized.get("product_type") in PRODUCT_TYPE_OPTIONS else "unknown"
    for key in ["is_single_luggage", "is_luggage_set", "is_front_pocket", "is_trunk_style", "is_carry_on", "is_checked"]:
        normalized[key] = bool(normalized.get(key))
    return normalized


def _keyword_hits(keyword: str, profile: dict[str, Any], rules: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "core": match_terms(keyword, profile.get("core_terms", [])),
        "size": match_terms(keyword, profile.get("size_terms", [])),
        "color": match_terms(keyword, profile.get("color_terms", [])),
        "feature": match_terms(keyword, compact_terms(_rules_list(rules, "functional_terms") + profile.get("feature_terms", []))),
        "scenario": match_terms(keyword, compact_terms(_rules_list(rules, "scene_terms") + profile.get("scenario_terms", []))),
        "exclude": match_terms(keyword, profile.get("exclude_terms", [])),
        "brand": match_terms(keyword, profile.get("brand_terms", [])),
        "accessory": match_terms(keyword, profile.get("accessory_terms", [])),
        "set": match_terms(keyword, _rules_list(rules, "set_terms")),
        "different_category": match_terms(keyword, _rules_list(rules, "different_category_terms")),
        "generic": match_terms(keyword, _rules_list(rules, "generic_terms")),
    }


def detect_keyword_intent(keyword: str, hits: dict[str, list[str]], profile: dict[str, Any]) -> str:
    word_count = len(keyword.split())
    normalized = " ".join(keyword.lower().replace("-", " ").split())
    if hits["brand"]:
        return "品牌/竞品词"
    if hits["accessory"]:
        return "配件词"
    if hits["set"]:
        return "套装词"
    if hits["different_category"]:
        return "不同品类词"
    if hits["exclude"]:
        return "明显不相关词"
    if normalized in {"luggage", "suitcase"}:
        return "泛类目词"
    if hits["core"] and word_count >= 3:
        return "精准长尾词"
    if hits["core"]:
        return "核心类目词"
    if hits["size"]:
        return "尺寸词"
    if hits["color"]:
        return "颜色词"
    if hits["feature"]:
        return "功能词"
    if hits["scenario"]:
        return "场景词"
    return "待人工确认"


def _is_carry_on_query(keyword: str) -> bool:
    return contains_term(keyword, "carry on") or contains_term(keyword, "22x14x9")


def _is_checked_query(keyword: str) -> bool:
    return contains_term(keyword, "checked luggage") or contains_term(keyword, "checked suitcase")


def calculate_product_relevance(keyword: str, hits: dict[str, list[str]], profile: dict[str, Any], intent: str) -> int:
    score = 0
    if hits["core"]:
        score += 45
    if hits["size"]:
        score += 15
    if hits["color"]:
        score += 10
    if hits["feature"]:
        score += 20
    if hits["scenario"]:
        score += 10

    if profile.get("is_front_pocket") and (contains_term(keyword, "front pocket") or contains_term(keyword, "laptop compartment")):
        score += 25
    if profile.get("is_trunk_style") and contains_term(keyword, "trunk"):
        score += 30
    if profile.get("is_carry_on") and _is_carry_on_query(keyword):
        score += 30
    if profile.get("is_checked") and _is_checked_query(keyword):
        score += 30

    if profile.get("is_carry_on") and _is_checked_query(keyword):
        score -= 45
    if profile.get("is_checked") and _is_carry_on_query(keyword):
        score -= 35
    if contains_term(keyword, "trunk") and not profile.get("is_trunk_style"):
        score -= 45
    if hits["set"] and not profile.get("is_luggage_set"):
        score -= 85
    if hits["accessory"] and profile.get("product_type") != "accessory":
        score -= 75
    if hits["different_category"]:
        score -= 75
    if hits["exclude"]:
        score -= 60

    if intent == "泛类目词":
        score = min(score + 25, 55)
    if hits["brand"]:
        score = min(max(score, 50), 75)

    return clamp(score)


def build_flags(keyword: str, hits: dict[str, list[str]], profile: dict[str, Any], intent: str) -> dict[str, Any]:
    return {
        "is_brand": bool(hits["brand"]),
        "is_accessory": bool(hits["accessory"] and profile.get("product_type") != "accessory"),
        "is_set_term": bool(hits["set"]),
        "is_set_mismatch": bool(hits["set"] and not profile.get("is_luggage_set")),
        "is_different_category": bool(hits["different_category"]),
        "is_irrelevant": bool(hits["exclude"]),
        "is_generic": intent == "泛类目词",
        "has_attribute_intent": intent in {"尺寸词", "颜色词", "功能词", "场景词"},
    }


def build_rule_hit_text(hits: dict[str, list[str]]) -> str:
    labels = {
        "core": "核心词",
        "size": "尺寸词",
        "color": "颜色词",
        "feature": "功能词",
        "scenario": "场景词",
        "exclude": "用户不相关词",
        "brand": "品牌/竞品词",
        "accessory": "配件词",
        "set": "套装词",
        "different_category": "不同品类词",
        "generic": "泛词",
    }
    parts: list[str] = []
    for key, label in labels.items():
        values = hits.get(key, [])
        if values:
            parts.append(f"{label}: {', '.join(values)}")
    return compact_join(parts)


def _negative_candidate(category: str, flags: dict[str, Any]) -> bool:
    return category == "D级不相关/否词" or flags["is_accessory"] or flags["is_set_mismatch"] or flags["is_different_category"] or flags["is_irrelevant"]


def _library_decision(category: str, risk: int) -> tuple[str, str]:
    if category in {"S级核心主推词", "A级重点词"}:
        return "是", "核心词库"
    if category == "C级Listing埋词":
        return "是", "Listing埋词库"
    if category == "B级低价测试词":
        return ("是", "测试词库") if risk < 50 else ("待确认", "测试词库")
    if category == "品牌/竞品词":
        return "是", "品牌竞品词库"
    if category == "D级不相关/否词":
        return "否", "否词候选库"
    return "待确认", "待确认库"


def _clean_missing(value: Any) -> Any:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return value


def analyze_aba_keywords(
    df: pd.DataFrame,
    keyword_column: str,
    detected_columns: dict[str, str],
    product_profile: dict[str, Any],
    rules: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    profile = normalize_profile(product_profile)
    output_rows: list[dict[str, Any]] = []
    rule_rows: list[dict[str, Any]] = []
    translation_terms = rules.get("translation_terms", {})

    for _, row in df.iterrows():
        keyword = str(row.get(keyword_column, "")).strip()
        if not keyword or keyword.lower() == "nan":
            continue

        translation, translation_note = translate_keyword(keyword, translation_terms)
        hits = _keyword_hits(keyword, profile, rules)
        intent = detect_keyword_intent(keyword, hits, profile)
        relevance = calculate_product_relevance(keyword, hits, profile, intent)
        flags = build_flags(keyword, hits, profile, intent)
        metrics = extract_aba_metrics(row, detected_columns)
        demand_score_value = demand_score(metrics["search_frequency_rank"])
        demand_level_value = demand_level(metrics["search_frequency_rank"])
        click_eff = click_conversion_efficiency(metrics["click_share"], metrics["conversion_share"])
        click_score = click_conversion_efficiency_score(metrics["click_share"], metrics["conversion_share"])
        conversion_advantage_value = conversion_advantage(metrics["click_share"], metrics["conversion_share"])
        risk = risk_score(flags, relevance)
        composite = composite_priority_score(relevance, demand_score_value, click_score, risk)
        scores = {"demand_score": demand_score_value, "click_efficiency_score": click_score, "risk_score": risk, "composite_score": composite}
        category, priority, action, reason = classify_priority(relevance, scores, flags, intent, click_eff)

        negative_candidate = _negative_candidate(category, flags)
        library_entry, library_type = _library_decision(category, risk)
        rule_hit_text = build_rule_hit_text(hits)

        notes = []
        if translation_note:
            notes.append(translation_note)
        if click_eff == "成交效率强":
            notes.append("Top1转化份额高于Top1点击份额，成交效率强")
        elif click_eff == "点击强但成交弱":
            notes.append("Top1点击份额高但Top1转化份额偏低")
        if category == "待人工确认":
            notes.append("数据或规则不足，需要人工确认")

        result = {
            "原搜索词": keyword,
            "中文翻译": translation,
            "词意图类型": intent,
            "搜索频率排名": _clean_missing(metrics["search_frequency_rank"]),
            "Top1点击份额": _clean_missing(metrics["click_share"]),
            "Top1转化份额": _clean_missing(metrics["conversion_share"]),
            "转化优势": _clean_missing(conversion_advantage_value),
            "需求评分": _clean_missing(demand_score_value),
            "需求等级": demand_level_value,
            "点击转化效率": click_eff,
            "点击转化效率评分": _clean_missing(click_score),
            "产品相关性评分": relevance,
            "相关性评分": relevance,
            "风险评分": risk,
            "综合优先级评分": composite,
            "分类结果": category,
            "推广优先级": priority,
            "建议动作": action,
            "命中的规则": rule_hit_text,
            "为什么这样分类": reason,
            "是否品牌词": yes_no(flags["is_brand"]),
            "是否配件词": yes_no(flags["is_accessory"]),
            "是否否词候选": yes_no(negative_candidate),
            "是否进入关键词库": library_entry,
            "词库类型": library_type,
            "备注": compact_join(notes),
        }

        for original_column in df.columns:
            if original_column == keyword_column:
                continue
            output_name = f"原表_{original_column}"
            if output_name not in result:
                result[output_name] = _clean_missing(row.get(original_column, ""))

        output_rows.append(result)
        rule_rows.append(
            {
                "原搜索词": keyword,
                "词意图类型": intent,
                "分类结果": category,
                "推广优先级": priority,
                "产品相关性评分": relevance,
                "需求评分": _clean_missing(demand_score_value),
                "点击转化效率评分": _clean_missing(click_score),
                "风险评分": risk,
                "综合优先级评分": composite,
                "是否否词候选": yes_no(negative_candidate),
                "命中的规则": rule_hit_text or "未命中明确规则",
                "为什么这样分类": reason,
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
