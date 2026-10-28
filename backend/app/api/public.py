"""公开访问 API：已发布应用的公开信息与匿名对话（官网嵌入用）"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.apps import app_chat_response
from app.database import get_db
from app.models import Application
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
    _published_app(db, app_id)
    req.role = "访客"
    return app_chat_response(app_id, req)
