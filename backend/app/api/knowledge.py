"""知识库 / 文档 / 分块 API"""
import os
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
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
def test_retrieval(kb_id: str, q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    """测试检索：验证召回/Rerank 效果（不入库、不写日志）"""
    kb = _get_kb(db, kb_id)
    from app.services.retrieval import retrieve

    outcome = retrieve(db, [kb_id], q, embedding_ref=kb.embedding_ref or None)
    return {
        "query": q,
        "chunks": [
            {
                "id": item.chunk.id,
                "doc_id": item.chunk.doc_id,
                "content": item.chunk.content,
                "source": (item.chunk.metadata_ or {}).get("source", ""),
                "page": (item.chunk.metadata_ or {}).get("page", 0),
                "heading": (item.chunk.metadata_ or {}).get("heading", ""),
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
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 异步解析入库（auto_index=false 时等待手动确认）
    if auto_index:
        from app.worker.tasks import parse_document

        parse_document.delay(doc.id)
    return doc


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
def reparse_document(doc_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
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
    return reparse_document(doc_id, db)


@doc_router.post("/{doc_id}/preview")
def preview_chunks(
    doc_id: str,
    strategy: str | None = Query(None, description="分块策略，缺省用知识库配置"),
    db: Session = Depends(get_db),
):
    """试切块预览：解析文档并按策略切分，返回前 50 块（不入库、不向量化）"""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    kb = db.get(KnowledgeBase, doc.kb_id)
    chosen = strategy or (kb.chunk_strategy if kb and kb.chunk_strategy else "smart")

    from app.services.chunking import STRATEGY_LABELS, split_markdown
    from app.services.files import resolve_stored_path
    from app.services.parsing.base import parse_file

    parsed = parse_file(resolve_stored_path(doc.file_path), doc.file_type, db)
    chunks = split_markdown(parsed.markdown, strategy=chosen, db=db)
    return {
        "strategy": chosen,
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
        )
        for c in rows
    ]
