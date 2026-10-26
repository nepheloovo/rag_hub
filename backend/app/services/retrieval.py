"""检索服务：向量召回（pgvector 余弦）→ Rerank 精排（可降级）"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Chunk
from app.services.embedding import get_embedding_service
from app.services.rerank import RerankService


class RetrievedChunk:
    def __init__(self, chunk: Chunk, score: float):
        self.chunk = chunk
        self.score = score


class RetrievalOutcome:
    def __init__(
        self,
        chunks: list[RetrievedChunk],
        embedding_model: str,
        embedding_is_fake: bool,
        rerank_model: str = "",
        rerank_used: bool = False,
        embedding_tokens: int = 0,
        rerank_tokens: int = 0,
    ):
        self.chunks = chunks
        self.embedding_model = embedding_model
        self.embedding_is_fake = embedding_is_fake
        self.rerank_model = rerank_model
        self.rerank_used = rerank_used
        self.embedding_tokens = embedding_tokens
        self.rerank_tokens = rerank_tokens


def retrieve(db: Session, kb_ids: list[str], query: str) -> RetrievalOutcome:
    """kb_ids 支持多知识库联合召回"""
    embed_service = get_embedding_service(db)
    query_vec, embed_tokens = embed_service.embed_texts_with_usage([query])
    query_vec = query_vec[0]

    if not kb_ids:
        return RetrievalOutcome(
            chunks=[],
            embedding_model=embed_service.model,
            embedding_is_fake=embed_service.is_fake,
            embedding_tokens=embed_tokens,
        )

    # 1. 向量召回 top-k（多库联合）
    rows = db.execute(
        text(
            """
            SELECT id, doc_id, content, metadata, 1 - (embedding <=> :q) AS sim
            FROM chunks
            WHERE kb_id = ANY(:kb_ids) AND embedding IS NOT NULL
            ORDER BY embedding <=> :q
            LIMIT :k
            """
        ),
        {"q": str(query_vec), "kb_ids": kb_ids, "k": settings.retrieval_top_k},
    ).fetchall()

    # 2. Rerank 精排（失败/未配置自动降级）
    rerank_model = ""
    rerank_used = False
    rerank_tokens = 0
    ranked_rows = []
    if rows:
        rerank_service = RerankService.resolve(db)
        if rerank_service:
            rerank_model = rerank_service.model
            documents = [r[1] for r in rows]
            try:
                result = rerank_service.rerank(query, documents, settings.rerank_top_n)
                rerank_used = True
                rerank_tokens = result.total_tokens
                ranked = sorted(result.ranked, key=lambda x: x["score"], reverse=True)
                for item in ranked:
                    idx = item["index"]
                    if 0 <= idx < len(rows):
                        ranked_rows.append((rows[idx], item["score"]))
            except Exception:  # noqa: BLE001 —— 任何异常降级为纯向量召回
                ranked_rows = [(r, r[4]) for r in rows]
        if not rerank_service:
            ranked_rows = [(r, r[4]) for r in rows]

    chunks = []
    for row, score in ranked_rows:
        chunk_id, doc_id, content, metadata, _sim = row
        meta = metadata or {}
        chunks.append(
            RetrievedChunk(
                chunk=Chunk(id=chunk_id, doc_id=doc_id, content=content, metadata_=meta),
                score=float(score),
            )
        )

    return RetrievalOutcome(
        chunks=chunks,
        embedding_model=embed_service.model,
        embedding_is_fake=embed_service.is_fake,
        rerank_model=rerank_model if rerank_used else "",
        rerank_used=rerank_used,
        embedding_tokens=embed_tokens,
        rerank_tokens=rerank_tokens,
    )
