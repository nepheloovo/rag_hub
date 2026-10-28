"""应用 API：CRUD + 应用级流式对话（SSE）+ AI 生成应用"""
import json
import time
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.config import settings
from app.models import Application, ChatLog, Conversation, KnowledgeBase, Message
from app.schemas.application import (
    AppChatRequest,
    AppGenerateRequest,
    AppRestoreRequest,
    ApplicationCreate,
    ApplicationOut,
    ApplicationUpdate,
)
from app.services.app_templates import get_template
from app.services.chat import build_llm, stream_answer
from app.services.retrieval import retrieve

router = APIRouter(prefix="/apps", tags=["应用"])

HISTORY_MESSAGES = 6

KIND_LABELS = {"simple": "简易应用", "chatflow": "Chat Flow", "agent": "Agent"}
STATUS_LABELS = {"draft": "草稿", "reviewing": "评测中", "published": "已发布"}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _get_app(db: Session, app_id: str) -> Application:
    app = db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    return app


def _call_count_7d(db: Session, app_id: str) -> int:
    return (
        db.query(ChatLog)
        .filter(ChatLog.app_id == app_id, ChatLog.time >= datetime.now() - timedelta(days=7))
        .count()
    )


@router.get("", response_model=list[ApplicationOut])
def list_apps(db: Session = Depends(get_db)):
    apps = db.query(Application).order_by(Application.created_at.desc()).all()
    result = []
    for app in apps:
        out = ApplicationOut.model_validate(app)
        out.call_count_7d = _call_count_7d(db, app.id)
        result.append(out)
    return result


@router.post("/generate", response_model=dict)
def generate_app(req: AppGenerateRequest, db: Session = Depends(get_db)):
    """描述需求 → AI 生成应用第一版（名称/类型/分类/提示词/开场白/推荐问题）"""
    if not req.description.strip():
        raise HTTPException(status_code=422, detail="请描述应用需求")
    prompt = (
        "你是企业 AI 应用配置助手。根据用户的需求描述，生成一个知识问答应用的第一版配置。\n"
        "app_type 选择规则：涉及客服/售后/订单/咨询 → service；涉及报告/分析/周报/研究/总结 → report；其余 → qa。\n"
        "只输出 JSON（不要任何其他文字），字段：\n"
        "{\n"
        '  "name": "应用名（≤12字）",\n'
        '  "app_type": "qa|service|report",\n'
        '  "category": "报告撰写|智能客服|制度与合同审校|营销内容|办公提效",\n'
        '  "description": "一句话介绍",\n'
        '  "system_prompt": "系统提示词",\n'
        '  "opening": "开场白",\n'
        '  "suggested_questions": ["推荐问题1","推荐问题2","推荐问题3"]\n'
        "}\n\n"
        f"需求描述：{req.description.strip()}"
    )
    llm, is_fake, model_name = build_llm(db, temperature=0.3)
    from langchain_core.prompts import ChatPromptTemplate

    chain = ChatPromptTemplate.from_messages([("human", "{input}")]) | llm
    text = chain.invoke({"input": prompt})
    content = text if isinstance(text, str) else (text.content if hasattr(text, "content") else str(text))

    # 容错解析 JSON（截取 { 到 } 区间）
    draft = None
    try:
        draft = json.loads(content)
    except Exception:  # noqa: BLE001
        start, end = content.find("{"), content.rfind("}")
        if start >= 0 and end > start:
            try:
                draft = json.loads(content[start : end + 1])
            except Exception:  # noqa: BLE001
                draft = None
    if not draft or not draft.get("name"):
        # 模拟 LLM / 解析失败：按关键词模板兜底
        desc = req.description
        if any(k in desc for k in ("客服", "售后", "订单", "咨询")):
            app_type, category = "service", "智能客服"
        elif any(k in desc for k in ("报告", "分析", "周报", "研究")):
            app_type, category = "report", "报告撰写"
        elif any(k in desc for k in ("合同", "制度", "合规", "审校")):
            app_type, category = "qa", "制度与合同审校"
        elif any(k in desc for k in ("文案", "营销", "话术", "活动")):
            app_type, category = "qa", "营销内容"
        else:
            app_type, category = "qa", "办公提效"
        template = get_template(app_type)
        draft = {
            "name": desc[:12] or "新应用",
            "app_type": app_type,
            "category": category,
            "description": desc,
            "system_prompt": template["system_prompt"],
            "opening": template["opening"],
            "suggested_questions": template["suggested_questions"],
        }
    return {"draft": draft, "models": {"llm": model_name, "fake": is_fake}}


