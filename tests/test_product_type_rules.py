from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analyzer import analyze_aba_keywords, build_product_profile
from src.loader import load_rules


WAIT = "\u5f85\u4eba\u5de5\u786e\u8ba4"
BRAND = "\u54c1\u724c/\u7ade\u54c1\u8bcd"
CORE_INTENT = "\u6838\u5fc3\u7c7b\u76ee\u8bcd"
PRECISION_INTENT = "\u7cbe\u51c6\u957f\u5c3e\u8bcd"
YES = "\u662f"


KEYWORDS = [
    "carry on luggage",
    "20 inch carry on luggage",
    "22x14x9 carry on luggage",
    "checked luggage",
    "medium checked luggage",
    "large checked luggage",
    "26 inch luggage",
    "30 inch luggage",
    "front pocket carry on luggage",
    "carry on luggage with laptop compartment",
    "laptop compartment carry on luggage",
    "trunk luggage",
    "trunk suitcase",
    "luggage set",
    "luggage tags",
    "luggage scale",
    "samsonite luggage",
]


def build_result(product_title: str):
    rules = load_rules("config/default_rules.yaml")
    df = pd.DataFrame(
        {
            "Search Term": KEYWORDS,
            "Search Frequency Rank": [1000 + index * 100 for index in range(len(KEYWORDS))],
            "Click Share": [10] * len(KEYWORDS),
            "Conversion Share": [12] * len(KEYWORDS),
        }
    )
    detected = {
        "keyword": "Search Term",
        "search_frequency_rank": "Search Frequency Rank",
        "click_share": "Click Share",
        "conversion_share": "Conversion Share",
    }
    profile = build_product_profile(product_title, "", "", "", "", "", rules)
    result, _ = analyze_aba_keywords(df, "Search Term", detected, profile, rules)
    columns = list(result.columns)
    return profile, result.set_index(columns[0]), columns


def value(row, columns, index):
    return row[columns[index]]


def category(row, columns):
    return value(row, columns, 15)


def intent(row, columns):
    return value(row, columns, 2)


def priority(row, columns):
    return value(row, columns, 16)


def negative(row, columns):
    return value(row, columns, 22)


def assert_good(row, columns):
    assert priority(row, columns) in {"S", "A"}


def assert_d(row, columns):
    assert str(category(row, columns)).startswith("D")
    assert negative(row, columns) == YES


def assert_downgrade(row, columns):
    assert category(row, columns) == WAIT


def test_carry_on_rules():
    profile, result, columns = build_result(
        "20 Inch Carry On Luggage 22x14x9 Airline Approved, Hardside Carry On Suitcase with Spinner Wheels, TSA Lock, Black"
    )
    assert profile["product_type"] == "carry_on_luggage"
    assert_good(result.loc["carry on luggage"], columns)
    assert intent(result.loc["carry on luggage"], columns) == CORE_INTENT
    assert_good(result.loc["20 inch carry on luggage"], columns)
    assert intent(result.loc["20 inch carry on luggage"], columns) == PRECISION_INTENT
    assert_downgrade(result.loc["checked luggage"], columns)
    for keyword in ["luggage set", "luggage tags", "luggage scale"]:
        assert_d(result.loc[keyword], columns)


def test_trunk_checked_rules():
    profile, result, columns = build_result(
        "26 Inch Medium Checked Luggage, PC Hardshell Trunk Luggage with 3:7 Split Design, TSA Lock, Spinner Wheels"
    )
    assert profile["product_type"] == "trunk_luggage"
    for keyword in ["trunk luggage", "trunk suitcase", "26 inch luggage", "medium checked luggage"]:
        assert_good(result.loc[keyword], columns)
    assert_downgrade(result.loc["carry on luggage"], columns)
    for keyword in ["front pocket carry on luggage", "laptop compartment carry on luggage", "luggage set", "luggage tags", "luggage scale"]:
        assert_d(result.loc[keyword], columns)


def test_large_trunk_checked_rules():
    profile, result, columns = build_result("30 Inch Large Checked Luggage, PC Hardshell Trunk Luggage with 3:7 Split Design")
    assert profile["product_type"] == "trunk_luggage"
    for keyword in ["30 inch luggage", "large checked luggage", "trunk luggage"]:
        assert_good(result.loc[keyword], columns)
    assert_downgrade(result.loc["carry on luggage"], columns)
    assert_downgrade(result.loc["medium checked luggage"], columns)
    for keyword in ["luggage tags", "luggage scale"]:
        assert_d(result.loc[keyword], columns)


def test_front_pocket_rules():
    profile, result, columns = build_result(
        "20 Inch Carry On Luggage with Front Pocket, 22x14x9 Airline Approved Expandable Hardside Suitcase with Laptop Compartment, TSA Lock, USB Port, Spinner Wheels"
    )
    assert profile["product_type"] == "front_pocket_luggage"
    for keyword in ["front pocket carry on luggage", "carry on luggage with laptop compartment", "carry on luggage", "22x14x9 carry on luggage"]:
        assert_good(result.loc[keyword], columns)
    assert_d(result.loc["trunk luggage"], columns)
    assert_downgrade(result.loc["checked luggage"], columns)
    for keyword in ["luggage set", "luggage tags", "luggage scale"]:
        assert_d(result.loc[keyword], columns)


def test_checked_and_accessory_are_different_profiles():
    profile, result, columns = build_result("28 Inch Checked Luggage Hardside Checked Suitcase with Spinner Wheels TSA Lock")
    assert profile["product_type"] == "checked_luggage"
    assert_downgrade(result.loc["carry on luggage"], columns)
    assert_good(result.loc["checked luggage"], columns)
    assert category(result.loc["samsonite luggage"], columns) == BRAND

    profile, result, columns = build_result("Leather Luggage Tags with Privacy Cover for Suitcase Travel Bag")
    assert profile["product_type"] == "luggage_accessory"
    assert_good(result.loc["luggage tags"], columns)
    assert_d(result.loc["carry on luggage"], columns)


if __name__ == "__main__":
    test_carry_on_rules()
    test_trunk_checked_rules()
    test_large_trunk_checked_rules()
    test_front_pocket_rules()
    test_checked_and_accessory_are_different_profiles()
    print("product type rule tests passed")
