"""质量闭环：发布快照、评测门禁、AI 设计、反馈与旧库兼容。"""
import json
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.models import Application, User
from app.services.auth import issue_token


def _flow(answer="许可通过"):
    return {
        "nodes": [
            {"id": "start", "type": "start", "data": {}},
            {"id": "answer", "type": "answer", "data": {"content": answer}},
        ],
        "edges": [{"id": "edge", "source": "start", "target": "answer"}],
    }


@pytest.fixture
def quality(client):
    """每个测试只清理自己创建的数据，不依赖其他测试的运行顺序。"""
    resources = {"apps": [], "sets": [], "cases": []}

    def make_app(answer="许可通过", **config):
        created = client.post("/api/apps", json={
            "name": "质量闭环-" + uuid.uuid4().hex[:8],
            "app_kind": "chatflow",
        })
        assert created.status_code == 201, created.text
        app_id = created.json()["id"]
        resources["apps"].append(app_id)
        updated = client.put(f"/api/apps/{app_id}", json={"flow": _flow(answer), **config})
        assert updated.status_code == 200, updated.text
        return updated.json()

    def make_set(app_id="", gate=False):
        created = client.post("/api/eval/sets", json={"name": "质量回归集"})
        assert created.status_code == 201, created.text
        set_id = created.json()["id"]
        resources["sets"].append(set_id)
        updated = client.patch(f"/api/eval/sets/{set_id}", json={
            "app_id": app_id, "is_release_gate": gate,
        })
        assert updated.status_code == 200, updated.text
        return updated.json()

    def make_case(set_id, **config):
        created = client.post("/api/eval/cases", json={
            "set_id": set_id, "question": "是否许可？", **config,
        })
        assert created.status_code == 201, created.text
        case = created.json()["case"]
        resources["cases"].append(case["id"])
        return case

    yield make_app, make_set, make_case, resources
    for set_id in resources["sets"]:
        client.delete(f"/api/eval/sets/{set_id}")
    for case_id in resources["cases"]:
        client.delete(f"/api/eval/cases/{case_id}")
    for app_id in resources["apps"]:
        client.delete(f"/api/apps/{app_id}")


@pytest.fixture
def business_headers(client):
    with SessionLocal() as db:
        user = User(
            id=uuid.uuid4().hex,
            username="quality-" + uuid.uuid4().hex[:12],
            role="business_user",
            enabled=True,
        )
        db.add(user)
        db.commit()
        headers = {"Authorization": f"Bearer {issue_token(user)}"}
        user_id = user.id
    yield headers
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user:
            db.delete(user)
            db.commit()


def _done(client, app_id, *, public=False, headers=None, **payload):
    prefix = "/api/public/apps" if public else "/api/apps"
    response = client.post(
        f"{prefix}/{app_id}/chat", json={"query": "质量验证", **payload}, headers=headers,
    )
    assert response.status_code == 200, response.text
    event = ""
    events = []
    for line in response.text.splitlines():
        if line.startswith("event: "):
            event = line[7:].strip()
        elif line.startswith("data: "):
            events.append((event, json.loads(line[6:])))
    assert not [data for name, data in events if name == "error"], events
    dones = [data for name, data in events if name == "done"]
    assert len(dones) == 1, events
    return dones[0]


def _release(client, app_id, notes="回归验证"):
    response = client.post(f"/api/apps/{app_id}/release", json={"release_notes": notes})
    assert response.status_code == 200, response.text
    return response.json()


def test_release_validation_and_no_snapshot_on_failure(client, quality):
    make_app, _, _, _ = quality
    app = make_app()
    app_id = app["id"]
    invalid_configs = [
        {"name": " "},
        {"kb_ids": ["missing-quality-kb"]},
        {"llm_ref": "missing-quality-provider:model"},
        {"flow": {"nodes": [], "edges": []}},
    ]
    valid = {"name": app["name"], "kb_ids": [], "llm_ref": "", "flow": _flow()}
    for config in invalid_configs:
        assert client.put(f"/api/apps/{app_id}", json={**valid, **config}).status_code == 200
        check = client.get(f"/api/apps/{app_id}/release-check").json()
        assert check["issues"] and check["can_release"] is False
        response = client.post(f"/api/apps/{app_id}/release", json={"release_notes": "无效"})
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["message"] == "草稿校验未通过"
        assert response.json()["detail"]["issues"]
        releases = client.get(f"/api/apps/{app_id}/releases").json()
        assert releases["versions"] == [] and releases["published_version_id"] is None


