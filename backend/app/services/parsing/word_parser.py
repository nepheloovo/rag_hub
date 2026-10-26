"""Word(.docx) 解析：正文/标题/表格按文档顺序输出，内嵌图片 OCR 后附于文末"""
import os
import uuid
import zipfile

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.services.parsing.base import ParsedDocument, ParsingError
from app.services.parsing.ocr import OCR_PROMPT, OCRService

from app.config import settings


def _row_to_markdown(cells) -> str:
    return "| " + " | ".join(str(c or "").replace("\n", " ").strip() for c in cells) + " |"


def parse_docx(file_path: str, db) -> ParsedDocument:
    warnings: list[str] = []
    try:
        doc = Document(file_path)
    except Exception as e:  # noqa: BLE001
        raise ParsingError(f"Word 文档打开失败: {e}") from e

    parts: list[str] = []
    images: list[str] = []

    # 按文档顺序遍历段落与表格
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            para = Paragraph(child, doc)
            text = para.text.strip()
            if not text:
                continue
            style = para.style.name if para.style else ""
            if style.startswith("Heading"):
                try:
                    level = min(int(style.split()[-1]), 6)
                except ValueError:
                    level = 1
                parts.append("#" * level + " " + text)
            else:
                parts.append(text)
        elif tag == "tbl":
            table = Table(child, doc)
            rows = [[c.text for c in row.cells] for row in table.rows]
            if rows:
                header = _row_to_markdown(rows[0])
                sep = "| " + " | ".join(["---"] * len(rows[0])) + " |"
                body_rows = "\n".join(_row_to_markdown(r) for r in rows[1:])
                parts.append(f"{header}\n{sep}\n{body_rows}")

    if not parts:
        raise ParsingError("Word 文档未解析出任何文本内容")

    # 内嵌图片：从 docx 压缩包提取 media 并 OCR
    ocr = OCRService.resolve(db)
    try:
        with zipfile.ZipFile(file_path) as zf:
            for name in zf.namelist():
                if name.startswith("word/media/") and not name.endswith("/"):
                    image_bytes = zf.read(name)
                    ext = os.path.splitext(name)[1].lstrip(".") or "png"
                    fname = f"{uuid.uuid4().hex}.{ext}"
                    path = os.path.join(settings.parsed_dir, "images", fname)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "wb") as f:
                        f.write(image_bytes)
                    images.append(path)
                    if ocr:
                        try:
                            desc = ocr.describe_image(image_bytes, OCR_PROMPT)
                            parts.append(f"### 文档图片\n\n图片内容：{desc.strip()}")
                        except Exception as e:  # noqa: BLE001
                            warnings.append(f"图片 OCR 失败: {e}")
                    else:
                        parts.append("### 文档图片\n\n[图片：OCR 服务商未配置，内容未解析]")
    except zipfile.BadZipFile:
        warnings.append("文档内嵌图片提取失败（非标准压缩包）")

    return ParsedDocument(markdown="\n\n".join(parts), images=images, warnings=warnings)
