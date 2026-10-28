"""认证 API：登录 / 当前用户 / SSO（飞书网页应用 OAuth）"""
import json
import secrets
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import User
from app.services.auth import audit, issue_token, verify_password
from app.services.feishu import FeishuError, authorize_url, exchange_code, get_config, get_user_info

router = APIRouter(prefix="/auth", tags=["认证"])


class LoginRequest(BaseModel):
    username: str
    password: str


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "department": user.department,
        "role": user.role,
    }


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
    return {"token": issue_token(user), "user": _user_payload(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_payload(user)


@router.get("/sso-config")
def sso_config(db: Session = Depends(get_db)):
    """SSO 通道状态（登录页按钮据此启用）"""
    cfg = get_config(db)
    return {
        "feishu": {
            "enabled": bool(cfg.feishu_enabled and cfg.feishu_app_id and cfg.feishu_app_secret),
            "note": "未配置：请在「设置 → SSO 配置」填写飞书应用 App ID / Secret",
        },
        "wecom": {
            "enabled": bool(cfg.wecom_enabled and cfg.wecom_corp_id and cfg.wecom_secret),
            "note": "未配置：请在「设置 → SSO 配置」填写企业微信自建应用凭证",
        },
    }


def _callback_base(request: Request) -> str:
    """当前部署的公网地址（用于回调/跳转），支持代理头"""
    forwarded = request.headers.get("x-forwarded-proto", "")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    scheme = forwarded.split(",")[0].strip() if forwarded else request.url.scheme
    return f"{scheme}://{host}"


@router.get("/feishu/login")
def feishu_login(request: Request, db: Session = Depends(get_db)):
    cfg = get_config(db)
    if not (cfg.feishu_enabled and cfg.feishu_app_id and cfg.feishu_app_secret):
        raise HTTPException(status_code=400, detail="飞书 SSO 未配置，请联系管理员在「设置 → SSO 配置」中配置")
    state = secrets.token_urlsafe(16)
    redirect_uri = f"{_callback_base(request)}/api/auth/feishu/callback"
    url = authorize_url(cfg, redirect_uri, state)
    return RedirectResponse(url)


@router.get("/feishu/callback")
def feishu_callback(code: str, request: Request, db: Session = Depends(get_db)):
    """飞书回调：code 换 token → 用户信息 → 自动创建/关联本地账号 → 跳回前端"""
    cfg = get_config(db)
    try:
        user_token = exchange_code(cfg, code)
        info = get_user_info(user_token)
    except FeishuError as e:
        return RedirectResponse(f"/login?error={urlencode({'msg': str(e)})}")
    except Exception as e:  # noqa: BLE001
        return RedirectResponse(f"/login?error={urlencode({'msg': f'飞书登录失败: {e}'})}")

    open_id = info.get("open_id") or ""
    name = info.get("name") or "飞书用户"
    if not open_id:
        return RedirectResponse("/login?error=" + urlencode({"msg": "飞书未返回 open_id"}))

    # 按 open_id 关联已有账号，否则自动创建
    user = db.query(User).filter(User.feishu_open_id == open_id).first()
    if not user:
        username = f"feishu_{open_id[-8:]}" if open_id else None
        # 避免用户名冲突
        base = f"feishu_{open_id[-8:]}"
        username = base
        n = 1
        while db.query(User).filter(User.username == username).first():
            n += 1
            username = f"{base}_{n}"
        user = User(
            id=uuid.uuid4().hex,
            username=username,
            display_name=name,
            role="business_user",
            password_hash="",  # SSO 用户无本地密码
            feishu_open_id=open_id,
            enabled=True,
        )
        db.add(user)
    else:
        user.display_name = name
    if user.enabled is False:
        return RedirectResponse("/login?error=" + urlencode({"msg": "账号已停用，请联系管理员"}))
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    audit(db, "sso_login", user.username, "飞书登录", actor=user.username, role=user.role)

    token = issue_token(user)
    params = urlencode({"token": token, "user": json.dumps(_user_payload(user), ensure_ascii=False)})
    return RedirectResponse(f"/sso-callback?{params}")
