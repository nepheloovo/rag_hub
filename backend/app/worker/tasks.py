"""Celery 任务：文档解析 → 按知识库分块策略切分 → embedding → 向量入库"""
import uuid

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import Chunk, Document, KnowledgeBase
from app.services.chunk_enhancement import chunk_index_text, enhance_chunks
from app.services.chunking import normalize_chunk_config, split_markdown
from app.services.embedding import get_embedding_service
from app.services.files import resolve_stored_path
from app.services.observability import TraceRecorder, explain_error
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
    """文档解析 → 分块 → Embedding → 入库；每个阶段写入可观测 Trace"""
    db = SessionLocal()
    rec = None
    try:
        doc = db.get(Document, doc_id)
        if not doc:
            return {"doc_id": doc_id, "status": "missing"}
        kb = db.get(KnowledgeBase, doc.kb_id)
        # 逐文件配置优先，未配置的项回退知识库默认
        config = normalize_chunk_config(
            doc.chunk_config, kb.chunk_strategy if kb and kb.chunk_strategy else "smart"
        )
        strategy = config["strategy"]

        doc.status = "parsing"
        doc.error = ""
        _refresh_kb_status(db, doc.kb_id)

        rec = TraceRecorder.begin(
            db,
            "kb_build",
            query=f"构建 {doc.filename}",
            title=doc.filename,
            kb=kb,
            context={
                "document": doc.filename,
                "file_type": doc.file_type,
                "file_size": doc.file_size,
                "strategy": strategy,
                "kb": getattr(kb, "name", ""),
                "embedding_ref": getattr(kb, "embedding_ref", ""),
            },
            metadata={"doc_id": doc_id, "kb_id": doc.kb_id, "strategy": strategy, "chunk_config": config},
        )

        # 1. 解析为统一 Markdown
        with rec.span(
            "build.parse",
            f"解析 · {doc.file_type.upper()}",
            code_key="build.parse",
            input={"file_type": doc.file_type, "file_size": doc.file_size, "filename": doc.filename},
        ) as span:
            parsed = parse_file(resolve_stored_path(doc.file_path), doc.file_type, db)
            span.output = {
                "chars": len(parsed.markdown or ""),
                "warnings": parsed.warnings,
                "preview": (parsed.markdown or "")[:1000],
            }

        # 2. 按知识库分块策略切分
        with rec.span(
            "build.chunk",
            f"分块 · {strategy}",
            code_key="build.chunk",
            input={k: config[k] for k in ("strategy", "chunk_size", "chunk_overlap", "separator")},
        ) as span:
            chunks = split_markdown(
                parsed.markdown,
                strategy=strategy,
                chunk_size=config["chunk_size"],
                chunk_overlap=config["chunk_overlap"],
                separator=config["separator"],
                db=db,
            )
            if not chunks:
                raise ParsingError("文档未切分出任何分块")
            span.output = {
                "count": len(chunks),
                "avg_chars": round(sum(len(c.get("content") or "") for c in chunks) / len(chunks)),
                "preview": [c["content"][:200] for c in chunks[:3]],
            }

        # 2.5 分块增强：关键词 / 问答对（可选，模型异常时降级不中断）
        if config["enhance_keywords"] or config["enhance_qa"]:
            with rec.span(
                "build.enhance",
                "分块增强",
                code_key="build.enhance",
                input={"keywords": config["enhance_keywords"], "qa": config["enhance_qa"], "chunks": len(chunks)},
            ) as span:
                result = enhance_chunks(
                    db, chunks, keywords=config["enhance_keywords"], qa=config["enhance_qa"],
                )
                span.output = result

        # 3. embedding：使用知识库绑定的模型（未绑定回退全局默认/伪向量）
        embed_service = get_embedding_service(db, (kb.embedding_ref if kb else None) or None)
        with rec.span(
            "build.embed",
            f"Embedding · {len(chunks)} 条",
            code_key="build.embed",
            input={"model": embed_service.model, "chunks": len(chunks), "batch_size": EMBED_BATCH_SIZE},
        ) as span:
            vectors: list[list[float]] = []
            embed_tokens = 0
            for i in range(0, len(chunks), EMBED_BATCH_SIZE):
                # 向量化文本 = 增强内容（关键词 / 可回答的问题）+ 原文
                batch = [chunk_index_text(c["content"], c) for c in chunks[i : i + EMBED_BATCH_SIZE]]
                batch_vectors, used = embed_service.embed_texts_with_usage(batch)
                vectors.extend(batch_vectors)
                embed_tokens += used
            if len(vectors) != len(chunks):
                raise ParsingError("embedding 返回数量与分块数不一致")
            usage = rec.add_usage("embedding", embed_service.model, embed_tokens, 0)
            span.tokens = usage.as_dict()
            span.cost_cny = usage.cost
            span.output = {
                "model": embed_service.model,
                "vectors": len(vectors),
                "dim": len(vectors[0]) if vectors else 0,
                "tokens": embed_tokens,
                "fake": getattr(embed_service, "is_fake", False),
            }

        # 4. 清理旧分块并入库（父子分块：child 记录 parent_group）
        with rec.span(
            "build.index",
            "向量入库",
            code_key="build.index",
            input={"chunks": len(chunks), "model": embed_service.model},
        ) as span:
            deleted = db.query(Chunk).filter(Chunk.doc_id == doc_id).delete()
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
                            "keywords": chunk.get("keywords") or [],
                            "qa_pairs": chunk.get("qa_pairs") or [],
                        },
                        embedding=vector,
                    )
                )
                stored += 1
            span.output = {"deleted_old": deleted, "stored": stored}

        doc.status = "done"
        doc.chunk_count = stored
        summary = f"解析 → 分块 → Embedding → 入库完成，共 {stored} 个分块"
        rec.finish(
            status="success",
            answer=summary,
            context={
                "document": doc.filename,
                "chunks": stored,
                "strategy": strategy,
                "embedding_model": embed_service.model,
            },
        )  # 同时提交文档状态
        _refresh_kb_status(db, doc.kb_id)
        return {"doc_id": doc_id, "status": "done", "chunks": stored, "strategy": strategy}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        if rec:
            try:
                rec.record_span(
                    "exception",
                    "异常 · 构建失败",
                    code_key="exception.error",
                    status="error",
                    error=str(e),
                    error_hint=explain_error(e),
                )
                rec.finish(status="error", error=str(e))
            except Exception:  # noqa: BLE001
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
