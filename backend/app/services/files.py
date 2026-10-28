"""存储路径解析：兼容容器与宿主的路径差异"""
import os

from app.config import BASE_DIR, settings

CONTAINER_PREFIX = "/app/data"


def resolve_stored_path(file_path: str) -> str:
    """把 DB 中存储的文件路径解析为当前环境可访问的真实路径。

    策略：
    1. 直接存在 → 原样返回
    2. 按后缀映射到当前环境的 data 目录（兼容宿主绝对路径与容器 /app/data 路径互迁）
    3. 容器前缀 /app/data/... → 映射到本地 data 目录
    """
    if not file_path:
        return file_path
    if os.path.exists(file_path):
        return file_path

    # 按后缀映射：uploads / parsed
    for marker, base in (("/uploads/", settings.upload_dir), ("/parsed/", settings.parsed_dir)):
        if marker in file_path:
            suffix = file_path.split(marker, 1)[1]
            candidate = os.path.join(base, suffix)
            if os.path.exists(candidate):
                return candidate
            # 容器前缀兜底
            if file_path.startswith(CONTAINER_PREFIX):
                candidate2 = os.path.join(BASE_DIR, "data", suffix)
                if os.path.exists(candidate2):
                    return candidate2

    if file_path.startswith(CONTAINER_PREFIX):
        local = os.path.join(BASE_DIR, "data", file_path[len(CONTAINER_PREFIX):].lstrip("/"))
        if os.path.exists(local):
            return local
    if not os.path.isabs(file_path):
        local = os.path.join(BASE_DIR, "data", file_path)
        if os.path.exists(local):
            return local
    return file_path
