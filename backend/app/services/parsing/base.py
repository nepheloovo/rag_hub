"""解析模块公共定义与入口"""
from dataclasses import dataclass, field


class ParsingError(Exception):
    """解析失败（可读信息写入文档 error 字段）"""


@dataclass
class ParsedDocument:
    """统一解析产物：Markdown 文本 + 提取的图片路径 + 告警"""

    markdown: str
    images: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_file(file_path: str, file_type: str, db) -> ParsedDocument:
    """按文件类型分派解析器"""
    from app.services.parsing import image_parser, markdown_parser, pdf_parser, table_parser, word_parser

    if file_type == "pdf":
        return pdf_parser.parse_pdf(file_path, db)
    if file_type == "word":
        return word_parser.parse_docx(file_path, db)
    if file_type == "markdown":
        return markdown_parser.parse_markdown(file_path)
    if file_type == "image":
        return image_parser.parse_image(file_path, db)
    if file_type == "table":
        return table_parser.parse_table(file_path)
    raise ParsingError(f"不支持的文件类型: {file_type}")
