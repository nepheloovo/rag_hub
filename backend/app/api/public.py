"""公开访问 API：已发布应用的公开信息与匿名对话（官网嵌入用）"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.apps import app_chat_response
from app.database import get_db
from app.models import Application, ChatLog
from app.schemas.application import AppChatRequest

router = APIRouter(prefix="/public/apps", tags=["公开访问"])


def _published_app(db: Session, app_id: str) -> Application:
    app = db.get(Application, app_id)
    if not app or app.status != "published" or not app.publish_enabled:
        raise HTTPException(status_code=404, detail="应用未发布或不存在")
    return app


@router.get("/{app_id}")
def public_app_info(app_id: str, db: Session = Depends(get_db)):
    app = _published_app(db, app_id)
    return {
        "id": app.id,
        "name": app.name,
        "description": app.description,
        "app_type": app.app_type,
        "app_kind": app.app_kind,
        "opening": app.opening,
        "suggested_questions": app.suggested_questions,
        "show_refs": app.show_refs,
    }


@router.post("/{app_id}/chat")
def public_chat(app_id: str, req: AppChatRequest, db: Session = Depends(get_db)):
    app = _published_app(db, app_id)
    # 访客每日限额
    if app.visitor_daily_limit and app.visitor_daily_limit > 0:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        used = (
            db.query(func.count(ChatLog.id))
            .filter(ChatLog.app_id == app_id, ChatLog.role == "访客", ChatLog.time >= today_start)
            .scalar() or 0
        )
        if used >= app.visitor_daily_limit:
            raise HTTPException(status_code=429, detail="该应用今日访客对话次数已达上限")
    req.role = "访客"
    return app_chat_response(app_id, req)


@router.get("/{app_id}/visitor-stats")
def visitor_stats(app_id: str, db: Session = Depends(get_db)):
    """访客会话统计（供 Agent 接入管理页；需登录后由 apps 接口提供，此处仅限限额查询）"""
    app = _published_app(db, app_id)
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    used = (
        db.query(func.count(ChatLog.id))
        .filter(ChatLog.app_id == app_id, ChatLog.role == "访客", ChatLog.time >= today_start)
        .scalar() or 0
    )
    return {"visitor_daily_limit": app.visitor_daily_limit or 0, "used_today": int(used)}
