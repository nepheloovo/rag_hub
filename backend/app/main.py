"""FastAPI 应用入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import apps, chat, health, knowledge, logs, providers, stats
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.provider_service import seed_presets


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 开发期直接建表（后续接入 Alembic 迁移）
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_presets(db)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(providers.router, prefix=settings.api_prefix)
app.include_router(knowledge.kb_router, prefix=settings.api_prefix)
app.include_router(knowledge.doc_router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(apps.router, prefix=settings.api_prefix)
app.include_router(logs.router, prefix=settings.api_prefix)
app.include_router(stats.router, prefix=settings.api_prefix)
