from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ApplicationCreate(BaseModel):
    name: str
    description: str = ""
    app_type: str = "qa"  # qa / service / report
    kb_ids: list[str] = Field(default_factory=list)


class ApplicationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    kb_ids: Optional[list[str]] = None
    llm_ref: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0, le=2)
    show_refs: Optional[bool] = None
    opening: Optional[str] = None
    suggested_questions: Optional[list[str]] = None
    fallback_reply: Optional[str] = None
    transfer_hint: Optional[str] = None


class ApplicationOut(BaseModel):
    id: str
    name: str
    description: str
    app_type: str
    kb_ids: list[str]
    llm_ref: str
    system_prompt: str
    temperature: float
    show_refs: bool
    opening: str
    suggested_questions: list[str]
    fallback_reply: str
    transfer_hint: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AppChatRequest(BaseModel):
    query: str
    role: str = "user"
    conversation_id: Optional[str] = None
