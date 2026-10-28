"""Chat Flow 执行器：节点图遍历 + 变量模板 + 条件分支 + 流式输出"""
import json
import re

import httpx
from sqlalchemy.orm import Session

from app.models import Application
from app.services.chat import build_llm
from app.services.retrieval import common_embedding_ref, retrieve

MAX_STEPS = 20
VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_\-]+)\s*\}\}")


class FlowError(Exception):
    """流程执行失败（可读信息）"""


def render_template(template: str, variables: dict) -> str:
    def repl(m):
        return str(variables.get(m.group(1), ""))
    return VAR_RE.sub(repl, template or "")


def _node_output(node: dict, variables: dict) -> str:
    key = node.get("data", {}).get("output_var") or f"{node['id']}_output"
    return variables.get(key, "")


def _execute_retrieval(db, node, variables, refs):
    data = node.get("data", {})
    kb_ids = data.get("kb_ids") or []
    if not kb_ids:
        raise FlowError("知识库检索节点未绑定知识库")
    top_k = int(data.get("top_k") or 5)
    query = variables.get("input", "")
    outcome = retrieve(db, kb_ids, query, embedding_ref=common_embedding_ref(db, kb_ids))
    chunks = outcome.chunks[:top_k]
    if not chunks:
        contexts = "（未检索到相关内容）"
    else:
        contexts = "\n\n".join(
            f"[{i}] {c.chunk.content}" for i, c in enumerate(chunks, start=1)
        )
    key = data.get("output_var") or f"{node['id']}_output"
    variables[key] = contexts
    for c in outcome.chunks[:5]:
        meta = c.chunk.metadata_ or {}
        refs.append(
            {
                "doc_id": c.chunk.doc_id,
                "title": meta.get("source", ""),
                "page": meta.get("page", 0),
                "snippet": c.chunk.content[:200],
                "score": round(c.score, 4),
            }
        )
    return contexts


def _execute_llm(db, node, variables):
    data = node.get("data", {})
    from langchain_core.prompts import ChatPromptTemplate

    system_prompt = render_template(data.get("system_prompt", ""), variables)
    user_prompt = render_template(data.get("user_prompt", "{{input}}"), variables)
    llm, _, model_name = build_llm(
        db,
        llm_ref=data.get("llm_ref") or None,
        temperature=float(data.get("temperature") or 0.2),
    )
    chain = ChatPromptTemplate.from_messages(
        [("system", system_prompt), ("human", user_prompt)]
    ) | llm
    resp = chain.invoke({})
    text = resp if isinstance(resp, str) else (resp.content if hasattr(resp, "content") else str(resp))
    key = data.get("output_var") or f"{node['id']}_output"
    variables[key] = text or ""
    variables["output"] = text or ""
    return text or ""


def _execute_tool(node, variables):
    """HTTP 工具节点：URL/方法/Headers/Body 支持变量模板，返回响应文本"""
    data = node.get("data", {})
    url = render_template(data.get("url", ""), variables)
    if not url:
        raise FlowError("HTTP 工具节点未配置 URL")
    method = (data.get("method") or "GET").upper()
    headers = {}
    for item in data.get("headers") or []:
        k = render_template(item.get("key", ""), variables)
        v = render_template(item.get("value", ""), variables)
        if k:
            headers[k] = v
    body = render_template(data.get("body", ""), variables)
    try:
        resp = httpx.request(method, url, headers=headers, content=body or None, timeout=20)
        resp.raise_for_status()
        text = resp.text[:4000]
    except Exception as e:  # noqa: BLE001
        raise FlowError(f"工具调用失败: {e}") from e
    key = data.get("output_var") or f"{node['id']}_output"
    variables[key] = text
    variables["output"] = text
    return text


def _evaluate_condition(node, variables) -> bool:
    data = node.get("data", {})
    left = render_template(data.get("left") or "{{output}}", variables)
    op = data.get("op") or "not_empty"
    value = data.get("value") or ""
    if op == "contains":
        return value in left
    if op == "not_contains":
        return value not in left
    if op == "is_empty":
        return not left.strip()
    if op == "not_empty":
        return bool(left.strip())
    if op == "equals":
        return left.strip() == value.strip()
    return bool(left.strip())


def _final_text(db, app: Application, variables: dict, refs: list) -> str:
    """顺序执行流程：返回最终输出文本与引用（LLM/工具节点同步生成，answer 节点渲染模板）"""
    flow = app.flow or {}
    nodes = {n["id"]: n for n in flow.get("nodes", [])}
    edges = flow.get("edges", [])
    if not nodes:
        raise FlowError("编排尚未完成：请先搭建流程")

    adjacency: dict[str, list[tuple[str | None, str]]] = {}
    for e in edges:
        adjacency.setdefault(e["source"], []).append((e.get("source_handle"), e["target"]))

    start = next((n for n in flow.get("nodes", []) if n.get("type") == "start"), None)
    if not start:
        raise FlowError("流程缺少「开始」节点")
    current = start["id"]
    steps = 0
    while current and steps < MAX_STEPS:
        steps += 1
        node = nodes.get(current)
        if not node:
            break
        ntype = node.get("type")
        if ntype == "start":
            variables.setdefault("input", variables.get("input", ""))
        elif ntype == "retrieval":
            _execute_retrieval(db, node, variables, refs)
        elif ntype == "llm":
            _execute_llm(db, node, variables)
        elif ntype == "tool":
            _execute_tool(node, variables)
        elif ntype == "condition":
            result = _evaluate_condition(node, variables)
            outgoing = adjacency.get(current, [])
            target = None
            for handle, t in outgoing:
                if (handle == "true" and result) or (handle == "false" and not result) or handle in (None, ""):
                    target = t
                    break
            current = target
            continue
        elif ntype == "answer":
            variables["output"] = render_template(node.get("data", {}).get("content", ""), variables)
        outgoing = adjacency.get(current, [])
        current = outgoing[0][1] if outgoing else None

    if steps >= MAX_STEPS:
        raise FlowError("流程执行超过最大步数，请检查是否成环")
    return variables.get("output", "")


def run_chatflow(db: Session, app: Application, query: str):
    """执行 Chat Flow；返回 (answer, refs)"""
    variables = {"input": query}
    refs: list[dict] = []
    answer = _final_text(db, app, variables, refs)
    return answer, refs, variables


def validate_flow(flow: dict | None) -> list[str]:
    """编排校验：返回问题列表（空=通过）"""
    problems = []
    if not flow or not flow.get("nodes"):
        return ["编排尚未完成：流程为空"]
    nodes = flow.get("nodes", [])
    edges = flow.get("edges", [])
    ids = {n["id"] for n in nodes}
    types = {n.get("type") for n in nodes}
    if "start" not in types:
        problems.append("缺少「开始」节点")
    if not any(t in ("answer", "llm", "tool") for t in types):
        problems.append("流程没有输出节点（结束输出/LLM/工具）")
    for e in edges:
        if e.get("source") not in ids or e.get("target") not in ids:
            problems.append(f"存在无效连线: {e.get('source')} → {e.get('target')}")
    return problems
