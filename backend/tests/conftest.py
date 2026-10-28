"""pytest 公共配置：使用独立的测试数据库，避免污染开发数据"""
import os

# 必须在导入 app 之前设置，确保 Settings 读取测试库
os.environ["DATABASE_URL"] = "postgresql+psycopg://rag:rag123456@localhost:5432/rag_zhongtai_test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    # 以上下文管理器方式使用，触发 lifespan（建表 + 预置数据）
    with TestClient(app) as c:
        # 以种子管理员登录并注入 token，使全部用例携带认证
        resp = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert resp.status_code == 200, f"管理员登录失败: {resp.text}"
        c.headers.update({"Authorization": f"Bearer {resp.json()['token']}"})
        yield c


@pytest.fixture(scope="session")
def anon_client():
    """未登录客户端（测试 401 行为）"""
    with TestClient(app) as c:
        yield c
