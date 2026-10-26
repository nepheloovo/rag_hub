"""分块：优先按 Markdown 标题切分，段内按长度二次切分"""
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app.config import settings


def split_markdown(
    markdown: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[dict]:
    """返回 [{"content": str, "heading": str}]"""
    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = chunk_overlap or settings.chunk_overlap

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=["\n\n", "\n", "。", "，", " ", ""]
    )
    chunks: list[dict] = []

    try:
        md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
            strip_headers=False,
        )
        sections = md_splitter.split_text(markdown)
    except Exception:  # noqa: BLE001
        sections = []

    for sec in sections:
        heading = sec.metadata.get("h1") or sec.metadata.get("h2") or sec.metadata.get("h3") or ""
        for piece in text_splitter.split_text(sec.page_content):
            if piece.strip():
                chunks.append({"content": piece, "heading": heading})

    if not chunks:
        for piece in text_splitter.split_text(markdown):
            if piece.strip():
                chunks.append({"content": piece, "heading": ""})
    return chunks
