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


def common_embedding_ref(db: Session, kb_ids: list[str]) -> str | None:
    """多知识库共用的 embedding 引用：全部一致时返回该 ref，否则返回 None（全局默认）"""
    from app.models import KnowledgeBase

    if not kb_ids:
        return None
    refs = {kb.embedding_ref or "" for kb in db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(kb_ids)).all()}
    ref = refs.pop() if len(refs) == 1 else ""
    return ref or None


def retrieve(db: Session, kb_ids: list[str], query: str, embedding_ref: str | None = None) -> RetrievalOutcome:
    """kb_ids 支持多知识库联合召回；embedding_ref 显式指定查询向量模型（与索引一致）"""
    embed_service = get_embedding_service(db, embedding_ref)
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
    parent_groups = set()
    for row, score in ranked_rows:
        chunk_id, doc_id, content, metadata, _sim = row
        meta = metadata or {}
        group = meta.get("parent_group")
        if meta.get("kind") == "child" and group:
            parent_groups.add((doc_id, group))
        chunks.append(
            RetrievedChunk(
                chunk=Chunk(id=chunk_id, doc_id=doc_id, content=content, metadata_=meta),
                score=float(score),
            )
        )

    # 父子分块展开：child 命中时返回所在 parent 的完整内容
    if parent_groups:
        from sqlalchemy import text as _text

        parents: dict[tuple, str] = {}
        for doc_id, group in parent_groups:
            row = db.execute(
                _text(
                    "SELECT content FROM chunks "
                    "WHERE doc_id = :doc_id AND metadata->>'parent_group' = :g AND metadata->>'kind' = 'parent' LIMIT 1"
                ),
                {"doc_id": doc_id, "g": group},
            ).first()
            if row:
                parents[(doc_id, group)] = row[0]
        for item in chunks:
            group = (item.chunk.metadata_ or {}).get("parent_group")
            if (item.chunk.metadata_ or {}).get("kind") == "child" and (item.chunk.doc_id, group) in parents:
                item.chunk.content = parents[(item.chunk.doc_id, group)]

    return RetrievalOutcome(
        chunks=chunks,
        embedding_model=embed_service.model,
        embedding_is_fake=embed_service.is_fake,
        rerank_model=rerank_model if rerank_used else "",
        rerank_used=rerank_used,
        embedding_tokens=embed_tokens,
        rerank_tokens=rerank_tokens,
    )
