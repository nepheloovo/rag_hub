"""可观测与评测集自测：链路埋点、成本核算、Case 回流、评测集聚合与导出"""
import io
import json

from app.celery_app import celery_app


def setup_module():
    celery_app.conf.task_always_eager = True



def _create_kb_with_md(client, name: str = "观测自测库") -> str:
    kb_id = client.post("/api/knowledge-bases", json={"name": name}).json()["id"]
    md = "# 制度\n\n## 考勤\n\n员工上班时间为早上九点整。\n\n## 报销\n\n差旅报销需附发票。"
    client.post(
        f"/api/knowledge-bases/{kb_id}/documents",
        files={"file": ("attendance.md", io.BytesIO(md.encode("utf-8")), "text/markdown")},
    )
    return kb_id


def _chat(client, kb_id: str, query: str):
    body = {"kb_id": kb_id, "query": query, "role": "user"}
    done = None
    with client.stream("POST", "/api/chat", json=body) as resp:
        assert resp.status_code == 200
        current = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
            elif line.startswith("data: ") and current == "done":
                done = json.loads(line[6:])
    return done


def test_chat_creates_trace_with_spans(client):
    kb_id = _create_kb_with_md(client)
    done = _chat(client, kb_id, "员工几点上班？")
    trace_id = done["trace_id"]
    assert trace_id

    trace = client.get(f"/api/observability/traces/{trace_id}").json()
    assert trace["trace_type"] == "chat"
    assert trace["status"] == "success"
    assert trace["answer"] == done["answer"]
    types = [s["span_type"] for s in trace["spans"]]
    assert "retrieval.embed" in types
    assert "retrieval.search" in types
    assert "llm.call" in types
    assert trace["span_count"] == len(trace["spans"])
    # 代码解释必须随节点返回
    embed = next(s for s in trace["spans"] if s["span_type"] == "retrieval.embed")
    assert embed["code"]
    assert len(embed["code_explain"]) >= 2
    llm = next(s for s in trace["spans"] if s["span_type"] == "llm.call")
    assert llm["input"]["contexts"]
    assert llm["input"]["system_prompt"]

    # 日志关联 trace
    logs = client.get("/api/logs?page_size=50").json()["items"]
    row = next(x for x in logs if x["query"] == "员工几点上班？")
    assert row["trace_id"] == trace_id


def test_overview_billing_and_price(client):
    overview = client.get("/api/observability/overview?days=7").json()
    assert overview["total"] >= 1
    assert "trend" in overview

    billing = client.get("/api/observability/billing?days=7").json()
    assert billing["days"] == 7
    assert "by_day" in billing and len(billing["by_day"]) == 7
    assert "by_model" in billing

    prices = client.get("/api/observability/prices").json()
    assert any(p["model"] == "qwen-max" for p in prices)
    resp = client.put(
        "/api/observability/prices/qwen-max",
        json={"input_price": 2.4, "output_price": 9.6},
    )
    assert resp.status_code == 200


def test_trace_to_case_and_eval_set(client):
    kb_id = _create_kb_with_md(client, "回流自测库")
    done = _chat(client, kb_id, "报销需要发票吗？")
    trace_id = done["trace_id"]

    created = client.post(
        f"/api/observability/traces/{trace_id}/to-case",
        json={"label": "bad", "note": "测试回流", "tags": ["自测"]},
    )
    assert created.status_code == 200
    case_id = created.json()["case_id"]

    cases = client.get("/api/eval/cases?label=bad&page_size=50").json()
    row = next(c for c in cases["items"] if c["id"] == case_id)
    assert row["question"] == "报销需要发票吗？"
    assert row["trace_id"] == trace_id

    eval_set = client.post(
        "/api/eval/sets",
        json={"name": "自测回归集", "description": "自动化测试", "case_ids": [case_id]},
    ).json()
    set_id = eval_set["id"]
    assert eval_set["bad_count"] == 1

    detail = client.get(f"/api/eval/sets/{set_id}").json()
    assert len(detail["cases"]) == 1

    exported = client.get(f"/api/eval/sets/{set_id}/export")
    assert exported.status_code == 200
    assert "报销需要发票吗？" in exported.text

    added = client.post(f"/api/eval/sets/{set_id}/cases", json={"case_ids": [case_id]})
    assert added.json()["added"] == 0  # 幂等：重复加入不重复计数

    client.delete(f"/api/eval/sets/{set_id}/cases/{case_id}")
    assert client.get(f"/api/eval/sets/{set_id}").json()["case_count"] == 0
    client.delete(f"/api/eval/sets/{set_id}")
    client.delete(f"/api/eval/cases/{case_id}")


def test_demo_data_and_builds(client):
    demo = client.post("/api/observability/demo")
    assert demo.status_code == 200
    builds = client.get("/api/observability/builds?page_size=50").json()
    assert builds["total"] >= 1
    first = builds["items"][0]
    assert any(s["span_type"].startswith("build.") for s in first["stages"])
