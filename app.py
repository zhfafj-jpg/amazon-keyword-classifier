from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import streamlit as st

from src.analyzer import analyze_aba_keywords, build_product_profile
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
        uploaded_file = st.file_uploader("上传 ABA 搜索词表", type=["csv", "xlsx"])

    if not uploaded_file:
        st.info("请先填写关键词库信息、粘贴产品信息，并上传 ABA 搜索词表。")
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
        if auto_keyword_column in column_names:
            default_index = column_names.index(auto_keyword_column)
            keyword_column = st.selectbox(
                "选择搜索词列",
                column_names,
                index=default_index,
                format_func=lambda column: column_labels.get(column, str(column)),
            )
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
        st.dataframe(aba_df.head(30), use_container_width=True)

    if start:
        product_profile = build_product_profile(
            product_info=product_info,
            core_terms=core_terms,
            color_terms=color_terms,
            size_terms=size_terms,
            irrelevant_terms=irrelevant_terms,
            brand_terms=brand_terms,
            rules=rules,
        )
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
        "是否否词候选",
        "命中的规则",
        "备注",
    ]
    preview_columns = [column for column in preview_columns if column in result_df.columns]
    st.dataframe(result_df[preview_columns].head(50), use_container_width=True)

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
