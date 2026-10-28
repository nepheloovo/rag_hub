"""业务统计 API：工作台/看板数据"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Application, ChatLog, Document, KnowledgeBase

router = APIRouter(prefix="/stats", tags=["统计"])


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
