from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from .utils import COLUMN_ALIASES, KEYWORD_ALIASES, find_best_column


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        inside = value[1:-1].strip()
        if not inside:
            return []
        items: list[str] = []
        current = ""
        quote: Optional[str] = None
        for char in inside:
            if char in {'"', "'"}:
                quote = None if quote == char else char
                current += char
            elif char == "," and quote is None:
                items.append(current.strip().strip('"').strip("'"))
                current = ""
            else:
                current += char
        if current:
            items.append(current.strip().strip('"').strip("'"))
        return items
    if value.startswith("{") or value.startswith("["):
        return json.loads(value)
    return value.strip('"').strip("'")


def _simple_yaml_load(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
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
    if not isinstance(data, dict) or "product_lines" not in data:
        raise ValueError("规则配置文件格式不正确，需要包含 product_lines。")
    return data


def list_excel_sheets(uploaded_file) -> list[str]:
    uploaded_file.seek(0)
    excel = pd.ExcelFile(uploaded_file, engine="openpyxl")
    uploaded_file.seek(0)
    return excel.sheet_names


def _read_csv_bytes(raw: bytes) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "gb18030", "latin1"]
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return pd.read_csv(io.StringIO(raw.decode(encoding)))
        except Exception as exc:  # pragma: no cover - keeps UI resilient.
            last_error = exc
    raise ValueError(f"CSV 文件无法识别编码：{last_error}")


def read_uploaded_file(uploaded_file, sheet_name: str | None = None) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    uploaded_file.seek(0)

    if name.endswith(".csv"):
        df = _read_csv_bytes(uploaded_file.read())
    elif name.endswith(".xlsx"):
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name or 0, engine="openpyxl")
    else:
        raise ValueError("仅支持 .xlsx 和 .csv 文件。")

    df.columns = [str(column).strip() for column in df.columns]
    df = df.dropna(how="all")
    return df


def detect_columns(df: pd.DataFrame) -> dict[str, str]:
    detected: dict[str, str] = {}
    keyword_col = find_best_column(df.columns, KEYWORD_ALIASES)
    if keyword_col:
        detected["keyword"] = keyword_col

    for canonical, aliases in COLUMN_ALIASES.items():
        column = find_best_column(df.columns, aliases)
        if column:
            detected[canonical] = column
    return detected
