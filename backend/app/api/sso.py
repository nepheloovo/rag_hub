"""SSO 配置管理 API（平台管理员）"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database import get_db
from app.models import User
from app.services.auth import audit
from app.services.feishu import get_config

router = APIRouter(prefix="/sso", tags=["SSO 配置"])


class SsoUpdate(BaseModel):
    feishu_enabled: bool | None = None
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    wecom_enabled: bool | None = None
    wecom_corp_id: str | None = None
    wecom_agent_id: str | None = None
    wecom_secret: str | None = None


@router.get("")
def get_sso(db: Session = Depends(get_db), admin: User = Depends(require_roles("platform_admin"))):
    cfg = get_config(db)
    return {
        "feishu_enabled": cfg.feishu_enabled,
        "feishu_app_id": cfg.feishu_app_id,
        "feishu_has_secret": bool(cfg.feishu_app_secret),
        "feishu_secret": "",  # 不回传明文，保存时留空表示不修改
        "wecom_enabled": cfg.wecom_enabled,
        "wecom_corp_id": cfg.wecom_corp_id,
        "wecom_agent_id": cfg.wecom_agent_id,
        "wecom_has_secret": bool(cfg.wecom_secret),
        "wecom_secret": "",
    }


@router.put("")
def update_sso(
    data: SsoUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("platform_admin")),
):
    cfg = get_config(db)
    payload = data.model_dump(exclude_none=True)
    secret_fields = {"feishu_app_secret": "feishu_app_secret", "wecom_secret": "wecom_secret"}
    for field, value in payload.items():
        if field in secret_fields and not value:
            continue  # 留空 = 不修改
        setattr(cfg, field, value)
    db.commit()
    audit(db, "sso_update", "SSO 配置", "更新飞书/企业微信 SSO 配置", actor=admin.username, role=admin.role)
    return get_sso(db, admin)
