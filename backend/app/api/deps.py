"""认证依赖：解析 Bearer Token → 当前用户；角色校验"""
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.auth import decode_token


def get_current_user(
    authorization: str | None = Header(None), db: Session = Depends(get_db)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    payload = decode_token(authorization[7:])
    if not payload:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    user = db.get(User, payload.get("sub"))
    if not user or not user.enabled:
        raise HTTPException(status_code=401, detail="账号不存在或已停用")
    return user


def require_roles(*roles: str):
    """角色校验依赖工厂"""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="当前角色无权限执行此操作")
        return user

    return checker
