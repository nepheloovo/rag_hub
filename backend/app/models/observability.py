"""可观测数据模型：一次执行（TraceRun）、执行步骤（TraceSpan）、模型单价（ModelPrice）"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TraceRun(Base):
    """一次完整执行：Agent / Chat Flow / 简易 RAG / 知识库构建"""

    __tablename__ = "trace_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    trace_type: Mapped[str] = mapped_column(String(20), index=True, default="chat")
    title: Mapped[str] = mapped_column(String(256), default="")
    query: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), index=True, default="running")
    app_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    app_name: Mapped[str] = mapped_column(String(128), default="")
    app_kind: Mapped[str] = mapped_column(String(16), default="")
    kb_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    kb_name: Mapped[str] = mapped_column(String(256), default="")
    conversation_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    message_id: Mapped[str] = mapped_column(String(32), default="")
    role: Mapped[str] = mapped_column(String(32), default="")
    source: Mapped[str] = mapped_column(String(16), default="internal")
    model: Mapped[str] = mapped_column(String(128), default="")
    models: Mapped[dict] = mapped_column(JSONB, default=dict)
    tokens: Mapped[dict] = mapped_column(JSONB, default=dict)
    cost_cny: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    span_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)


class TraceSpan(Base):
    """Trace 内的一步执行：ReAct 思考/工具/Skill、检索、构建阶段等"""

    __tablename__ = "trace_spans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    trace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("trace_runs.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[str] = mapped_column(String(32), default="")
    seq: Mapped[int] = mapped_column(Integer, default=0)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    span_type: Mapped[str] = mapped_column(String(40), index=True, default="")
    name: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(16), default="success")
    started_offset_ms: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    input: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tokens: Mapped[dict] = mapped_column(JSONB, default=dict)
    cost_cny: Mapped[float] = mapped_column(Float, default=0.0)
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    error_hint: Mapped[str] = mapped_column(Text, default="")
    code_key: Mapped[str] = mapped_column(String(64), default="")
    code: Mapped[str] = mapped_column(Text, default="")
    code_explain: Mapped[list] = mapped_column(JSONB, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)


class ModelPrice(Base):
    """模型计费单价（元 / 百万 Token）"""

    __tablename__ = "model_prices"

    model: Mapped[str] = mapped_column(String(128), primary_key=True)
    input_price: Mapped[float] = mapped_column(Float, default=0.0)
    output_price: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
