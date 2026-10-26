"""Celery 任务：文档解析 → 分块 → embedding → 向量入库"""
import re
import uuid

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import Chunk, Document
from app.services.chunking import split_markdown
from app.services.embedding import get_embedding_service
from app.services.parsing.base import ParsingError, parse_file

EMBED_BATCH_SIZE = 64
PAGE_RE = re.compile(r"<!--\s*第\s*(\d+)\s*页(?:\(OCR\))?\s*-->")


def _extract_page(text: str) -> tuple[str, int]:
    """从分块文本中提取页码标注并移除注释"""
    page = 0
    match = PAGE_RE.search(text)
    if match:
        page = int(match.group(1))
        text = PAGE_RE.sub("", text).strip()
    return text, page


@celery_app.task(
    name="app.worker.tasks.parse_document",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def parse_document(self, doc_id: str) -> dict:
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        if not doc:
            return {"doc_id": doc_id, "status": "missing"}
        doc.status = "parsing"
        doc.error = ""
        db.commit()

        # 1. 解析为统一 Markdown
        parsed = parse_file(doc.file_path, doc.file_type, db)

        # 2. 分块
        chunks = split_markdown(parsed.markdown)
        if not chunks:
            raise ParsingError("文档未切分出任何分块")

        # 3. embedding（无真实模型时自动降级为伪向量）
        embed_service = get_embedding_service(db)
        vectors: list[list[float]] = []
        for i in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = [c["content"] for c in chunks[i : i + EMBED_BATCH_SIZE]]
            vectors.extend(embed_service.embed_texts(batch))
        if len(vectors) != len(chunks):
            raise ParsingError("embedding 返回数量与分块数不一致")

        # 4. 清理旧分块并入库
        db.query(Chunk).filter(Chunk.doc_id == doc_id).delete()
        for chunk, vector in zip(chunks, vectors):
            content, page = _extract_page(chunk["content"])
            if not content:
                continue
            db.add(
                Chunk(
                    id=uuid.uuid4().hex,
                    kb_id=doc.kb_id,
                    doc_id=doc_id,
                    content=content,
                    metadata_={
                        "source": doc.filename,
                        "page": page,
                        "heading": chunk["heading"],
                        "embedding_model": embed_service.model,
                    },
                    embedding=vector,
                )
            )

        doc.status = "done"
        doc.chunk_count = len(chunks)
        db.commit()
        return {"doc_id": doc_id, "status": "done", "chunks": len(chunks)}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        doc = db.get(Document, doc_id)
        if doc:
            doc.status = "failed"
            doc.error = str(e)[:2000]
            db.commit()
        raise
    finally:
        db.close()
