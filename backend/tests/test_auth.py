"""Phase 4 认证 / 成员管理 / 审计 / 权限自测"""
import io
import json

from app.celery_app import celery_app

celery_app.conf.task_always_eager = True


def test_login_and_me(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    me = resp.json()
    assert me["username"] == "admin"
    assert me["role"] == "platform_admin"


def test_unauthorized_without_token(anon_client):
    assert anon_client.get("/api/knowledge-bases").status_code == 401
    assert anon_client.get("/api/apps").status_code == 401
    # 公开接口无需登录
    assert anon_client.get("/api/auth/sso-config").status_code == 200


def test_login_wrong_password(anon_client):
    resp = anon_client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_user_crud_and_role_guard(client, anon_client):
    # 创建成员
    resp = client.post("/api/users", json={
        "username": "zhangsan",
        "display_name": "张三",
        "department": "客服中心",
        "role": "business_user",
        "password": "pass123456",
    })
    assert resp.status_code == 201
    uid = resp.json()["id"]

    # 更新角色与停用
    resp = client.put(f"/api/users/{uid}", json={"role": "kb_admin", "display_name": "张三丰"})
    assert resp.json()["role"] == "kb_admin"
    assert resp.json()["display_name"] == "张三丰"

    # 成员用自身账号登录，无权限访问用户管理
    login = anon_client.post("/api/auth/login", json={"username": "zhangsan", "password": "pass123456"})
    assert login.status_code == 200
    token = login.json()["token"]
    resp = anon_client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403  # 非平台管理员
    # 业务角色可访问应用列表
    resp = anon_client.get("/api/apps", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    # 停用后无法登录
    client.put(f"/api/users/{uid}", json={"enabled": False})
    resp = anon_client.post("/api/auth/login", json={"username": "zhangsan", "password": "pass123456"})
    assert resp.status_code == 403


def test_audit_logs(client):
    # 登录与成员操作应产生审计记录
    logs = client.get("/api/audit?page_size=50").json()["items"]
    actions = {l["action"] for l in logs}
    assert "login" in actions
    # 成员操作按动作过滤查询，避免被其他用例产生的较新审计记录挤出首页
    filtered = client.get("/api/audit?action=user").json()["items"]
    assert {"user_create", "user_update"} & {l["action"] for l in filtered}
    assert all("user" in l["action"] for l in filtered)


def test_role_guard_on_mutations(client, anon_client):
    # 创建业务使用者并登录
    client.post("/api/users", json={
        "username": "lisi", "display_name": "李四", "role": "business_user", "password": "pass123456"
    })
    token = anon_client.post("/api/auth/login", json={"username": "lisi", "password": "pass123456"}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    # 业务使用者不能创建应用/知识库/工具
    assert anon_client.post("/api/apps", headers=headers, json={"name": "x", "app_type": "qa", "kb_ids": []}).status_code == 403
    assert anon_client.post("/api/knowledge-bases", headers=headers, json={"name": "x"}).status_code == 403
    assert anon_client.post("/api/tools", headers=headers, json={"name": "x"}).status_code == 403
    # 对话可用
    kb = client.post("/api/knowledge-bases", json={"name": "权限库"}).json()
    client.post(f"/api/knowledge-bases/{kb['id']}/documents", files={"file": ("a.md", io.BytesIO("# T\n\n内容。".encode()), "text/markdown")})
    app = client.post("/api/apps", json={"name": "权限应用", "app_type": "qa", "kb_ids": [kb["id"]]}).json()
    # 未发布应用业务使用者不可用，也不能调试草稿
    assert anon_client.post(f"/api/apps/{app['id']}/chat", headers=headers, json={"query": "x", "role": "user"}).status_code == 409
    assert anon_client.post(f"/api/apps/{app['id']}/chat", headers=headers, json={"query": "x", "role": "user", "draft": True}).status_code == 403
    assert client.post(f"/api/apps/{app['id']}/release", json={"release_notes": "v1"}).status_code == 200
    with anon_client.stream("POST", f"/api/apps/{app['id']}/chat", headers=headers, json={"query": "x", "role": "user"}) as resp:
        assert resp.status_code == 200
