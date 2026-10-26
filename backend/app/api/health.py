from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["健康检查"])


@router.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name, "version": "0.1.0"}
