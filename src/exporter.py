from __future__ import annotations

from io import BytesIO
from typing import Iterable

import pandas as pd


SHEET_MAP = {
    "全部关键词": None,
    "核心主推词": "核心主推词",
    "低价测试词": "低价测试词",
    "Listing埋词": "Listing埋词",
    "词组否定建议": "词组否定建议",
    "精准否定建议": "精准否定建议",
    "品牌词/竞品词": "品牌词/竞品词",
    "待人工确认": "待人工确认",
}


def _filter_sheet(df: pd.DataFrame, category: str | None) -> pd.DataFrame:
    if category is None or df.empty:
        return df
    mask = (df["分类结果"].astype(str) == category) | df["标签"].astype(str).str.contains(category, na=False)
    return df.loc[mask].copy()


def _safe_sheet_name(name: str) -> str:
    return name.replace("/", "_")[:31]


def _write_sheet(writer: pd.ExcelWriter, sheet_name: str, df: pd.DataFrame) -> None:
    safe_name = _safe_sheet_name(sheet_name)
    df.to_excel(writer, sheet_name=safe_name, index=False)
    workbook = writer.book
    worksheet = writer.sheets[safe_name]

    header_format = workbook.add_format(
        {"bold": True, "bg_color": "#0F766E", "font_color": "white", "border": 1}
    )
    text_format = workbook.add_format({"text_wrap": True, "valign": "top"})
    warning_format = workbook.add_format({"bg_color": "#FFE4E1"})
    core_format = workbook.add_format({"bg_color": "#DDF6E6"})

    for col_idx, column in enumerate(df.columns):
        worksheet.write(0, col_idx, column, header_format)
        sample_values = [str(column), *df[column].astype(str).head(80).tolist()]
        width = min(max(len(value) for value in sample_values) + 2, 42)
        worksheet.set_column(col_idx, col_idx, width, text_format)

    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, max(len(df), 1), max(len(df.columns) - 1, 0))

    if "分类结果" in df.columns and len(df) > 0:
        category_col = df.columns.get_loc("分类结果")
        first_row = 1
        last_row = len(df)
        worksheet.conditional_format(
            first_row,
            category_col,
            last_row,
            category_col,
            {"type": "text", "criteria": "containing", "value": "否定", "format": warning_format},
        )
        worksheet.conditional_format(
            first_row,
            category_col,
            last_row,
            category_col,
            {"type": "text", "criteria": "containing", "value": "核心主推词", "format": core_format},
        )


def create_excel_bytes(result_df: pd.DataFrame, hit_df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        for sheet_name, category in SHEET_MAP.items():
            sheet_df = _filter_sheet(result_df, category)
            _write_sheet(writer, sheet_name, sheet_df)
        _write_sheet(writer, "规则命中说明", hit_df)
    output.seek(0)
    return output.read()


def summarize_counts(result_df: pd.DataFrame) -> pd.DataFrame:
    if result_df.empty:
        return pd.DataFrame(columns=["分类结果", "数量"])
    return (
        result_df.groupby("分类结果", dropna=False)
        .size()
        .reset_index(name="数量")
        .sort_values("数量", ascending=False)
    )
