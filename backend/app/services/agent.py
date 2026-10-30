"""Agent 执行：LLM 函数调用自主规划（Tool + 内置 Skill），全链路 Trace 埋点

ReAct 循环每一步都会落 TraceSpan：
- react.plan       ：本轮可用能力、上下文规模、执行策略
- react.thought    ：模型原始输出、推理内容、tool_calls、单步 Token
- react.action     ：模型选择调用的 Tool / Skill 与入参
- tool.call        ：注册工具执行（HTTP / 系统工具）
- skill.call       ：内置 Skill 执行（知识库检索 / 数据计算）
- react.observation：回填给模型的执行结果
- final.answer     ：最终回答
- exception        ：工具超时、参数错误、循环上限等异常
"""
import ast
import json
import operator
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session

from app.models import Application, Tool
from app.services.chat import build_llm, format_contexts
from app.services.observability import explain_error
from app.services.tools import execute_tool

MAX_AGENT_STEPS = 5

# 内置 Skill：不依赖管理员注册工具，开箱即用
AGENT_SKILLS = {
    "skill_kb_search": {
        "label": "知识库检索",
        "description": "检索当前应用绑定的知识库，返回与问题最相关的内容片段。需要事实依据时优先调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词或完整问题"},
                "top_k": {"type": "integer", "description": "返回条数，默认 5，最大 8"},
            },
            "required": ["query"],
        },
    },
    "skill_calculate": {
        "label": "数据计算",
        "description": "对数字表达式做四则运算（支持 + - * / 括号），用于报价、折扣、汇总等计算。",
        "parameters": {
            "type": "object",
            "properties": {"expression": {"type": "string", "description": "例如 (1280*0.88)+59"}},
            "required": ["expression"],
        },
    },
}

TOOL_SCHEMAS = {
    "http": {
        "type": "object",
        "properties": {"input": {"type": "string", "description": "工具入参（可用自然语言或 JSON 描述）"}},
    },
    "system": {
        "type": "object",
        "properties": {"input": {"type": "string", "description": "工具入参（如要导出的 Markdown 内容）"}},
    },
}

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def _safe_calc(expression: str) -> float:
    """只允许数字、括号和四则运算的 AST 求值，杜绝任意代码执行"""
    if not expression or len(expression) > 200:
        raise ValueError("表达式为空或过长（上限 200 字符）")

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
            return _ALLOWED_BINOPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = _eval(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        raise ValueError("表达式仅支持数字和 + - * / ( ) 运算")

    return float(_eval(ast.parse(expression, mode="eval")))


def _tools_spec(db: Session) -> list[dict]:
    tools = db.query(Tool).filter(Tool.enabled.is_(True)).all()
    return [
        {
            "type": "function",
            "function": {
                "name": f"tool_{t.id.replace('-', '_')}",
                "description": t.description or t.name,
                "parameters": TOOL_SCHEMAS.get(t.tool_type, TOOL_SCHEMAS["http"]),
            },
        }
        for t in tools
    ]


def _skills_spec() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": spec["description"],
                "parameters": spec["parameters"],
            },
        }
        for name, spec in AGENT_SKILLS.items()
    ]


def _skill_label(name: str) -> str:
    return AGENT_SKILLS.get(name, {}).get("label", name)


def _messages_payload(messages) -> list[dict]:
    """把发给模型的消息原样结构化，满足「ReAct 全量上下文」可回放"""
    payload = []
    for message in messages:
        role = getattr(message, "type", None) or message.__class__.__name__.lower()
        item = {
            "role": role,
            "content": getattr(message, "content", ""),
        }
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            item["tool_calls"] = [
                {"name": c.get("name"), "args": c.get("args"), "id": c.get("id")}
                for c in tool_calls
            ]
        tool_call_id = getattr(message, "tool_call_id", None)
        if tool_call_id:
            item["tool_call_id"] = tool_call_id
        payload.append(item)
    return payload


def _run_skill(db: Session, app: Application, name: str, args: dict, rec=None) -> str:
    """执行内置 Skill；知识库检索复用 RAG 链路，因此子 span 也在同一 Trace 内"""
    if name == "skill_kb_search":
        if not app.kb_ids:
            return "当前应用未绑定知识库，无法检索。请直接基于已有信息回答。"
        from app.services.retrieval import common_embedding_ref, retrieve

        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("Skill 参数缺失：query")
        top_k = min(max(int(args.get("top_k") or 5), 1), 8)
        outcome = retrieve(
            db,
            list(app.kb_ids),
            query,
            embedding_ref=common_embedding_ref(db, list(app.kb_ids)),
            rec=rec,
        )
        if not outcome.chunks:
            return "知识库中未检索到相关内容。"
        return format_contexts(outcome.chunks[:top_k])
    if name == "skill_calculate":
        expression = str(args.get("expression") or "").strip()
        result = _safe_calc(expression)
        return f"{expression} = {result:g}"
    raise ValueError(f"未知 Skill: {name}")


