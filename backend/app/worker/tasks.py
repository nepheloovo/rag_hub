"""Celery 任务：文档解析 → 按知识库分块策略切分 → embedding → 向量入库"""
import uuid

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import Chunk, Document, KnowledgeBase
from app.services.chunking import split_markdown
from app.services.embedding import get_embedding_service
from app.services.files import resolve_stored_path
from app.services.parsing.base import ParsingError, parse_file

EMBED_BATCH_SIZE = 64


def _refresh_kb_status(db, kb_id: str) -> None:
    """知识库状态机：有文档在解析中 → indexing；否则 → available"""
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        return
    busy = (
        db.query(Document)
        .filter(Document.kb_id == kb_id, Document.status.in_(("pending", "parsing")))
        .count()
    )
    kb.status = "indexing" if busy > 0 else "available"
    db.commit()


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
        kb = db.get(KnowledgeBase, doc.kb_id)
        strategy = kb.chunk_strategy if kb and kb.chunk_strategy else "smart"

        doc.status = "parsing"
        doc.error = ""
        _refresh_kb_status(db, doc.kb_id)

        # 1. 解析为统一 Markdown
        parsed = parse_file(resolve_stored_path(doc.file_path), doc.file_type, db)

        # 2. 按知识库分块策略切分
        chunks = split_markdown(
            parsed.markdown,
            strategy=strategy,
            chunk_size=settings_chunk_size(),
            db=db,
        )
        if not chunks:
            raise ParsingError("文档未切分出任何分块")

        # 3. embedding：使用知识库绑定的模型（未绑定回退全局默认/伪向量）
        embed_service = get_embedding_service(db, (kb.embedding_ref if kb else None) or None)
        vectors: list[list[float]] = []
        for i in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = [c["content"] for c in chunks[i : i + EMBED_BATCH_SIZE]]
            vectors.extend(embed_service.embed_texts(batch))
        if len(vectors) != len(chunks):
            raise ParsingError("embedding 返回数量与分块数不一致")

        # 4. 清理旧分块并入库（父子分块：child 记录 parent_group）
        db.query(Chunk).filter(Chunk.doc_id == doc_id).delete()
        stored = 0
        for chunk, vector in zip(chunks, vectors):
            content = (chunk.get("content") or "").strip()
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
                        "page": chunk.get("page", 0),
                        "heading": chunk.get("heading", ""),
                        "kind": chunk.get("kind", "chunk"),
                        "parent_group": chunk.get("parent_group"),
                        "strategy": strategy,
                        "embedding_model": embed_service.model,
                    },
                    embedding=vector,
                )
            )
            stored += 1

        doc.status = "done"
        doc.chunk_count = stored
        db.commit()  # 先提交文档状态，再刷新知识库状态（autoflush 关闭）
        _refresh_kb_status(db, doc.kb_id)
        return {"doc_id": doc_id, "status": "done", "chunks": stored, "strategy": strategy}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        doc = db.get(Document, doc_id)
        if doc:
            doc.status = "failed"
            doc.error = str(e)[:2000]
            db.commit()
        _refresh_kb_status(db, doc.kb_id)
        raise
    finally:
        db.close()


def settings_chunk_size() -> int:
    from app.config import settings

    return settings.chunk_size
