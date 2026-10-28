"""飞书 SSO 自测：mock 飞书 API 覆盖完整 OAuth 流程"""
import json
import urllib.parse

from app.celery_app import celery_app

celery_app.conf.task_always_eager = True


def _mock_feishu_api(monkeypatch, open_id="ou_test12345", name="周敏"):
    import httpx

    class FakeResp:
        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

    def fake_post(url, **kwargs):
        if url.endswith("app_access_token/internal"):
            return FakeResp({"code": 0, "app_access_token": "t-app-xxx"})
        if url.endswith("oidc/access_token"):
            return FakeResp({"code": 0, "data": {"access_token": "u-user-xxx"}})
        raise AssertionError(f"unexpected POST: {url}")

    def fake_get(url, **kwargs):
        if url.endswith("user_info"):
            return FakeResp(
                {"code": 0, "data": {"name": name, "open_id": open_id, "employee_id": "E001"}}
            )
        raise AssertionError(f"unexpected GET: {url}")

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)


def _setup_sso(client):
    resp = client.put("/api/sso", json={
        "feishu_enabled": True,
        "feishu_app_id": "cli_test",
        "feishu_app_secret": "secret_test",
    })
    assert resp.status_code == 200
    return resp.json()


def test_sso_config_crud(client, anon_client):
    cfg = _setup_sso(client)
    assert cfg["feishu_enabled"] is True
    assert cfg["feishu_app_id"] == "cli_test"
    assert cfg["feishu_has_secret"] is True
    assert cfg["feishu_secret"] == ""  # 不回传明文
    # 匿名访问配置接口被拒
    assert anon_client.get("/api/sso").status_code == 401
    # sso-config 公开（登录页使用）
    resp = anon_client.get("/api/auth/sso-config")
    assert resp.json()["feishu"]["enabled"] is True


def test_feishu_login_redirect(client):
    _setup_sso(client)
    resp = client.get("/api/auth/feishu/login", follow_redirects=False)
    assert resp.status_code in (302, 307)
    loc = resp.headers["location"]
    assert "open.feishu.cn/open-apis/authen/v1/authorize" in loc
    assert "app_id=cli_test" in loc
    assert "redirect_uri=" in loc


def test_feishu_login_unconfigured(client, anon_client):
    # 重置配置（关闭并清空凭证）
    client.put("/api/sso", json={
        "feishu_enabled": False,
        "feishu_app_id": "",
        "feishu_app_secret": "",
    })
    resp = anon_client.get("/api/auth/feishu/login", follow_redirects=False)
    assert resp.status_code == 400


def test_feishu_callback_creates_user(client, anon_client, monkeypatch):
    _setup_sso(client)
    _mock_feishu_api(monkeypatch, open_id="ou_newuser", name="飞书新人")

    resp = anon_client.get("/api/auth/feishu/callback?code=fake-code", follow_redirects=False)
    assert resp.status_code in (302, 307)
    loc = resp.headers["location"]
    assert loc.startswith("/sso-callback?")
    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
    token = parsed["token"][0]
    user = json.loads(parsed["user"][0])
    assert user["display_name"] == "飞书新人"
    assert user["role"] == "business_user"

    # token 可用，且自动创建了本地账号（feishu_open_id 关联）
    me = anon_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"].startswith("feishu_")

    # 同 open_id 再次登录 → 复用同一账号（登录次数不新增用户）
    resp2 = anon_client.get("/api/auth/feishu/callback?code=fake-code-2", follow_redirects=False)
    loc2 = resp2.headers["location"]
    user2 = json.loads(urllib.parse.parse_qs(urllib.parse.urlparse(loc2).query)["user"][0])
    assert user2["id"] == user["id"]

    # 审计记录 sso_login
    logs = client.get("/api/audit?action=sso_login&page_size=50").json()["items"]
    assert len(logs) >= 1
    assert logs[0]["actor"].startswith("feishu_")


def test_feishu_callback_error(anon_client, monkeypatch):
    _setup_sso_pub = None
    import httpx

    class FakeResp:
        def json(self):
            return {"code": 19021, "msg": "invalid code"}

    monkeypatch.setattr(httpx, "post", lambda url, **kw: FakeResp())

    # 未配置时回调也应优雅跳转
    resp = anon_client.get("/api/auth/feishu/callback?code=bad", follow_redirects=False)
    loc = resp.headers["location"]
    assert "/login" in loc and "error" in loc