def _extract_reasoning(resp) -> str:
    extra = getattr(resp, "additional_kwargs", {}) or {}
    for key in ("reasoning_content", "reasoning"):
        value = extra.get(key)
        if value:
            return str(value)
    return ""


def run_agent(db: Session, app: Application, query: str, contexts: str = "", rec=None):
    """执行 Agent 循环，yield 文本片段（流式）；rec 为 TraceRecorder"""
    llm, is_fake, model_name = build_llm(
        db, llm_ref=app.llm_ref or None, temperature=app.temperature or 0.2
    )

    tools = db.query(Tool).filter(Tool.enabled.is_(True)).all()
    tool_by_name = {f"tool_{t.id.replace('-', '_')}": t for t in tools}

    if rec:
        rec.record_span(
            "react.plan",
            "规划 · 装配上下文与可用能力",
            code_key="agent.plan",
            input={"query": query, "context_chars": len(contexts or "")},
            output={
                "strategy": "ReAct 工具循环",
                "max_steps": MAX_AGENT_STEPS,
                "available_skills": [
                    {"name": k, "label": v["label"]} for k, v in AGENT_SKILLS.items()
                ],
                "available_tools": [
                    {"name": f"tool_{t.id.replace('-', '_')}", "label": t.name, "type": t.tool_type}
                    for t in tools
                ],
            },
            context={
                "system_prompt": app.system_prompt or "你是企业智能助手。",
                "contexts": contexts or "（无）",
                "message_count": 2,
            },
            metadata={"model": model_name, "is_fake": is_fake},
        )

    # 无真实 LLM / 无工具与 Skill 可用 → 降级为带上下文的直接回答
    if is_fake:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", app.system_prompt or "你是企业智能助手。"),
                ("human", "参考资料：\n{contexts}\n\n用户问题：{query}\n\n请回答："),
            ]
        )
        chain = prompt | llm
        start = time.monotonic()
        resp = chain.invoke({"contexts": contexts or "（无）", "query": query})
        duration = int((time.monotonic() - start) * 1000)
        text = resp if isinstance(resp, str) else (resp.content if hasattr(resp, "content") else str(resp))
        usage = getattr(resp, "usage_metadata", None) or {}
        tokens = {}
        if rec:
            if usage:
                u = rec.add_usage(
                    "llm", model_name, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
                )
                tokens = u.as_dict()
            rec.record_span(
                "llm.call",
                "LLM 降级直答（未配置真实模型）",
                code_key="chat.llm",
                input={"query": query, "contexts_chars": len(contexts or "")},
                output={"content": text},
                duration_ms=duration,
                tokens=tokens,
                cost_cny=tokens.get("cost_cny", 0),
                status="success",
                metadata={"fallback": "fake_llm"},
            )
        for piece in _chunks(text or "", 12):
            yield piece
        return

    system_prompt = (
        (app.system_prompt or "你是企业智能助手。")
        + "\n\n你可以调用工具和 Skill 完成任务。工具/Skill 调用后根据结果继续回答，任务完成后直接输出最终回答。"
        + "\n可用 Skill：知识库检索、数据计算；可用工具见函数列表。"
        + "\n参考资料（可能有用）：\n" + (contexts or "（无）")
    )
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=query)]
    llm_with_tools = llm.bind_tools(_tools_spec(db) + _skills_spec())

    final_text = ""
    for round_no in range(1, MAX_AGENT_STEPS + 1):
        call_start = time.monotonic()
        resp = llm_with_tools.invoke(messages)
        call_duration = int((time.monotonic() - call_start) * 1000)
        tool_calls = getattr(resp, "tool_calls", None) or []
        content = resp.content if isinstance(resp.content, str) else json.dumps(resp.content, ensure_ascii=False)
        reasoning = _extract_reasoning(resp)

        usage_payload = {}
        usage = getattr(resp, "usage_metadata", None) or {}
        if rec:
            u = None
            if usage:
                u = rec.add_usage(
                    "llm", model_name, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
                )
                usage_payload = u.as_dict()
            rec.record_span(
                "react.thought",
                f"第 {round_no} 轮 · Thought",
                code_key="agent.thought",
                input={
                    "message_count": len(messages),
                    "model": model_name,
                    "messages": _messages_payload(messages),
                },
                output={
                    "content": content or "",
                    "reasoning": reasoning,
                    "tool_calls": [
                        {"name": c.get("name"), "args": c.get("args"), "id": c.get("id")} for c in tool_calls
                    ],
                    "finish": "tool_call" if tool_calls else "final_answer",
                },
                duration_ms=call_duration,
                tokens=usage_payload,
                cost_cny=usage_payload.get("cost_cny", 0),
                context={
                    "model": model_name,
                    "messages": len(messages),
                    "prompt_tokens": int(usage.get("input_tokens", 0)),
                },
                metadata={"round": round_no},
            )

        if tool_calls:
            messages.append(resp)
            for call in tool_calls:
                name = call.get("name", "")
                args = call.get("args") or {}
                if not isinstance(args, dict):
                    args = {"input": str(args)}
                call_id = call.get("id", "0")
                is_skill = name in AGENT_SKILLS
                label = _skill_label(name) if is_skill else (
                    tool_by_name[name].name if name in tool_by_name else name
                )
                span_type = "skill.call" if is_skill else "tool.call"
                code_key = "agent.skill" if is_skill else "agent.tool"

                if rec:
                    rec.record_span(
                        "react.action",
                        f"第 {round_no} 轮 · Action → {label}",
                        code_key="agent.action",
                        input={"tool": name, "args": args, "call_id": call_id},
                        output={"decision": "execute", "kind": "skill" if is_skill else "tool"},
                        metadata={"round": round_no, "call_id": call_id},
                    )
                    span = rec.record_span(
                        span_type,
                        f"{'Skill' if is_skill else 'Tool'} · {label}",
                        code_key=code_key,
                        input=args,
                        status="running",
                        context={"round": round_no, "call_id": call_id},
                        metadata={
                            "round": round_no,
                            "call_id": call_id,
                            "skill": name if is_skill else "",
                            "skill_label": label if is_skill else "",
                            "tool_type": (tool_by_name[name].tool_type if name in tool_by_name else ""),
                        },
                    )
                else:
                    span = None

                exec_start = time.monotonic()
                status = "success"
                error_text = ""
                try:
                    if is_skill:
                        result = _run_skill(db, app, name, args, rec=rec)
                    else:
                        tool = tool_by_name.get(name)
                        if tool:
                            tool_input = args.get("input") if isinstance(args, dict) else str(args)
                            result = execute_tool(
                                db, tool, {"input": str(tool_input)}, app_id=app.id, app_name=app.name
                            )
                        else:
                            result = f"工具 {name} 不存在"
                    if result.startswith("工具执行失败") or result.startswith("知识库中未检索"):
                        status = "error" if result.startswith("工具执行失败") else "success"
                        if status == "error":
                            error_text = result
                except Exception as exc:  # noqa: BLE001
                    result = f"Skill/工具执行失败: {exc}"
                    status = "error"
                    error_text = str(exc)
                exec_duration = int((time.monotonic() - exec_start) * 1000)

                if rec and span is not None:
                    span.status = status
                    span.duration_ms = exec_duration
                    span.output = {
                        "result": result,
                        "result_chars": len(result),
                    }
                    if error_text:
                        span.error = error_text[:8000]
                        span.error_hint = explain_error(error_text)
                        rec.record_span(
                            "exception",
                            f"异常 · {label}",
                            code_key="exception.error",
                            status="error",
                            duration_ms=1,
                            error=error_text,
                            error_hint=explain_error(error_text),
                            input={"call": name, "args": args},
                        )
                    rec.db.flush()

                messages.append(ToolMessage(content=result[:4000], tool_call_id=call_id))
                if rec:
                    rec.record_span(
                        "react.observation",
                        f"第 {round_no} 轮 · Observation · {label}",
                        code_key="agent.observation",
                        input={"tool_call_id": call_id, "tool": name},
                        output={"content": result, "truncated": len(result) > 4000},
                        status="error" if status == "error" else "success",
                        metadata={"round": round_no},
                    )
            continue

        final_text = content or ""
        if rec:
            rec.record_span(
                "final.answer",
                "Final Answer",
                code_key="agent.final",
                input={"round": round_no},
                output={"content": final_text},
                metadata={"round": round_no},
            )
        for piece in _chunks(final_text, 12):
            yield piece
        return

    # 循环超限：要求模型总结，并记录异常
    if rec:
        rec.record_span(
            "exception",
            f"异常 · 达到最大循环次数（{MAX_AGENT_STEPS}）",
            code_key="exception.error",
            status="error",
            error=f"Agent 在 {MAX_AGENT_STEPS} 轮内未收敛，可能工具反复失败或任务过于复杂。",
            error_hint="检查工具是否稳定、提示词是否要求模型在拿到结果后收敛；必要时提高上限或拆分子任务。",
            metadata={"max_steps": MAX_AGENT_STEPS},
        )
        rec.trace.status = "degraded"
    summary_start = time.monotonic()
    resp = llm.invoke(messages + [HumanMessage(content="请基于以上工具结果，直接给出最终回答。")])
    summary_duration = int((time.monotonic() - summary_start) * 1000)
    text = resp.content if hasattr(resp, "content") else str(resp)
    usage = getattr(resp, "usage_metadata", None) or {}
    tokens = {}
    if rec:
        if usage:
            u = rec.add_usage(
                "llm", model_name, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
            )
            tokens = u.as_dict()
        rec.record_span(
            "final.answer",
            "Final Answer（循环超限后总结）",
            code_key="agent.final",
            output={"content": text},
            duration_ms=summary_duration,
            tokens=tokens,
            cost_cny=tokens.get("cost_cny", 0),
            status="degraded",
        )
    for piece in _chunks(text or "", 12):
        yield piece


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i : i + size]
