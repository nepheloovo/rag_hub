"""应用模型：简易(simple) / Chat Flow(chatflow) / Agent(agent)，草稿→评测中→已发布"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

APP_KINDS = ("simple", "chatflow", "agent")
APP_STATUSES = ("draft", "reviewing", "published")
APP_CATEGORIES = ("报告撰写", "智能客服", "制度与合同审校", "营销内容", "办公提效")


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    # qa=问答应用 / service=智能客服 / report=报告分析
    app_type: Mapped[str] = mapped_column(String(16), nullable=False, default="qa", index=True)
    # 应用形态：simple / chatflow / agent
    app_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="simple", index=True)
    # 发布状态：draft / reviewing / published
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # 业务场景分类
    category: Mapped[str] = mapped_column(String(32), default="办公提效", index=True)
    # 绑定知识库（可多库）
    kb_ids: Mapped[list] = mapped_column(JSONB, default=list)
    # "provider_id:model"，空 = 使用全局默认 LLM
    llm_ref: Mapped[str] = mapped_column(String(128), default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    show_refs: Mapped[bool] = mapped_column(Boolean, default=True)
    opening: Mapped[str] = mapped_column(Text, default="")
    suggested_questions: Mapped[list] = mapped_column(JSONB, default=list)
    # 客服专属：未检索到内容时的兜底话术 / 转人工提示
    fallback_reply: Mapped[str] = mapped_column(Text, default="")
    transfer_hint: Mapped[str] = mapped_column(Text, default="")
    # Chat Flow 编排：{"nodes": [...], "edges": [...]}
    flow: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    # 版本快照：{"2": {flow}, "3": {flow}, ...}（上限 20）
    flow_history: Mapped[dict] = mapped_column(JSONB, default=dict)
    # 对外发布：开启后可通过公开页面/嵌入访问（仅 status=published 生效）
    publish_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # 访客每日限额（0=不限）：限制公开页面每日匿名对话次数
    visitor_daily_limit: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
