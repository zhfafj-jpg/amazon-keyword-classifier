from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import streamlit as st

from src.analyzer import PRODUCT_TYPE_OPTIONS, analyze_aba_keywords, build_product_profile, normalize_profile
from src.exporter import create_excel_bytes, summarize_counts
from src.loader import build_column_choice_labels, list_excel_sheets, load_rules, read_aba_file


BASE_DIR = Path(__file__).parent
RULE_PATH = BASE_DIR / "config" / "default_rules.yaml"


def get_secret_password() -> str | None:
    for key in ["APP_PASSWORD", "app_password", "password"]:
        try:
            value = st.secrets.get(key)
        except Exception:
            value = None
        if value:
            return str(value)
    return None


def password_gate() -> bool:
    expected_password = get_secret_password()
    if not expected_password:
        st.info("本地调试模式：未设置 Streamlit Secrets 密码，已自动放行。")
        return True

    if st.session_state.get("authenticated"):
        return True

    st.title("Amazon ABA Keyword Analyzer")
    password = st.text_input("请输入访问密码", type="password")
    if password:
        if password == expected_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("密码不正确")
    return False


def join_terms(values: Any) -> str:
    if not values:
        return ""
    if isinstance(values, str):
        return values
    return ", ".join(str(value) for value in values if str(value).strip())


def split_input(value: str) -> list[str]:
    return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]


def column_samples(df, column: str, limit: int = 3) -> str:
    values = [
        str(value).strip()
        for value in df[column].dropna().astype(str).head(12).tolist()
        if str(value).strip() and str(value).lower() != "nan"
    ][:limit]
    return ", ".join(values)


def render_product_profile_editor(auto_profile: dict[str, Any]) -> dict[str, Any]:
    profile = normalize_profile(auto_profile)
    with st.expander("自动识别到的产品画像（可修改）", expanded=True):
        st.caption("请快速确认程序对产品的理解是否正确。这里的结果会直接影响 ABA 词分类。")
        product_type = st.selectbox(
            "产品类型",
            PRODUCT_TYPE_OPTIONS,
            index=PRODUCT_TYPE_OPTIONS.index(profile["product_type"]),
            format_func=lambda value: {
                "carry_on_luggage": "登机箱 / carry on",
                "checked_luggage": "托运行李箱 / checked",
                "trunk_luggage": "trunk结构行李箱",
                "front_pocket_luggage": "前仓商务登机箱",
                "luggage_set": "行李箱套装",
                "accessory": "配件",
                "unknown": "未确认",
            }.get(value, value),
        )

        col1, col2 = st.columns(2)
        with col1:
            is_single_luggage = st.checkbox("是否单个行李箱", value=profile["is_single_luggage"])
            is_front_pocket = st.checkbox("是否前仓", value=profile["is_front_pocket"])
            is_carry_on = st.checkbox("是否 carry on", value=profile["is_carry_on"])
        with col2:
            is_luggage_set = st.checkbox("是否套装", value=profile["is_luggage_set"])
            is_trunk_style = st.checkbox("是否 trunk 结构", value=profile["is_trunk_style"])
            is_checked = st.checkbox("是否 checked", value=profile["is_checked"])

        core_terms = st.text_input("核心词", value=join_terms(profile["core_terms"]))
        color_terms = st.text_input("颜色词", value=join_terms(profile["color_terms"]))
        size_terms = st.text_input("尺寸词", value=join_terms(profile["size_terms"]))
        feature_terms = st.text_input("功能词", value=join_terms(profile["feature_terms"]))
        scenario_terms = st.text_input("场景词", value=join_terms(profile["scenario_terms"]))
        exclude_terms = st.text_input("不相关词", value=join_terms(profile["exclude_terms"]))
        accessory_terms = st.text_input("配件词", value=join_terms(profile["accessory_terms"]))
        brand_terms = st.text_input("品牌词", value=join_terms(profile["brand_terms"]))

    return normalize_profile(
        {
            "product_type": product_type,
            "core_terms": split_input(core_terms),
            "color_terms": split_input(color_terms),
            "size_terms": split_input(size_terms),
            "feature_terms": split_input(feature_terms),
            "scenario_terms": split_input(scenario_terms),
            "exclude_terms": split_input(exclude_terms),
            "accessory_terms": split_input(accessory_terms),
            "brand_terms": split_input(brand_terms),
            "is_single_luggage": is_single_luggage,
            "is_luggage_set": is_luggage_set,
            "is_front_pocket": is_front_pocket,
            "is_trunk_style": is_trunk_style,
            "is_carry_on": is_carry_on,
            "is_checked": is_checked,
        }
    )


