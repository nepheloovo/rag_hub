"""服务商与默认模型配置的业务逻辑"""
import time
import uuid

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import ModelDefaults, Provider
from app.schemas.provider import DefaultsUpdate, ProviderUpdate

# 预置服务商（首次启动时写入）
PRESET_PROVIDERS = [
    {
        "id": "tongyi",
        "name": "通义千问",
        "provider_type": "tongyi",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": {
            "embedding": ["text-embedding-v3", "text-embedding-v4"],
            "rerank": ["gte-rerank"],
            "llm": ["qwen-max", "qwen-plus", "qwen-turbo"],
        },
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "provider_type": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models": {
            "embedding": ["openai/text-embedding-3-small"],
            "rerank": [],
            "llm": ["openai/gpt-4o", "anthropic/claude-3.5-sonnet", "deepseek/deepseek-chat"],
        },
    },
    {
        "id": "aihubmix",
        "name": "AIHubmix",
        "provider_type": "aihubmix",
        "base_url": "https://aihubmix.com/v1",
        "models": {
            "embedding": ["text-embedding-3-small", "bge-m3"],
            "rerank": ["bge-reranker-v2-m3"],
            "llm": ["gpt-4o", "claude-3.5-sonnet", "deepseek-v3", "qwen-max"],
        },
    },
]


def seed_presets(db: Session) -> None:
    """初始化预置服务商与默认模型（幂等）"""
    for preset in PRESET_PROVIDERS:
        if not db.get(Provider, preset["id"]):
            db.add(Provider(id=preset["id"], api_key="", **{
                k: v for k, v in preset.items() if k != "id"
            }))
    if not db.get(ModelDefaults, "default"):
        defaults = ModelDefaults(id="default")
        # 默认走通义（三类模型齐全）
        defaults.default_embedding = "tongyi:text-embedding-v3"
        defaults.default_rerank = "tongyi:gte-rerank"
        defaults.default_llm = "tongyi:qwen-max"
        db.add(defaults)
    db.commit()


def get_defaults(db: Session) -> ModelDefaults:
    defaults = db.get(ModelDefaults, "default")
    if not defaults:
        seed_presets(db)
        defaults = db.get(ModelDefaults, "default")
    return defaults


def update_defaults(db: Session, data: DefaultsUpdate) -> ModelDefaults:
    defaults = get_defaults(db)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(defaults, field, value)
    db.commit()
    db.refresh(defaults)
    return defaults


def get_provider(db: Session, provider_id: str) -> Provider:
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"服务商 {provider_id} 不存在")
    return provider


def create_provider(db: Session, data: dict) -> Provider:
    provider = Provider(id=uuid.uuid4().hex[:16], **data)
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


def update_provider(db: Session, provider_id: str, data: ProviderUpdate) -> Provider:
    provider = get_provider(db, provider_id)
    for field, value in data.model_dump(exclude_none=True).items():
        if field == "models" and isinstance(value, dict):
            provider.models = {**provider.models, **value}
        else:
            setattr(provider, field, value)
    db.commit()
    db.refresh(provider)
    return provider


def delete_provider(db: Session, provider_id: str) -> None:
    provider = get_provider(db, provider_id)
    db.delete(provider)
    db.commit()


def test_provider_connection(provider: Provider, model_type: str | None = None) -> dict:
    """通过 OpenAI 兼容接口测试连通性：拉取可用模型列表（可选过滤类别）"""
    if not provider.api_key:
        return {"ok": False, "message": "未配置 API Key", "latency_ms": None}

    start = time.time()
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{provider.base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {provider.api_key}"},
            )
        latency = int((time.time() - start) * 1000)
        if resp.status_code != 200:
            return {"ok": False, "message": f"HTTP {resp.status_code}: {resp.text[:200]}", "latency_ms": latency}

        models = resp.json().get("data", [])
        ids = [m.get("id") for m in models if m.get("id")]
        configured = (
            provider.models.get(model_type, []) if model_type in ("embedding", "rerank", "llm")
            else [m for t in ("embedding", "rerank", "llm") for m in provider.models.get(t, [])]
        )
        missing = [m for m in configured if m and m not in ids]
        msg = f"连接成功，服务商可用模型 {len(ids)} 个"
        if model_type:
            msg += f"；已配置 {model_type} 模型 {len(configured)} 个"
        if missing:
            msg += f"；注意：以下模型未在服务商返回列表中：{', '.join(missing)}"
        return {"ok": True, "message": msg, "latency_ms": latency}
    except Exception as e:  # noqa: BLE001
        latency = int((time.time() - start) * 1000)
        return {"ok": False, "message": f"连接失败: {e}", "latency_ms": latency}
