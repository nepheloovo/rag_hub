"""应用 API：CRUD + 应用级流式对话（SSE）"""
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.config import settings
from app.models import Application, ChatLog, Conversation, KnowledgeBase, Message
from app.schemas.application import (
    AppChatRequest,
    ApplicationCreate,
    ApplicationOut,
    ApplicationUpdate,
)
from app.services.app_templates import get_template
from app.services.chat import stream_answer
from app.services.retrieval import retrieve

router = APIRouter(prefix="/apps", tags=["应用"])

HISTORY_MESSAGES = 6


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _get_app(db: Session, app_id: str) -> Application:
    app = db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    return app


@router.get("", response_model=list[ApplicationOut])
def list_apps(db: Session = Depends(get_db)):
    return db.query(Application).order_by(Application.created_at.desc()).all()


@router.post("", response_model=ApplicationOut, status_code=201)
def create_app(data: ApplicationCreate, db: Session = Depends(get_db)):
    if not data.name.strip():
        raise HTTPException(status_code=422, detail="应用名称不能为空")
    if data.app_type not in ("qa", "service", "report"):
        raise HTTPException(status_code=422, detail="应用类型必须是 qa / service / report")
    # 校验知识库存在
    for kb_id in data.kb_ids:
        if not db.get(KnowledgeBase, kb_id):
            raise HTTPException(status_code=404, detail=f"知识库 {kb_id} 不存在")

    template = get_template(data.app_type)
    app = Application(
        id=uuid.uuid4().hex,
        name=data.name.strip(),
        description=data.description,
        app_type=data.app_type,
        kb_ids=data.kb_ids,
        system_prompt=template["system_prompt"],
        opening=template["opening"],
        suggested_questions=template["suggested_questions"],
        fallback_reply=template.get("fallback_reply", ""),
        transfer_hint=template.get("transfer_hint", ""),
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


@router.get("/{app_id}", response_model=ApplicationOut)
def get_app(app_id: str, db: Session = Depends(get_db)):
    return _get_app(db, app_id)


@router.put("/{app_id}", response_model=ApplicationOut)
def update_app(app_id: str, data: ApplicationUpdate, db: Session = Depends(get_db)):
    app = _get_app(db, app_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(app, field, value)
    db.commit()
    db.refresh(app)
    return app


@router.delete("/{app_id}", status_code=204)
def delete_app(app_id: str, db: Session = Depends(get_db)):
    app = _get_app(db, app_id)
    # 删除应用下的会话与消息
    conv_ids = [c.id for c in db.query(Conversation.id).filter(Conversation.app_id == app_id).all()]
    if conv_ids:
        db.query(Message).filter(Message.conv_id.in_(conv_ids)).delete(synchronize_session=False)
        db.query(Conversation).filter(Conversation.app_id == app_id).delete(synchronize_session=False)
    db.delete(app)
    db.commit()


def _stream_text_chunks(text: str, size: int = 12):
    for i in range(0, len(text), size):
        yield text[i : i + size]


@router.post("/{app_id}/chat")
async def chat_app(app_id: str, req: AppChatRequest):
    if not req.query.strip():
        raise HTTPException(status_code=422, detail="问题不能为空")

    db = SessionLocal()
    try:
        app = db.get(Application, app_id)
        if not app:
            raise HTTPException(status_code=404, detail="应用不存在")
        # 校验绑定的知识库均存在
        for kb_id in app.kb_ids:
            if not db.get(KnowledgeBase, kb_id):
                raise HTTPException(status_code=404, detail=f"应用绑定的知识库 {kb_id} 已不存在，请更新应用配置")

        conv_id = req.conversation_id
        if conv_id:
            conv = db.get(Conversation, conv_id)
            if not conv or conv.app_id != app_id:
                raise HTTPException(status_code=404, detail="会话不存在")
        else:
            conv = Conversation(
                id=uuid.uuid4().hex,
                kb_id=app.kb_ids[0] if app.kb_ids else "",
                app_id=app_id,
                role=req.role,
                title=req.query.strip()[:24],
            )
            db.add(conv)
            db.commit()
            conv_id = conv.id

        history = (
            db.query(Message)
            .filter(Message.conv_id == conv_id)
            .order_by(Message.created_at.desc())
            .limit(HISTORY_MESSAGES)
            .all()
        )[::-1]
        history = [m for m in history if m.content]

        db.add(Message(id=uuid.uuid4().hex, conv_id=conv_id, role="user", content=req.query))
        db.commit()

        # 多库联合检索
        outcome = retrieve(db, list(app.kb_ids), req.query)
        # 相关性阈值过滤（默认 0 关闭；伪向量模式分值无意义，不要开启）
        if settings.retrieval_min_score > 0:
            outcome.chunks = [
                c for c in outcome.chunks if c.score >= settings.retrieval_min_score
            ]

        kb_names = (
            db.query(KnowledgeBase.name)
            .filter(KnowledgeBase.id.in_(app.kb_ids))
            .all()
        )
        kb_names_str = "、".join(n[0] for n in kb_names) if kb_names else "（未绑定知识库）"

        # 无检索结果时的降级回答
        no_context_reply = ""
        if not outcome.chunks:
            if app.app_type == "service" and app.fallback_reply:
                no_context_reply = app.fallback_reply
                if app.transfer_hint:
                    no_context_reply += "\n\n" + app.transfer_hint
            else:
                no_context_reply = "知识库中未检索到相关内容，请换一种方式描述问题，或先在应用中导入更多文档。"

        app_meta = {
            "app_id": app.id,
            "app_name": app.name,
            "app_type": app.app_type,
            "system_prompt": app.system_prompt,
            "temperature": app.temperature,
            "show_refs": app.show_refs,
            "llm_ref": app.llm_ref,
            "kb_ids": list(app.kb_ids),
            "kb_names": kb_names_str,
        }
        history_rows = [(m.role, m.content) for m in history]
        db.close()
    except HTTPException:
        db.close()
        raise
    except Exception as e:  # noqa: BLE001
        db.close()
        raise HTTPException(status_code=500, detail=f"检索失败: {e}") from e

    def generate():
        start = time.monotonic()
        answer_parts: list[str] = []
        llm_prompt_tokens = 0
        llm_completion_tokens = 0
        model_name = ""
        is_fake = False
        gen_db = SessionLocal()
        try:
            refs = []
            if app_meta["show_refs"]:
                for item in outcome.chunks[:5]:
                    meta = item.chunk.metadata_ or {}
                    refs.append(
                        {
                            "doc_id": item.chunk.doc_id,
                            "title": meta.get("source", ""),
                            "page": meta.get("page", 0),
                            "snippet": item.chunk.content[:200],
                            "score": round(item.score, 4),
                        }
                    )

            if no_context_reply:
                # 无检索结果：直接流式输出兜底话术（不调用 LLM，避免编造）
                for piece in _stream_text_chunks(no_context_reply):
                    answer_parts.append(piece)
                    yield _sse("delta", {"text": piece})
                model_name = "none"
            else:
                for chunk, fake, mname in stream_answer(
                    gen_db,
                    req.query,
                    history_rows,
                    outcome.chunks,
                    system_prompt=app_meta["system_prompt"],
                    llm_ref=app_meta["llm_ref"] or None,
                    temperature=app_meta["temperature"],
                ):
                    is_fake = fake
                    model_name = mname
                    usage = {}
                    if isinstance(chunk, str):
                        text = chunk
                    else:
                        text = chunk.content if isinstance(chunk.content, str) else ""
                        usage = getattr(chunk, "usage_metadata", None) or {}
                    if text:
                        answer_parts.append(text)
                        yield _sse("delta", {"text": text})
                    if usage:
                        llm_prompt_tokens = int(usage.get("input_tokens", 0))
                        llm_completion_tokens = int(usage.get("output_tokens", 0))

            answer = "".join(answer_parts)
            duration_ms = int((time.monotonic() - start) * 1000)

            assistant_msg = Message(
                id=uuid.uuid4().hex, conv_id=conv_id, role="assistant", content=answer, refs=refs
            )
            gen_db.add(assistant_msg)

            tokens = {
                "embedding": outcome.embedding_tokens,
                "rerank": outcome.rerank_tokens,
                "llm": llm_prompt_tokens + llm_completion_tokens,
                "total": outcome.embedding_tokens
                + outcome.rerank_tokens
                + llm_prompt_tokens
                + llm_completion_tokens,
            }
            gen_db.add(
                ChatLog(
                    id=uuid.uuid4().hex,
                    role=req.role,
                    kb_id=",".join(app_meta["kb_ids"]),
                    kb_name=app_meta["kb_names"],
                    app_id=app_meta["app_id"],
                    app_name=app_meta["app_name"],
                    query=req.query,
                    answer=answer,
                    llm_model=model_name,
                    embedding_model=outcome.embedding_model
                    + ("(fake)" if outcome.embedding_is_fake else ""),
                    rerank_model=outcome.rerank_model,
                    tokens=tokens,
                    duration_ms=duration_ms,
                    status="success",
                )
            )
            gen_db.commit()
            yield _sse(
                "done",
                {
                    "refs": refs,
                    "tokens": tokens,
                    "duration_ms": duration_ms,
                    "message_id": assistant_msg.id,
                    "conversation_id": conv_id,
                    "answer": answer,
                    "app": app_meta,
                    "models": {
                        "llm": model_name,
                        "embedding": outcome.embedding_model,
                        "rerank": outcome.rerank_model,
                        "fake": is_fake,
                    },
                },
            )
        except Exception as e:  # noqa: BLE001
            gen_db.rollback()
            duration_ms = int((time.monotonic() - start) * 1000)
            try:
                gen_db.add(
                    ChatLog(
                        id=uuid.uuid4().hex,
                        role=req.role,
                        kb_name=app_meta["kb_names"],
                        app_id=app_meta["app_id"],
                        app_name=app_meta["app_name"],
                        query=req.query,
                        answer="",
                        llm_model=model_name,
                        embedding_model=outcome.embedding_model,
                        rerank_model=outcome.rerank_model,
                        tokens={},
                        duration_ms=duration_ms,
                        status="error",
                    )
                )
                gen_db.commit()
            except Exception:  # noqa: BLE001
                gen_db.rollback()
            yield _sse("error", {"message": f"生成失败: {e}"})
        finally:
            gen_db.close()

    return StreamingResponse(generate(), media_type="text/event-stream")
