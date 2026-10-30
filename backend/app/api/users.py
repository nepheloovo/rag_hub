"""成员管理 API（平台管理员）"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.database import get_db
from app.models import User
from app.models.user import ROLES, ROLE_LABELS
from app.services.auth import audit, hash_password

router = APIRouter(prefix="/users", tags=["成员管理"])


class UserCreate(BaseModel):
    username: str
    display_name: str = ""
    department: str = ""
    role: str = "business_user"
    password: str


class UserUpdate(BaseModel):
    display_name: str | None = None
    department: str | None = None
    role: str | None = None
    enabled: bool | None = None
    password: str | None = None


def _user_out(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "display_name": u.display_name,
        "department": u.department,
        "role": u.role,
        "role_label": ROLE_LABELS.get(u.role, u.role),
        "enabled": u.enabled,
        "last_login_at": u.last_login_at,
        "created_at": u.created_at,
    }


@router.get("")
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("platform_admin")),
):
    users = db.query(User).order_by(User.created_at).all()
    return [_user_out(u) for u in users]


@router.post("", status_code=201)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("platform_admin")),
):
    if not data.username.strip() or len(data.password) < 6:
        raise HTTPException(status_code=422, detail="用户名不能为空，密码至少 6 位")
    if data.role not in ROLES:
        raise HTTPException(status_code=422, detail="角色无效")
    if db.query(User).filter(User.username == data.username.strip()).first():
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = User(
        id=uuid.uuid4().hex,
        username=data.username.strip(),
        display_name=data.display_name or data.username.strip(),
        department=data.department,
        role=data.role,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    audit(db, "user_create", user.username, f"角色：{user.role}", actor=admin.username, role=admin.role)
    return _user_out(user)


@router.put("/{user_id}")
def update_user(
    user_id: str,
    data: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("platform_admin")),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="成员不存在")
    changes = []
    for field, value in data.model_dump(exclude_none=True).items():
        if field == "password":
            if len(value) < 6:
                raise HTTPException(status_code=422, detail="密码至少 6 位")
            user.password_hash = hash_password(value)
            changes.append("重置密码")
        elif field == "role":
            if value not in ROLES:
                raise HTTPException(status_code=422, detail="角色无效")
            setattr(user, field, value)
            changes.append(f"角色 → {ROLE_LABELS.get(value, value)}")
        else:
            setattr(user, field, value)
            changes.append(f"{field}")
    db.commit()
    audit(
        db, "user_update", user.username, "；".join(changes), actor=admin.username, role=admin.role
    )
    return _user_out(user)
