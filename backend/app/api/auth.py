"""认证 API：登录 / 当前用户 / SSO 配置"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import User
from app.services.auth import audit, issue_token, verify_password

router = APIRouter(prefix="/auth", tags=["认证"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash or ""):
        audit(db, "login_failed", req.username, "密码错误或账号不存在", actor=req.username)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.enabled:
        raise HTTPException(status_code=403, detail="账号已停用，请联系管理员")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    audit(db, "login", user.username, f"角色：{user.role}", actor=user.username, role=user.role)
    return {
        "token": issue_token(user),
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "department": user.department,
            "role": user.role,
        },
    }


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "department": user.department,
        "role": user.role,
    }


@router.get("/sso-config")
def sso_config():
    """SSO 通道配置（飞书/企业微信需企业应用凭证，未配置时前端展示提示）"""
    return {
        "feishu": {"enabled": False, "note": "需在配置中提供飞书应用 App ID / Secret 与回调地址"},
        "wecom": {"enabled": False, "note": "需在配置中提供企业微信自建应用凭证"},
    }
