"""运营洞察：满意度 / 命中率 / 知识缺口聚类 / 最新差评 / 日志反馈筛选 / 评测流量排除 / 补充知识"""
import json
import uuid

from app.celery_app import celery_app
from app.services.insights import cluster_questions, question_terms

celery_app.conf.task_always_eager = True


def _chat(client, app_id: str, query: str, role: str = "user") -> dict:
    """调用应用对话，返回 SSE done 事件数据"""
    resp = client.post(f"/api/apps/{app_id}/chat", json={"query": query, "role": role})
    assert resp.status_code == 200, resp.text
    for frame in resp.text.split("\n\n"):
        if frame.startswith("event: done"):
            return json.loads(frame.split("data: ", 1)[1])
    raise AssertionError(f"没有 done 事件：{resp.text[:300]}")


def _miss_app(client) -> tuple[dict, dict]:
    """绑定一个空知识库的应用：每次回答都没有引用 = 未命中"""
    kb = client.post("/api/knowledge-bases", json={"name": "缺口库-" + uuid.uuid4().hex[:6]}).json()
    app = client.post("/api/apps", json={
        "name": "缺口应用-" + uuid.uuid4().hex[:6], "app_type": "qa", "kb_ids": [kb["id"]],
    }).json()
    return app, kb


def test_cluster_questions_groups_similar():
    t0 = "2026-10-01T00:00:00"
    items = [
        {"question": "海外订单的保修政策是什么？", "kind": "miss", "app_name": "客服", "kb_names": ["售后"], "time": t0},
        {"question": "海外订单保修政策", "kind": "dislike", "app_name": "客服", "kb_names": ["售后"], "time": "2026-10-02"},
        {"question": "异地办公的通讯补贴标准", "kind": "miss", "app_name": "制度", "kb_names": ["制度库"], "time": "2026-10-03"},
    ]
    clusters = cluster_questions(items)
    assert len(clusters) == 2
    top = clusters[0]
    assert top["count"] == 2 and top["dislike_count"] == 1 and top["miss_count"] == 1
    assert top["question"] == "海外订单的保修政策是什么？"
    assert len(top["sample_questions"]) == 2
    assert question_terms("E07") == {"e07"}


def test_feedback_overview_gaps_and_bad_feedback(client):
    app, kb = _miss_app(client)
    question = f"海外订单的保修政策 {uuid.uuid4().hex[:4]}"
    done = _chat(client, app["id"], question)
    assert done["refs"] == []

    before = client.get("/api/stats/overview").json()
    assert {"satisfaction", "like_count", "dislike_count", "hit_rate", "miss_count"} <= set(before)
    assert before["miss_count"] >= 1

    assert client.post(f"/api/chat/messages/{done['message_id']}/feedback",
                       json={"rating": -1, "comment": "答非所问"}).status_code == 200
    after = client.get("/api/stats/overview").json()
    assert after["dislike_count"] == before["dislike_count"] + 1
    assert after["satisfaction"] is not None

    gaps = client.get(f"/api/stats/knowledge-gaps?app_id={app['id']}").json()
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["question"] == question and gap["dislike_count"] == 1
    assert gap["kb_ids"] == [kb["id"]] and gap["apps"] == [app["name"]]

    bad = client.get("/api/stats/bad-feedback").json()
    mine = next(item for item in bad if item["message_id"] == done["message_id"])
    assert mine["question"] == question and mine["comment"] == "答非所问"
    assert mine["trace_id"] == done["trace_id"]


def test_logs_feedback_filter(client):
    app, _ = _miss_app(client)
    liked = _chat(client, app["id"], "点赞问题 " + uuid.uuid4().hex[:4])
    disliked = _chat(client, app["id"], "点踩问题 " + uuid.uuid4().hex[:4])
    client.post(f"/api/chat/messages/{liked['message_id']}/feedback", json={"rating": 1})
    client.post(f"/api/chat/messages/{disliked['message_id']}/feedback", json={"rating": -1})

    rows = client.get("/api/logs?feedback=dislike&page_size=100").json()["items"]
    traces = {r["trace_id"]: r["feedback"] for r in rows}
    assert traces.get(disliked["trace_id"]) == -1 and liked["trace_id"] not in traces

    rows = client.get("/api/logs?feedback=like&page_size=100").json()["items"]
    traces = {r["trace_id"]: r["feedback"] for r in rows}
    assert traces.get(liked["trace_id"]) == 1 and disliked["trace_id"] not in traces

    plain = client.get("/api/logs?page_size=100").json()["items"]
    assert all("feedback" in r for r in plain)


def test_eval_traffic_excluded(client):
    app, _ = _miss_app(client)
    before = client.get("/api/stats/overview").json()
    logs_before = client.get("/api/logs/stats").json()["today_count"]
    done = _chat(client, app["id"], "评测问题 " + uuid.uuid4().hex[:4], role="eval")

    after = client.get("/api/stats/overview").json()
    assert after["month_app_calls"] == before["month_app_calls"]
    assert after["miss_count"] == before["miss_count"]
    assert client.get("/api/logs/stats").json()["today_count"] == logs_before
    default_rows = client.get("/api/logs?page_size=100").json()["items"]
    assert done["trace_id"] not in {r["trace_id"] for r in default_rows}
    eval_rows = client.get("/api/logs?role=eval&page_size=100").json()["items"]
    assert done["trace_id"] in {r["trace_id"] for r in eval_rows}
    gaps = client.get(f"/api/stats/knowledge-gaps?app_id={app['id']}").json()
    assert gaps == []


def test_supplement_knowledge_creates_document(client):
    _, kb = _miss_app(client)
    resp = client.post("/api/stats/knowledge-gaps/supplement", json={
        "kb_id": kb["id"], "question": "海外订单的保修政策？", "answer": "海外订单整机保修 3 年。",
    })
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    assert doc["filename"].startswith("知识补充-") and doc["filename"].endswith(".md")
    docs = client.get(f"/api/knowledge-bases/{kb['id']}/documents").json()
    assert any(d["id"] == doc["id"] for d in docs)
    assert client.post("/api/stats/knowledge-gaps/supplement", json={
        "kb_id": "missing", "question": "q", "answer": "a",
    }).status_code == 404
