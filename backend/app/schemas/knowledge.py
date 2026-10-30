from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str = ""
    kb_type: str = "generic"  # generic / qa_pair / table / website / feishu
    chunk_strategy: str = "heading"
    embedding_ref: str = ""


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    chunk_strategy: Optional[str] = None
    embedding_ref: Optional[str] = None


class KnowledgeBaseOut(BaseModel):
    id: str
    name: str
    description: str
    kb_type: str = "generic"
    chunk_strategy: str = "heading"
    status: str = "available"
    embedding_ref: str = ""
    doc_count: int = 0
    chunk_count: int = 0
    # 被引用应用（名称列表，由 API 填充）
    used_by_apps: list[str] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentOut(BaseModel):
    id: str
    kb_id: str
    filename: str
    file_type: str
    file_size: int
    status: str
    error: str
    chunk_count: int
    chunk_config: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChunkOut(BaseModel):
    id: str
    content: str
    source: str = ""
    page: int = 0
    heading: str = ""
    kind: str = "chunk"
    keywords: list[str] = Field(default_factory=list)
    qa_pairs: list[dict] = Field(default_factory=list)
