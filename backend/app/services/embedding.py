"""Embedding 服务：优先真实模型，无可用配置时降级为哈希伪向量（保证链路可自测）"""
import hashlib
import math
import struct

from sqlalchemy.orm import Session

from app.config import settings
from app.services.llm_client import get_openai_client, resolve_default_model


def _fake_embed(texts: list[str]) -> list[list[float]]:
    """确定性伪向量：同一文本永远得到同一向量，维度对齐 settings.embedding_dim。
    用整数哈希映射到 [-1, 1]，避免浮点位型产生 NaN/Inf。"""
    dim = settings.embedding_dim
    vectors = []
    for text in texts:
        base = hashlib.sha256(text.encode("utf-8")).digest()
        vec = []
        for i in range(dim):
            h = hashlib.sha256(base + struct.pack(">I", i)).digest()
            v = int.from_bytes(h[:8], "big") / (2**63) - 1.0  # [-1, 1)
            vec.append(v)
        # L2 归一化，使余弦相似度可用
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vectors.append([v / norm for v in vec])
    return vectors


class EmbeddingService:
    """embed_texts(texts) -> list[list[float]]"""

    def __init__(self, provider, model: str):
        self.provider = provider
        self.model = model
        self.client = get_openai_client(provider)
        self.is_fake = False

    def embed_texts_with_usage(self, texts: list[str]) -> tuple[list[list[float]], int]:
        resp = self.client.embeddings.create(model=self.model, input=texts)
        data = sorted(resp.data, key=lambda d: d.index)
        tokens = getattr(resp, "usage", None)
        total = int(tokens.prompt_tokens) if tokens else 0
        return [d.embedding for d in data], total

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors, _ = self.embed_texts_with_usage(texts)
        return vectors

    @classmethod
    def resolve(cls, db: Session) -> "EmbeddingService | None":
        found = resolve_default_model(db, "embedding")
        if found:
            return cls(*found)
        return None


def get_embedding_service(db: Session) -> EmbeddingService:
    """获取 embedding 服务；无真实配置时返回伪向量服务（is_fake=True）"""
    service = EmbeddingService.resolve(db)
    if service:
        return service
    if not settings.allow_fake_embedding:
        raise RuntimeError("未配置可用的 embedding 模型，且已禁用伪向量降级")

    class FakeEmbeddingService(EmbeddingService):
        is_fake = True

        def __init__(self):
            self.provider = None
            self.model = "fake-hash-embedding"
            self.client = None

        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return _fake_embed(texts)

        def embed_texts_with_usage(self, texts: list[str]) -> tuple[list[list[float]], int]:
            return _fake_embed(texts), 0

    return FakeEmbeddingService()
