from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

from src.classifier import analyze_keywords
from src.exporter import create_excel_bytes, summarize_counts
from src.loader import detect_columns, list_excel_sheets, load_rules, read_uploaded_file


BASE_DIR = Path(__file__).parent
RULE_PATH = BASE_DIR / "config" / "product_rules.yaml"


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
        st.info("本地调试模式：未设置 Streamlit secrets 密码，已自动放行。")
        return True

    if st.session_state.get("authenticated"):
        return True

    st.title("Amazon Keyword Classifier")
    password = st.text_input("请输入访问密码", type="password")
    if password:
        if password == expected_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("密码不正确")
    return False


def render_detected_columns(detected: dict[str, str]) -> None:
    labels = {
        "keyword": "关键词列",
        "aba_rank": "ABA排名",
        "click_share": "点击占比",
        "conversion_share": "转化份额",
        "clicks": "点击量",
        "spend": "花费",
        "orders": "订单",
        "sales": "销售额",
        "acos": "ACOS",
        "ctr": "CTR",
        "cpc": "CPC",
    }
    with st.expander("自动识别到的列", expanded=False):
        if not detected:
            st.write("暂未识别到标准列名。")
            return
        for key, column in detected.items():
            st.write(f"- {labels.get(key, key)}：`{column}`")


def main() -> None:
    st.set_page_config(page_title="Amazon Keyword Classifier", layout="wide")

    if not password_gate():
        return

    rules = load_rules(RULE_PATH)
    product_lines = list(rules["product_lines"].keys())

    st.title("Amazon Keyword Classifier")
    st.caption("上传 ABA 搜索词表、广告搜索词表或关键词词库表，按产品线规则自动分类并导出 Excel。")

    left, right = st.columns([0.36, 0.64], gap="large")
    with left:
        uploaded_file = st.file_uploader("上传文件", type=["xlsx", "csv"])
        product_line = st.selectbox("选择产品线", product_lines)
        analysis_mode = st.selectbox("选择分析模式", ["ABA选词", "广告搜索词", "综合分析"], index=2)

    if not uploaded_file:
        st.info("请先上传 .xlsx 或 .csv 文件。")
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
        df = read_uploaded_file(uploaded_file, sheet_name=sheet_name)
    except Exception as exc:
        st.error(f"读取文件失败：{exc}")
        st.stop()

    if df.empty:
        st.warning("上传的表格没有可分析的数据。")
        st.stop()

    detected_columns = detect_columns(df)
    column_names = list(df.columns)
    auto_keyword_col = detected_columns.get("keyword")

    with left:
        if auto_keyword_col and auto_keyword_col in column_names:
            default_index = column_names.index(auto_keyword_col)
            keyword_column = st.selectbox("选择关键词列", column_names, index=default_index)
        else:
            st.warning("未能自动识别关键词列，请手动选择。")
            keyword_column = st.selectbox("选择关键词列", column_names)

        start = st.button("开始分析", type="primary", use_container_width=True)

    with right:
        st.subheader("数据预览")
        st.dataframe(df.head(50), use_container_width=True)
        render_detected_columns(detected_columns)

    if start:
        with st.spinner("正在分类关键词..."):
            result_df, hit_df = analyze_keywords(
                df=df,
                keyword_column=keyword_column,
                product_line=product_line,
                rules=rules,
                analysis_mode=analysis_mode,
                detected_columns=detected_columns,
            )
            st.session_state["result_df"] = result_df
            st.session_state["hit_df"] = hit_df
            st.session_state["download_name"] = (
                f"amazon_keyword_classified_{product_line.replace('/', '_')}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
            )

    result_df = st.session_state.get("result_df")
    hit_df = st.session_state.get("hit_df")
    if result_df is None or hit_df is None:
        return

    st.divider()
    st.subheader("结果预览")

    metric_cols = st.columns(4)
    summary = summarize_counts(result_df)
    metric_cols[0].metric("关键词数量", len(result_df))
    metric_cols[1].metric("核心主推词", int((result_df["分类结果"] == "核心主推词").sum()) if not result_df.empty else 0)
    metric_cols[2].metric("否定建议", int(result_df["分类结果"].astype(str).str.contains("否定").sum()) if not result_df.empty else 0)
    metric_cols[3].metric("待确认", int((result_df["分类结果"] == "待人工确认").sum()) if not result_df.empty else 0)

    preview_cols = [
        "原关键词",
        "产品线",
        "分类结果",
        "标签",
        "匹配到的规则",
        "ABA排名",
        "点击占比",
        "转化份额",
        "点击量",
        "订单",
        "ACOS",
        "建议动作",
        "备注",
    ]
    preview_cols = [column for column in preview_cols if column in result_df.columns]
    st.dataframe(result_df[preview_cols].head(200), use_container_width=True)

    with st.expander("分类统计", expanded=True):
        st.dataframe(summary, use_container_width=True, hide_index=True)

    excel_bytes = create_excel_bytes(result_df, hit_df)
    st.download_button(
        label="下载 Excel",
        data=excel_bytes,
        file_name=st.session_state.get("download_name", "amazon_keyword_classified.xlsx"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )


if __name__ == "__main__":
    main()
