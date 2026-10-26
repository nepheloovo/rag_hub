"""模型调用统一入口：三个服务商均走 OpenAI 兼容接口"""
from openai import OpenAI

from app.models import Provider


def get_openai_client(provider: Provider) -> OpenAI:
    return OpenAI(base_url=provider.base_url, api_key=provider.api_key, timeout=60.0, max_retries=1)


def resolve_default_model(db, kind: str) -> tuple[Provider, str] | None:
    """按全局默认配置解析 (provider, model)；kind: embedding/rerank/llm"""
    from app.services.provider_service import get_defaults

    defaults = get_defaults(db)
    ref = getattr(defaults, f"default_{kind}") or ""
    if ":" not in ref:
        return None
    return resolve_model_ref(db, ref, kind)


def resolve_model_ref(db, ref: str, kind: str) -> tuple[Provider, str] | None:
    """按 "provider_id:model" 显式引用解析 (provider, model)；校验服务商启用与模型存在"""
    if ":" not in ref:
        return None
    provider_id, model = ref.split(":", 1)
    provider = db.get(Provider, provider_id)
    if not provider or not provider.enabled or not provider.api_key:
        return None
    if model not in provider.models.get(kind, []):
        return None
    return provider, model
