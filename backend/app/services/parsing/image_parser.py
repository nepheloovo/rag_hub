"""独立图片解析：云端 OCR + 内容理解"""
from app.services.parsing.base import ParsedDocument, ParsingError
from app.services.parsing.ocr import OCR_PROMPT, OCRService

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB


def parse_image(file_path: str, db) -> ParsedDocument:
    with open(file_path, "rb") as f:
        data = f.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise ParsingError("图片超过 10MB，请压缩后重试")

    ocr = OCRService.resolve(db)
    if not ocr:
        raise ParsingError("解析图片需要 OCR 能力；请在「模型配置」启用通义并配置 API Key")

    desc = ocr.describe_image(data, OCR_PROMPT)
    if not desc.strip():
        raise ParsingError("OCR 未返回有效内容")
    return ParsedDocument(markdown=f"# 图片内容\n\n{desc.strip()}", images=[file_path])
