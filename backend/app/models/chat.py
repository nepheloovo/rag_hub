"""对话与日志"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    # 应用会话可能未绑定知识库（Chat Flow 应用），故可空
    kb_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True, nullable=True
    )
    # 应用会话：绑定应用（应用级对话时使用，kb_id 存第一个绑定的知识库）
    app_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="user")  # 会话发起角色
    title: Mapped[str] = mapped_column(String(256), default="新对话")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    conv_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 引用来源 [{doc, page, snippet}]
    refs: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatLog(Base):
    """对话日志：查询内容、Token 消耗、使用时长"""

    __tablename__ = "chat_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    role: Mapped[str] = mapped_column(String(16), default="user")
    kb_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    kb_name: Mapped[str] = mapped_column(String(128), default="")
    # 应用来源（应用级对话时记录）
    app_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    app_name: Mapped[str] = mapped_column(String(128), default="")
    query: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    llm_model: Mapped[str] = mapped_column(String(128), default="")
    embedding_model: Mapped[str] = mapped_column(String(128), default="")
    rerank_model: Mapped[str] = mapped_column(String(128), default="")  # 空 => 已降级
    # {"embedding": n, "rerank": n, "llm": n, "total": n}
    tokens: Mapped[dict] = mapped_column(JSONB, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="success")  # success / error
    trace_id: Mapped[str] = mapped_column(String(32), default="", index=True)
