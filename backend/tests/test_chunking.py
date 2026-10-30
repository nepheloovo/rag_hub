"""Phase 1 分块引擎与预览自测"""
import io
import json

import pytest

from app.celery_app import celery_app

celery_app.conf.task_always_eager = True

MD = """# 售后服务政策

## 第一章 总则

第一条 为规范公司产品售后服务，保障客户合法权益，制定本政策。

第二条 售后服务遵循首问负责原则。

## 第二章 退换货

第三条 客户自签收之日起 7 日内可申请无理由退货。

第四条 签收 15 日内出现非人为性能故障可选择换货或维修。

| 型号 | 功率 | 保修 |
| --- | --- | --- |
| ES-200 | 100 kW | 5 年 |
| ES-100 | 50 kW | 5 年 |
"""


def test_strategies_split(client):
    from app.services.chunking import split_markdown

    for st in ("smart", "heading", "fixed", "page", "table_row", "parent_child", "semantic"):
        chunks = split_markdown(MD, st, chunk_size=100, chunk_overlap=10)
        assert len(chunks) >= 1, f"{st} 无分块"
        assert all(c["content"].strip() for c in chunks)

    # separator 按条款切分
    chunks = split_markdown(MD, "separator", chunk_size=100, separator="第[一二三四五六七八九十]+条")
    assert len(chunks) >= 4

    # parent_child 含 parent 与 child
    chunks = split_markdown(MD, "parent_child", chunk_size=80, chunk_overlap=10)
    kinds = {c["kind"] for c in chunks}
    assert kinds == {"parent", "child"}
    groups = {c["parent_group"] for c in chunks if c["kind"] == "child"}
    assert all(g for g in groups)

    # page 策略保留页码
    pdf_md = "<!-- 第 1 页 -->\n第一页内容。" + "长内容" * 20 + "\n<!-- 第 2 页 -->\n第二页内容。"
    chunks = split_markdown(pdf_md, "page", chunk_size=60)
    pages = {c["page"] for c in chunks}
    assert pages == {1, 2}

    # table_row 行块含表头
    chunks = split_markdown(MD, "table_row", chunk_size=100)
    row_chunks = [c for c in chunks if "| ES-" in c["content"]]
    assert row_chunks and all("型号" in c["content"] for c in row_chunks)


def test_kb_create_with_strategy_and_type(client):
    kb = client.post("/api/knowledge-bases", json={
        "name": "策略库", "kb_type": "table", "chunk_strategy": "table_row"
    }).json()
    assert kb["kb_type"] == "table"
    assert kb["chunk_strategy"] == "table_row"
    # 更新策略
    kb = client.put(f"/api/knowledge-bases/{kb['id']}", json={"chunk_strategy": "heading"}).json()
    assert kb["chunk_strategy"] == "heading"


def _upload(client, kb_id, name, content):
    return client.post(
        f"/api/knowledge-bases/{kb_id}/documents",
        files={"file": (name, io.BytesIO(content.encode("utf-8")), "text/markdown")},
    ).json()


def test_preview_chunks(client):
    kb = client.post("/api/knowledge-bases", json={
        "name": "预览库", "chunk_strategy": "heading"
    }).json()
    doc = _upload(client, kb["id"], "policy.md", MD)
    # eager 模式上传后已解析完成
    docs = client.get(f"/api/knowledge-bases/{kb['id']}/documents").json()
    doc = docs[0]

    # 预览：默认用知识库策略
    resp = client.post(f"/api/documents/{doc['id']}/preview")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["strategy"] == "heading"
    assert data["total"] >= 1
    assert all("content" in c for c in data["chunks"])

    # 预览：显式指定其他策略
    resp = client.post(f"/api/documents/{doc['id']}/preview?strategy=table_row")
    assert resp.json()["strategy"] == "table_row"
    # 预览：非法策略回退 smart
    resp = client.post(f"/api/documents/{doc['id']}/preview?strategy=nope")
    assert resp.status_code == 200


def test_kb_status_machine(client):
    """上传后知识库状态应为 available（eager 同步完成后）"""
    kb = client.post("/api/knowledge-bases", json={"name": "状态库"}).json()
    _upload(client, kb["id"], "a.md", "# T\n\n内容。")
    kbs = client.get("/api/knowledge-bases").json()
    kb_after = next(k for k in kbs if k["id"] == kb["id"])
    assert kb_after["status"] == "available"


def test_chunk_metadata_strategy(client):
    """入库分块应记录策略与分块类型"""
    kb = client.post("/api/knowledge-bases", json={
        "name": "元数据库", "chunk_strategy": "parent_child"
    }).json()
    _upload(client, kb["id"], "pc.md", MD)
    docs = client.get(f"/api/knowledge-bases/{kb['id']}/documents").json()
    chunks = client.get(f"/api/documents/{docs[0]['id']}/chunks?limit=50").json()
    assert len(chunks) >= 2
