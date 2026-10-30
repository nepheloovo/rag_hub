"""日志监测 API：查询内容 / Token 消耗 / 使用时长"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ChatLog
from app.models.chat import MessageFeedback
from app.models.observability import TraceRun
from app.services.insights import EVAL_ROLE, trace_feedback

# 评测流量（role=eval）默认不计入日志与统计
NOT_EVAL = func.coalesce(ChatLog.role, "") != EVAL_ROLE

router = APIRouter(prefix="/logs", tags=["日志监测"])


@router.get("")
def list_logs(
    role: str | None = None,
    kb_id: str | None = None,
    status: str | None = None,
    q: str | None = None,
    feedback: str | None = Query(None, pattern="^(like|dislike|any)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(ChatLog)
    if role:
        query = query.filter(ChatLog.role == role)
    else:
        query = query.filter(NOT_EVAL)
    if feedback:
        rated = db.query(TraceRun.id).join(MessageFeedback, MessageFeedback.message_id == TraceRun.message_id)
        if feedback == "like":
            # 点赞且没有点踩
            disliked = rated.filter(MessageFeedback.rating < 0)
            rated = rated.filter(MessageFeedback.rating > 0, ~TraceRun.id.in_(disliked))
        elif feedback == "dislike":
            rated = rated.filter(MessageFeedback.rating < 0)
        query = query.filter(ChatLog.trace_id.in_(rated))
    if kb_id:
        query = query.filter(ChatLog.kb_id == kb_id)
    if status:
        query = query.filter(ChatLog.status == status)
    if q:
        query = query.filter(ChatLog.query.ilike(f"%{q}%"))
    total = query.count()
    rows = (
        query.order_by(ChatLog.time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    ratings = trace_feedback(db, [r.trace_id for r in rows])
    items = [
        {**{c.key: getattr(r, c.key) for c in ChatLog.__mapper__.column_attrs}, "feedback": ratings.get(r.trace_id, 0)}
        for r in rows
    ]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/stats")
def log_stats(db: Session = Depends(get_db)):
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    base = db.query(ChatLog).filter(ChatLog.time >= today_start, NOT_EVAL)
    total = base.count()
    success = base.filter(ChatLog.status == "success").count()

    tokens_sum = db.query(
        func.coalesce(
            func.sum(func.jsonb_extract_path_text(ChatLog.tokens, "total").cast(Integer)), 0
        )
    ).filter(ChatLog.time >= today_start, NOT_EVAL).scalar()

    avg_ms = db.query(func.avg(ChatLog.duration_ms)).filter(ChatLog.time >= today_start, NOT_EVAL).scalar() or 0

    # 近 7 日趋势
    trend = []
    for i in range(6, -1, -1):
        day = (today_start - timedelta(days=i)).date()
        day_count = (
            db.query(func.count(ChatLog.id))
            .filter(ChatLog.time >= datetime.combine(day, datetime.min.time()))
            .filter(ChatLog.time < datetime.combine(day, datetime.min.time()) + timedelta(days=1), NOT_EVAL)
            .scalar()
        )
        trend.append({"date": str(day), "count": day_count})

    return {
        "today_count": total,
        "today_tokens": int(tokens_sum or 0),
        "avg_duration_ms": round(float(avg_ms)),
        "success_rate": round(success / total * 100, 1) if total else 100.0,
        "trend": trend,
    }
