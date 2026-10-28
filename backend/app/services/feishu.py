"""飞书网页应用登录客户端（OAuth：授权码换 token → 获取用户信息）"""
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.models import SsoConfig

FEISHU_HOST = "https://open.feishu.cn"


def get_config(db: Session) -> SsoConfig:
    cfg = db.get(SsoConfig, "default")
    if not cfg:
        cfg = SsoConfig(id="default")
        db.add(cfg)
        db.commit()
    return cfg


def authorize_url(cfg: SsoConfig, redirect_uri: str, state: str) -> str:
    """飞书授权页 URL"""
    params = urlencode({"app_id": cfg.feishu_app_id, "redirect_uri": redirect_uri, "state": state})
    return f"{FEISHU_HOST}/open-apis/authen/v1/authorize?{params}"


class FeishuError(Exception):
    pass


def _app_access_token(cfg: SsoConfig) -> str:
    resp = httpx.post(
        f"{FEISHU_HOST}/open-apis/auth/v3/app_access_token/internal",
        json={"app_id": cfg.feishu_app_id, "app_secret": cfg.feishu_app_secret},
        timeout=15,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise FeishuError(f"获取应用凭证失败: {data.get('msg', data)}")
    return data["app_access_token"]


def exchange_code(cfg: SsoConfig, code: str) -> str:
    """授权码 → user_access_token"""
    app_token = _app_access_token(cfg)
    resp = httpx.post(
        f"{FEISHU_HOST}/open-apis/authen/v1/oidc/access_token",
        headers={"Authorization": f"Bearer {app_token}"},
        json={"grant_type": "authorization_code", "code": code},
        timeout=15,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise FeishuError(f"换取用户凭证失败: {data.get('msg', data)}")
    return data["data"]["access_token"]


def get_user_info(user_access_token: str) -> dict:
    """user_access_token → 用户信息（name/open_id/employee_id）"""
    resp = httpx.get(
        f"{FEISHU_HOST}/open-apis/authen/v1/user_info",
        headers={"Authorization": f"Bearer {user_access_token}"},
        timeout=15,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise FeishuError(f"获取用户信息失败: {data.get('msg', data)}")
    return data.get("data", {})
