"""存储路径解析：兼容容器与宿主的路径差异"""
import os

from app.config import BASE_DIR, settings

CONTAINER_PREFIX = "/app/data"


def resolve_stored_path(file_path: str) -> str:
    """把 DB 中存储的文件路径解析为当前环境可访问的真实路径。
    - 直接存在 → 原样返回
    - 容器路径 /app/data/... → 映射到本地 data 目录（宿主开发场景）
    - 相对路径 → 基于 BASE_DIR/data 解析
    """
    if not file_path:
        return file_path
    if os.path.exists(file_path):
        return file_path
    if file_path.startswith(CONTAINER_PREFIX):
        local = os.path.join(BASE_DIR, "data", file_path[len(CONTAINER_PREFIX):].lstrip("/"))
        if os.path.exists(local):
            return local
    if not os.path.isabs(file_path):
        local = os.path.join(BASE_DIR, "data", file_path)
        if os.path.exists(local):
            return local
    return file_path
