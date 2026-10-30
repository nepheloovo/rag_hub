"""知识库强化：逐文件切块配置 / 分块增强 / 混合检索 / 文本与网页导入 / 分块编辑 / 应用检索参数"""
import io
import json
import uuid

import pytest

from app.celery_app import celery_app
from app.services.chunk_enhancement import chunk_index_text, rule_keywords
from app.services.retrieval import normalize_retrieval, query_terms
from app.services.web_import import html_to_markdown



@pytest.fixture(autouse=True)
def eager_celery():
    # test_knowledge.py 的夹具会在结束时关闭 eager，这里每个用例显式打开
    celery_app.conf.task_always_eager = True
    yield

DOC = """# 故障处理

## 常见故障代码
E07 BMS 通讯中断：检查 CAN 通讯线及终端电阻。储能柜断电 5 分钟后重新上电。
E01 电池过温：检查散热风道是否堵塞，环境温度是否超过 50 度。

## 质保说明
储能柜整机保修 5 年，电芯保修 10 年或 6000 次循环，以先到者为准。
"""


def _kb(client) -> dict:
    return client.post("/api/knowledge-bases", json={"name": "强化库-" + uuid.uuid4().hex[:6]}).json()


def _upload(client, kb_id: str, config: dict | None = None, text: str = DOC) -> dict:
    data = {"config": json.dumps(config)} if config else {}
    resp = client.post(
        f"/api/knowledge-bases/{kb_id}/documents",
        files={"file": ("手册.md", io.BytesIO(text.encode()), "text/markdown")},
        data=data,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _chunks(client, doc_id: str) -> list[dict]:
    return client.get(f"/api/documents/{doc_id}/chunks?limit=100").json()


def test_pure_helpers():
    assert normalize_retrieval({"mode": "bad", "top_k": 500, "top_n": 50, "score_threshold": 3})["mode"] == "semantic"
    opts = normalize_retrieval({"mode": "hybrid", "top_k": 10, "top_n": 50, "score_threshold": 3, "rerank": False})
    assert opts == {"mode": "hybrid", "top_k": 10, "top_n": 10, "score_threshold": 1.0, "rerank": False}
    assert query_terms("E07 报警") == ["e07", "报警"]
    assert "储能柜" in rule_keywords("储能柜保修。储能柜电芯。储能柜循环。")
    assert chunk_index_text("原文", {"keywords": ["保修"], "qa_pairs": [{"q": "保修多久", "a": "5 年"}]}).startswith("[本段关键词] 保修")
    title, md = html_to_markdown("<html><head><title>帮助</title><script>x()</script></head><body><h2>退货</h2><p>7 天无理由</p><ul><li>包装完整</li></ul></body></html>")
    assert title == "帮助" and "## 退货" in md and "- 包装完整" in md and "x()" not in md


def test_per_file_config_and_keyword_enhancement(client):
    kb = _kb(client)
    doc = _upload(client, kb["id"], {"strategy": "fixed", "chunk_size": 100, "chunk_overlap": 0, "enhance_keywords": True})
    assert doc["chunk_config"]["strategy"] == "fixed" and doc["chunk_config"]["chunk_size"] == 100
    docs = client.get(f"/api/knowledge-bases/{kb['id']}/documents").json()
    assert docs[0]["status"] == "done", docs[0]
    chunks = _chunks(client, doc["id"])
    assert len(chunks) >= 2 and all(c["keywords"] for c in chunks)

    # 单文件重切：改为按标题，分块数变化且配置落库
    resp = client.post(f"/api/documents/{doc['id']}/reparse", json={"config": {"strategy": "heading", "chunk_size": 800}})
    assert resp.status_code == 200 and resp.json()["chunk_config"]["strategy"] == "heading"
    rechunked = _chunks(client, doc["id"])
    assert rechunked and all(not c["keywords"] for c in rechunked)

    preview = client.post(f"/api/documents/{doc['id']}/preview", json={"config": {"strategy": "fixed", "chunk_size": 120}}).json()
    assert preview["strategy"] == "fixed" and preview["config"]["chunk_size"] == 120 and preview["max_chars"] <= 200


def test_retrieval_modes(client):
    kb = _kb(client)
    _upload(client, kb["id"])
    base = f"/api/knowledge-bases/{kb['id']}/test-retrieval"

    fulltext = client.get(base, params={"q": "E07 通讯", "mode": "fulltext"}).json()
    assert fulltext["options"]["mode"] == "fulltext" and fulltext["chunks"]
    assert "E07" in fulltext["chunks"][0]["content"]
    assert fulltext["models"]["embedding"] == ""  # 全文模式不做向量化

    hybrid = client.get(base, params={"q": "E07 通讯", "mode": "hybrid", "rerank": "false"}).json()
    assert hybrid["chunks"] and hybrid["chunks"][0]["score"] <= 1.0

    none = client.get(base, params={"q": "完全无关的问题xyz", "mode": "fulltext"}).json()
    assert none["chunks"] == []
    strict = client.get(base, params={"q": "E07", "mode": "semantic", "score_threshold": 1.0, "rerank": "false"}).json()
    assert all(c["score"] >= 1.0 for c in strict["chunks"])


def test_text_import_and_chunk_edit(client):
    kb = _kb(client)
    resp = client.post(f"/api/knowledge-bases/{kb['id']}/text-import", json={
        "title": "新品口径", "content": "ES-300 储能柜将于 12 月上市，首发价格另行通知。",
    })
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    assert doc["filename"] == "新品口径.md"
    chunk = _chunks(client, doc["id"])[0]

    edited = client.patch(f"/api/chunks/{chunk['id']}", json={
        "content": chunk["content"] + " 预售通道已开放。", "keywords": ["预售", "预售"],
        "qa_pairs": [{"q": "ES-300 什么时候上市", "a": "12 月"}, {"q": "", "a": "无效"}],
    })
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["keywords"] == ["预售"] and len(body["qa_pairs"]) == 1 and "预售通道" in body["content"]

    hit = client.get(f"/api/knowledge-bases/{kb['id']}/test-retrieval", params={"q": "预售", "mode": "fulltext"}).json()
    assert hit["chunks"] and hit["chunks"][0]["id"] == chunk["id"]

    assert client.delete(f"/api/chunks/{chunk['id']}").status_code == 204
    assert _chunks(client, doc["id"]) == []


def test_web_import_blocks_private_network(client):
    kb = _kb(client)
    resp = client.post(f"/api/knowledge-bases/{kb['id']}/web-import", json={"urls": ["http://127.0.0.1:8000/x", "ftp://example.com"]})
    assert resp.status_code == 422
    assert "内网" in resp.text and "http/https" in resp.text


def test_app_retrieval_params(client):
    kb = _kb(client)
    app = client.post("/api/apps", json={"name": "检索参数-" + uuid.uuid4().hex[:6], "app_type": "qa", "kb_ids": [kb["id"]]}).json()
    assert app["retrieval"] == {}
    before = client.get(f"/api/apps/{app['id']}/releases").json()["draft_fingerprint"]
    updated = client.put(f"/api/apps/{app['id']}", json={"retrieval": {"mode": "hybrid", "top_n": 3, "score_threshold": 0.2}}).json()
    assert updated["retrieval"]["mode"] == "hybrid" and updated["retrieval"]["top_n"] == 3
    after = client.get(f"/api/apps/{app['id']}/releases").json()["draft_fingerprint"]
    assert before != after  # 检索参数属于应用行为，修改后需重新评测
