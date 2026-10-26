"""应用配置：全部通过环境变量覆盖，默认值适配本地开发"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    # 基础
    app_name: str = "企业知识库中台"
    api_prefix: str = "/api"
    debug: bool = True

    # 数据库（默认与 docker-compose.yml 一致）
    database_url: str = "postgresql+psycopg://rag:rag123456@localhost:5432/rag_zhongtai"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # 文件存储（上传文件与解析产物）
    upload_dir: str = str(BASE_DIR / "data" / "uploads")
    parsed_dir: str = str(BASE_DIR / "data" / "parsed")

    # 分块参数
    chunk_size: int = 600
    chunk_overlap: int = 80
    # 向量维度需与所选 embedding 模型一致：通义 text-embedding-v3/v4 默认 1024
    embedding_dim: int = 1024

    # OCR（通义多模态）
    ocr_provider_id: str = "tongyi"
    ocr_model: str = "qwen-vl-plus"

    # 无可用 embedding 服务商时，使用哈希伪向量保证全链路可自测（上线前应配置真实模型）
    allow_fake_embedding: bool = True
    # 无可用 LLM 时，使用模拟流式模型保证链路可自测（上线前应配置真实模型）
    allow_fake_llm: bool = True
    # 平均每页字符数低于该值时判定 PDF 为扫描件
    scanned_pdf_min_chars_per_page: int = 60

    # RAG 检索参数
    retrieval_top_k: int = 20      # 向量召回候选数
    rerank_top_n: int = 5          # Rerank 精排后条数
    # 召回相关性阈值（余弦相似度，0=不启用）。真实 embedding 下可设如 0.3 过滤无关内容；
    # 伪向量模式分值无意义，保持 0 关闭。
    retrieval_min_score: float = 0.0

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


settings = Settings()
