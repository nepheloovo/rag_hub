"""Markdown 解析：直接读取，同时提取图片引用"""
import re

from app.services.parsing.base import ParsedDocument, ParsingError

IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")


def parse_markdown(file_path: str) -> ParsedDocument:
    try:
        with open(file_path, encoding="utf-8") as f:
            text = f.read()
    except UnicodeDecodeError:
        with open(file_path, encoding="gbk", errors="replace") as f:
            text = f.read()
    except OSError as e:
        raise ParsingError(f"Markdown 读取失败: {e}") from e

    if not text.strip():
        raise ParsingError("Markdown 文件内容为空")
    images = [m for m in IMG_RE.findall(text)]
    return ParsedDocument(markdown=text, images=images)
