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
from .utils import clamp, compact_join, contains_term, match_terms, normalize_text, split_terms, yes_no


PRODUCT_TYPE_OPTIONS = [
    "carry_on_luggage",
    "checked_luggage",
    "trunk_luggage",
    "front_pocket_luggage",
    "luggage_set",
    "luggage_accessory",
    "other_unknown",
]

PRODUCT_TYPE_LABELS = {
    "carry_on_luggage": "Carry-On Luggage 登机箱",
    "checked_luggage": "Checked Luggage 托运行李箱",
    "trunk_luggage": "Trunk Luggage / Trunk-Style Luggage",
    "front_pocket_luggage": "Front Pocket Carry-On Luggage 前仓登机箱",
    "luggage_set": "Luggage Set 行李箱套装",
    "luggage_accessory": "Luggage Accessory 行李箱配件",
    "other_unknown": "Other / Unknown",
}

LEGACY_PRODUCT_TYPE_ALIASES = {
    "accessory": "luggage_accessory",
    "unknown": "other_unknown",
    "": "other_unknown",
    None: "other_unknown",
}

DEFAULT_PRODUCT_TYPE_RULES = {
    "carry_on_luggage": {
        "core_terms": ["carry on luggage", "carry-on luggage", "carry on suitcase", "carry-on suitcase"],
        "precision_terms": [
            "20 inch carry on luggage",
            "22x14x9 carry on luggage",
            "airline approved carry on luggage",
            "hardside carry on luggage",
        ],
        "downgrade_terms": ["checked luggage", "checked suitcase", "large checked luggage", "30 inch luggage", "26 inch luggage"],
        "hard_negative_terms": [],
    },
    "checked_luggage": {
        "core_terms": ["checked luggage", "checked suitcase"],
        "precision_terms": ["medium checked luggage", "large checked luggage", "26 inch luggage", "28 inch luggage", "30 inch luggage"],
        "downgrade_terms": ["carry on luggage", "carry-on luggage", "22x14x9 carry on luggage", "20 inch carry on luggage"],
        "hard_negative_terms": [],
    },
    "trunk_luggage": {
        "core_terms": ["trunk luggage", "trunk suitcase", "trunk style luggage", "trunk-style luggage"],
        "precision_terms": [
            "checked trunk luggage",
            "medium trunk luggage",
            "large trunk luggage",
            "26 inch luggage",
            "30 inch luggage",
            "medium checked luggage",
            "large checked luggage",
        ],
        "downgrade_terms": ["carry on luggage", "carry-on luggage", "20 inch carry on luggage", "22x14x9 carry on luggage"],
        "hard_negative_terms": ["front pocket", "laptop compartment", "usb", "underseat"],
    },
    "front_pocket_luggage": {
        "core_terms": [
            "front pocket carry on luggage",
            "carry on luggage with front pocket",
            "laptop compartment carry on luggage",
            "carry on luggage with laptop compartment",
        ],
        "precision_terms": [
            "22x14x9 carry on luggage",
            "20 inch carry on luggage",
            "airline approved carry on luggage",
            "business carry on luggage",
        ],
        "downgrade_terms": ["checked luggage", "large checked luggage", "30 inch luggage"],
        "hard_negative_terms": ["trunk luggage", "trunk suitcase", "trunk style luggage"],
    },
    "luggage_set": {
        "core_terms": ["luggage set", "luggage sets", "suitcase set", "suitcase sets"],
        "precision_terms": ["2 piece luggage set", "3 piece luggage set", "4 piece luggage set", "3 piece suitcase set"],
        "downgrade_terms": ["single carry on luggage", "single checked luggage"],
        "hard_negative_terms": [],
    },
    "luggage_accessory": {
        "core_terms": ["luggage tag", "luggage tags", "luggage cover", "luggage scale", "weight scale", "luggage strap", "luggage straps", "tsa lock"],
        "precision_terms": ["leather luggage tags", "digital luggage scale", "suitcase cover", "luggage weight scale"],
        "downgrade_terms": [],
        "hard_negative_terms": [],
    },
}

