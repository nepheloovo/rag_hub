"""对话 API：会话管理 + 流式问答（SSE）"""
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import ChatLog, Chunk, Conversation, Document, KnowledgeBase, Message
from app.schemas.chat import ChatRequest, ConversationCreate
from app.services.chat import stream_answer
from app.services.retrieval import retrieve

router = APIRouter(tags=["对话"])

HISTORY_MESSAGES = 6  # 参与上下文的历史消息条数


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/conversations")
def list_conversations(
    kb_id: str | None = Query(None),
    app_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Conversation)
    if kb_id:
        q = q.filter(Conversation.kb_id == kb_id)
    if app_id:
        q = q.filter(Conversation.app_id == app_id)
    return q.order_by(Conversation.created_at.desc()).limit(50).all()


@router.post("/conversations", status_code=201)
def create_conversation(data: ConversationCreate, db: Session = Depends(get_db)):
    kb = db.get(KnowledgeBase, data.kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    conv = Conversation(
        id=uuid.uuid4().hex,
        kb_id=data.kb_id,
        role="user",
        title=(data.title or "新对话")[:100],
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations/{conv_id}/messages")
def list_messages(conv_id: str, db: Session = Depends(get_db)):
    conv = db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    return (
        db.query(Message)
        .filter(Message.conv_id == conv_id)
        .order_by(Message.created_at)
        .all()
    )


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: str, db: Session = Depends(get_db)):
    conv = db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.query(Message).filter(Message.conv_id == conv_id).delete()
    db.delete(conv)
    db.commit()


@router.post("/chat")
async def chat(req: ChatRequest):
    if not req.query.strip():
        raise HTTPException(status_code=422, detail="问题不能为空")

    db = SessionLocal()
    try:
        kb = db.get(KnowledgeBase, req.kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")

        conv_id = req.conversation_id
        if conv_id:
            conv = db.get(Conversation, conv_id)
            if not conv:
                raise HTTPException(status_code=404, detail="会话不存在")
        else:
            conv = Conversation(
                id=uuid.uuid4().hex,
                kb_id=req.kb_id,
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

        # 保存用户消息
        user_msg = Message(id=uuid.uuid4().hex, conv_id=conv_id, role="user", content=req.query)
        db.add(user_msg)
        db.commit()

        # 检索（独立会话，避免长连接持有请求级 session）
        outcome = retrieve(db, [req.kb_id], req.query)
        if not outcome.chunks:
            raise HTTPException(status_code=422, detail="知识库中未检索到相关内容，请先导入文档")

        # 提取纯数据（生成器生命周期长于请求，不能跨 session 引用 ORM 对象）
        kb_name = kb.name
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
            for i, item in enumerate(outcome.chunks[:5]):
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

            for chunk, fake, mname in stream_answer(gen_db, req.query, history_rows, outcome.chunks):
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

            # 保存助手消息
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
                    kb_id=req.kb_id,
                    kb_name=kb_name,
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
                        kb_id=req.kb_id,
                        kb_name=kb_name,
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
