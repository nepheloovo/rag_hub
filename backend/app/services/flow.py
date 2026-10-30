"""Chat Flow 执行器：节点图遍历 + 变量模板 + 条件分支 + 流式输出（含节点级 Trace）"""
import json
import re
import time

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


def _execute_retrieval(db, node, variables, refs, rec=None):
    data = node.get("data", {})
    kb_ids = data.get("kb_ids") or []
    if not kb_ids:
        raise FlowError("知识库检索节点未绑定知识库")
    top_k = int(data.get("top_k") or 5)
    query = variables.get("input", "")
    outcome = retrieve(db, kb_ids, query, embedding_ref=common_embedding_ref(db, kb_ids), rec=rec)
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


def _execute_llm(db, node, variables, rec=None):
    data = node.get("data", {})
    from langchain_core.prompts import ChatPromptTemplate

    system_prompt = render_template(data.get("system_prompt", ""), variables)
    user_prompt = render_template(data.get("user_prompt", "{{input}}"), variables)
    llm, is_fake, model_name = build_llm(
        db,
        llm_ref=data.get("llm_ref") or None,
        temperature=float(data.get("temperature") or 0.2),
    )
    if rec:
        models = rec.trace.models or {}
        rec.trace.model = model_name
        rec.trace.models = {**models, "llm": model_name, "fake": bool(models.get("fake") or is_fake)}
    chain = ChatPromptTemplate.from_messages(
        [("system", system_prompt), ("human", user_prompt)]
    ) | llm
    resp = chain.invoke({})
    text = resp if isinstance(resp, str) else (resp.content if hasattr(resp, "content") else str(resp))
    usage = getattr(resp, "usage_metadata", None) or {}
    usage_payload = {}
    if rec and usage:
        u = rec.add_usage(
            "llm", model_name, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
        )
        usage_payload = u.as_dict()
    key = data.get("output_var") or f"{node['id']}_output"
    variables[key] = text or ""
    variables["output"] = text or ""
    return text or "", usage_payload, model_name


def _execute_tool(db, node, variables, app=None):
    """工具节点：优先引用注册工具（带调用统计），否则内联 HTTP 配置"""
    data = node.get("data", {})
    tool_ref = data.get("tool_ref")
    if tool_ref:
        from app.models import Tool
        from app.services.tools import execute_tool

        tool = db.get(Tool, tool_ref)
        if not tool:
            raise FlowError("引用的工具不存在或已删除")
        result = execute_tool(
            db, tool, variables,
            app_id=app.id if app else "",
            app_name=app.name if app else "",
        )
        key = data.get("output_var") or f"{node['id']}_output"
        variables[key] = result
        variables["output"] = result
        return result
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


NODE_LABELS = {
    "start": "开始",
    "retrieval": "知识库检索",
    "llm": "LLM 生成",
    "tool": "工具调用",
    "condition": "条件分支",
    "answer": "结束输出",
}


def _node_label(node: dict) -> str:
    data = node.get("data", {}) or {}
    name = data.get("label") or data.get("name")
    base = NODE_LABELS.get(node.get("type", ""), node.get("type", "节点"))
    return f"{base} · {name}" if name else base


def _record_exception(rec, exc, node: dict) -> None:
    if not rec:
        return
    rec.record_span(
        "exception",
        f"异常 · {_node_label(node)}",
        code_key="exception.error",
        status="error",
        error=str(exc),
        input={"node_id": node.get("id"), "node_type": node.get("type")},
        metadata={"node_id": node.get("id")},
    )


def _final_text(db, app: Application, variables: dict, refs: list, rec=None) -> str:
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
        node_start = time.monotonic()
        span = None
        if rec:
            span = rec.record_span(
                "flow.node",
                _node_label(node),
                code_key="flow.node",
                status="running",
                input={
                    "node_id": node.get("id"),
                    "node_type": ntype,
                    "node_config": node.get("data") or {},
                    "variables": variables,
                },
                metadata={"node_id": node.get("id"), "node_type": ntype, "step": steps},
            )
        detail = {}
        try:
            if ntype == "start":
                variables.setdefault("input", variables.get("input", ""))
            elif ntype == "retrieval":
                contexts = _execute_retrieval(db, node, variables, refs, rec=rec)
                detail = {"chunks_chars": len(contexts or "")}
            elif ntype == "llm":
                text, usage_payload, model_name = _execute_llm(db, node, variables, rec=rec)
                detail = {"model": model_name, "chars": len(text or "")}
                if span is not None:
                    span.tokens = usage_payload
                    span.cost_cny = float(usage_payload.get("cost_cny", 0))
            elif ntype == "tool":
                tool_span_start = time.monotonic()
                result = _execute_tool(db, node, variables, app)
                detail = {
                    "result_chars": len(result or ""),
                    "tool_ref": (node.get("data") or {}).get("tool_ref", ""),
                    "duration_ms": int((time.monotonic() - tool_span_start) * 1000),
                }
            elif ntype == "condition":
                result = _evaluate_condition(node, variables)
                outgoing = adjacency.get(current, [])
                target = None
                for handle, t in outgoing:
                    if (handle == "true" and result) or (handle == "false" and not result) or handle in (None, ""):
                        target = t
                        break
                detail = {"result": result, "next": target}
                if span is not None:
                    span.output = {"node_type": ntype, "result": result, "next": target}
                    rec.close_span(span, node_start, status="success")
                current = target
                continue
            elif ntype == "answer":
                variables["output"] = render_template(node.get("data", {}).get("content", ""), variables)
                detail = {"chars": len(variables["output"] or "")}
        except Exception as exc:  # noqa: BLE001
            if span is not None:
                span.status = "error"
                span.error = str(exc)[:8000]
                rec.close_span(span, node_start, status="error", output={"error": str(exc)})
            _record_exception(rec, exc, node)
            raise
        if span is not None:
            rec.close_span(
                span,
                node_start,
                status="success",
                output={"node_type": ntype, "variables": variables, **detail},
            )
        outgoing = adjacency.get(current, [])
        current = outgoing[0][1] if outgoing else None

    if steps >= MAX_STEPS:
        if rec:
            rec.record_span(
                "exception",
                "异常 · 流程执行超过最大步数",
                code_key="exception.error",
                status="error",
                error="流程执行超过最大步数，请检查是否成环",
                error_hint="检查条件分支是否形成环路，或调高 MAX_STEPS。",
            )
        raise FlowError("流程执行超过最大步数，请检查是否成环")
    return variables.get("output", "")


def run_chatflow(db: Session, app: Application, query: str, rec=None):
    """执行 Chat Flow；返回 (answer, refs, variables)"""
    variables = {"input": query}
    refs: list[dict] = []
    answer = _final_text(db, app, variables, refs, rec=rec)
    if rec:
        rec.record_span(
            "final.answer",
            "流程输出",
            code_key="flow.node",
            output={"content": answer},
            metadata={"nodes": len((app.flow or {}).get("nodes", [])) if app.flow else 0},
        )
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
