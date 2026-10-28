"""Agent 执行：LLM 函数调用自主规划注册工具（循环上限，流式输出）"""
import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session

from app.models import Application, Tool
from app.services.chat import build_llm
from app.services.tools import execute_tool

MAX_AGENT_STEPS = 5

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


def run_agent(db: Session, app: Application, query: str, contexts: str = ""):
    """执行 Agent 循环，yield 文本片段（流式）"""
    llm, is_fake, model_name = build_llm(
        db, llm_ref=app.llm_ref or None, temperature=app.temperature or 0.2
    )

    # 无真实 LLM / 无工具 → 降级为带上下文的直接回答
    tools = db.query(Tool).filter(Tool.enabled.is_(True)).all()
    if is_fake or not tools:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", app.system_prompt or "你是企业智能助手。"),
                ("human", "参考资料：\n{contexts}\n\n用户问题：{query}\n\n请回答："),
            ]
        )
        chain = prompt | llm
        resp = chain.invoke({"contexts": contexts or "（无）", "query": query})
        text = resp if isinstance(resp, str) else (resp.content if hasattr(resp, "content") else str(resp))
        for piece in _chunks(text or "", 12):
            yield piece
        return

    messages = [
        SystemMessage(
            content=(
                (app.system_prompt or "你是企业智能助手。")
                + "\n\n你可以调用工具完成任务。工具调用后根据结果继续回答，任务完成后直接输出最终回答。"
                + "\n参考资料（可能有用）：\n" + (contexts or "（无）")
            )
        ),
        HumanMessage(content=query),
    ]

    llm_with_tools = llm.bind_tools(_tools_spec(db))
    tool_by_name = {f"tool_{t.id.replace('-', '_')}": t for t in tools}

    for _ in range(MAX_AGENT_STEPS):
        resp = llm_with_tools.invoke(messages)
        if getattr(resp, "tool_calls", None):
            messages.append(resp)
            for call in resp.tool_calls:
                tool = tool_by_name.get(call.get("name", ""))
                args = call.get("args") or {}
                tool_input = args.get("input") if isinstance(args, dict) else str(args)
                if tool:
                    result = execute_tool(
                        db, tool, {"input": str(tool_input)}, app_id=app.id, app_name=app.name
                    )
                else:
                    result = f"工具 {call.get('name')} 不存在"
                messages.append(
                    ToolMessage(content=result[:4000], tool_call_id=call.get("id", "0"))
                )
            continue
        text = resp.content if hasattr(resp, "content") else str(resp)
        for piece in _chunks(text or "", 12):
            yield piece
        return
    # 循环超限：要求总结
    resp = llm.invoke(messages + [HumanMessage(content="请基于以上工具结果，直接给出最终回答。")])
    text = resp.content if hasattr(resp, "content") else str(resp)
    for piece in _chunks(text or "", 12):
        yield piece


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i : i + size]
