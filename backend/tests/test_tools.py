"""Phase 3 工具模块 / 看板趋势 / 发布自测"""
import io
import json

from app.celery_app import celery_app

celery_app.conf.task_always_eager = True


def test_system_tools_seeded(client):
    tools = client.get("/api/tools").json()
    ids = {t["id"] for t in tools}
    assert "sys-export-word" in ids
    assert "sys-web-search" in ids
    export = next(t for t in tools if t["id"] == "sys-export-word")
    assert export["tool_type"] == "system"
    assert export["status"] == "available"
    web = next(t for t in tools if t["id"] == "sys-web-search")
    assert web["status"] == "beta"


def test_tool_crud_and_test(client):
    resp = client.post("/api/tools", json={
        "name": "自测 HTTP 工具",
        "description": "测试用",
        "tool_type": "http",
        "config": {"url": "http://127.0.0.1:9/none", "method": "GET"},
    })
    assert resp.status_code == 201
    tool_id = resp.json()["id"]
    # 更新
    resp = client.put(f"/api/tools/{tool_id}", json={"status": "beta"})
    assert resp.json()["status"] == "beta"
    # 试运行（优雅失败）
    resp = client.post(f"/api/tools/{tool_id}/test", json={"input": "hello"})
    assert "工具调用失败" in resp.json()["result"] or "失败" in resp.json()["result"]
    # 删除
    assert client.delete(f"/api/tools/{tool_id}").status_code == 204


def test_system_export_word(client):
    resp = client.post("/api/tools/sys-export-word/test", json={"input": "# 标题\n\n正文内容。\n\n- 要点一"})
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert "已生成 Word 文档" in result
    # 下载
    fname = result.split("：")[1].split("\n")[0].strip()
    dl = client.get(f"/api/tools/exports/{fname}")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/vnd.openxmlformats")


def test_flow_tool_ref_and_stats(client):
    """流程工具节点引用注册工具（导出 Word），调用统计递增"""
    flow = {
        "nodes": [
            {"id": "n1", "type": "start", "data": {}},
            {"id": "n2", "type": "tool", "data": {"tool_ref": "sys-export-word"}},
            {"id": "n3", "type": "answer", "data": {"content": "{{n2_output}}"}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ],
    }
    app = client.post("/api/apps", json={
        "name": "导出流程", "app_type": "qa", "app_kind": "chatflow", "kb_ids": []
    }).json()
    client.put(f"/api/apps/{app['id']}", json={"flow": flow})

    before = next(t for t in client.get("/api/tools").json() if t["id"] == "sys-export-word")["call_count"]
    events = []
    with client.stream("POST", f"/api/apps/{app['id']}/chat", json={"query": "# 周报\n\n本周完成三件事", "role": "user"}) as resp:
        current = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
            elif line.startswith("data: ") and current:
                events.append((current, json.loads(line[6:])))
                current = None
    dones = [d for e, d in events if e == "done"]
    assert len(dones) == 1
    assert "已生成 Word 文档" in dones[0]["answer"]
    after = next(t for t in client.get("/api/tools").json() if t["id"] == "sys-export-word")["call_count"]
    assert after == before + 1
    # 调用日志
    logs = client.get("/api/tools/sys-export-word/logs").json()
    assert len(logs) >= 1
    assert logs[0]["app_name"] == "导出流程"


def test_stats_trend(client):
    trend = client.get("/api/stats/trend?days=14").json()
    assert len(trend["calls"]) == 14
    assert len(trend["docs"]) == 14
    assert all(isinstance(v, int) for v in trend["calls"])
