"""PDF 解析：PyMuPDF 提取文字/表格/图片；扫描件走云端 OCR"""
import os
import re
import uuid

import fitz

from app.config import settings
from app.services.parsing.base import ParsedDocument, ParsingError
from app.services.parsing.ocr import OCR_PROMPT, OCRService


def _table_to_markdown(rows: list) -> str:
    if not rows:
        return ""
    rows = [[str(c or "").replace("\n", " ").strip() for c in row] for row in rows]
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header = "| " + " | ".join(rows[0]) + " |"
    sep = "| " + " | ".join(["---"] * width) + " |"
    body = "\n".join("| " + " | ".join(r) + " |" for r in rows[1:])
    return f"{header}\n{sep}\n{body}"


def _save_image(image_bytes: bytes, ext: str) -> str:
    fname = f"{uuid.uuid4().hex}.{ext or 'png'}"
    path = os.path.join(settings.parsed_dir, "images", fname)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(image_bytes)
    return path


def _describe_image(image_bytes: bytes, ocr: OCRService | None) -> tuple[str, str]:
    """返回 (描述文本, 保存路径)；OCR 不可用时返回占位说明"""
    path = _save_image(image_bytes, "png")
    if ocr:
        try:
            desc = ocr.describe_image(image_bytes, OCR_PROMPT)
            return desc.strip(), path
        except Exception as e:  # noqa: BLE001
            return f"[图片 OCR 失败: {e}]", path
    return "[图片：OCR 服务商未配置，内容未解析]", path


def _extract_page_images(page, doc) -> list[bytes]:
    images = []
    for img in page.get_images(full=True):
        try:
            images.append(doc.extract_image(img[0])["image"])
        except Exception:  # noqa: BLE001
            continue
    return images


def parse_pdf(file_path: str, db) -> ParsedDocument:
    warnings: list[str] = []
    doc = fitz.open(file_path)
    if doc.page_count == 0:
        doc.close()
        raise ParsingError("PDF 无页面内容")

    ocr = OCRService.resolve(db)
    parts: list[str] = []
    images: list[str] = []
    total_chars = 0

    for pno in range(doc.page_count):
        page = doc[pno]
        text = page.get_text("text").strip()
        total_chars += len(text)

        page_parts = []
        if text:
            page_parts.append(text)

        # 表格
        try:
            tabs = page.find_tables()
            for tab in tabs.tables:
                md_table = _table_to_markdown(tab.extract())
                if md_table:
                    page_parts.append(md_table)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"第 {pno + 1} 页表格提取失败: {e}")

        # 内嵌图片：OCR 描述后随页内容参与检索
        for idx, image_bytes in enumerate(_extract_page_images(page, doc)):
            desc, path = _describe_image(image_bytes, ocr)
            images.append(path)
            page_parts.append(f"![图片](images/{os.path.basename(path)})\n\n图片内容：{desc}")

        parts.append(f"<!-- 第 {pno + 1} 页 -->\n" + "\n\n".join(page_parts))

    # 扫描件判定
    if total_chars / doc.page_count < settings.scanned_pdf_min_chars_per_page:
        if not ocr:
            doc.close()
            raise ParsingError(
                "PDF 为扫描件且无文字层，需要 OCR 解析；请在「模型配置」启用通义并配置 API Key"
            )
        warnings.append("检测为扫描件，启用整页 OCR")
        ocr_parts = []
        for pno in range(doc.page_count):
            page = doc[pno]
            pix = page.get_pixmap(dpi=150)
            image_bytes = pix.tobytes("png")
            try:
                text = ocr.describe_image(image_bytes, OCR_PROMPT)
            except Exception as e:  # noqa: BLE001
                warnings.append(f"第 {pno + 1} 页 OCR 失败: {e}")
                text = ""
            ocr_parts.append(f"<!-- 第 {pno + 1} 页(OCR) -->\n{text}")
        parts = ocr_parts

    doc.close()
    return ParsedDocument(markdown="\n\n".join(parts), images=images, warnings=warnings)


def sniff_pdf_needs_ocr(file_path: str) -> bool:
    """仅检测：PDF 是否需要 OCR（供测试/预检使用）"""
    doc = fitz.open(file_path)
    page_count = doc.page_count
    if page_count == 0:
        doc.close()
        return False
    total = sum(len(doc[p].get_text("text").strip()) for p in range(page_count))
    doc.close()
    return total / page_count < settings.scanned_pdf_min_chars_per_page
