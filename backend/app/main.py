"""FastAPI 应用入口"""
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import (
    apps,
    audit,
    auth,
    chat,
    eval as eval_api,
    health,
    knowledge,
    logs,
    observability,
    providers,
    public,
    sso,
    stats,
    tools,
    users,
)
from app.api.deps import get_current_user, require_roles
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import User
from app.services.auth import hash_password
from app.services.observability import seed_prices
from app.services.provider_service import seed_presets
from app.services.tools import seed_system_tools

DEFAULT_ADMIN = ("admin", "admin123")


def seed_admin(db) -> None:
    username, password = DEFAULT_ADMIN
    if not db.query(User).filter(User.username == username).first():
        db.add(
            User(
                id=uuid.uuid4().hex,
                username=username,
                display_name="系统管理员",
                department="平台",
                role="platform_admin",
                password_hash=hash_password(password),
            )
        )
        db.commit()


def ensure_schema() -> None:
    """开发期轻量迁移：新表由 create_all 创建，旧表补列保持兼容"""
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS trace_id VARCHAR(32) DEFAULT ''")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_chat_logs_trace_id ON chat_logs (trace_id)")
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 开发期直接建表（后续接入 Alembic 迁移）
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    with SessionLocal() as db:
        seed_presets(db)
        seed_system_tools(db)
        seed_admin(db)
        seed_prices(db)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 公开与认证接口
app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(public.router, prefix=settings.api_prefix)

# 登录后可用
app.include_router(
    chat.router, prefix=settings.api_prefix, dependencies=[Depends(get_current_user)]
)
app.include_router(
    apps.router, prefix=settings.api_prefix, dependencies=[Depends(get_current_user)]
)
app.include_router(
    knowledge.kb_router, prefix=settings.api_prefix, dependencies=[Depends(get_current_user)]
)
app.include_router(
    knowledge.doc_router, prefix=settings.api_prefix, dependencies=[Depends(get_current_user)]
)
app.include_router(
    tools.router, prefix=settings.api_prefix, dependencies=[Depends(get_current_user)]
)
app.include_router(
    stats.router, prefix=settings.api_prefix, dependencies=[Depends(get_current_user)]
)
app.include_router(
    logs.router,
    prefix=settings.api_prefix,
    dependencies=[Depends(require_roles("platform_admin"))],
)
app.include_router(
    observability.router,
    prefix=settings.api_prefix,
    dependencies=[Depends(require_roles("platform_admin", "app_developer", "kb_admin"))],
)
app.include_router(
    eval_api.router,
    prefix=settings.api_prefix,
    dependencies=[Depends(require_roles("platform_admin", "app_developer", "kb_admin"))],
)
app.include_router(
    providers.router,
    prefix=settings.api_prefix,
    dependencies=[Depends(require_roles("platform_admin"))],
)
app.include_router(
    users.router, prefix=settings.api_prefix, dependencies=[Depends(get_current_user)]
)
app.include_router(
    audit.router, prefix=settings.api_prefix, dependencies=[Depends(get_current_user)]
)

app.include_router(
    sso.router,
    prefix=settings.api_prefix,
    dependencies=[Depends(require_roles("platform_admin"))],
)
