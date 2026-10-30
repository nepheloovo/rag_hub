"""工具模型：HTTP / MCP / 工作流插件 / 系统内置"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Tool(Base):
    __tablename__ = "tools"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    # http / mcp / plugin / system
    tool_type: Mapped[str] = mapped_column(String(16), nullable=False, default="http", index=True)
    # http: {"url","method","headers","body"}; system: {"system_key","content_template"}
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    # available / beta
    status: Mapped[str] = mapped_column(String(16), default="available")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    call_count: Mapped[int] = mapped_column(Integer, default=0)
    last_called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ToolCallLog(Base):
    __tablename__ = "tool_call_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tool_id: Mapped[str] = mapped_column(String(32), index=True)
    tool_name: Mapped[str] = mapped_column(String(128), default="")
    app_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    app_name: Mapped[str] = mapped_column(String(128), default="")
    input_snippet: Mapped[str] = mapped_column(Text, default="")
    output_snippet: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="success")
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
