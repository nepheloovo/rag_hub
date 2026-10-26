"""模型服务商配置"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # tongyi / openrouter / aihubmix / custom
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False, default="custom")
    base_url: Mapped[str] = mapped_column(String(256), nullable=False)
    api_key: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # {"embedding": [...], "rerank": [...], "llm": [...]}
    models: Mapped[dict] = mapped_column(JSONB, default=lambda: {"embedding": [], "rerank": [], "llm": []})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ModelDefaults(Base):
    """全局默认模型（单行表，id 固定为 'default'）"""

    __tablename__ = "model_defaults"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default="default")
    # 形如 "tongyi:text-embedding-v3"
    default_embedding: Mapped[str] = mapped_column(String(128), default="")
    default_rerank: Mapped[str] = mapped_column(String(128), default="")  # 可为空 => 自动降级
    default_llm: Mapped[str] = mapped_column(String(128), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
