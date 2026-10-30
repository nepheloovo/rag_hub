"""审计日志查询 API（平台管理员）"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database import get_db
from app.models import AuditLog, User

router = APIRouter(prefix="/audit", tags=["审计日志"])


@router.get("")
def list_audit(
    action: str | None = Query(None),
    actor: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("platform_admin")),
):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action}%"))
    if actor:
        q = q.filter(AuditLog.actor.ilike(f"%{actor}%"))
    total = q.count()
    rows = (
        q.order_by(AuditLog.time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"total": total, "page": page, "page_size": page_size, "items": rows}
