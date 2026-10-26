"""应用模块自测：CRUD + 三种类型模板 + 应用级 SSE 对话（伪向量/模拟 LLM 降级模式）"""
import io
import json

from app.celery_app import celery_app

celery_app.conf.task_always_eager = True


def _create_kb(client, name: str) -> str:
    kb_id = client.post("/api/knowledge-bases", json={"name": name}).json()["id"]
    md = "# 产品制度\n\n## 考勤\n\n员工上班时间为早上九点整，迟到需请假。\n\n## 报销\n\n差旅报销需附发票。"
    client.post(
        f"/api/knowledge-bases/{kb_id}/documents",
        files={"file": ("rules.md", io.BytesIO(md.encode("utf-8")), "text/markdown")},
    )
    docs = client.get(f"/api/knowledge-bases/{kb_id}/documents").json()
    assert docs[0]["status"] == "done"
    return kb_id


def _chat_stream(client, app_id: str, query: str, conv_id: str | None = None):
    body = {"query": query, "role": "user"}
    if conv_id:
        body["conversation_id"] = conv_id
    events = []
    with client.stream("POST", f"/api/apps/{app_id}/chat", json=body) as resp:
        assert resp.status_code == 200, resp.text
        current = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
            elif line.startswith("data: ") and current:
                events.append((current, json.loads(line[6:])))
                current = None
    return events


def test_app_crud_and_templates(client):
    kb_id = _create_kb(client, "应用自测库")

    # 创建三种类型的应用，验证模板填充
    cases = {
        "qa": {"expect": ["系统支持哪些功能？"], "fallback": ""},
        "service": {"expect": ["如何联系人工客服？"], "fallback": "非常抱歉"},
        "report": {"expect": ["生成运营周报"], "fallback": ""},
    }
    app_ids = {}
    for app_type, info in cases.items():
        resp = client.post("/api/apps", json={
            "name": f"自测-{app_type}",
            "app_type": app_type,
            "kb_ids": [kb_id],
        })
        assert resp.status_code == 201, resp.text
        app = resp.json()
        assert app["app_type"] == app_type
        assert info["expect"][0] in app["suggested_questions"]
        assert info["fallback"] in app["fallback_reply"] or (not info["fallback"] and not app["fallback_reply"])
        assert app["system_prompt"]
        assert app["show_refs"] is True
        app_ids[app_type] = app["id"]

    # 非法类型
    resp = client.post("/api/apps", json={"name": "x", "app_type": "nope", "kb_ids": []})
    assert resp.status_code == 422
    # 不存在的知识库
    resp = client.post("/api/apps", json={"name": "x", "app_type": "qa", "kb_ids": ["no-such"]})
    assert resp.status_code == 404

    # 更新（自定义提示词 + 引用开关）
    resp = client.put(f"/api/apps/{app_ids['qa']}", json={
        "system_prompt": "自定义提示词",
        "show_refs": False,
        "temperature": 0.7,
    })
    assert resp.status_code == 200
    assert resp.json()["system_prompt"] == "自定义提示词"
    assert resp.json()["show_refs"] is False
    assert resp.json()["temperature"] == 0.7

    # 列表
    apps = client.get("/api/apps").json()
    assert len(apps) >= 3

    # 删除
    assert client.delete(f"/api/apps/{app_ids['report']}").status_code == 204
    assert client.get(f"/api/apps/{app_ids['report']}").status_code == 404

    return client, app_ids, kb_id


def test_app_chat_qa(client):
    kb_id = _create_kb(client, "问答应用库")
    app_id = client.post("/api/apps", json={"name": "问答助手", "app_type": "qa", "kb_ids": [kb_id]}).json()["id"]
    events = _chat_stream(client, app_id, "员工几点上班？")
    deltas = [d for e, d in events if e == "delta"]
    dones = [d for e, d in events if e == "done"]
    assert len(deltas) >= 2 and len(dones) == 1
    done = dones[0]
    assert done["app"]["app_type"] == "qa"
    assert done["refs"], "问答应用默认展示引用"
    # 日志带应用信息
    logs = client.get("/api/logs?page_size=50").json()["items"]
    row = next(l for l in logs if l["query"] == "员工几点上班？")
    assert row["app_id"] == app_id
    assert row["app_name"] == "问答助手"
    assert row["status"] == "success"


def test_app_chat_service_fallback(client):
    # 绑定空知识库 → 零召回 → 输出兜底话术（确定性验证，不受伪向量影响）
    empty_kb = client.post("/api/knowledge-bases", json={"name": "空客服库"}).json()["id"]
    app_id = client.post("/api/apps", json={"name": "智能客服", "app_type": "service", "kb_ids": [empty_kb]}).json()["id"]
    events = _chat_stream(client, app_id, "给我讲个笑话吧")
    dones = [d for e, d in events if e == "done"]
    assert len(dones) == 1
    answer = dones[0]["answer"]
    assert "非常抱歉" in answer and "人工客服" in answer
    assert dones[0]["models"]["llm"] == "none"  # 未调用 LLM，直接兜底


def test_app_chat_report_stream_and_multi_turn(client):
    kb_id = _create_kb(client, "报告应用库")
    app_id = client.post("/api/apps", json={"name": "报告助手", "app_type": "report", "kb_ids": [kb_id]}).json()["id"]
    events = _chat_stream(client, app_id, "分析考勤制度并给出建议")
    dones = [d for e, d in events if e == "done"]
    assert len(dones) == 1
    conv_id = dones[0]["conversation_id"]
    assert dones[0]["app"]["app_type"] == "report"
    # 多轮
    events2 = _chat_stream(client, app_id, "补充报销流程的建议", conv_id=conv_id)
    done2 = [d for e, d in events2 if e == "done"][0]
    msgs = client.get(f"/api/conversations/{conv_id}/messages").json()
    assert len(msgs) == 4
    # 应用会话列表过滤
    convs = client.get(f"/api/conversations?app_id={app_id}").json()
    assert convs[0]["app_id"] == app_id


def test_app_chat_not_found(client):
    with client.stream("POST", "/api/apps/no-such/chat", json={"query": "x", "role": "user"}) as resp:
        assert resp.status_code == 404
