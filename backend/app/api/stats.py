"""业务统计 API：工作台/看板数据"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Application, ChatLog, Document, KnowledgeBase

router = APIRouter(prefix="/stats", tags=["统计"])


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
            .filter(ChatLog.time >= start, ChatLog.time < end, ChatLog.status == "success")
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
        .filter(ChatLog.time >= month_start, ChatLog.status == "success")
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
    }
