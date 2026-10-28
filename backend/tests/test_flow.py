"""Chat Flow 执行器与编排 API 自测"""
import io
import json

from app.celery_app import celery_app

celery_app.conf.task_always_eager = True


def _create_kb(client, name: str) -> str:
    kb_id = client.post("/api/knowledge-bases", json={"name": name}).json()["id"]
    md = "# 售后政策\n\n## 退换货\n\n七日内无理由退货，退货运费由客户承担。\n\n## 保修\n\n整机保修 5 年。"
    client.post(
        f"/api/knowledge-bases/{kb_id}/documents",
        files={"file": ("policy.md", io.BytesIO(md.encode("utf-8")), "text/markdown")},
    )
    return kb_id


def _flow_start_answer(content: str) -> dict:
    return {
        "nodes": [
            {"id": "n1", "type": "start", "data": {}, "position": {"x": 0, "y": 0}},
            {"id": "n2", "type": "answer", "data": {"content": content}, "position": {"x": 300, "y": 0}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }


def _chat(client, app_id, query, conv_id=None):
    body = {"query": query, "role": "user"}
    if conv_id:
        body["conversation_id"] = conv_id
    events = []
    with client.stream("POST", f"/api/apps/{app_id}/chat", json=body) as resp:
        current = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
            elif line.startswith("data: ") and current:
                events.append((current, json.loads(line[6:])))
                current = None
    return events


def test_validate_flow():
    from app.services.flow import validate_flow

    assert validate_flow(None) != []
    assert validate_flow({"nodes": [{"id": "n1", "type": "answer"}], "edges": []}) != []
    ok = {
        "nodes": [
            {"id": "n1", "type": "start", "data": {}},
            {"id": "n2", "type": "answer", "data": {"content": "你好 {{input}}"}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }
    assert validate_flow(ok) == []
    # 无效连线
    bad = {**ok, "edges": [{"id": "e1", "source": "n1", "target": "nX"}]}
    assert any("无效连线" in p for p in validate_flow(bad))


def test_render_template():
    from app.services.flow import render_template

    assert render_template("你好 {{name}}", {"name": "知枢"}) == "你好 知枢"
    assert render_template("{{missing}} x", {}) == " x"


def test_chatflow_start_answer(client):
    """最简流程：start → answer（变量模板），流式输出"""
    app = client.post("/api/apps", json={
        "name": "流程测试", "app_type": "qa", "app_kind": "chatflow", "kb_ids": []
    }).json()
    client.put(f"/api/apps/{app['id']}", json={"flow": _flow_start_answer("你说的是：{{input}}")})

    events = _chat(client, app["id"], "测试问题")
    dones = [d for e, d in events if e == "done"]
    assert len(dones) == 1
    assert dones[0]["answer"] == "你说的是：测试问题"
    assert dones[0]["models"]["llm"] == "chatflow"


def test_chatflow_condition_branch(client):
    """条件分支：包含「退货」走 true 出口"""
    flow = {
        "nodes": [
            {"id": "n1", "type": "start", "data": {}},
            {"id": "n2", "type": "condition", "data": {"left": "{{input}}", "op": "contains", "value": "退货"}},
            {"id": "n3", "type": "answer", "data": {"content": "退货场景回答"}},
            {"id": "n4", "type": "answer", "data": {"content": "其他场景回答"}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3", "source_handle": "true"},
            {"id": "e3", "source": "n2", "target": "n4", "source_handle": "false"},
        ],
    }
    app = client.post("/api/apps", json={
        "name": "分支测试", "app_type": "qa", "app_kind": "chatflow", "kb_ids": []
    }).json()
    client.put(f"/api/apps/{app['id']}", json={"flow": flow})

    dones = [d for e, d in _chat(client, app["id"], "我要退货怎么办理") if e == "done"]
    assert dones[0]["answer"] == "退货场景回答"
    dones2 = [d for e, d in _chat(client, app["id"], "保修多久") if e == "done"]
    assert dones2[0]["answer"] == "其他场景回答"


def test_chatflow_retrieval_refs(client):
    """检索节点：回答引用来源"""
    kb_id = _create_kb(client, "流程检索库")
    flow = {
        "nodes": [
            {"id": "n1", "type": "start", "data": {}},
            {"id": "n2", "type": "retrieval", "data": {"kb_ids": [kb_id], "top_k": 3}},
            {"id": "n3", "type": "answer", "data": {"content": "资料：{{n2_output}}"}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ],
    }
    app = client.post("/api/apps", json={
        "name": "检索流程", "app_type": "qa", "app_kind": "chatflow", "kb_ids": [kb_id]
    }).json()
    client.put(f"/api/apps/{app['id']}", json={"flow": flow})

    events = _chat(client, app["id"], "退货政策是什么")
    dones = [d for e, d in events if e == "done"]
    assert len(dones) == 1
    assert "资料：" in dones[0]["answer"]
    assert dones[0]["refs"], "检索节点应产生引用"


def test_chatflow_missing_flow_422(client):
    app = client.post("/api/apps", json={
        "name": "空流程", "app_type": "qa", "app_kind": "chatflow", "kb_ids": []
    }).json()
    with client.stream("POST", f"/api/apps/{app['id']}/chat", json={"query": "x", "role": "user"}) as resp:
        assert resp.status_code == 422


def test_flow_versions_and_restore(client):
    app = client.post("/api/apps", json={
        "name": "版本测试", "app_type": "qa", "app_kind": "chatflow", "kb_ids": []
    }).json()
    v1 = _flow_start_answer("第一版 {{input}}")
    v2 = _flow_start_answer("第二版 {{input}}")
    a = client.put(f"/api/apps/{app['id']}", json={"flow": v1}).json()
    b = client.put(f"/api/apps/{app['id']}", json={"flow": v2}).json()
    assert b["version"] == a["version"] + 1

    versions = client.get(f"/api/apps/{app['id']}/versions").json()
    assert versions["current"] == b["version"]
    assert len(versions["versions"]) >= 2

    # 恢复到第一版
    restored = client.post(f"/api/apps/{app['id']}/restore", json={"version": a["version"]}).json()
    assert restored["version"] == b["version"] + 1
    assert "第一版" in json.dumps(restored["flow"], ensure_ascii=False)

    # 不存在的版本
    resp = client.post(f"/api/apps/{app['id']}/restore", json={"version": 999})
    assert resp.status_code == 404


def test_chatflow_tool_error(client):
    """工具节点：无效 URL 应抛出可读错误"""
    flow = {
        "nodes": [
            {"id": "n1", "type": "start", "data": {}},
            {"id": "n2", "type": "tool", "data": {"url": "http://127.0.0.1:9/none", "method": "GET"}},
            {"id": "n3", "type": "answer", "data": {"content": "{{n2_output}}"}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ],
    }
    app = client.post("/api/apps", json={
        "name": "工具测试", "app_type": "qa", "app_kind": "chatflow", "kb_ids": []
    }).json()
    client.put(f"/api/apps/{app['id']}", json={"flow": flow})

    events = _chat(client, app["id"], "调用工具")
    errs = [d for e, d in events if e == "error"]
    assert errs and "工具调用失败" in errs[0]["message"]