DIMENSION_TERMS = [
    "20 inch",
    "21 inch",
    "22 inch",
    "24 inch",
    "26 inch",
    "28 inch",
    "30 inch",
    "22x14x9",
    "medium",
    "large",
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


def canonical_product_type(value: object) -> str:
    product_type = str(value or "").strip()
    product_type = LEGACY_PRODUCT_TYPE_ALIASES.get(product_type, product_type)
    if product_type not in PRODUCT_TYPE_OPTIONS:
        return "other_unknown"
    return product_type


def _rules_list(rules: dict[str, Any], key: str) -> list[str]:
    return compact_terms(rules.get(key, []))


def _product_rules(rules: dict[str, Any], product_type: str) -> dict[str, Any]:
    product_type = canonical_product_type(product_type)
    configured = rules.get("product_type_rules", {})
    if isinstance(configured, dict) and isinstance(configured.get(product_type), dict):
        merged = dict(DEFAULT_PRODUCT_TYPE_RULES.get(product_type, {}))
        merged.update(configured[product_type])
        return merged
    legacy_key = "accessory" if product_type == "luggage_accessory" else "unknown" if product_type == "other_unknown" else product_type
    if isinstance(configured, dict) and isinstance(configured.get(legacy_key), dict):
        merged = dict(DEFAULT_PRODUCT_TYPE_RULES.get(product_type, {}))
        merged.update(configured[legacy_key])
        return merged
    return DEFAULT_PRODUCT_TYPE_RULES.get(product_type, {})


def _product_rule_terms(rules: dict[str, Any], product_type: str, key: str) -> list[str]:
    return compact_terms(_product_rules(rules, product_type).get(key, []))


def _extract_sizes(text: str, configured_sizes: list[str]) -> list[str]:
    found = set(match_terms(text, configured_sizes))
    for match in re.findall(r"\b\d{2}\s?inch\b|\b\d{2}x\d{2}x\d{1,2}\b", text.lower()):
        found.add(match.replace(" ", " "))
    return sorted(found)


def _has_any(text: str, terms: list[str]) -> bool:
    return bool(match_terms(text, terms))


def _is_carry_on_query(keyword: str) -> bool:
    return _has_any(keyword, ["carry on", "carry-on", "cabin luggage", "22x14x9", "airline approved"])


def _is_checked_query(keyword: str) -> bool:
    return _has_any(
        keyword,
        [
            "checked luggage",
            "checked suitcase",
            "medium checked",
            "large checked",
            "26 inch luggage",
            "28 inch luggage",
            "30 inch luggage",
        ],
    )


def _is_trunk_query(keyword: str) -> bool:
    return _has_any(keyword, ["trunk luggage", "trunk suitcase", "trunk style", "trunk-style", "trunk"])


def _is_front_pocket_query(keyword: str) -> bool:
    return _has_any(keyword, ["front pocket", "laptop compartment"])


def _is_front_pocket_mismatch_query(keyword: str) -> bool:
    return _has_any(keyword, ["front pocket", "laptop compartment", "usb", "underseat"])


def _is_generic_query(keyword: str) -> bool:
    return normalize_text(keyword) in {"luggage", "suitcase"}


def _size_token(term: str) -> str:
    return normalize_text(term).replace(" ", "")


def _expand_size_terms(terms: list[str]) -> set[str]:
    values = {_size_token(term) for term in terms if term}
    if "medium" in values:
        values.update({"24inch", "26inch"})
    if "large" in values:
        values.update({"28inch", "30inch"})
    if "20inch" in values:
        values.update({"22x14x9"})
    if "22x14x9" in values:
        values.add("20inch")
    return values


def _query_size_terms(keyword: str) -> list[str]:
    return _extract_sizes(keyword, DIMENSION_TERMS)


def _size_matches_profile(keyword: str, profile: dict[str, Any]) -> tuple[bool, list[str]]:
    query_sizes = _query_size_terms(keyword)
    if not query_sizes:
        return True, []
    profile_sizes = compact_terms(profile.get("size_terms", []))
    if not profile_sizes:
        return True, query_sizes
    return bool(_expand_size_terms(query_sizes) & _expand_size_terms(profile_sizes)), query_sizes


def infer_product_type(text: str, core_terms: list[str], rules: dict[str, Any]) -> str:
    source = " ".join([text, *core_terms])
    if _has_any(source, _rules_list(rules, "set_terms")):
        return "luggage_set"
    if _has_any(source, _rules_list(rules, "accessory_terms")):
        return "luggage_accessory"
    if _has_any(source, ["front pocket", "laptop compartment"]):
        return "front_pocket_luggage"
    if _has_any(source, ["trunk luggage", "trunk suitcase", "trunk style", "trunk-style", "deep compartment", "3:7 split", "3 7 split"]):
        return "trunk_luggage"
    if _has_any(source, ["checked luggage", "checked suitcase", "medium checked", "large checked", "26 inch", "28 inch", "30 inch"]):
        return "checked_luggage"
    if _has_any(source, ["carry on luggage", "carry-on luggage", "carry on suitcase", "carry-on suitcase", "22x14x9", "airline approved"]):
        return "carry_on_luggage"
    return "other_unknown"


def _default_core_for_product_type(product_type: str, rules: dict[str, Any]) -> list[str]:
    core = _product_rule_terms(rules, product_type, "core_terms")
    if core:
        return core[:2]
    return []


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
    configured_core = compact_terms(_rules_list(rules, "core_candidate_terms") + sum((list(v.get("core_terms", [])) for v in DEFAULT_PRODUCT_TYPE_RULES.values()), []))
    configured_colors = _rules_list(rules, "color_terms")
    configured_sizes = _rules_list(rules, "size_terms")
    configured_features = _rules_list(rules, "functional_terms")
    configured_scenarios = _rules_list(rules, "scene_terms")

    detected_core = compact_terms(split_terms(core_terms) or match_terms(product_text, configured_core))
    product_type = infer_product_type(product_text, detected_core, rules)
    if not detected_core:
        detected_core = _default_core_for_product_type(product_type, rules) or match_terms(product_text, ["luggage", "suitcase"])

    is_luggage_set = product_type == "luggage_set"
    is_accessory = product_type == "luggage_accessory"
    is_front_pocket = product_type == "front_pocket_luggage" or _has_any(product_text, ["front pocket", "laptop compartment"])
    is_trunk_style = product_type == "trunk_luggage" or _has_any(product_text, ["trunk", "deep compartment", "3:7 split", "3 7 split"])
    is_carry_on = product_type in {"carry_on_luggage", "front_pocket_luggage"} or _is_carry_on_query(product_text)
    is_checked = product_type == "checked_luggage" or (is_trunk_style and _is_checked_query(product_text)) or _has_any(product_text, ["checked luggage", "26 inch", "28 inch", "30 inch"])

    return normalize_profile(
        {
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
            "is_accessory": is_accessory,
            "is_front_pocket": is_front_pocket,
            "is_trunk_style": is_trunk_style,
            "is_carry_on": is_carry_on,
            "is_checked": is_checked,
        }
    )


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

    product_type = canonical_product_type(normalized.get("product_type"))
    normalized["product_type"] = product_type
    for key in ["is_single_luggage", "is_luggage_set", "is_accessory", "is_front_pocket", "is_trunk_style", "is_carry_on", "is_checked"]:
        normalized[key] = bool(normalized.get(key))

    if product_type == "carry_on_luggage":
        normalized.update({"is_carry_on": True, "is_single_luggage": True, "is_luggage_set": False, "is_accessory": False})
    elif product_type == "front_pocket_luggage":
        normalized.update({"is_carry_on": True, "is_front_pocket": True, "is_single_luggage": True, "is_luggage_set": False, "is_accessory": False})
    elif product_type == "checked_luggage":
        normalized.update({"is_checked": True, "is_single_luggage": True, "is_luggage_set": False, "is_accessory": False})
    elif product_type == "trunk_luggage":
        normalized.update({"is_trunk_style": True, "is_single_luggage": True, "is_luggage_set": False, "is_accessory": False})
    elif product_type == "luggage_set":
        normalized.update({"is_luggage_set": True, "is_single_luggage": False, "is_accessory": False})
    elif product_type == "luggage_accessory":
        normalized.update({"is_accessory": True, "is_single_luggage": False, "is_luggage_set": False})

    return normalized


def _keyword_hits(keyword: str, profile: dict[str, Any], rules: dict[str, Any]) -> dict[str, list[str]]:
    product_type = canonical_product_type(profile.get("product_type"))
    return {
        "core": match_terms(keyword, profile.get("core_terms", [])),
        "product_core": match_terms(keyword, _product_rule_terms(rules, product_type, "core_terms")),
        "product_precision": match_terms(keyword, _product_rule_terms(rules, product_type, "precision_terms")),
        "product_downgrade": match_terms(keyword, _product_rule_terms(rules, product_type, "downgrade_terms")),
        "product_negative": match_terms(keyword, _product_rule_terms(rules, product_type, "hard_negative_terms")),
        "size": match_terms(keyword, profile.get("size_terms", [])),
        "query_size": _query_size_terms(keyword),
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


def _has_long_tail_qualifier(keyword: str, hits: dict[str, list[str]], rules: dict[str, Any]) -> bool:
    qualifier_terms = compact_terms(
        _rules_list(rules, "functional_terms")
        + _rules_list(rules, "material_terms")
        + ["airline approved", "business", "international", "lightweight"]
    )
    return bool(hits["query_size"] or hits["color"] or match_terms(keyword, qualifier_terms))


def assess_keyword_fit(keyword: str, hits: dict[str, list[str]], profile: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    product_type = canonical_product_type(profile.get("product_type"))
    score = 0
    reasons: list[str] = []
    hard_mismatch = False
    type_downgrade = False
    size_mismatch = False
    product_match = False

    size_matches, query_sizes = _size_matches_profile(keyword, profile)
    if query_sizes and not size_matches:
        size_mismatch = True
        reasons.append(f"命中尺寸 {', '.join(query_sizes)}，但与当前产品尺寸画像不一致")

    if hits["different_category"] or hits["exclude"]:
        hard_mismatch = True
        reasons.append("命中不同品类或用户手动不相关词")

    if hits["accessory"]:
        if product_type == "luggage_accessory":
            product_match = True
            score = max(score, 90)
            reasons.append("当前产品为配件，搜索词命中配件方向")
        else:
            hard_mismatch = True
            score = max(score, 10)
            reasons.append("当前产品不是配件，搜索词命中配件方向")

    if hits["set"]:
        if product_type == "luggage_set":
            product_match = True
            score = max(score, 92)
            reasons.append("当前产品为套装，搜索词命中套装方向")
        else:
            hard_mismatch = True
            score = max(score, 10)
            reasons.append("当前产品不是套装，搜索词命中 luggage set / suitcase set")

    if hits["product_negative"]:
        hard_mismatch = True
        score = max(score, 15)
        reasons.append("命中当前产品类型的不适配词")

    if product_type == "carry_on_luggage":
        if _is_carry_on_query(keyword):
            product_match = True
            score = max(score, 86)
            reasons.append("当前产品为 Carry-On，搜索词命中登机箱方向")
        if _is_checked_query(keyword):
            type_downgrade = True
            score = max(score, 42)
            reasons.append("当前产品为 Carry-On，搜索词偏 Checked 托运方向")
        if _is_trunk_query(keyword):
            hard_mismatch = True
            score = max(score, 18)
            reasons.append("当前产品不是 Trunk，搜索词偏 trunk 方向")
        if _is_front_pocket_query(keyword) and not profile.get("is_front_pocket"):
            type_downgrade = True
            score = max(score, 48)
            reasons.append("当前产品未确认前仓，搜索词偏 front pocket / laptop compartment")

    elif product_type == "checked_luggage":
        if _is_checked_query(keyword):
            product_match = True
            score = max(score, 88)
            reasons.append("当前产品为 Checked，搜索词命中托运行李箱方向")
        if _is_carry_on_query(keyword):
            type_downgrade = True
            score = max(score, 42)
            reasons.append("当前产品为 Checked，搜索词偏 Carry-On 登机箱方向")
        if _is_trunk_query(keyword) and not profile.get("is_trunk_style"):
            type_downgrade = True
            score = max(score, 45)
            reasons.append("当前产品不是 trunk 结构，搜索词偏 trunk 方向")

    elif product_type == "trunk_luggage":
        if _is_trunk_query(keyword):
            product_match = True
            score = max(score, 90)
            reasons.append("当前产品为 Trunk / Trunk-Style，搜索词命中 trunk luggage")
        if _is_checked_query(keyword) and not _is_carry_on_query(keyword):
            product_match = True
            score = max(score, 80)
            reasons.append("当前 trunk 产品偏 checked 尺寸，搜索词命中 checked / 托运尺寸方向")
        if _is_carry_on_query(keyword):
            type_downgrade = True
            score = max(score, 40)
            reasons.append("当前产品为 Trunk Checked，搜索词偏 Carry-On 登机箱方向")
        if _is_front_pocket_mismatch_query(keyword):
            hard_mismatch = True
            score = max(score, 15)
            reasons.append("当前产品为 Trunk，front pocket / laptop compartment / usb / underseat 不适配")

    elif product_type == "front_pocket_luggage":
        if _is_front_pocket_query(keyword):
            product_match = True
            score = max(score, 92)
            reasons.append("当前产品为 Front Pocket Carry-On，搜索词命中前仓或电脑仓方向")
        if _is_carry_on_query(keyword):
            product_match = True
            score = max(score, 84)
            reasons.append("当前产品为 Front Pocket Carry-On，搜索词命中登机箱方向")
        if _is_trunk_query(keyword):
            hard_mismatch = True
            score = max(score, 15)
            reasons.append("当前产品不是 Trunk，搜索词偏 trunk 方向")
        if _is_checked_query(keyword):
            type_downgrade = True
            score = max(score, 40)
            reasons.append("当前产品为 Carry-On，搜索词偏 Checked 托运方向")

    elif product_type == "luggage_set":
        if hits["set"]:
            product_match = True
            score = max(score, 92)
        elif _is_carry_on_query(keyword) or _is_checked_query(keyword):
            type_downgrade = True
            score = max(score, 55)
            reasons.append("当前产品为套装，搜索词偏单个行李箱方向，需要确认承接")

    elif product_type == "luggage_accessory":
        if hits["accessory"]:
            product_match = True
            score = max(score, 90)
        elif _is_carry_on_query(keyword) or _is_checked_query(keyword) or _is_trunk_query(keyword) or hits["set"]:
            hard_mismatch = True
            score = max(score, 20)
            reasons.append("当前产品为配件，搜索词偏行李箱主体或套装方向")

    if hits["product_core"]:
        product_match = True
        score = max(score, 86)
        reasons.append("命中当前产品类型核心词")
    if hits["product_precision"]:
        product_match = True
        score = max(score, 92)
        reasons.append("命中当前产品类型精准长尾词")

    if size_mismatch and product_type in {"checked_luggage", "trunk_luggage", "carry_on_luggage", "front_pocket_luggage"}:
        type_downgrade = True
        if not product_match:
            score = max(score, 42)
        else:
            score = min(score, 58)

    if _is_generic_query(keyword):
        score = max(score, 55)
        reasons.append("搜索词为 luggage / suitcase 泛类目词")

    if score == 0:
        if hits["feature"] or hits["color"] or hits["scenario"] or hits["size"]:
            score = 55
            reasons.append("命中产品属性或使用场景，但不是明确核心词")
        elif hits["core"]:
            score = 50
            reasons.append("命中用户补充核心词，但产品类型关系不够明确")

    if hard_mismatch:
        score = min(score, 25)
    elif type_downgrade:
        score = min(max(score, 38), 58)

    return {
        "score": clamp(score),
        "product_match": product_match,
        "hard_mismatch": hard_mismatch,
        "type_downgrade": type_downgrade,
        "size_mismatch": size_mismatch,
        "size_matches": size_matches,
        "query_sizes": query_sizes,
        "reason_parts": reasons,
    }


def detect_keyword_intent(keyword: str, hits: dict[str, list[str]], profile: dict[str, Any], assessment: dict[str, Any] | None = None, rules: dict[str, Any] | None = None) -> str:
    rules = rules or {}
    assessment = assessment or {}
    product_type = canonical_product_type(profile.get("product_type"))

    if hits["brand"]:
        return "品牌/竞品词"
    if hits["accessory"]:
        if product_type == "luggage_accessory":
            return "精准长尾词" if _has_long_tail_qualifier(keyword, hits, rules) else "核心类目词"
        return "配件词"
    if hits["set"]:
        if product_type == "luggage_set":
            return "精准长尾词" if _has_long_tail_qualifier(keyword, hits, rules) else "核心类目词"
        return "套装词"
    if hits["different_category"] or hits["exclude"] or hits["product_negative"] or assessment.get("hard_mismatch"):
        return "明显不相关词"
    if assessment.get("type_downgrade") or assessment.get("size_mismatch"):
        return "不同产品类型词"
    if _is_generic_query(keyword):
        return "泛类目词"
    if hits["product_precision"]:
        return "精准长尾词"
    if hits["product_core"]:
        return "精准长尾词" if _has_long_tail_qualifier(keyword, hits, rules) else "核心类目词"
    if hits["core"] and _has_long_tail_qualifier(keyword, hits, rules):
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


def calculate_product_relevance(keyword: str, hits: dict[str, list[str]], profile: dict[str, Any], intent: str, rules: dict[str, Any] | None = None) -> int:
    return int(assess_keyword_fit(keyword, hits, profile, rules or {}).get("score", 0))


def build_flags(
    keyword: str,
    hits: dict[str, list[str]],
    profile: dict[str, Any],
    intent: str,
    assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assessment = assessment or {}
    return {
        "is_brand": bool(hits["brand"]),
        "is_accessory": bool(hits["accessory"] and canonical_product_type(profile.get("product_type")) != "luggage_accessory"),
        "is_accessory_product_match": bool(hits["accessory"] and canonical_product_type(profile.get("product_type")) == "luggage_accessory"),
        "is_set_term": bool(hits["set"]),
        "is_set_mismatch": bool(hits["set"] and not profile.get("is_luggage_set")),
        "is_different_category": bool(hits["different_category"]),
        "is_hard_mismatch": bool(assessment.get("hard_mismatch")),
        "is_type_downgrade": bool(assessment.get("type_downgrade")),
        "is_size_mismatch": bool(assessment.get("size_mismatch")),
        "is_irrelevant": bool(hits["exclude"] or assessment.get("hard_mismatch")),
        "is_generic": intent == "泛类目词",
        "has_attribute_intent": intent in {"尺寸词", "颜色词", "功能词", "场景词"},
    }


def build_rule_hit_text(hits: dict[str, list[str]]) -> str:
    labels = {
        "product_core": "当前产品类型核心词",
        "product_precision": "当前产品类型精准词",
        "product_downgrade": "当前产品类型降级词",
        "product_negative": "当前产品类型不适配词",
        "core": "用户核心词",
        "size": "产品尺寸词",
        "query_size": "搜索词尺寸",
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
    return (
        category == "D级不相关/否词"
        or flags["is_accessory"]
        or flags["is_set_mismatch"]
        or flags["is_different_category"]
        or flags["is_hard_mismatch"]
        or flags["is_irrelevant"]
    )


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


def product_profile_label(profile: dict[str, Any]) -> str:
    label = PRODUCT_TYPE_LABELS.get(canonical_product_type(profile.get("product_type")), "Other / Unknown")
    if profile.get("is_trunk_style") and profile.get("is_checked"):
        return "Trunk Checked 行李箱"
    if profile.get("is_front_pocket"):
        return "Front Pocket Carry-On 前仓登机箱"
    return label


def explain_classification(
    category: str,
    intent: str,
    profile: dict[str, Any],
    hits: dict[str, list[str]],
    flags: dict[str, Any],
    assessment: dict[str, Any],
    fallback_reason: str,
) -> str:
    product_label = product_profile_label(profile)
    if flags["is_brand"]:
        return f"当前产品为{product_label}，该词命中品牌/竞品词：{', '.join(hits['brand'])}，应进入品牌/竞品词库，不进入普通主推词。"
    if flags["is_accessory"]:
        return f"当前产品为{product_label}，不是配件；该词命中配件词：{', '.join(hits['accessory'])}，建议作为否词候选。"
    if flags["is_set_mismatch"]:
        return f"当前产品为{product_label}，不是套装；该词命中套装词：{', '.join(hits['set'])}，建议作为否词候选。"
    if flags["is_hard_mismatch"]:
        detail = compact_join(assessment.get("reason_parts", [])) or "命中当前产品类型的不适配词"
        return f"当前产品为{product_label}，{detail}，因此不进入主推词。"
    if flags["is_type_downgrade"]:
        detail = compact_join(assessment.get("reason_parts", [])) or "搜索词方向与当前产品类型不完全匹配"
        return f"当前产品为{product_label}，{detail}，建议降级或人工确认。"
    if flags["is_size_mismatch"]:
        return f"当前产品为{product_label}，搜索词尺寸与当前产品尺寸画像不一致，建议人工确认。"
    if category in {"S级核心主推词", "A级重点词"}:
        if intent == "核心类目词":
            return f"当前产品为{product_label}，该词是当前产品类型的核心类目词，相关性高。"
        if intent == "精准长尾词":
            return f"当前产品为{product_label}，该词命中当前产品类型的精准长尾方向，相关性高。"
        return f"当前产品为{product_label}，该词与产品画像匹配度高，适合重点测试。"
    if category == "C级Listing埋词":
        return f"当前产品为{product_label}，该词偏功能、属性或场景，可用于 Listing 埋词。"
    if category == "B级低价测试词":
        return f"当前产品为{product_label}，该词有一定相关性但不适合作为主预算，建议低价测试。"
    if intent == "泛类目词":
        return f"当前产品为{product_label}，该词为泛类目词，需求可能大但不够精准。"
    return fallback_reason


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
        assessment = assess_keyword_fit(keyword, hits, profile, rules)
        intent = detect_keyword_intent(keyword, hits, profile, assessment, rules)
        relevance = int(assessment["score"])
        flags = build_flags(keyword, hits, profile, intent, assessment)
        metrics = extract_aba_metrics(row, detected_columns)
        demand_score_value = demand_score(metrics["search_frequency_rank"])
        demand_level_value = demand_level(metrics["search_frequency_rank"])
        click_eff = click_conversion_efficiency(metrics["click_share"], metrics["conversion_share"])
        click_score = click_conversion_efficiency_score(metrics["click_share"], metrics["conversion_share"])
        conversion_advantage_value = conversion_advantage(metrics["click_share"], metrics["conversion_share"])
        risk = risk_score(flags, relevance)
        composite = composite_priority_score(relevance, demand_score_value, click_score, risk)
        scores = {"demand_score": demand_score_value, "click_efficiency_score": click_score, "risk_score": risk, "composite_score": composite}
        category, priority, action, base_reason = classify_priority(relevance, scores, flags, intent, click_eff)
        reason = explain_classification(category, intent, profile, hits, flags, assessment, base_reason)

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
            notes.append("数据或产品类型规则需要人工确认")

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
            "是否配件词": yes_no(flags["is_accessory"] or flags["is_accessory_product_match"]),
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
                "产品类型": product_profile_label(profile),
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


def analyze_keywords(*args, **kwargs):
    return analyze_aba_keywords(*args, **kwargs)


def analyze(*args, **kwargs):
    return analyze_aba_keywords(*args, **kwargs)


__all__ = [
    "PRODUCT_TYPE_OPTIONS",
    "PRODUCT_TYPE_LABELS",
    "analyze",
    "analyze_keywords",
    "analyze_aba_keywords",
    "build_product_profile",
    "normalize_profile",
]