def test_release_gate_blocks_then_passes_and_reuses_latest(client, quality):
    make_app, make_set, make_case, _ = quality
    app = make_app()
    app_id = app["id"]
    eval_set = make_set(app_id, gate=True)
    set_id = eval_set["id"]
    # 全部待补标准时也不能把空门禁视作通过。
    unready = make_case(set_id)
    assert unready["readiness"] == "needs_standard"
    assert client.post(f"/api/eval/sets/{set_id}/runs").status_code == 409
    assert client.get(f"/api/apps/{app_id}/release-check").json()["can_release"] is False
    ready = make_case(set_id, expected_keywords=["许可"], forbidden_keywords=["拒绝"])
    assert ready["readiness"] == "ready"
    assert client.post(f"/api/apps/{app_id}/release", json={"release_notes": "未评测"}).status_code == 409
    run = client.post(f"/api/eval/sets/{set_id}/run")
    assert run.status_code == 200, run.text
    assert run.json()["status"] == "success"
    assert run.json()["passed_count"] == 1 and run.json()["total_count"] == 1
    check = client.get(f"/api/apps/{app_id}/release-check").json()
    assert check["can_release"] is True and check["gates"][0]["passed"] is True
    first = _release(client, app_id)
    assert first["status"] == "published" and first["published_version"] == 1
    assert first["draft_dirty"] is False
    second = _release(client, app_id, "重复发布")
    assert second["published_version_id"] == first["published_version_id"]
    releases = client.get(f"/api/apps/{app_id}/releases").json()
    assert len(releases["versions"]) == 1
    assert releases["versions"][0]["is_published"] is True
    # 改草稿后，之前通过的结果不再允许发布。
    client.put(f"/api/apps/{app_id}", json={"system_prompt": "修改后的草稿"})
    stale = client.get(f"/api/apps/{app_id}/release-check").json()
    assert stale["draft_dirty"] is True and stale["gates"][0]["passed"] is False
    assert stale["gates"][0]["latest_run"]["matches_draft"] is False
    assert client.post(f"/api/apps/{app_id}/release", json={"release_notes": "过期结果"}).status_code == 409


def test_published_snapshot_draft_preview_rollback_and_public(client, quality):
    make_app, make_set, _, _ = quality
    app = make_app("线上回答", system_prompt="线上提示词", publish_enabled=True, opening="线上开场")
    app_id = app["id"]
    v1 = _release(client, app_id)
    client.put(f"/api/apps/{app_id}", json={
        "flow": _flow("草稿回答"), "system_prompt": "草稿提示词", "opening": "草稿开场",
    })
    online = _done(client, app_id)
    assert online["answer"] == "线上回答"
    online_trace = client.get(f"/api/observability/traces/{online['trace_id']}").json()
    assert online_trace["context"]["system_prompt"] == "线上提示词"
    preview = _done(client, app_id, draft=True)
    assert preview["answer"] == "草稿回答"
    preview_trace = client.get(f"/api/observability/traces/{preview['trace_id']}").json()
    assert preview_trace["context"]["system_prompt"] == "草稿提示词"
    # 公开入口忽略客户端传入的草稿请求，只使用线上配置。
    public = _done(client, app_id, public=True, draft=True)
    assert public["answer"] == "线上回答"
    assert client.get(f"/api/public/apps/{app_id}").json()["opening"] == "线上开场"
    v2 = _release(client, app_id)
    assert v2["published_version"] == 2
    assert _done(client, app_id)["answer"] == "草稿回答"
    make_set(app_id, gate=True)
    assert client.get(f"/api/apps/{app_id}/release-check").json()["can_release"] is False
    # 当前门禁不过，也允许切回已固化的历史版本。
    rolled_back = client.post(f"/api/apps/{app_id}/rollback", json={"version_id": v1["published_version_id"]})
    assert rolled_back.status_code == 200, rolled_back.text
    assert rolled_back.json()["published_version"] == 1
    assert rolled_back.json()["draft_dirty"] is True
    assert _done(client, app_id)["answer"] == "线上回答"
    assert client.get(f"/api/apps/{app_id}").json()["system_prompt"] == "草稿提示词"
    other = make_app()
    wrong = client.post(f"/api/apps/{other['id']}/rollback", json={"version_id": v1["published_version_id"]})
    assert wrong.status_code == 404


