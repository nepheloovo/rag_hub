"""对话链路（RAG SSE 流式）与日志监测自测：无 Key 时走伪 embedding + 模拟 LLM"""
import io
import json

from app.celery_app import celery_app

celery_app.conf.task_always_eager = True


def _create_kb_with_md(client) -> str:
    kb_id = client.post("/api/knowledge-bases", json={"name": "对话自测库"}).json()["id"]
    md = "# 制度\n\n## 考勤\n\n员工上班时间为早上九点整。\n\n## 报销\n\n差旅报销需附发票。"
    client.post(
        f"/api/knowledge-bases/{kb_id}/documents",
        files={"file": ("attendance.md", io.BytesIO(md.encode("utf-8")), "text/markdown")},
    )
    docs = client.get(f"/api/knowledge-bases/{kb_id}/documents").json()
    assert docs[0]["status"] == "done"
    return kb_id


def _chat_stream(client, kb_id: str, query: str, role: str = "user", conv_id: str | None = None):
    body = {"kb_id": kb_id, "query": query, "role": role}
    if conv_id:
        body["conversation_id"] = conv_id
    events = []
    with client.stream("POST", "/api/chat", json=body) as resp:
        assert resp.status_code == 200
        current = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
            elif line.startswith("data: ") and current:
                events.append((current, json.loads(line[6:])))
                current = None
    return events


def test_chat_stream_and_log(client):
    kb_id = _create_kb_with_md(client)
    events = _chat_stream(client, kb_id, "员工几点上班？")

    deltas = [d for e, d in events if e == "delta"]
    dones = [d for e, d in events if e == "done"]
    assert len(deltas) >= 2
    assert len(dones) == 1
    done = dones[0]
    answer = "".join(d["text"] for d in deltas)
    assert answer == done["answer"]
    assert "模拟回答" in answer  # 未配置 Key，使用模拟 LLM
    assert done["refs"], "应有引用来源"
    assert done["refs"][0]["title"] == "attendance.md"
    assert done["tokens"]["total"] >= 0
    assert done["models"]["fake"] is True

    # 会话与消息已持久化
    msgs = client.get(f"/api/conversations/{done['conversation_id']}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["refs"]  # 引用已存

    # 日志已写入
    logs = client.get(f"/api/logs?q={done['conversation_id'][:8]}&page_size=50").json()
    logs = client.get("/api/logs?page_size=50").json()
    row = next(l for l in logs["items"] if l["query"] == "员工几点上班？")
    assert row["status"] == "success"
    assert row["duration_ms"] >= 0
    assert "kb_name" in row


def test_chat_multi_turn_history(client):
    kb_id = _create_kb_with_md(client)
    events = _chat_stream(client, kb_id, "第一个问题")
    conv_id = [d for e, d in events if e == "done"][0]["conversation_id"]
    events2 = _chat_stream(client, kb_id, "第二个问题", conv_id=conv_id)
    done2 = [d for e, d in events2 if e == "done"][0]
    msgs = client.get(f"/api/conversations/{conv_id}/messages").json()
    assert len(msgs) == 4  # 两轮四句
    assert done2["conversation_id"] == conv_id


def test_chat_empty_kb(client):
    kb_id = client.post("/api/knowledge-bases", json={"name": "空库"}).json()["id"]
    with client.stream("POST", "/api/chat", json={"kb_id": kb_id, "query": "x", "role": "user"}) as resp:
        body = b"".join(resp.iter_bytes())
    assert resp.status_code == 422


def test_chat_kb_not_found(client):
    with client.stream("POST", "/api/chat", json={"kb_id": "no-such-kb", "query": "x", "role": "user"}) as resp:
        body = b"".join(resp.iter_bytes())
    assert resp.status_code == 404


def test_logs_stats_and_filters(client):
    stats = client.get("/api/logs/stats").json()
    assert "today_count" in stats and "trend" in stats
    assert len(stats["trend"]) == 7
    # 角色过滤
    logs = client.get("/api/logs?role=user&page_size=50").json()
    assert all(l["role"] == "user" for l in logs["items"])
    # 状态过滤
    logs = client.get("/api/logs?status=success&page_size=50").json()
    assert all(l["status"] == "success" for l in logs["items"])


def test_conversation_crud(client):
    kb_id = _create_kb_with_md(client)
    conv = client.post("/api/conversations", json={"kb_id": kb_id, "title": "测试会话"}).json()
    assert conv["title"] == "测试会话"
    assert client.get(f"/api/conversations?kb_id={kb_id}").json()[0]["id"] == conv["id"]
    assert client.delete(f"/api/conversations/{conv['id']}").status_code == 204
    assert client.get(f"/api/conversations/{conv['id']}/messages").status_code == 404
