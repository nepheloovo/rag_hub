"""表格解析：Excel(.xlsx/.xls) 与 CSV 转 Markdown 表格"""
import os

import pandas as pd

from app.services.parsing.base import ParsedDocument, ParsingError

MAX_ROWS_PER_SHEET = 300


def _df_to_markdown(df: pd.DataFrame) -> str:
    df = df.astype(str).fillna("")
    rows = df.values.tolist()
    if not rows:
        return ""
    header = df.columns.tolist()
    width = len(header)
    lines = [
        "| " + " | ".join(str(h) for h in header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def parse_table(file_path: str) -> ParsedDocument:
    ext = os.path.splitext(file_path)[1].lower()
    parts: list[str] = []
    warnings: list[str] = []

    if ext in (".xlsx", ".xls"):
        try:
            sheets = pd.read_excel(file_path, sheet_name=None, header=None)
        except Exception as e:  # noqa: BLE001
            raise ParsingError(f"Excel 读取失败: {e}") from e
        for sheet_name, raw in sheets.items():
            # 第一行作为表头
            df = raw
            df.columns = [f"列{i + 1}" for i in range(df.shape[1])]
            if len(df) > MAX_ROWS_PER_SHEET:
                warnings.append(f"工作表「{sheet_name}」行数过多，仅取前 {MAX_ROWS_PER_SHEET} 行")
                df = df.head(MAX_ROWS_PER_SHEET)
            md = _df_to_markdown(df)
            if md:
                parts.append(f"## 工作表：{sheet_name}\n\n{md}")
    elif ext == ".csv":
        for encoding in ("utf-8", "gbk", "latin-1"):
            try:
                df = pd.read_csv(file_path, encoding=encoding)
                break
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        else:
            raise ParsingError("CSV 读取失败：编码无法识别")
        if len(df) > MAX_ROWS_PER_SHEET:
            warnings.append(f"行数过多，仅取前 {MAX_ROWS_PER_SHEET} 行")
            df = df.head(MAX_ROWS_PER_SHEET)
        md = _df_to_markdown(df)
        if md:
            parts.append(md)
    else:
        raise ParsingError(f"不支持的表格格式: {ext}")

    if not parts:
        raise ParsingError("表格文件未解析出任何内容")
    return ParsedDocument(markdown="\n\n".join(parts), warnings=warnings)
