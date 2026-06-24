from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any

import pandas as pd


SHEET_MAP = {
    "全部ABA词": None,
    "S级核心主推词": "S级核心主推词",
    "A级重点词": "A级重点词",
    "B级低价测试词": "B级低价测试词",
    "C级Listing埋词": "C级Listing埋词",
    "D级不相关否词": "D级不相关/否词",
    "品牌竞品词": "品牌/竞品词",
    "待人工确认": "待人工确认",
}


KEYWORD_LIBRARY_COLUMNS = [
    "关键词",
    "中文翻译",
    "产品线",
    "适用产品",
    "分类结果",
    "推广优先级",
    "建议动作",
    "搜索频率排名",
    "点击占比",
    "转化份额",
    "转化优势",
    "相关性评分",
    "是否品牌词",
    "是否配件词",
    "是否否词候选",
    "来源",
    "首次发现日期",
    "最近更新日期",
    "备注",
]


PERCENT_COLUMNS = ["点击占比", "转化份额", "转化优势"]
NUMBER_COLUMNS = ["搜索频率排名", "相关性评分"]
DATE_COLUMNS = ["首次发现日期", "最近更新日期"]


def filter_sheet(df: pd.DataFrame, category: str | None) -> pd.DataFrame:
    if category is None or df.empty:
        return df.copy()
    return df.loc[df["分类结果"].astype(str).eq(category)].copy()


def build_keyword_library_df(result_df: pd.DataFrame, metadata: dict[str, Any] | None = None) -> pd.DataFrame:
    metadata = metadata or {}
    today = metadata.get("analysis_date") or date.today().isoformat()
    product_line = metadata.get("product_line") or "未填写"
    applicable_product = metadata.get("applicable_product") or "未填写"
    source = metadata.get("source") or "ABA搜索词表"

    rows: list[dict[str, Any]] = []
    for _, row in result_df.iterrows():
        rows.append(
            {
                "关键词": row.get("原搜索词", ""),
                "中文翻译": row.get("中文翻译", ""),
                "产品线": product_line,
                "适用产品": applicable_product,
                "分类结果": row.get("分类结果", ""),
                "推广优先级": row.get("推广优先级", ""),
                "建议动作": row.get("建议动作", ""),
                "搜索频率排名": row.get("搜索频率排名", ""),
                "点击占比": row.get("点击占比", ""),
                "转化份额": row.get("转化份额", ""),
                "转化优势": row.get("转化优势", ""),
                "相关性评分": row.get("相关性评分", ""),
                "是否品牌词": row.get("是否品牌词", ""),
                "是否配件词": row.get("是否配件词", ""),
                "是否否词候选": row.get("是否否词候选", ""),
                "来源": source,
                "首次发现日期": today,
                "最近更新日期": today,
                "备注": row.get("备注", ""),
            }
        )

    return pd.DataFrame(rows, columns=KEYWORD_LIBRARY_COLUMNS)


def _write_sheet(writer: pd.ExcelWriter, sheet_name: str, df: pd.DataFrame) -> None:
    safe_name = sheet_name[:31]
    df.to_excel(writer, sheet_name=safe_name, index=False)
    workbook = writer.book
    worksheet = writer.sheets[safe_name]

    header_format = workbook.add_format({"bold": True, "bg_color": "#0F766E", "font_color": "white", "border": 1})
    text_format = workbook.add_format({"text_wrap": True, "valign": "top"})
    percent_format = workbook.add_format({"num_format": "0.00%", "valign": "top"})
    number_format = workbook.add_format({"num_format": "#,##0", "valign": "top"})
    score_format = workbook.add_format({"num_format": "0", "valign": "top"})
    date_format = workbook.add_format({"num_format": "yyyy-mm-dd", "valign": "top"})
    s_format = workbook.add_format({"bg_color": "#DDF6E6"})
    d_format = workbook.add_format({"bg_color": "#FFE4E1"})

    for col_idx, column in enumerate(df.columns):
        worksheet.write(0, col_idx, column, header_format)
        sample_values = [str(column), *df[column].astype(str).head(80).tolist()] if not df.empty else [str(column)]
        width = min(max(len(value) for value in sample_values) + 2, 46)
        fmt = text_format
        if column in PERCENT_COLUMNS:
            fmt = percent_format
        elif column == "搜索频率排名":
            fmt = number_format
        elif column == "相关性评分":
            fmt = score_format
        elif column in DATE_COLUMNS:
            fmt = date_format
        worksheet.set_column(col_idx, col_idx, width, fmt)

    worksheet.freeze_panes(1, 0)
    if len(df.columns) > 0:
        worksheet.autofilter(0, 0, max(len(df), 1), len(df.columns) - 1)

    if "分类结果" in df.columns and not df.empty:
        category_col = df.columns.get_loc("分类结果")
        worksheet.conditional_format(
            1,
            category_col,
            len(df),
            category_col,
            {"type": "text", "criteria": "containing", "value": "S级", "format": s_format},
        )
        worksheet.conditional_format(
            1,
            category_col,
            len(df),
            category_col,
            {"type": "text", "criteria": "containing", "value": "D级", "format": d_format},
        )


def create_excel_bytes(
    result_df: pd.DataFrame,
    rules_df: pd.DataFrame,
    keyword_library_metadata: dict[str, Any] | None = None,
) -> bytes:
    output = BytesIO()
    keyword_library_df = build_keyword_library_df(result_df, keyword_library_metadata)
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        for sheet_name, category in SHEET_MAP.items():
            _write_sheet(writer, sheet_name, filter_sheet(result_df, category))
        _write_sheet(writer, "可沉淀关键词库", keyword_library_df)
        _write_sheet(writer, "规则说明", rules_df)
    output.seek(0)
    return output.read()


def summarize_counts(result_df: pd.DataFrame) -> dict[str, int]:
    categories = [
        "S级核心主推词",
        "A级重点词",
        "B级低价测试词",
        "C级Listing埋词",
        "D级不相关/否词",
        "品牌/竞品词",
        "待人工确认",
    ]
    if result_df.empty:
        return {category: 0 for category in categories}
    return {category: int((result_df["分类结果"] == category).sum()) for category in categories}
