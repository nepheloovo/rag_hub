"""评测集模型：线上 Case 回流池 + 评测集聚合"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EvalCase(Base):
    """一条线上回流 Case：问题 + 实际回答 + 期望回答 + good/bad 标签"""

    __tablename__ = "eval_cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    question: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    reference_answer: Mapped[str] = mapped_column(Text, default="")
    contexts: Mapped[list] = mapped_column(JSONB, default=list)
    label: Mapped[str] = mapped_column(String(8), index=True, default="good")  # good / bad
    status: Mapped[str] = mapped_column(String(16), default="candidate")  # candidate / confirmed
    app_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    app_name: Mapped[str] = mapped_column(String(128), default="")
    source: Mapped[str] = mapped_column(String(16), default="manual")  # trace / log / manual
    trace_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EvalSet(Base):
    """评测集：人工把 good / bad Case 汇总在一起，作为回归基线"""

    __tablename__ = "eval_sets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EvalSetItem(Base):
    __tablename__ = "eval_set_items"
    __table_args__ = (UniqueConstraint("set_id", "case_id", name="uq_eval_set_case"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    set_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("eval_sets.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("eval_cases.id", ondelete="CASCADE"), index=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
