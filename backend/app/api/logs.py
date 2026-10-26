"""日志监测 API：查询内容 / Token 消耗 / 使用时长"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ChatLog

router = APIRouter(prefix="/logs", tags=["日志监测"])


@router.get("")
def list_logs(
    role: str | None = None,
    kb_id: str | None = None,
    status: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(ChatLog)
    if role:
        query = query.filter(ChatLog.role == role)
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
    return {"total": total, "page": page, "page_size": page_size, "items": rows}


@router.get("/stats")
def log_stats(db: Session = Depends(get_db)):
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    base = db.query(ChatLog).filter(ChatLog.time >= today_start)
    total = base.count()
    success = base.filter(ChatLog.status == "success").count()

    tokens_sum = db.query(
        func.coalesce(
            func.sum(func.jsonb_extract_path_text(ChatLog.tokens, "total").cast(Integer)), 0
        )
    ).filter(ChatLog.time >= today_start).scalar()

    avg_ms = db.query(func.avg(ChatLog.duration_ms)).filter(ChatLog.time >= today_start).scalar() or 0

    # 近 7 日趋势
    trend = []
    for i in range(6, -1, -1):
        day = (today_start - timedelta(days=i)).date()
        day_count = (
            db.query(func.count(ChatLog.id))
            .filter(ChatLog.time >= datetime.combine(day, datetime.min.time()))
            .filter(ChatLog.time < datetime.combine(day, datetime.min.time()) + timedelta(days=1))
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