def test_business_runtime_permissions_and_unpublish(client, quality, business_headers):
    make_app, _, _, _ = quality
    app_id = make_app(publish_enabled=True)["id"]
    assert client.post("/api/apps", json={"name": "禁止绕过发布", "status": "published"}).status_code == 422
    assert client.put(f"/api/apps/{app_id}", json={"status": "published"}).status_code == 422
    draft = client.post(f"/api/apps/{app_id}/chat", json={"query": "x"}, headers=business_headers)
    assert draft.status_code == 409 and "尚未发布" in draft.json()["detail"]
    forbidden = client.post(f"/api/apps/{app_id}/chat", json={"query": "x", "draft": True}, headers=business_headers)
    assert forbidden.status_code == 403
    _release(client, app_id)
    assert _done(client, app_id, headers=business_headers)["answer"] == "许可通过"
    offline = client.post(f"/api/apps/{app_id}/unpublish")
    assert offline.status_code == 200 and offline.json()["status"] == "offline"
    assert offline.json()["published_version_id"]
    blocked = client.post(f"/api/apps/{app_id}/chat", json={"query": "x"}, headers=business_headers)
    assert blocked.status_code == 409 and "已下线" in blocked.json()["detail"]
    assert client.post(f"/api/public/apps/{app_id}/chat", json={"query": "x"}).status_code in (404, 409)
    assert _done(client, app_id)["answer"] == "许可通过"  # 搭建者下线后仍可调试草稿


def test_eval_steps_readiness_fingerprint_and_failed_rules(client, quality):
    make_app, make_set, make_case, _ = quality
    app_id = make_app("许可通过")["id"]
    set_id = make_set(app_id)["id"]
    make_case(set_id, expected_keywords=["许可"])
    make_case(set_id, require_citations=True, forbidden_keywords=["通过"], expected_keywords=["缺失词"])
    make_case(set_id)  # 待补标准不计入总数
    created = client.post(f"/api/eval/sets/{set_id}/runs")
    assert created.status_code == 201, created.text
    run = created.json()
    assert run["status"] == "running" and run["done_count"] == 0 and run["total_count"] == 2
    step_url = f"/api/eval/sets/{set_id}/runs/{run['id']}/step"
    first = client.post(step_url).json()
    assert first["status"] == "running" and first["done_count"] == 1
    second = client.post(step_url).json()
    assert second["status"] == "failed" and second["done_count"] == 2
    assert second["passed_count"] == 1 and second["failed_count"] == 1
    reasons = "；".join(next(r for r in second["results"] if not r["passed"])["reasons"])
    assert "缺少期望关键词" in reasons and "包含禁止关键词" in reasons and "没有引用来源" in reasons
    assert client.post(step_url).json()["done_count"] == 2
    pending = client.post(f"/api/eval/sets/{set_id}/runs").json()
    client.put(f"/api/apps/{app_id}", json={"system_prompt": "新指纹"})
    stale = client.post(f"/api/eval/sets/{set_id}/runs/{pending['id']}/step")
    assert stale.status_code == 409
    assert stale.json()["detail"] == "应用草稿在评测过程中被修改，请重新开始评测"
    history = client.get(f"/api/eval/sets/{set_id}/runs?limit=1").json()
    assert len(history) == 1 and history[0]["id"] == pending["id"]
    assert history[0]["matches_draft"] is False


