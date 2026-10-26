"""模型服务商配置模块自测"""
import uuid


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_preset_providers_seeded(client):
    resp = client.get("/api/providers")
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()}
    assert {"tongyi", "openrouter", "aihubmix"} <= ids
    tongyi = next(p for p in resp.json() if p["id"] == "tongyi")
    assert "text-embedding-v3" in tongyi["models"]["embedding"]
    assert "gte-rerank" in tongyi["models"]["rerank"]
    assert "qwen-max" in tongyi["models"]["llm"]


def test_defaults_get(client):
    resp = client.get("/api/providers/defaults/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_embedding"] == "tongyi:text-embedding-v3"
    assert data["default_rerank"] == "tongyi:gte-rerank"
    assert data["default_llm"] == "tongyi:qwen-max"


def test_provider_crud(client):
    name = f"自测服务商-{uuid.uuid4().hex[:6]}"
    # 创建
    resp = client.post("/api/providers", json={
        "name": name,
        "base_url": "http://127.0.0.1:9/v1",
        "models": {"embedding": ["e1"], "rerank": [], "llm": ["l1"]},
    })
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]
    assert resp.json()["models"]["llm"] == ["l1"]

    # 更新（追加模型 + 启用）
    resp = client.put(f"/api/providers/{pid}", json={
        "enabled": True,
        "models": {"rerank": ["r1"]},
    })
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True
    assert resp.json()["models"]["rerank"] == ["r1"]
    assert resp.json()["models"]["llm"] == ["l1"]  # 原字段保留

    # 连通性测试：无 Key 时应优雅返回失败而非 500
    resp = client.post(f"/api/providers/{pid}/test", json={"model_type": "llm"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert "API Key" in resp.json()["message"]

    # 删除
    resp = client.delete(f"/api/providers/{pid}")
    assert resp.status_code == 204
    ids = {p["id"] for p in client.get("/api/providers").json()}
    assert pid not in ids


def test_provider_not_found(client):
    resp = client.put("/api/providers/not-exist", json={"enabled": True})
    assert resp.status_code == 404


def test_defaults_update_and_restore(client):
    resp = client.put("/api/providers/defaults/models", json={"default_llm": "tongyi:qwen-turbo"})
    assert resp.status_code == 200
    assert resp.json()["default_llm"] == "tongyi:qwen-turbo"
    # 恢复
    client.put("/api/providers/defaults/models", json={"default_llm": "tongyi:qwen-max"})
    resp = client.get("/api/providers/defaults/models")
    assert resp.json()["default_llm"] == "tongyi:qwen-max"