@router.post("", response_model=ApplicationOut, status_code=201)
def create_app(data: ApplicationCreate, db: Session = Depends(get_db)):
    if not data.name.strip():
        raise HTTPException(status_code=422, detail="应用名称不能为空")
    if data.app_type not in ("qa", "service", "report"):
        raise HTTPException(status_code=422, detail="应用类型必须是 qa / service / report")
    if data.app_kind not in ("simple", "chatflow", "agent"):
        raise HTTPException(status_code=422, detail="应用形态必须是 simple / chatflow / agent")
    if data.status not in ("draft", "reviewing", "published"):
        raise HTTPException(status_code=422, detail="状态必须是 draft / reviewing / published")
    if data.category not in ("报告撰写", "智能客服", "制度与合同审校", "营销内容", "办公提效"):
        data.category = "办公提效"
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
        app_kind=data.app_kind,
        status=data.status,
        version=1,
        category=data.category,
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
    payload = data.model_dump(exclude_none=True)
    flow_update = payload.pop("flow", None)
    for field, value in payload.items():
        setattr(app, field, value)
    app.version = (app.version or 0) + 1  # 每次保存版本 +1
    if flow_update is not None:
        app.flow = flow_update
        # 版本快照（上限 20）
        history = dict(app.flow_history or {})
        history[str(app.version)] = flow_update
        if len(history) > 20:
            oldest = sorted(int(k) for k in history.keys())[0]
            history.pop(str(oldest), None)
        app.flow_history = history
    db.commit()
    db.refresh(app)
    return app


@router.get("/{app_id}/versions")
def list_versions(app_id: str, db: Session = Depends(get_db)):
    app = _get_app(db, app_id)
    history = app.flow_history or {}
    versions = sorted((int(k) for k in history.keys()), reverse=True)
    return {"current": app.version, "versions": versions}


@router.post("/{app_id}/restore", response_model=ApplicationOut)
def restore_version(app_id: str, req: AppRestoreRequest, db: Session = Depends(get_db)):
    app = _get_app(db, app_id)
    history = app.flow_history or {}
    snapshot = history.get(str(req.version))
    if not snapshot:
        raise HTTPException(status_code=404, detail="版本快照不存在")
    app.flow = snapshot
    app.version = (app.version or 0) + 1
    history[str(app.version)] = snapshot
    app.flow_history = history
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


