"""SSO 配置（单行表）：飞书 / 企业微信 应用凭证"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SsoConfig(Base):
    __tablename__ = "sso_configs"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default="default")
    feishu_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    feishu_app_id: Mapped[str] = mapped_column(String(128), default="")
    feishu_app_secret: Mapped[str] = mapped_column(String(256), default="")
    wecom_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    wecom_corp_id: Mapped[str] = mapped_column(String(128), default="")
    wecom_agent_id: Mapped[str] = mapped_column(String(64), default="")
    wecom_secret: Mapped[str] = mapped_column(String(256), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
