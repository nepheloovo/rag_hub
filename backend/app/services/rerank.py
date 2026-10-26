"""Rerank 客户端：通义走原生 DashScope API，其余服务商走 OpenAI 兼容 /rerank（Jina 格式）
任何失败自动降级：跳过精排，仅用向量召回结果。"""
import httpx
from sqlalchemy.orm import Session

from app.models import Provider
from app.services.llm_client import resolve_default_model

DASHSCOPE_RERANK_URL = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"


class RerankResult:
    def __init__(self, ranked: list[dict], total_tokens: int = 0):
        # ranked: [{"index": i, "score": s}]
        self.ranked = ranked
        self.total_tokens = total_tokens


def _rerank_tongyi(provider: Provider, model: str, query: str, documents: list[str], top_n: int) -> RerankResult:
    resp = httpx.post(
        DASHSCOPE_RERANK_URL,
        headers={"Authorization": f"Bearer {provider.api_key}"},
        json={
            "model": model,
            "input": {"query": query, "documents": documents},
            "parameters": {"top_n": top_n, "return_documents": False},
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("output", {}).get("results", []) or []
    usage = data.get("usage", {}) or {}
    ranked = [{"index": r["index"], "score": r.get("relevance_score", 0.0)} for r in results]
    return RerankResult(ranked, int(usage.get("total_tokens", 0)))


def _rerank_compatible(provider: Provider, model: str, query: str, documents: list[str], top_n: int) -> RerankResult:
    resp = httpx.post(
        f"{provider.base_url.rstrip('/')}/rerank",
        headers={"Authorization": f"Bearer {provider.api_key}"},
        json={"model": model, "query": query, "documents": documents, "top_n": top_n},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", []) or []
    usage = data.get("usage", {}) or {}
    ranked = [{"index": r["index"], "score": r.get("relevance_score", 0.0)} for r in results]
    return RerankResult(ranked, int(usage.get("total_tokens", 0)))


class RerankService:
    def __init__(self, provider: Provider, model: str):
        self.provider = provider
        self.model = model

    def rerank(self, query: str, documents: list[str], top_n: int) -> RerankResult:
        if self.provider.provider_type == "tongyi":
            return _rerank_tongyi(self.provider, self.model, query, documents, top_n)
        return _rerank_compatible(self.provider, self.model, query, documents, top_n)

    @classmethod
    def resolve(cls, db: Session) -> "RerankService | None":
        found = resolve_default_model(db, "rerank")
        if found:
            return cls(*found)
        return None
