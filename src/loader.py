from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .utils import ABA_COLUMN_ALIASES, ABA_HEADER_HINTS, find_best_column, normalize_column_name


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        inside = value[1:-1].strip()
        if not inside:
            return []
        return [item.strip().strip('"').strip("'") for item in inside.split(",")]
    return value.strip('"').strip("'")


def _simple_yaml_load(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip() or ":" not in line:
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, value = line.strip().split(":", 1)
        key = key.strip().strip('"').strip("'")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value.strip():
            parent[key] = _parse_scalar(value)
        else:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
    return root


def load_rules(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
    except Exception:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = _simple_yaml_load(text)
    if not isinstance(data, dict):
        raise ValueError("规则配置文件格式不正确。")
    return data


def list_excel_sheets(uploaded_file) -> list[str]:
    uploaded_file.seek(0)
    excel = pd.ExcelFile(uploaded_file, engine="openpyxl")
    uploaded_file.seek(0)
    return excel.sheet_names


def _csv_text_score(text: str) -> int:
    sample = normalize_column_name(text[:20000])
    score = 0
    for alias in ABA_HEADER_HINTS:
        normalized_alias = normalize_column_name(alias)
        if normalized_alias and normalized_alias in sample:
            score += 1
    return score


def _decode_csv(raw: bytes) -> str:
    encodings = ["gb18030", "utf-8-sig", "utf-8", "latin1"]
    candidates: list[tuple[str, str, int]] = []
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        score = _csv_text_score(text)
        candidates.append((encoding, text, score))
        if score > 0:
            return text

    for encoding, text, _ in candidates:
        if encoding in {"utf-8-sig", "utf-8"}:
            return text
    if candidates:
        return candidates[0][1]
    return raw.decode("utf-8", errors="replace")


def _read_csv_rows(uploaded_file) -> list[list[Any]]:
    uploaded_file.seek(0)
    text = _decode_csv(uploaded_file.read())
    return [
        row
        for row in csv.reader(
            io.StringIO(text),
            delimiter=",",
            quotechar='"',
            doublequote=True,
            skipinitialspace=False,
            strict=False,
        )
    ]


def _read_excel_rows(uploaded_file, sheet_name: str | None) -> list[list[Any]]:
    uploaded_file.seek(0)
    frame = pd.read_excel(
        uploaded_file,
        sheet_name=sheet_name or 0,
        header=None,
        dtype=object,
        engine="openpyxl",
    )
    frame = frame.where(pd.notnull(frame), "")
    return frame.values.tolist()


def _row_values(row: list[Any]) -> list[str]:
    return [str(value).strip() for value in row if str(value).strip() and str(value).lower() != "nan"]


def _score_header_row(row: list[Any]) -> int:
    cells = [normalize_column_name(value) for value in row if str(value).strip()]
    if not cells:
        return 0
    score = 0
    for alias in ABA_HEADER_HINTS:
        normalized_alias = normalize_column_name(alias)
        if normalized_alias in cells:
            score += 3
        elif any(normalized_alias and normalized_alias in cell for cell in cells):
            score += 1

    keyword_aliases = [normalize_column_name(alias) for alias in ABA_COLUMN_ALIASES["keyword"]]
    metric_aliases = [
        normalize_column_name(alias)
        for key in ["search_frequency_rank", "click_share", "conversion_share"]
        for alias in ABA_COLUMN_ALIASES[key]
    ]
    has_keyword = any(alias in cells for alias in keyword_aliases)
    has_metric = any(alias in cells for alias in metric_aliases)
    if has_keyword:
        score += 8
    if has_metric:
        score += 5
    return score


def find_aba_header_row(rows: list[list[Any]], scan_rows: int = 50) -> tuple[int, bool, int]:
    best_index = 0
    best_score = -1
    for index, row in enumerate(rows[:scan_rows]):
        score = _score_header_row(row)
        if score > best_score:
            best_index = index
            best_score = score

    if best_score >= 8:
        return best_index, True, best_score

    for index, row in enumerate(rows):
        if _row_values(row):
            return index, False, max(best_score, 0)
    return 0, False, 0


def _dedupe_headers(headers: list[str]) -> list[str]:
    output: list[str] = []
    counts: dict[str, int] = {}
    for index, header in enumerate(headers):
        name = str(header or "").strip()
        if not name or name.lower() == "nan":
            name = f"Column {index + 1}"
        if name in counts:
            counts[name] += 1
            name = f"{name}_{counts[name]}"
        else:
            counts[name] = 1
        output.append(name)
    return output


def _rows_to_dataframe(rows: list[list[Any]], header_index: int) -> pd.DataFrame:
    header_row = rows[header_index] if rows else []
    header_width = max(len(header_row), 1)
    headers = _dedupe_headers([str(value).strip() for value in header_row])

    records: list[list[Any]] = []
    bad_rows: list[str] = []
    for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not _row_values(row):
            continue
        if len(row) != header_width:
            preview = " | ".join(str(value) for value in row[:8])
            bad_rows.append(f"第 {offset} 行：解析到 {len(row)} 列，表头为 {header_width} 列。预览：{preview}")
            continue
        records.append(list(row))

    if bad_rows:
        details = "\n".join(bad_rows[:10])
        raise ValueError(
            "CSV/Excel 数据行列数与真实表头不一致，已停止分析，避免生成错位结果。\n"
            "请检查商品标题等字段中的逗号和双引号是否按 CSV 标准正确转义。\n"
            f"{details}"
        )

    frame = pd.DataFrame(records, columns=headers)
    frame = frame.dropna(how="all")
    return frame


def read_aba_file(uploaded_file, sheet_name: str | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        rows = _read_csv_rows(uploaded_file)
    elif name.endswith(".xlsx"):
        rows = _read_excel_rows(uploaded_file, sheet_name)
    else:
        raise ValueError("仅支持 .csv 和 .xlsx 文件。")

    header_index, header_detected, header_score = find_aba_header_row(rows)
    frame = _rows_to_dataframe(rows, header_index)
    detected_columns = detect_aba_columns(frame)
    keyword_column = detected_columns.get("keyword")
    if keyword_column:
        frame = frame[frame[keyword_column].astype(str).str.strip().ne("")]

    info = {
        "header_row_index": header_index,
        "header_row_number": header_index + 1,
        "header_detected": header_detected,
        "header_score": header_score,
        "detected_columns": detected_columns,
    }
    return frame.reset_index(drop=True), info


def detect_aba_columns(df: pd.DataFrame) -> dict[str, str]:
    detected: dict[str, str] = {}
    for canonical, aliases in ABA_COLUMN_ALIASES.items():
        column = find_best_column(df.columns, aliases)
        if column:
            detected[canonical] = column
    return detected


def build_column_choice_labels(df: pd.DataFrame) -> dict[str, str]:
    labels: dict[str, str] = {}
    for column in df.columns:
        examples = [
            str(value).strip()
            for value in df[column].dropna().astype(str).head(8).tolist()
            if str(value).strip() and str(value).lower() != "nan"
        ][:3]
        suffix = ", ".join(examples)
        labels[column] = f"{column} | {suffix}" if suffix else str(column)
    return labels
