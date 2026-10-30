from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ApplicationCreate(BaseModel):
    name: str
    description: str = ""
    app_type: str = "qa"  # qa / service / report
    app_kind: str = "simple"  # simple / chatflow / agent
    status: str = "draft"  # 创建时仅允许草稿，发布通过专用接口
    category: str = "办公提效"
    kb_ids: list[str] = Field(default_factory=list)


class ApplicationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    app_kind: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    kb_ids: Optional[list[str]] = None
    llm_ref: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0, le=2)
    show_refs: Optional[bool] = None
    opening: Optional[str] = None
    suggested_questions: Optional[list[str]] = None
    fallback_reply: Optional[str] = None
    transfer_hint: Optional[str] = None
    flow: Optional[dict] = None  # Chat Flow 编排（保存时自动生成版本快照）
    publish_enabled: Optional[bool] = None
    visitor_daily_limit: Optional[int] = Field(None, ge=0)


class ApplicationOut(BaseModel):
    id: str
    name: str
    description: str
    app_type: str
    app_kind: str
    status: str
    published_version_id: Optional[str] = None
    published_version: Optional[int] = None
    draft_dirty: bool = True
    version: int
    category: str
    kb_ids: list[str]
    llm_ref: str
    system_prompt: str
    temperature: float
    show_refs: bool
    opening: str
    suggested_questions: list[str]
    fallback_reply: str
    transfer_hint: str
    flow: Optional[dict] = None
    flow_history: dict = Field(default_factory=dict)
    publish_enabled: bool = False
    visitor_daily_limit: int = 0
    created_at: datetime
    updated_at: datetime
    # 统计（由 API 填充，非 ORM 字段）
    call_count_7d: int = 0

    model_config = {"from_attributes": True}


class AppRestoreRequest(BaseModel):
    version: int


class AppGenerateRequest(BaseModel):
    description: str


class AppChatRequest(BaseModel):
    query: str
    role: str = "user"
    conversation_id: Optional[str] = None
    draft: bool = False


class AppReleaseRequest(BaseModel):
    release_notes: str = ""


class AppRollbackRequest(BaseModel):
    version_id: str = Field(min_length=1)
