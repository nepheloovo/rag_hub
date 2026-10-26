from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str = ""


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class KnowledgeBaseOut(BaseModel):
    id: str
    name: str
    description: str
    doc_count: int = 0
    chunk_count: int = 0
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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChunkOut(BaseModel):
    id: str
    content: str
    source: str = ""
    page: int = 0
    heading: str = ""