def app_chat_response(app_id: str, req: AppChatRequest) -> StreamingResponse:
    """应用级对话核心（简易 / Chat Flow / Agent 形态统一入口），供内部与公开路由复用"""
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
                kb_id=app.kb_ids[0] if app.kb_ids else None,
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

        # Chat Flow 应用：校验编排后交给流程执行器（检索逻辑在流程节点内）
        is_chatflow = app.app_kind == "chatflow"
        is_agent = app.app_kind == "agent"
        if is_chatflow:
            from app.services.flow import validate_flow

            problems = validate_flow(app.flow)
            if problems:
                db.close()
                raise HTTPException(status_code=422, detail="；".join(problems))
            outcome = None
            no_context_reply = ""
        elif is_agent:
            # Agent：先做知识库检索供模型参考，工具由模型函数调用规划
            from app.services.retrieval import common_embedding_ref

            outcome = retrieve(
                db, list(app.kb_ids), req.query,
                embedding_ref=common_embedding_ref(db, list(app.kb_ids)),
            ) if app.kb_ids else None
            no_context_reply = ""
        else:
            # 多库联合检索（embedding 模型与索引保持一致）
            from app.services.retrieval import common_embedding_ref

            outcome = retrieve(
                db, list(app.kb_ids), req.query,
                embedding_ref=common_embedding_ref(db, list(app.kb_ids)),
            )
            # 相关性阈值过滤（默认 0 关闭；伪向量模式分值无意义，不要开启）
            if settings.retrieval_min_score > 0:
                outcome.chunks = [
                    c for c in outcome.chunks if c.score >= settings.retrieval_min_score
                ]

            # 无检索结果时的降级回答
            no_context_reply = ""
            if not outcome.chunks:
                if app.app_type == "service" and app.fallback_reply:
                    no_context_reply = app.fallback_reply
                    if app.transfer_hint:
                        no_context_reply += "\n\n" + app.transfer_hint
                else:
                    no_context_reply = "知识库中未检索到相关内容，请换一种方式描述问题，或先在应用中导入更多文档。"

        kb_names = (
            db.query(KnowledgeBase.name)
            .filter(KnowledgeBase.id.in_(app.kb_ids))
            .all()
        )
        kb_names_str = "、".join(n[0] for n in kb_names) if kb_names else "（未绑定知识库）"

        app_meta = {
            "app_id": app.id,
            "app_name": app.name,
            "app_type": app.app_type,
            "app_kind": app.app_kind,
            "is_chatflow": is_chatflow,
            "is_agent": is_agent,
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
            if app_meta["is_agent"]:
                # Agent：LLM 函数调用规划工具，流式输出
                from app.services.agent import run_agent

                app_obj = gen_db.get(Application, app_meta["app_id"])
                contexts = ""
                if outcome:
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
                    contexts = "\n\n".join(
                        f"[{i}] {c.chunk.content}" for i, c in enumerate(outcome.chunks, start=1)
                    )
                for piece in run_agent(gen_db, app_obj, req.query, contexts):
                    answer_parts.append(piece)
                    yield _sse("delta", {"text": piece})
                model_name = "agent"
                is_fake = False
            elif app_meta["is_chatflow"]:
                # 执行 Chat Flow（LLM/HTTP 工具同步生成，最终文本流式输出）
                from app.services.flow import FlowError, run_chatflow

                app_obj = gen_db.get(Application, app_meta["app_id"])
                answer_text, flow_refs, _vars = run_chatflow(gen_db, app_obj, req.query)
                if app_meta["show_refs"]:
                    refs = flow_refs
                for piece in _stream_text_chunks(answer_text or "", size=8):
                    answer_parts.append(piece)
                    yield _sse("delta", {"text": piece})
                model_name = "chatflow"
                is_fake = False
            else:
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

            emb_tokens = outcome.embedding_tokens if outcome else 0
            rerank_tokens = outcome.rerank_tokens if outcome else 0
            emb_model = outcome.embedding_model if outcome else ""
            emb_fake = outcome.embedding_is_fake if outcome else False
            rerank_model = outcome.rerank_model if outcome else ""
            tokens = {
                "embedding": emb_tokens,
                "rerank": rerank_tokens,
                "llm": llm_prompt_tokens + llm_completion_tokens,
                "total": emb_tokens + rerank_tokens + llm_prompt_tokens + llm_completion_tokens,
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
                    embedding_model=emb_model + ("(fake)" if emb_fake else ""),
                    rerank_model=rerank_model,
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
                        "embedding": emb_model,
                        "rerank": rerank_model,
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
                        embedding_model=outcome.embedding_model if outcome else "",
                        rerank_model=outcome.rerank_model if outcome else "",
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


@router.post("/{app_id}/chat")
def chat_app(app_id: str, req: AppChatRequest):
    """内部应用对话路由"""
    return app_chat_response(app_id, req)
