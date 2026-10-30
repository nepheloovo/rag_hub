from typing import Literal, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    kb_id: str
    query: str
    role: str = "user"  # admin / manager / user
    conversation_id: Optional[str] = None


class ConversationCreate(BaseModel):
    kb_id: str
    title: Optional[str] = None


class FeedbackRequest(BaseModel):
    rating: Literal[1, -1, 0]
    comment: Optional[str] = None


class RefItem(BaseModel):
    doc_id: str = ""
    title: str
    page: int = 0
    snippet: str
    score: Optional[float] = None


class ChatDone(BaseModel):
    refs: list[RefItem]
    tokens: dict  # {"embedding": n, "rerank": n, "llm": n, "total": n}
    duration_ms: int
    message_id: str = ""
    answer: str = ""
