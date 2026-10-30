"""知识库 / 文档 / 分块 API"""
import json
import os
import re
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.api.deps import require_roles
from app.models import Chunk, Document, KnowledgeBase
from app.schemas.knowledge import (
    ChunkOut,
    DocumentOut,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
)

kb_router = APIRouter(prefix="/knowledge-bases", tags=["知识库"])
doc_router = APIRouter(prefix="/documents", tags=["文档"])
chunk_router = APIRouter(prefix="/chunks", tags=["分块"])

EDITOR_ROLES = ("platform_admin", "kb_admin", "app_developer")


class ChunkConfigBody(BaseModel):
    """逐文件切块配置（缺省项用知识库默认）"""
    config: dict = Field(default_factory=dict)


class WebImportRequest(ChunkConfigBody):
    urls: list[str] = Field(min_length=1, max_length=20)


class TextImportRequest(ChunkConfigBody):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=500_000)


class ChunkUpdate(BaseModel):
    content: str | None = Field(default=None, max_length=20000)
    keywords: list[str] | None = None
    qa_pairs: list[dict] | None = None


def _chunk_config(db: Session, kb_id: str, raw: dict | str | None) -> dict:
    from app.services.chunking import normalize_chunk_config

    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="切块配置不是合法 JSON") from exc
    kb = db.get(KnowledgeBase, kb_id)
    return normalize_chunk_config(raw, kb.chunk_strategy if kb and kb.chunk_strategy else "smart")


def _safe_filename(title: str, suffix: str = ".md") -> str:
    name = re.sub(r'[\\/:*?"<>|\s]+', " ", title).strip()[:60] or "未命名"
    return f"{name}{suffix}"

# 允许的文件类型（映射到解析器）
ALLOWED_TYPES = {
    ".docx": "word",
    ".doc": "word",
    ".pdf": "pdf",
    ".md": "markdown",
    ".markdown": "markdown",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".xlsx": "table",
    ".xls": "table",
    ".csv": "table",
}
MAX_FILE_MB = 20


def _get_kb(db: Session, kb_id: str) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return kb


@kb_router.get("", response_model=list[KnowledgeBaseOut])
def list_kbs(db: Session = Depends(get_db)):
    from app.models import Application

    rows = (
        db.query(
            KnowledgeBase,
            func.count(func.distinct(Document.id)).label("doc_count"),
            func.coalesce(func.sum(Document.chunk_count), 0).label("chunk_count"),
        )
        .outerjoin(Document, Document.kb_id == KnowledgeBase.id)
        .group_by(KnowledgeBase.id)
        .order_by(KnowledgeBase.created_at.desc())
        .all()
    )
    apps = db.query(Application).all()
    result = []
    for kb, doc_count, chunk_count in rows:
        out = KnowledgeBaseOut.model_validate(kb)
        out.doc_count = doc_count
        out.chunk_count = chunk_count
        out.used_by_apps = [a.name for a in apps if kb.id in (a.kb_ids or [])]
        result.append(out)
    return result


