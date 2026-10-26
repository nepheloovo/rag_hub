from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ModelList(BaseModel):
    embedding: list[str] = Field(default_factory=list)
    rerank: list[str] = Field(default_factory=list)
    llm: list[str] = Field(default_factory=list)


class ProviderBase(BaseModel):
    name: str
    provider_type: str = "custom"
    base_url: str
    api_key: str = ""
    enabled: bool = False
    models: ModelList = Field(default_factory=ModelList)


class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    provider_type: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    enabled: Optional[bool] = None
    # 仅合并显式传入的模型类别（如 {"rerank": [...]}）
    models: Optional[dict] = None


class ProviderOut(ProviderBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DefaultsOut(BaseModel):
    default_embedding: str
    default_rerank: str
    default_llm: str


class DefaultsUpdate(BaseModel):
    default_embedding: Optional[str] = None
    default_rerank: Optional[str] = None
    default_llm: Optional[str] = None


class TestProviderRequest(BaseModel):
    """测试服务商连通性（可选指定模型类别）"""
    model_type: Optional[str] = None  # embedding / rerank / llm


class TestProviderResult(BaseModel):
    ok: bool
    message: str
    latency_ms: Optional[int] = None
