"""业务统计 API：工作台/看板数据"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database import get_db
from app.models import Application, ChatLog, Document, KnowledgeBase
from app.schemas.knowledge import DocumentOut
from app.services import insights

router = APIRouter(prefix="/stats", tags=["统计"])

# 评测流量（role=eval）不计入业务统计
NOT_EVAL = func.coalesce(ChatLog.role, "") != insights.EVAL_ROLE


@router.get("/trend")
def trend(days: int = Query(14, ge=1, le=60), db: Session = Depends(get_db)):
    """近 N 日趋势：应用调用（成功）/ 新增文档 / 新增应用"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    dates = [(today - timedelta(days=i)).date() for i in range(days - 1, -1, -1)]
    calls, docs, apps = [], [], []
    for day in dates:
        start = datetime.combine(day, datetime.min.time())
        end = start + timedelta(days=1)
        calls.append(
            db.query(func.count(ChatLog.id))
            .filter(ChatLog.time >= start, ChatLog.time < end, ChatLog.status == "success", NOT_EVAL)
            .scalar() or 0
        )
        docs.append(
            db.query(func.count(Document.id))
            .filter(Document.created_at >= start, Document.created_at < end)
            .scalar() or 0
        )
        apps.append(
            db.query(func.count(Application.id))
            .filter(Application.created_at >= start, Application.created_at < end)
            .scalar() or 0
        )
    return {
        "dates": [str(d) for d in dates],
        "calls": [int(v) for v in calls],
        "docs": [int(v) for v in docs],
        "apps": [int(v) for v in apps],
    }


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    app_calls = (
        db.query(func.count(ChatLog.id))
        .filter(ChatLog.time >= month_start, ChatLog.status == "success", NOT_EVAL)
        .scalar()
    )
    new_docs = db.query(func.count(Document.id)).filter(Document.created_at >= month_start).scalar()
    new_apps = db.query(func.count(Application.id)).filter(Application.created_at >= month_start).scalar()
    kb_count = db.query(func.count(KnowledgeBase.id)).scalar()
    app_count = db.query(func.count(Application.id)).scalar()
    published = (
        db.query(func.count(Application.id)).filter(Application.status == "published").scalar()
    )

    return {
        "month_app_calls": int(app_calls or 0),
        "month_new_docs": int(new_docs or 0),
        "month_new_apps": int(new_apps or 0),
        "kb_count": int(kb_count or 0),
        "app_count": int(app_count or 0),
        "published_count": int(published or 0),
        **insights.feedback_overview(db),
    }


@router.get("/knowledge-gaps")
def knowledge_gaps(
    days: int = Query(30, ge=1, le=90),
    app_id: str | None = None,
    db: Session = Depends(get_db),
):
    """知识缺口：未命中 + 被点踩的问题，按相似问题聚类"""
    return insights.knowledge_gaps(db, days=days, app_id=app_id)


@router.get("/bad-feedback")
def bad_feedback(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return insights.bad_feedback(db, limit=limit)


class SupplementRequest(BaseModel):
    kb_id: str
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=20000)


@router.post(
    "/knowledge-gaps/supplement", response_model=DocumentOut, status_code=201,
    dependencies=[Depends(require_roles("platform_admin", "kb_admin", "app_developer"))],
)
def supplement_knowledge(req: SupplementRequest, db: Session = Depends(get_db)):
    """把缺口问题的标准答案作为 Markdown 文档补充进知识库，走常规解析入库"""
    from app.api.knowledge import store_document

    if not db.get(KnowledgeBase, req.kb_id):
        raise HTTPException(status_code=404, detail="知识库不存在")
    question, answer = req.question.strip(), req.answer.strip()
    if not question or not answer:
        raise HTTPException(status_code=422, detail="问题和答案都不能为空")
    safe_title = "".join(ch for ch in question[:20] if ch not in '\\/:*?"<>|').strip() or "问答"
    content = f"# {question}\n\n问：{question}\n\n答：{answer}\n"
    return store_document(db, req.kb_id, f"知识补充-{safe_title}.md", "markdown", content.encode("utf-8"))