def test_eval_unbound_set_and_case_standard_edit(client, quality):
    _, make_set, make_case, _ = quality
    set_id = make_set()["id"]
    case = make_case(set_id)
    assert client.post(f"/api/eval/sets/{set_id}/runs").status_code == 422
    updated = client.patch(f"/api/eval/cases/{case['id']}", json={
        "expected_keywords": ["许可"], "forbidden_keywords": ["拒绝"], "require_citations": True,
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["readiness"] == "ready"
    detail = client.get(f"/api/eval/sets/{set_id}").json()["cases"][0]
    assert detail["expected_keywords"] == ["许可"] and detail["require_citations"] is True


def test_ai_design_simulated_fallback_and_scene_rules(client, quality, monkeypatch):
    from app.services import eval_design
    from app.services.chat import FakeStreamingLLM

    monkeypatch.setattr(eval_design, "build_llm", lambda *args, **kwargs: (FakeStreamingLLM(), True, "fake-echo-llm"))
    make_app, _, _, resources = quality
    app = make_app(category="营销内容", suggested_questions=["如何撰写活动文案？"])
    rules = client.get(f"/api/eval/design-rules?app_id={app['id']}")
    assert rules.status_code == 200, rules.text
    data = rules.json()
    assert len(data["rules"]) == 7 and data["default_keys"]
    assert all("content" in rule["scenes"] for rule in data["rules"] if rule["key"] in data["default_keys"])
    response = client.post("/api/eval/ai-design", json={
        "app_id": app["id"], "rule_keys": data["default_keys"], "directions": "活动宣传合规", "count": 3,
    })
    assert response.status_code == 200, response.text
    generated = response.json()
    resources["sets"].append(generated["set"]["id"])
    resources["cases"].extend(c["id"] for c in generated["cases"])
    assert generated["simulated"] is True and len(generated["cases"]) == 3
    assert generated["set"]["app_id"] == app["id"]
    for case in generated["cases"]:
        assert case["source"] == "ai" and case["status"] == "confirmed" and case["label"] == "good"
        assert case["readiness"] == "ready" and "AI 设计" in case["tags"]
        assert len(case["tags"]) >= 2
    result = client.post(f"/api/eval/sets/{generated['set']['id']}/run")
    assert result.status_code == 200, result.text
    assert result.json()["done_count"] == 3


def test_feedback_upsert_cancel_and_public_app_scope(client, quality, business_headers):
    from app.models.chat import MessageFeedback

    make_app, _, _, _ = quality
    app_id = make_app(publish_enabled=True)["id"]
    _release(client, app_id)
    done = _done(client, app_id)
    message_id, conv_id = done["message_id"], done["conversation_id"]
    endpoint = f"/api/chat/messages/{message_id}/feedback"
    assert client.post(endpoint, json={"rating": 1}).json() == {"ok": True, "rating": 1}
    assert client.post(endpoint, json={"rating": -1, "comment": "回答需要补充"}).json()["rating"] == -1
    with SessionLocal() as db:
        rows = db.query(MessageFeedback).filter(MessageFeedback.message_id == message_id).all()
        assert len(rows) == 1 and rows[0].rating == -1 and rows[0].comment == "回答需要补充"
    messages = client.get(f"/api/conversations/{conv_id}/messages").json()
    assert next(m for m in messages if m["id"] == message_id)["feedback"] == -1
    other_view = client.get(f"/api/conversations/{conv_id}/messages", headers=business_headers).json()
    assert next(m for m in other_view if m["id"] == message_id)["feedback"] == 0
    assert client.post(endpoint, json={"rating": 0}).json() == {"ok": True, "rating": 0}
    with SessionLocal() as db:
        assert db.query(MessageFeedback).filter(MessageFeedback.message_id == message_id).count() == 0
    assert client.get(f"/api/conversations/{conv_id}/messages").json()[-1]["feedback"] == 0
    user_message = next(m for m in messages if m["role"] == "user")
    assert client.post(f"/api/chat/messages/{user_message['id']}/feedback", json={"rating": 1}).status_code in (404, 422)
    assert client.post(endpoint, json={"rating": 2}).status_code == 422
    visitor = _done(client, app_id, public=True)
    public_endpoint = f"/api/public/apps/{app_id}/messages/{visitor['message_id']}/feedback"
    assert client.post(public_endpoint, json={"rating": -1}).json()["rating"] == -1
    assert client.post(public_endpoint, json={"rating": 1}).json()["rating"] == 1
    assert client.post(public_endpoint, json={"rating": 0}).json()["rating"] == 0
    wrong_app = make_app(publish_enabled=True)["id"]
    _release(client, wrong_app)
    assert client.post(f"/api/public/apps/{wrong_app}/messages/{visitor['message_id']}/feedback", json={"rating": 1}).status_code == 404


def test_legacy_schema_startup_migration_is_idempotent(client, monkeypatch):
    """隔离 schema 模拟旧表缺列，避免修改其他用例正在使用的公共表。"""
    from app import main
    from app.models.application import AppVersion
    from app.services.app_release import migrate_app_releases

    schema = "quality_legacy_" + uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    legacy_engine = create_engine(
        engine.url,
        connect_args={"options": f"-csearch_path={schema},public"},
    ).execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(bind=legacy_engine)
        published_id, reviewing_id = uuid.uuid4().hex, uuid.uuid4().hex
        with Session(legacy_engine) as db:
            db.add_all([
                Application(id=published_id, name="旧线上应用", status="published", system_prompt="旧提示词"),
                Application(id=reviewing_id, name="旧评审应用", status="reviewing"),
            ])
            db.commit()
        with legacy_engine.begin() as conn:
            for table, columns in {
                "applications": ["published_version_id"],
                "eval_cases": ["expected_keywords", "forbidden_keywords", "require_citations"],
                "eval_sets": ["app_id", "is_release_gate"],
                "chat_logs": ["trace_id"],
            }.items():
                for column in columns:
                    conn.execute(text(f'ALTER TABLE "{schema}"."{table}" DROP COLUMN "{column}"'))
            # 旧库还没有这些新表，由下一步 create_all 自动创建。
            for table in ("app_versions", "eval_runs", "message_feedback"):
                conn.execute(text(f'DROP TABLE "{schema}"."{table}"'))
        monkeypatch.setattr(main, "engine", legacy_engine)
        # 与 lifespan 相同：新表 create_all，旧表 ensure_schema，然后回填旧应用。
        Base.metadata.create_all(bind=legacy_engine)
        main.ensure_schema()
        main.ensure_schema()
        with Session(legacy_engine) as db:
            migrate_app_releases(db)
            db.commit()
            migrate_app_releases(db)
            db.commit()
            published = db.get(Application, published_id)
            assert published.status == "published" and published.published_version_id
            version = db.get(AppVersion, published.published_version_id)
            assert version.version == 1 and version.snapshot["system_prompt"] == "旧提示词"
            assert db.query(AppVersion).filter(AppVersion.app_id == published_id).count() == 1
            assert db.get(Application, reviewing_id).status == "draft"
        inspector = inspect(legacy_engine)
        assert "published_version_id" in {c["name"] for c in inspector.get_columns("applications", schema=schema)}
        assert {"expected_keywords", "forbidden_keywords", "require_citations"} <= {
            c["name"] for c in inspector.get_columns("eval_cases", schema=schema)
        }
    finally:
        legacy_engine.dispose()
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_snapshot_fingerprint_unicode_order_and_detached_runtime():
    from app.models.application import AppVersion
    from app.services.app_release import runtime_app, snapshot_app, snapshot_fingerprint

    # 固定契约编码：默认 JSON 分隔符、键排序、UTF-8 中文，不转义为 ASCII。
    assert snapshot_fingerprint({"name": "中文应用", "temperature": 0.2, "flow": None}) == (
        "0ed8b065d56ff2d140a80373c6e8f618ac185db252376832879fb45f6b87fbd9"
    )
    app = Application(
        id="app", name="线上", kb_ids=["kb"], suggested_questions=["推荐问题"],
        flow=_flow("旧回答"), status="published", published_version_id="v1",
        version=1, publish_enabled=True, visitor_daily_limit=0,
    )
    snapshot = snapshot_app(app)
    version = AppVersion(id="v1", app_id="app", version=1, snapshot=snapshot)

    class VersionStore:
        def get(self, model, version_id):
            assert model is AppVersion and version_id == "v1"
            return version

    app.name = "编辑中的草稿"
    runtime = runtime_app(VersionStore(), app)
    assert inspect(runtime).transient and runtime.name == "线上"
    runtime.kb_ids.append("other")
    runtime.flow["nodes"][1]["data"]["content"] = "被改动的临时回答"
    assert app.kb_ids == ["kb"] and version.snapshot["kb_ids"] == ["kb"]
    assert app.flow["nodes"][1]["data"]["content"] == "旧回答"
    assert version.snapshot["flow"]["nodes"][1]["data"]["content"] == "旧回答"


@pytest.mark.parametrize(
    "rules, output, refs, reasons",
    [
        ({"expected_keywords": ["许可"], "forbidden_keywords": ["拒绝"]}, "许可通过", [{}], []),
        ({"expected_keywords": ["许可"], "forbidden_keywords": ["拒绝"], "require_citations": True},
         "拒绝", [], ["缺少期望关键词：许可", "包含禁止关键词：拒绝", "没有引用来源"]),
        ({"label": "bad", "reference_answer": " A B C "}, "a\nbc", [], []),
        ({"label": "bad", "reference_answer": "标准答案"}, "实际输出", [], ["输出与标准答案不一致"]),
        ({"label": "bad", "reference_answer": "其他答案", "expected_keywords": ["许可"]}, "许可", [], []),
    ],
)
def test_evaluate_case_rules_without_database(monkeypatch, rules, output, refs, reasons):
    from app.models.eval import EvalCase
    from app.services import eval_runner

    monkeypatch.setattr(eval_runner, "run_application", lambda *args: {
        "answer": output, "refs": refs, "models": {"fake": True},
    })
    case = EvalCase(id="case", question="问题", **rules)
    result = eval_runner.evaluate_case(Application(id="app"), case)
    assert result["passed"] is (not reasons) and result["reasons"] == reasons
    assert result["output"] == output and result["refs_count"] == len(refs)
    assert result["simulated"] is True


@pytest.mark.parametrize("error", [False, True])
def test_eval_sse_consumption_and_error_without_database(monkeypatch, error):
    from fastapi.responses import StreamingResponse
    from app.api import apps
    from app.models.eval import EvalCase
    from app.services.eval_runner import evaluate_case

    def response(app_id, req, source, application):
        assert app_id == "app" and req.draft is True and source == "eval"
        assert inspect(application).transient
        payload = {"message": "模型服务失败"} if error else {
            "answer": "许可通过", "refs": [{"title": "制度"}], "models": {"fake": True},
        }
        frame = f"event: {'error' if error else 'done'}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        # 切分帧以覆盖 StreamingResponse 迭代器并非逐事件返回的情形。
        return StreamingResponse(iter([frame[:15], frame[15:].encode("utf-8")]))

    monkeypatch.setattr(apps, "app_chat_response", response)
    result = evaluate_case(Application(id="app"), EvalCase(id="case", question="问题", expected_keywords=["许可"]))
    assert result["passed"] is (not error)
    if error:
        assert result["reasons"] == ["模型服务失败"]
    else:
        assert result["output"] == "许可通过" and result["simulated"] is True and result["refs_count"] == 1


def test_ai_design_fallback_without_database(monkeypatch):
    from app.services import eval_design

    class NoInvoke:
        def invoke(self, *args, **kwargs):
            pytest.fail("模拟模型应走规则兜底，无需调用模型")

    monkeypatch.setattr(eval_design, "build_llm", lambda *args, **kwargs: (NoInvoke(), True, "fake"))
    app = Application(
        id="app", name="报销助手", category="制度与合同审校", app_type="qa",
        llm_ref="", kb_ids=["kb"], suggested_questions=["报销需要什么？"],
    )
    cases, simulated = eval_design.design_cases(
        None, app, rule_keys=["knowledge_fact", "safety"], directions="差旅报销", count=3,
        knowledge_samples=["发票。报销必须提供原始凭证。"],
    )
    assert simulated is True and len(cases) == 3
    assert eval_design.app_scene(app) == "review"
    assert cases[0]["require_citations"] is True and "发票" in cases[0]["expected_keywords"]
    assert cases[1]["forbidden_keywords"] and all("AI 设计" in case["tags"] for case in cases)