@kb_router.post("", response_model=KnowledgeBaseOut, status_code=201, dependencies=[Depends(require_roles("platform_admin", "kb_admin", "app_developer"))])
def create_kb(data: KnowledgeBaseCreate, db: Session = Depends(get_db)):
    if not data.name.strip():
        raise HTTPException(status_code=422, detail="知识库名称不能为空")
    if data.kb_type not in ("generic", "qa_pair", "table", "website", "feishu"):
        data.kb_type = "generic"
    kb = KnowledgeBase(
        id=uuid.uuid4().hex,
        name=data.name.strip(),
        description=data.description,
        kb_type=data.kb_type,
        chunk_strategy=data.chunk_strategy,
        embedding_ref=data.embedding_ref,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


@kb_router.get("/{kb_id}", response_model=KnowledgeBaseOut)
def get_kb(kb_id: str, db: Session = Depends(get_db)):
    return _get_kb(db, kb_id)


@kb_router.put("/{kb_id}", response_model=KnowledgeBaseOut, dependencies=[Depends(require_roles("platform_admin", "kb_admin", "app_developer"))])
def update_kb(kb_id: str, data: KnowledgeBaseUpdate, db: Session = Depends(get_db)):
    kb = _get_kb(db, kb_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(kb, field, value)
    db.commit()
    db.refresh(kb)
    return kb


@kb_router.delete("/{kb_id}", status_code=204, dependencies=[Depends(require_roles("platform_admin", "kb_admin", "app_developer"))])
def delete_kb(kb_id: str, db: Session = Depends(get_db)):
    kb = _get_kb(db, kb_id)
    db.query(Chunk).filter(Chunk.kb_id == kb_id).delete()
    db.query(Document).filter(Document.kb_id == kb_id).delete()
    db.delete(kb)
    db.commit()


@kb_router.get("/{kb_id}/test-retrieval")
def test_retrieval(
    kb_id: str,
    q: str = Query(..., min_length=1),
    mode: str = Query("semantic", pattern="^(semantic|fulltext|hybrid)$"),
    top_k: int | None = Query(None, ge=1, le=100),
    top_n: int | None = Query(None, ge=1, le=100),
    score_threshold: float = Query(0.0, ge=0.0, le=1.0),
    rerank: bool = True,
    db: Session = Depends(get_db),
):
    """测试检索：语义 / 全文 / 混合三种模式对比召回效果（不入库、不写日志）"""
    kb = _get_kb(db, kb_id)
    from app.services.retrieval import normalize_retrieval, retrieve

    options = normalize_retrieval({
        "mode": mode, "score_threshold": score_threshold, "rerank": rerank,
        **({"top_k": top_k} if top_k else {}), **({"top_n": top_n} if top_n else {}),
    })
    outcome = retrieve(db, [kb_id], q, embedding_ref=kb.embedding_ref or None, options=options)
    return {
        "query": q,
        "options": options,
        "chunks": [
            {
                "id": item.chunk.id,
                "doc_id": item.chunk.doc_id,
                "content": item.chunk.content,
                "source": (item.chunk.metadata_ or {}).get("source", ""),
                "page": (item.chunk.metadata_ or {}).get("page", 0),
                "heading": (item.chunk.metadata_ or {}).get("heading", ""),
                "keywords": (item.chunk.metadata_ or {}).get("keywords") or [],
                "score": round(item.score, 4),
            }
            for item in outcome.chunks
        ],
        "models": {
            "embedding": outcome.embedding_model,
            "embedding_fake": outcome.embedding_is_fake,
            "rerank": outcome.rerank_model,
            "rerank_used": outcome.rerank_used,
        },
    }


@kb_router.post("/{kb_id}/documents", response_model=DocumentOut, status_code=201, dependencies=[Depends(require_roles("platform_admin", "kb_admin", "app_developer"))])
async def upload_document(
    kb_id: str,
    file: UploadFile,
    auto_index: bool = Form(True, description="上传后立即索引；false=仅存储，预览分块后手动索引入库"),
    config: str = Form("", description="逐文件切块配置 JSON：strategy/chunk_size/chunk_overlap/separator/enhance_keywords/enhance_qa"),
    db: Session = Depends(get_db),
):
    kb = _get_kb(db, kb_id)
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    file_type = ALLOWED_TYPES.get(ext)
    if not file_type:
        raise HTTPException(status_code=415, detail=f"不支持的文件格式 {ext}；支持：Word/PDF/Markdown/图片/表格")

    data = await file.read()
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件超过 {MAX_FILE_MB}MB 上限")
    return store_document(
        db, kb_id, filename, file_type, data, auto_index=auto_index,
        chunk_config=_chunk_config(db, kb_id, config) if config.strip() else {},
    )


def store_document(
    db: Session, kb_id: str, filename: str, file_type: str, data: bytes,
    auto_index: bool = True, chunk_config: dict | None = None,
) -> Document:
    """文件落盘 + 建文档记录 + 投递异步解析（上传与「补充知识」共用）"""
    ext = os.path.splitext(filename)[1].lower()
    # 落盘
    kb_dir = os.path.join(settings.upload_dir, kb_id)
    os.makedirs(kb_dir, exist_ok=True)
    file_path = os.path.join(kb_dir, f"{uuid.uuid4().hex}{ext}")
    with open(file_path, "wb") as f:
        f.write(data)

    doc = Document(
        id=uuid.uuid4().hex,
        kb_id=kb_id,
        filename=filename,
        file_type=file_type,
        file_size=len(data),
        file_path=file_path,
        status="pending",
        chunk_config=chunk_config or {},
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 异步解析入库（auto_index=false 时等待手动确认）
    if auto_index:
        from app.worker.tasks import parse_document

        parse_document.delay(doc.id)
    return doc


@kb_router.post("/{kb_id}/web-import", response_model=list[DocumentOut], status_code=201, dependencies=[Depends(require_roles(*EDITOR_ROLES))])
def web_import(kb_id: str, req: WebImportRequest, db: Session = Depends(get_db)):
    """网页导入：逐个抓取正文转 Markdown 入库；任一网址失败整体报错，已成功的保留"""
    from app.services.web_import import fetch_markdown

    _get_kb(db, kb_id)
    config = _chunk_config(db, kb_id, req.config)
    docs, errors = [], []
    for url in dict.fromkeys(u.strip() for u in req.urls if u.strip()):
        try:
            title, markdown = fetch_markdown(url)
        except Exception as exc:  # noqa: BLE001 —— 逐个网址报告失败原因（含 WebImportError）
            errors.append(f"{url}：{exc}")
            continue
        docs.append(store_document(db, kb_id, _safe_filename(title), "markdown", markdown.encode("utf-8"), chunk_config=config))
    if errors and not docs:
        raise HTTPException(status_code=422, detail="；".join(errors))
    return docs


@kb_router.post("/{kb_id}/text-import", response_model=DocumentOut, status_code=201, dependencies=[Depends(require_roles(*EDITOR_ROLES))])
def text_import(kb_id: str, req: TextImportRequest, db: Session = Depends(get_db)):
    """自定义文本导入：标题 + Markdown 正文，作为文档入库"""
    _get_kb(db, kb_id)
    title, content = req.title.strip(), req.content.strip()
    if not title or not content:
        raise HTTPException(status_code=422, detail="标题和内容都不能为空")
    body = content if content.lstrip().startswith("#") else f"# {title}\n\n{content}"
    return store_document(
        db, kb_id, _safe_filename(title), "markdown", body.encode("utf-8"),
        chunk_config=_chunk_config(db, kb_id, req.config),
    )


@kb_router.get("/{kb_id}/documents", response_model=list[DocumentOut])
def list_documents(kb_id: str, db: Session = Depends(get_db)):
    _get_kb(db, kb_id)
    return (
        db.query(Document)
        .filter(Document.kb_id == kb_id)
        .order_by(Document.created_at.desc())
        .all()
    )


@doc_router.delete("/{doc_id}", status_code=204, dependencies=[Depends(require_roles("platform_admin", "kb_admin", "app_developer"))])
def delete_document(doc_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    db.query(Chunk).filter(Chunk.doc_id == doc_id).delete()
    try:
        if doc.file_path and os.path.exists(doc.file_path):
            os.remove(doc.file_path)
    except OSError:
        pass
    db.delete(doc)
    db.commit()


@doc_router.post("/{doc_id}/reparse", response_model=DocumentOut, dependencies=[Depends(require_roles("platform_admin", "kb_admin", "app_developer"))])
def reparse_document(doc_id: str, req: ChunkConfigBody | None = None, db: Session = Depends(get_db)):
    """重新解析；传入 config 时按新的切块配置单文件重切（完成后自动替换旧分块）"""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if req is not None and req.config:
        doc.chunk_config = _chunk_config(db, doc.kb_id, req.config)
    doc.status = "pending"
    doc.error = ""
    db.commit()
    from app.worker.tasks import parse_document

    parse_document.delay(doc_id)
    db.refresh(doc)
    return doc


@doc_router.post("/{doc_id}/index", response_model=DocumentOut, dependencies=[Depends(require_roles("platform_admin", "kb_admin", "app_developer"))])
def index_document(doc_id: str, db: Session = Depends(get_db)):
    """预览确认后索引入库（等同 reparse，语义区分）"""
    return reparse_document(doc_id, None, db)


@doc_router.post("/{doc_id}/preview")
def preview_chunks(
    doc_id: str,
    strategy: str | None = Query(None, description="分块策略，缺省用文件/知识库配置"),
    req: ChunkConfigBody | None = None,
    db: Session = Depends(get_db),
):
    """试切块预览：解析文档并按策略切分，返回前 50 块（不入库、不向量化）"""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    raw = {**(doc.chunk_config or {}), **(req.config if req else {})}
    if strategy:
        raw["strategy"] = strategy
    config = _chunk_config(db, doc.kb_id, raw)
    chosen = config["strategy"]

    from app.services.chunking import STRATEGY_LABELS, split_markdown
    from app.services.files import resolve_stored_path
    from app.services.parsing.base import parse_file

    parsed = parse_file(resolve_stored_path(doc.file_path), doc.file_type, db)
    chunks = split_markdown(
        parsed.markdown, strategy=chosen, chunk_size=config["chunk_size"],
        chunk_overlap=config["chunk_overlap"], separator=config["separator"], db=db,
    )
    lengths = [len(c["content"]) for c in chunks] or [0]
    return {
        "strategy": chosen,
        "config": config,
        "avg_chars": round(sum(lengths) / len(lengths)),
        "max_chars": max(lengths),
        "strategy_label": STRATEGY_LABELS.get(chosen, chosen),
        "total": len(chunks),
        "chunks": [
            {
                "content": c["content"],
                "heading": c.get("heading", ""),
                "page": c.get("page", 0),
                "kind": c.get("kind", "chunk"),
            }
            for c in chunks[:50]
        ],
        "warnings": parsed.warnings,
    }


@doc_router.get("/{doc_id}/chunks", response_model=list[ChunkOut])
def list_chunks(
    doc_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    rows = (
        db.query(Chunk)
        .filter(Chunk.doc_id == doc_id)
        .order_by(Chunk.created_at, Chunk.id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        ChunkOut(
            id=c.id,
            content=c.content,
            source=c.metadata_.get("source", ""),
            page=c.metadata_.get("page", 0),
            heading=c.metadata_.get("heading", ""),
            kind=c.metadata_.get("kind", "chunk"),
            keywords=c.metadata_.get("keywords") or [],
            qa_pairs=c.metadata_.get("qa_pairs") or [],
        )
        for c in rows
    ]


@chunk_router.patch("/{chunk_id}", response_model=ChunkOut, dependencies=[Depends(require_roles(*EDITOR_ROLES))])
def update_chunk(chunk_id: str, req: ChunkUpdate, db: Session = Depends(get_db)):
    """编辑分块内容 / 关键词 / 问答对，保存后立即重新向量化"""
    from app.services.chunk_enhancement import chunk_index_text, clean_keywords, clean_qa
    from app.services.embedding import get_embedding_service

    chunk = db.get(Chunk, chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="分块不存在")
    meta = dict(chunk.metadata_ or {})
    if req.content is not None:
        if not req.content.strip():
            raise HTTPException(status_code=422, detail="分块内容不能为空")
        chunk.content = req.content.strip()
    if req.keywords is not None:
        meta["keywords"] = clean_keywords(req.keywords)
    if req.qa_pairs is not None:
        meta["qa_pairs"] = clean_qa(req.qa_pairs)
    kb = db.get(KnowledgeBase, chunk.kb_id)
    embed_service = get_embedding_service(db, (kb.embedding_ref if kb else None) or None)
    vectors, _tokens = embed_service.embed_texts_with_usage([chunk_index_text(chunk.content, meta)])
    meta["edited"] = True
    meta["embedding_model"] = embed_service.model
    chunk.metadata_ = meta
    chunk.embedding = vectors[0]
    db.commit()
    return ChunkOut(
        id=chunk.id, content=chunk.content, source=meta.get("source", ""), page=meta.get("page", 0),
        heading=meta.get("heading", ""), kind=meta.get("kind", "chunk"),
        keywords=meta.get("keywords") or [], qa_pairs=meta.get("qa_pairs") or [],
    )


@chunk_router.delete("/{chunk_id}", status_code=204, dependencies=[Depends(require_roles(*EDITOR_ROLES))])
def delete_chunk(chunk_id: str, db: Session = Depends(get_db)):
    chunk = db.get(Chunk, chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="分块不存在")
    doc = db.get(Document, chunk.doc_id)
    db.delete(chunk)
    if doc:
        doc.chunk_count = max(0, (doc.chunk_count or 0) - 1)
    db.commit()
