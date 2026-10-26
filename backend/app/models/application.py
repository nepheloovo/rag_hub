"""应用模型：问答应用 / 智能客服 / 报告分析（类型=预设模板差异）"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    # qa=问答应用 / service=智能客服 / report=报告分析
    app_type: Mapped[str] = mapped_column(String(16), nullable=False, default="qa", index=True)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