def main() -> None:
    st.set_page_config(page_title="Amazon ABA Keyword Analyzer", layout="wide")
    if not password_gate():
        return

    rules = load_rules(RULE_PATH)

    st.title("Amazon ABA Keyword Analyzer")
    st.caption("ABA 搜索词分析 + 可沉淀关键词库导出，帮助长期维护关键词资产。")

    left, right = st.columns([0.38, 0.62], gap="large")
    with left:
        st.subheader("关键词库信息")
        product_line = st.text_input("产品线", placeholder="例如：M2 / G3-G4 / M19 / 通用工具类")
        applicable_product = st.text_input("适用产品", placeholder="例如：20 inch front pocket carry on luggage / SKU / ASIN")
        source = st.text_input("来源", value="ABA搜索词表")

        product_info = st.text_area(
            "粘贴产品标题、五点或产品说明",
            height=220,
            placeholder="例如：20 inch hardside carry on luggage with front pocket and laptop compartment, black/silver/red/blue...",
        )
        st.subheader("可选补充字段")
        core_terms = st.text_input("产品核心词", placeholder="carry on luggage, front pocket, laptop compartment")
        color_terms = st.text_input("产品颜色", placeholder="black, silver, red, blue")
        size_terms = st.text_input("产品尺寸", placeholder="20 inch, 22x14x9")
        irrelevant_terms = st.text_input("不相关词", placeholder="kids, backpack, duffel, luggage cover")
        brand_terms = st.text_input("竞品/品牌词", placeholder="samsonite, rimowa, away, monos")

        auto_profile = build_product_profile(
            product_info=product_info,
            core_terms=core_terms,
            color_terms=color_terms,
            size_terms=size_terms,
            irrelevant_terms=irrelevant_terms,
            brand_terms=brand_terms,
            rules=rules,
        )
        product_profile = render_product_profile_editor(auto_profile)

        uploaded_file = st.file_uploader("上传 ABA 搜索词表", type=["csv", "xlsx"])

    if not uploaded_file:
        st.info("请先填写产品信息，并上传 ABA 搜索词表。")
        st.stop()

    sheet_name = None
    if uploaded_file.name.lower().endswith(".xlsx"):
        try:
            sheets = list_excel_sheets(uploaded_file)
            with left:
                sheet_name = st.selectbox("选择工作表", sheets)
        except Exception as exc:
            st.error(f"读取工作表失败：{exc}")
            st.stop()

    try:
        aba_df, file_info = read_aba_file(uploaded_file, sheet_name)
    except Exception as exc:
        st.error(f"读取 ABA 文件失败：{exc}")
        st.stop()

    detected_columns = file_info["detected_columns"]
    column_labels = build_column_choice_labels(aba_df)
    column_names = list(aba_df.columns)
    auto_keyword_column = detected_columns.get("keyword")

    with left:
        keyword_column = auto_keyword_column
        if auto_keyword_column in column_names:
            st.success(f"已自动识别搜索词列：{auto_keyword_column}")
            samples = column_samples(aba_df, auto_keyword_column)
            if samples:
                st.caption(f"样例：{samples}")
            with st.expander("高级设置：手动修正搜索词列", expanded=False):
                manual_column = st.selectbox(
                    "手动选择搜索词列",
                    column_names,
                    index=column_names.index(auto_keyword_column),
                    format_func=lambda column: column_labels.get(column, str(column)),
                )
                if st.checkbox("使用手动选择的搜索词列", value=False):
                    keyword_column = manual_column
        else:
            st.warning("未能自动识别搜索词列，请手动选择。")
            keyword_column = st.selectbox(
                "选择搜索词列",
                column_names,
                format_func=lambda column: column_labels.get(column, str(column)),
            )

        start = st.button("开始分析并生成关键词库", type="primary", use_container_width=True)

    with right:
        st.subheader("ABA 表预览")
        header_status = "已识别" if file_info["header_detected"] else "未完全确认"
        st.write(f"真实表头行：第 {file_info['header_row_number']} 行（{header_status}，得分 {file_info['header_score']}）")
        if detected_columns:
            st.write("自动识别字段：" + "；".join([f"{key}: {value}" for key, value in detected_columns.items()]))
        st.dataframe(aba_df.head(30).fillna(""), use_container_width=True)

    if start:
        with st.spinner("正在分析 ABA 搜索词并生成可沉淀关键词库..."):
            result_df, rules_df = analyze_aba_keywords(
                df=aba_df,
                keyword_column=keyword_column,
                detected_columns=detected_columns,
                product_profile=product_profile,
                rules=rules,
            )
        st.session_state["result_df"] = result_df
        st.session_state["rules_df"] = rules_df
        st.session_state["keyword_library_metadata"] = {
            "product_line": product_line.strip() or "未填写",
            "applicable_product": applicable_product.strip() or "未填写",
            "source": source.strip() or "ABA搜索词表",
            "analysis_date": date.today().isoformat(),
        }
        st.session_state["download_name"] = f"amazon_aba_keyword_library_{datetime.now():%Y%m%d_%H%M%S}.xlsx"

    result_df = st.session_state.get("result_df")
    rules_df = st.session_state.get("rules_df")
    keyword_library_metadata = st.session_state.get("keyword_library_metadata")
    if result_df is None or rules_df is None:
        return

    st.divider()
    st.subheader("结果预览")
    counts = summarize_counts(result_df)

    metric_cols = st.columns(4)
    metric_cols[0].metric("总关键词数量", len(result_df))
    metric_cols[1].metric("S级核心主推词", counts["S级核心主推词"])
    metric_cols[2].metric("A级重点词", counts["A级重点词"])
    metric_cols[3].metric("B级低价测试词", counts["B级低价测试词"])

    metric_cols = st.columns(4)
    metric_cols[0].metric("C级Listing埋词", counts["C级Listing埋词"])
    metric_cols[1].metric("D级不相关/否词", counts["D级不相关/否词"])
    metric_cols[2].metric("品牌/竞品词", counts["品牌/竞品词"])
    metric_cols[3].metric("待人工确认", counts["待人工确认"])

    preview_columns = [
        "原搜索词",
        "中文翻译",
        "词意图类型",
        "搜索频率排名",
        "Top1点击份额",
        "Top1转化份额",
        "转化优势",
        "产品相关性评分",
        "需求评分",
        "点击转化效率评分",
        "风险评分",
        "综合优先级评分",
        "分类结果",
        "推广优先级",
        "建议动作",
        "是否进入关键词库",
        "词库类型",
        "为什么这样分类",
        "备注",
    ]
    preview_columns = [column for column in preview_columns if column in result_df.columns]
    st.dataframe(result_df[preview_columns].head(50).fillna(""), use_container_width=True)

    excel_bytes = create_excel_bytes(result_df, rules_df, keyword_library_metadata)
    st.download_button(
        "下载 Excel（含可沉淀关键词库）",
        data=excel_bytes,
        file_name=st.session_state.get("download_name", "amazon_aba_keyword_library.xlsx"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )


if __name__ == "__main__":
    main()
