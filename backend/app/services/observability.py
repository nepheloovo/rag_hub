"""可观测服务：Trace/Span 记录、成本核算、代码快照与解释、演示数据

设计要点：
- 一次执行 = 一条 TraceRun；一步执行 = 一条 TraceSpan。
- 记录器既支持在请求开始时 begin，也支持在流式生成器/后台任务中 resume。
- 每个 span 可绑定 code_key，自动带上内部实现代码与逐段中文解释。
"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.models import ModelPrice, TraceRun, TraceSpan

MAX_TEXT = 200_000  # 单段文本落库上限，避免超长上下文撑爆存储

DEFAULT_PRICE = {"input": 1.0, "output": 2.0}

PRICE_SEEDS = [
    ("qwen-max", 2.4, 9.6),
    ("qwen-plus", 0.8, 2.0),
    ("qwen-turbo", 0.3, 0.6),
    ("qwen-long", 0.5, 2.0),
    ("qwen-vl-plus", 1.5, 4.5),
    ("text-embedding-v3", 0.5, 0.0),
    ("text-embedding-v4", 0.5, 0.0),
    ("gte-rerank", 0.8, 0.0),
    ("bge-reranker-v2-m3", 0.8, 0.0),
    ("gpt-4o", 18.0, 72.0),
    ("gpt-4o-mini", 1.1, 4.4),
    ("deepseek-chat", 2.0, 8.0),
    ("deepseek-reasoner", 4.0, 16.0),
    ("claude-3-5-sonnet", 21.0, 105.0),
    ("__default__", DEFAULT_PRICE["input"], DEFAULT_PRICE["output"]),
]


# ---------------------------------------------------------------------------
# 代码快照：满足「单节点可展开查看内部运行代码，代码需要做解释」
# ---------------------------------------------------------------------------
CODE_SNIPPETS: dict[str, dict] = {
    "agent.plan": {
        "language": "python",
        "code": '''tools = db.query(Tool).filter(Tool.enabled.is_(True)).all()
skills = AGENT_SKILLS  # 内置能力：知识检索 / 数据计算
specs = _tools_spec(tools) + _skills_spec(skills)
system = (
    (app.system_prompt or "你是企业智能助手。")
    + "\\n\\n你可以调用工具和 Skill 完成任务。"
    + "\\n参考资料：\\n" + (contexts or "（无）")
)
messages = [SystemMessage(content=system), HumanMessage(content=query)]
llm_with_tools = llm.bind_tools(specs)''',
        "explain": [
            {"lines": [1, 2], "title": "装载能力清单", "text": "只把启用中的注册工具与内置 Skill 暴露给模型；停用的工具不会出现在函数签名里，避免模型调用不存在的函数。"},
            {"lines": [3, 7], "title": "组装系统提示词", "text": "系统提示词 + 工具使用约束 + 检索到的参考资料一起进入上下文。参考资料在这里一次性注入，后续每轮都复用，保证多轮决策不丢背景。"},
            {"lines": [8, 9], "title": "生成初始上下文", "text": "SystemMessage 放规则，HumanMessage 放用户问题。完整的 messages 会随 trace 一起留痕，便于复现模型为什么做出某个决策。"},
            {"lines": [10, 11], "title": "绑定函数调用", "text": "LangChain 的 bind_tools 把工具 schema 转成 OpenAI function calling 协议；模型返回 tool_calls 时由 Agent 循环接管执行。"},
        ],
    },
    "agent.thought": {
        "language": "python",
        "code": '''resp = llm_with_tools.invoke(messages)
usage = getattr(resp, "usage_metadata", None) or {}
if usage:
    recorder.add_usage(
        "llm", model_name,
        int(usage.get("input_tokens", 0)),
        int(usage.get("output_tokens", 0)),
    )
messages.append(resp)''',
        "explain": [
            {"lines": [1, 1], "title": "一次模型推理", "text": "把当前完整消息列表发给模型，模型决定：直接回答，还是发起一个/多个工具调用。这是 ReAct 中的 Reason + Act 决策点。"},
            {"lines": [2, 6], "title": "单步 Token 计费", "text": "usage_metadata 包含本次输入的 prompt tokens 与输出 tokens；立即折算成本写回 trace，因此详情页能核对「第 N 轮花了多少钱」。"},
            {"lines": [7, 7], "title": "保留模型原始消息", "text": "AIMessage 必须原样回填到 messages，否则下一轮模型看不到自己刚发起的 tool_call，上下文会断裂。"},
        ],
    },
    "agent.action": {
        "language": "python",
        "code": '''if getattr(resp, "tool_calls", None):
    for call in resp.tool_calls:
        name = call.get("name", "")
        args = call.get("args") or {}
        recorder.record_span(
            "react.action", name,
            input={"tool": name, "args": args},
            output={"decision": "execute"},
            metadata={"round": round_no, "call_id": call.get("id")},
        )''',
        "explain": [
            {"lines": [1, 4], "title": "解析模型决策", "text": "tool_calls 是模型给出的结构化动作，包含函数名、参数与调用 id。一个模型回合可能并行发起多个调用，这里逐个处理。"},
            {"lines": [5, 10], "title": "动作留痕", "text": "把「调用谁、参数是什么」单独记为 action span，让执行链路上「思考」与「真正执行」分开，出现问题时可判断是模型选错还是工具执行错。"},
        ],
    },
    "agent.tool": {
        "language": "python",
        "code": '''tool = tool_by_name.get(name)
result = execute_tool(
    db, tool, {"input": str(tool_input)},
    app_id=app.id, app_name=app.name,
)
status = "error" if result.startswith("工具执行失败") else "success"
recorder.record_span(
    "tool.call", tool.name,
    input={"input": tool_input},
    output={"result": result},
    status=status,
    duration_ms=duration,
)''',
        "explain": [
            {"lines": [1, 4], "title": "按注册信息执行", "text": "通过函数名映射回数据库里的工具配置，HTTP 工具走 URL/Header/Body 模板，系统工具走内置实现；应用 id/name 一并写入调用日志。"},
            {"lines": [5, 5], "title": "错误识别", "text": "execute_tool 内部捕获异常并返回可读错误文本，这里根据前缀判定状态，确保错误不会伪装成成功结果继续喂给模型。"},
            {"lines": [6, 13], "title": "落 tool span", "text": "记录工具入参、出参、耗时和状态。详情页的 Tool 卡片直接读取这条 span；失败时同时生成 exception span。"},
        ],
    },
    "agent.skill": {
        "language": "python",
        "code": '''if name == "skill_kb_search":
    outcome = retrieve(db, app.kb_ids, query, rec=recorder)
    result = format_chunks(outcome.chunks)
elif name == "skill_calculate":
    result = safe_eval_arithmetic(args["expression"])
recorder.record_span(
    "skill.call", skill_label,
    input=args, output={"result": result},
    status="success" if not err else "error",
)''',
        "explain": [
            {"lines": [1, 3], "title": "Skill 分发", "text": "Skill 是平台内置的高阶能力，不依赖管理员注册工具。知识检索 Skill 复用 RAG 检索链路，会把召回/重排的子 span 一并挂到同一条 trace 上。"},
            {"lines": [4, 5], "title": "安全计算", "text": "数据计算 Skill 只允许数字、括号和四则运算，用 AST 白名单求值，不执行任意代码。"},
            {"lines": [6, 11], "title": "Skill 观测", "text": "Skill 与 Tool 分开展示，便于统计「内置能力 vs 外部工具」的使用占比与失败率。"},
        ],
    },
    "agent.observation": {
        "language": "python",
        "code": '''messages.append(
    ToolMessage(content=result[:4000], tool_call_id=call.get("id", "0"))
)
recorder.record_span(
    "react.observation", f"第 {round_no} 轮 · 观察结果",
    input={"tool_call_id": call.get("id")},
    output={"content": result},
)''',
        "explain": [
            {"lines": [1, 3], "title": "回填执行结果", "text": "Observation 以 ToolMessage 形式回填，必须带 tool_call_id 才能与上一轮 tool_call 配对；过长的结果截断到 4000 字符，避免撑爆上下文。"},
            {"lines": [4, 8], "title": "观测留痕", "text": "完整结果（不截断）另存到 span，前端可展开查看模型到底看到了什么，这是排查「回答不对」的关键证据。"},
        ],
    },
    "agent.final": {
        "language": "python",
        "code": '''text = resp.content if hasattr(resp, "content") else str(resp)
recorder.record_span(
    "final.answer", "最终回答",
    input={"round": round_no},
    output={"content": text},
)
for piece in _chunks(text or "", 12):
    yield piece''',
        "explain": [
            {"lines": [1, 1], "title": "提取最终回答", "text": "模型不再发起 tool_calls 时，content 就是最终答案；部分模型会把内容放在 content 数组中，这里统一兼容。"},
            {"lines": [2, 6], "title": "最终回答留痕", "text": "Final span 与 trace.answer 同时保存，列表页展示摘要，详情页展示全文。"},
            {"lines": [7, 8], "title": "流式返回", "text": "按 12 字符切片通过 SSE 推给前端，既保留打字机体验，又不影响先落库再展示。"},
        ],
    },
    "retrieval.embed": {
        "language": "python",
        "code": '''service = get_embedding_service(db, embedding_ref)
vectors, tokens = service.embed_texts_with_usage([query])
recorder.add_usage("embedding", service.model, tokens, 0)
sql = """
SELECT 1 - (embedding <=> :q) AS sim
FROM chunks WHERE kb_id = ANY(:kb_ids)
ORDER BY embedding <=> :q LIMIT :k
"""''',
        "explain": [
            {"lines": [1, 2], "title": "查询向量化", "text": "查询与文档必须使用同一个 embedding 模型；知识库绑定了模型就优先用它，否则回退全局默认。"},
            {"lines": [3, 3], "title": "Embedding 计费", "text": "embedding 按输入 token 计费，没有输出 token；伪向量模式 token 为 0，便于区分真实调用。"},
            {"lines": [4, 9], "title": "余弦相似度召回", "text": "pgvector 的 <=> 是余弦距离，1 - distance 得到相似度；按距离升序取 top-k，多知识库通过 ANY(kb_ids) 联合召回。"},
        ],
    },
    "retrieval.search": {
        "language": "python",
        "code": '''rows = db.execute(text(VECTOR_SQL), {
    "q": str(query_vec), "kb_ids": kb_ids, "k": settings.retrieval_top_k,
}).fetchall()
candidates = [
    {"chunk_id": r[0], "doc_id": r[1], "score": float(r[4]),
     "content": r[2][:300]}
    for r in rows
]''',
        "explain": [
            {"lines": [1, 3], "title": "向量召回", "text": "默认召回 20 条候选；kb_ids 越界或 embedding 为空的分块不会参与排序。"},
            {"lines": [4, 8], "title": "候选留痕", "text": "召回结果保存 chunk id、文档、分数与内容片段。详情页可对比「召回分高但最终没用」的情况，辅助调参。"},
        ],
    },
    "retrieval.rerank": {
        "language": "python",
        "code": '''service = RerankService.resolve(db)
if service:
    result = service.rerank(query, documents, settings.rerank_top_n)
    ranked = sorted(result.ranked, key=lambda x: x["score"], reverse=True)
else:
    recorder.record_span(
        "retrieval.rerank", "Rerank 已降级",
        status="skipped",
        output={"reason": "未配置 rerank 模型"},
    )''',
        "explain": [
            {"lines": [1, 3], "title": "精排", "text": "Rerank 用交叉编码器对「问题-文档」逐对打分，通常比纯向量更准；精排后只保留 top-n 给 LLM。"},
            {"lines": [4, 8], "title": "降级可观测", "text": "未配置或调用失败时记录 skipped span 而不是静默跳过，避免「明明配了重排却没生效」无法排查。"},
        ],
    },
    "chat.context": {
        "language": "python",
        "code": '''inputs = {
    "history": format_history(history_rows),
    "contexts": format_contexts(outcome.chunks),
    "question": query,
}
chain = ChatPromptTemplate.from_messages([
    ("system", app.system_prompt),
    ("human", HUMAN_TEMPLATE),
]) | llm''',
        "explain": [
            {"lines": [1, 5], "title": "上下文组装", "text": "历史对话取最近 6 条，参考资料按 [编号] + 来源拼接；这是最终进入模型的真实上下文。"},
            {"lines": [6, 8], "title": "LCEL 生成链", "text": "Prompt → LLM 的管道；流式模式下每个 chunk 通过 SSE 推给前端，trace 中保存完整答案。"},
        ],
    },
    "chat.llm": {
        "language": "python",
        "code": '''for chunk in chain.stream(inputs):
    usage = getattr(chunk, "usage_metadata", None) or {}
    if usage:
        llm_prompt_tokens = int(usage.get("input_tokens", 0))
        llm_completion_tokens = int(usage.get("output_tokens", 0))
    yield chunk.content''',
        "explain": [
            {"lines": [1, 1], "title": "流式推理", "text": "chain.stream 边生成边返回；首字延迟与总耗时都会体现在 span 上。"},
            {"lines": [2, 5], "title": "用量统计", "text": "最后一个 chunk 通常携带 usage；记录输入/输出 token，用于单次与聚合计费。"},
        ],
    },
    "flow.node": {
        "language": "python",
        "code": '''node = nodes[current]
with recorder.span("flow.node", node_label, input=variables) as span:
    if ntype == "retrieval":
        _execute_retrieval(db, node, variables, refs)
    elif ntype == "llm":
        _execute_llm(db, node, variables)
    elif ntype == "tool":
        _execute_tool(db, node, variables, app)
    span.output = {"variables": variables}''',
        "explain": [
            {"lines": [1, 4], "title": "节点执行", "text": "Chat Flow 按邻接表顺序执行，每个节点是一个 span；节点配置、变量快照和输出都保存。"},
            {"lines": [5, 10], "title": "分支与变量", "text": "条件节点根据左右值比较决定下一节点；变量在节点间传递，span 中保留每一步的变量快照，便于定位是哪个节点改坏了值。"},
        ],
    },
    "build.parse": {
        "language": "python",
        "code": '''parsed = parse_file(resolve_stored_path(doc.file_path), doc.file_type, db)
recorder.record_span(
    "build.parse", f"解析 · {doc.filename}",
    input={"file_type": doc.file_type, "size": doc.file_size},
    output={"chars": len(parsed.markdown), "warnings": parsed.warnings},
)
strategy = kb.chunk_strategy or "smart"''',
        "explain": [
            {"lines": [1, 1], "title": "统一解析", "text": "Word/PDF/图片/表格最终都转成 Markdown；扫描版 PDF 或图片会走通义 qwen-vl OCR。"},
            {"lines": [2, 6], "title": "解析留痕", "text": "记录文件类型、大小、解析字符数与 OCR 警告；解析失败时错误原文进入 exception span。"},
            {"lines": [7, 7], "title": "选择分块策略", "text": "策略来自知识库配置；构建 Trace 会记录策略，方便对比不同策略的构建效果。"},
        ],
    },
    "build.chunk": {
        "language": "python",
        "code": '''chunks = split_markdown(
    parsed.markdown, strategy=strategy,
    chunk_size=settings.chunk_size, db=db,
)
if not chunks:
    raise ParsingError("文档未切分出任何分块")
recorder.record_span(
    "build.chunk", f"分块 · {strategy}",
    output={"count": len(chunks), "preview": [c["content"][:200] for c in chunks[:3]]},
)''',
        "explain": [
            {"lines": [1, 5], "title": "9 种分块策略", "text": "智能/标题层级/分隔符/固定长度/父子/语义/问答对/按页/表格按行；空结果是硬错误，直接终止构建。"},
            {"lines": [6, 10], "title": "分块留痕", "text": "记录分块数量与前 3 条样例，满足构建过程可观察；完整分块可在知识库详情查看。"},
        ],
    },
    "build.embed": {
        "language": "python",
        "code": '''service = get_embedding_service(db, kb.embedding_ref or None)
vectors, tokens = [], 0
for i in range(0, len(chunks), EMBED_BATCH_SIZE):
    batch = [c["content"] for c in chunks[i:i + EMBED_BATCH_SIZE]]
    vs, used = service.embed_texts_with_usage(batch)
    vectors += vs; tokens += used
recorder.add_usage("embedding", service.model, tokens, 0)''',
        "explain": [
            {"lines": [1, 1], "title": "模型一致", "text": "索引必须使用知识库绑定的 embedding 模型，否则查询向量与库内向量不在同一空间，检索会失效。"},
            {"lines": [2, 6], "title": "分批向量化", "text": "每批 64 条，避免单次请求过大被服务商拒绝；每批失败都会抛出并记录错误。"},
            {"lines": [7, 7], "title": "构建计费", "text": "构建同样消耗 token，会计入计费页的「知识库构建」用途，方便核算入库成本。"},
        ],
    },
    "build.index": {
        "language": "python",
        "code": '''db.query(Chunk).filter(Chunk.doc_id == doc_id).delete()
for chunk, vector in zip(chunks, vectors):
    db.add(Chunk(
        kb_id=doc.kb_id, doc_id=doc_id,
        content=chunk["content"],
        metadata_={"source": doc.filename, "page": chunk.get("page", 0),
                   "strategy": strategy, "embedding_model": service.model},
        embedding=vector,
    ))
doc.status = "done"; doc.chunk_count = stored''',
        "explain": [
            {"lines": [1, 1], "title": "幂等重建", "text": "重新解析时先删除旧分块，避免同一文档出现重复向量。"},
            {"lines": [2, 9], "title": "写入向量", "text": "content 与 metadata 一起入库，metadata 保留来源、页码、策略与模型，检索结果引用溯源依赖这些字段。"},
            {"lines": [10, 10], "title": "状态收口", "text": "文档状态置为 done 并记录 chunk 数；知识库状态在文档全部完成后刷新为可用。"},
        ],
    },
    "exception.error": {
        "language": "python",
        "code": '''except Exception as exc:
    recorder.record_span(
        "exception", "执行异常",
        status="error",
        error=str(exc),
        error_hint=explain_error(exc),
    )
    recorder.finish(status="error", error=str(exc))
    raise''',
        "explain": [
            {"lines": [1, 5], "title": "异常留痕", "text": "异常不会被吞掉：既有结构化 error，也有面向排障的中文提示（超时/鉴权/限流/上下文超长等）。"},
            {"lines": [6, 8], "title": "结束 Trace", "text": "trace 状态置为 error 并记录错误摘要，列表页红色标识；重新执行会生成新的 trace，保留历史。"},
        ],
    },
}

ERROR_HINTS = [
    ("timeout", "上游模型/工具超时。可检查网络、调大超时时间，或切换备用服务商。"),
    ("timed out", "上游模型/工具超时。可检查网络、调大超时时间，或切换备用服务商。"),
    ("401", "鉴权失败。请到「模型配置」检查 API Key 是否正确、是否过期。"),
    ("403", "权限不足。请确认账号/Key 是否开通了该模型或工具权限。"),
    ("429", "触发限流。可降低并发、增加重试退避，或升级配额。"),
    ("rate limit", "触发限流。可降低并发、增加重试退避，或升级配额。"),
    ("context length", "上下文超出模型窗口。可减少历史消息、降低 top-k 或缩短文档分块。"),
    ("maximum context", "上下文超出模型窗口。可减少历史消息、降低 top-k 或缩短文档分块。"),
    ("connection", "连接失败。检查 base_url、网络代理与目标服务是否存活。"),
    ("未配置", "能力未配置。请到「模型配置」启用服务商并设置默认模型。"),
    ("工具", "工具调用失败。检查工具 URL、鉴权 Header、入参模板与超时设置。"),
]


def explain_error(error: Any) -> str:
    text = str(error or "").lower()
    for needle, hint in ERROR_HINTS:
        if needle.lower() in text:
            return hint
    return "请展开异常详情查看原始报错，并结合上游服务状态与入参排查。"


def jsonable(value: Any, _depth: int = 0) -> Any:
    """把任意对象转成可 JSON 序列化的结构，并做长度保护"""
    if _depth > 8:
        return str(value)[:2000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + f"\n…（已截断，原长 {len(value)} 字符）"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): jsonable(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v, _depth + 1) for v in value]
    if hasattr(value, "model_dump"):
        try:
            return jsonable(value.model_dump(), _depth + 1)
        except Exception:  # noqa: BLE001
            pass
    return jsonable(str(value), _depth + 1)


def chunk_payload(item: Any, content_limit: int = 4000) -> dict:
    """检索结果 → 可观测上下文"""
    chunk = getattr(item, "chunk", item)
    meta = getattr(chunk, "metadata_", None) or {}
    content = getattr(chunk, "content", "") or ""
    return {
        "chunk_id": getattr(chunk, "id", ""),
        "doc_id": getattr(chunk, "doc_id", ""),
        "source": meta.get("source", ""),
        "page": meta.get("page", 0),
        "heading": meta.get("heading", ""),
        "score": round(float(getattr(item, "score", 0.0)), 4),
        "content": content[:content_limit],
        "length": len(content),
    }


def _aware(dt: datetime | None) -> datetime:
    if not dt:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cost: float = 0.0
    model: str = ""

    def as_dict(self) -> dict:
        return {
            "input": self.input,
            "output": self.output,
            "total": self.input + self.output,
            "cost_cny": round(self.cost, 6),
            "model": self.model,
        }


class TraceRecorder:
    """Trace 写入器；可 begin（新建）或 resume（流式生成器/Async 中续写）"""

    def __init__(self, db: Session, trace: TraceRun):
        self.db = db
        self.trace = trace
        self.started_at = _aware(trace.started_at)
        self._prices: dict[str, tuple[float, float]] | None = None
        self._seq = int(trace.span_count or 0)

    # ---------- 创建 / 恢复 ----------
    @classmethod
    def begin(
        cls,
        db: Session,
        trace_type: str,
        *,
        query: str = "",
        title: str = "",
        app: Any = None,
        kb: Any = None,
        kb_name: str = "",
        role: str = "",
        source: str = "internal",
        model: str = "",
        models: dict | None = None,
        context: dict | None = None,
        metadata: dict | None = None,
        started_at: datetime | None = None,
    ) -> "TraceRecorder":
        trace = TraceRun(
            id=uuid.uuid4().hex,
            trace_type=trace_type,
            title=(title or query or "")[:250],
            query=query,
            status="running",
            app_id=getattr(app, "id", "") or "",
            app_name=getattr(app, "name", "") or "",
            app_kind=getattr(app, "app_kind", "") or "",
            role=role or "",
            source=source,
            model=model or "",
            models=models or {},
            context=jsonable(context or {}),
            metadata_=jsonable(metadata or {}),
            started_at=_aware(started_at),
            tokens={"input": 0, "output": 0, "total": 0, "embedding": 0, "rerank": 0, "llm": 0},
        )
        if kb is not None:
            trace.kb_id = getattr(kb, "id", "") or ""
            trace.kb_name = getattr(kb, "name", "") or ""
        elif kb_name:
            trace.kb_name = kb_name
        db.add(trace)
        db.commit()
        db.refresh(trace)
        return cls(db, trace)

    @classmethod
    def resume(cls, db: Session, trace_id: str) -> "TraceRecorder | None":
        trace = db.get(TraceRun, trace_id) if trace_id else None
        if not trace:
            return None
        return cls(db, trace)

    @property
    def id(self) -> str:
        return self.trace.id

    def _offset_ms(self) -> int:
        return max(0, int((datetime.now(timezone.utc) - self.started_at).total_seconds() * 1000))

    # ---------- 价格 / 用量 ----------
    def _load_prices(self) -> dict[str, tuple[float, float]]:
        if self._prices is None:
            rows = self.db.query(ModelPrice).all()
            self._prices = {r.model: (r.input_price or 0.0, r.output_price or 0.0) for r in rows}
        return self._prices

    def price_for(self, model: str) -> tuple[float, float]:
        prices = self._load_prices()
        if model in prices:
            return prices[model]
        needle = (model or "").lower()
        # 长模型名优先，避免 gpt-4o-mini 命中 gpt-4o
        for key in sorted(prices, key=len, reverse=True):
            if key != "__default__" and key.lower() in needle:
                return prices[key]
        return prices.get("__default__", (DEFAULT_PRICE["input"], DEFAULT_PRICE["output"]))

    def usage_for(self, model: str, input_tokens: int, output_tokens: int) -> Usage:
        ip, op = self.price_for(model)
        cost = (max(0, input_tokens) * ip + max(0, output_tokens) * op) / 1_000_000
        return Usage(input=max(0, input_tokens), output=max(0, output_tokens), cost=cost, model=model)

    def add_usage(
        self,
        kind: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        usage: Usage | None = None,
    ) -> Usage:
        usage = usage or self.usage_for(model, input_tokens, output_tokens)
        tokens = dict(self.trace.tokens or {})
        for key in ("input", "output", "total", "embedding", "rerank", "llm"):
            tokens.setdefault(key, 0)
        tokens["input"] += usage.input
        tokens["output"] += usage.output
        tokens["total"] += usage.input + usage.output
        if kind in ("embedding", "rerank", "llm"):
            tokens[kind] += usage.input + usage.output
        self.trace.tokens = tokens
        self.trace.cost_cny = round(float(self.trace.cost_cny or 0) + usage.cost, 6)
        if model and (not self.trace.model or kind == "llm"):
            self.trace.model = model
        models = dict(self.trace.models or {})
        if model:
            models[kind] = model
        self.trace.models = models
        self.db.flush()
        return usage

    # ---------- Span ----------
    def record_span(
        self,
        span_type: str,
        name: str,
        *,
        input: Any = None,
        output: Any = None,
        status: str = "success",
        duration_ms: int | None = None,
        started_offset_ms: int | None = None,
        tokens: dict | None = None,
        cost_cny: float | None = None,
        context: Any = None,
        error: str = "",
        error_hint: str = "",
        parent_id: str = "",
        code_key: str = "",
        metadata: dict | None = None,
        depth: int = 0,
    ) -> TraceSpan:
        snippet = CODE_SNIPPETS.get(code_key, {})
        span = TraceSpan(
            id=uuid.uuid4().hex,
            trace_id=self.trace.id,
            parent_id=parent_id or "",
            seq=self._seq,
            depth=depth,
            span_type=span_type,
            name=name[:250],
            status=status,
            started_offset_ms=started_offset_ms if started_offset_ms is not None else max(0, self._offset_ms() - (duration_ms or 0)),
            duration_ms=int(duration_ms or 0),
            input=jsonable(input),
            output=jsonable(output),
            tokens=jsonable(tokens or {}),
            cost_cny=float(cost_cny or 0.0),
            context=jsonable(context or {}),
            error=str(error or "")[:8000],
            error_hint=error_hint or (explain_error(error) if error else ""),
            code_key=code_key,
            code=snippet.get("code", ""),
            code_explain=jsonable(snippet.get("explain", [])),
            metadata_=jsonable(metadata or {}),
        )
        self._seq += 1
        self.trace.span_count = self._seq
        self.db.add(span)
        self.db.flush()
        return span

    @contextmanager
    def span(self, span_type: str, name: str, *, code_key: str = "", **kwargs) -> Iterator[TraceSpan]:
        """同步步骤：自动计算耗时，异常自动标红"""
        start = time.monotonic()
        span = self.record_span(
            span_type,
            name,
            status="running",
            started_offset_ms=self._offset_ms(),
            code_key=code_key,
            **kwargs,
        )
        try:
            yield span
            if span.status == "running":
                span.status = "success"
        except Exception as exc:  # noqa: BLE001
            span.status = "error"
            span.error = str(exc)[:8000]
            span.error_hint = span.error_hint or explain_error(exc)
            if not span.output:
                span.output = {"error": str(exc)}
            raise
        finally:
            span.duration_ms = int((time.monotonic() - start) * 1000)
            span.started_offset_ms = max(0, span.started_offset_ms)
            self.db.flush()

    def start_span(self, span_type: str, name: str, *, code_key: str = "", **kwargs) -> tuple[TraceSpan, float]:
        """异步/流式步骤：先落一条 running span，结束后手动 close_span"""
        start = time.monotonic()
        span = self.record_span(
            span_type,
            name,
            status="running",
            started_offset_ms=self._offset_ms(),
            code_key=code_key,
            **kwargs,
        )
        return span, start

    def close_span(self, span: TraceSpan, started: float, *, status: str = "success", output: Any = None, **kwargs) -> None:
        span.duration_ms = int((time.monotonic() - started) * 1000)
        span.status = status
        if output is not None:
            span.output = jsonable(output)
        for key, value in kwargs.items():
            setattr(span, key, jsonable(value) if key in ("input", "context", "metadata_", "tokens") else value)
        self.db.flush()

    # ---------- 结束 ----------
    def finish(
        self,
        *,
        status: str = "success",
        answer: str | None = None,
        error: str = "",
        context: dict | None = None,
        message_id: str = "",
    ) -> None:
        trace = self.trace
        if answer is not None:
            trace.answer = answer
        if error:
            trace.error = str(error)[:8000]
        if message_id:
            trace.message_id = message_id
        if context:
            merged = dict(trace.context or {})
            merged.update(jsonable(context))
            trace.context = merged
        trace.duration_ms = max(trace.duration_ms or 0, int((datetime.now(timezone.utc) - self.started_at).total_seconds() * 1000))
        trace.status = status
        trace.span_count = self._seq
        trace.context = {**(trace.context or {}), "tokens": trace.tokens or {}}
        self.db.commit()


def finish_trace_error(trace_id: str, error: Any, name: str = "异常 · 请求失败") -> None:
    """请求阶段失败（检索/预检）时收口 Trace，避免长期停留在 running"""
    if not trace_id:
        return
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        rec = TraceRecorder.resume(db, trace_id)
        if not rec:
            return
        rec.record_span(
            "exception",
            name,
            code_key="exception.error",
            status="error",
            error=str(error),
            error_hint=explain_error(error),
        )
        rec.finish(status="error", error=str(error))
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()


def seed_prices(db: Session) -> None:
    for model, inp, out in PRICE_SEEDS:
        if not db.get(ModelPrice, model):
            db.add(ModelPrice(model=model, input_price=inp, output_price=out))
    db.commit()


# ---------------------------------------------------------------------------
# 演示数据：用于空态一键体验（不自动写入，用户/演示按钮显式触发）
# ---------------------------------------------------------------------------
def seed_demo_observability(db: Session, created_by: str = "系统管理员") -> dict:
    from app.models import EvalCase, EvalSet, EvalSetItem

    if db.query(TraceRun).filter(TraceRun.metadata_["demo"].astext == "true").count() > 0:
        return {"created": False, "message": "演示数据已存在"}

    now = datetime.now(timezone.utc).replace(microsecond=0)
    created_traces: list[TraceRun] = []
    created_cases: list[EvalCase] = []

    def add_trace(
        trace_type: str,
        title: str,
        query: str,
        answer: str,
        status: str,
        app_name: str,
        app_kind: str,
        kb_name: str,
        model: str,
        offset_hours: float,
        tokens: dict,
        cost: float,
        duration_ms: int,
        context: dict,
        spans: list[dict],
        error: str = "",
    ) -> TraceRun:
        trace = TraceRun(
            id=uuid.uuid4().hex,
            trace_type=trace_type,
            title=title,
            query=query,
            answer=answer,
            status=status,
            app_name=app_name,
            app_kind=app_kind,
            kb_name=kb_name,
            model=model,
            models={"llm": model, "embedding": "text-embedding-v3", "rerank": "gte-rerank"},
            tokens=tokens,
            cost_cny=cost,
            duration_ms=duration_ms,
            span_count=len(spans),
            started_at=now - timedelta(hours=offset_hours),
            context=jsonable(context),
            error=error,
            metadata_={"demo": True, "source": "演示数据"},
        )
        db.add(trace)
        offset = 0
        for idx, item in enumerate(spans):
            code_key = item.get("code_key", "")
            snippet = CODE_SNIPPETS.get(code_key, {})
            offset += int(item.get("gap", 0))
            duration = int(item.get("duration_ms", 0))
            tokens_payload = dict(item.get("tokens") or {})
            if tokens_payload.get("total") and not tokens_payload.get("model"):
                span_type = item["span_type"]
                if span_type in ("retrieval.embed", "build.embed"):
                    tokens_payload["model"] = "text-embedding-v3"
                elif span_type == "retrieval.rerank":
                    tokens_payload["model"] = "gte-rerank"
                else:
                    tokens_payload["model"] = model
            db.add(
                TraceSpan(
                    id=uuid.uuid4().hex,
                    trace_id=trace.id,
                    seq=idx,
                    depth=item.get("depth", 0),
                    span_type=item["span_type"],
                    name=item["name"],
                    status=item.get("status", "success"),
                    started_offset_ms=offset,
                    duration_ms=duration,
                    input=jsonable(item.get("input")),
                    output=jsonable(item.get("output")),
                    tokens=jsonable(tokens_payload),
                    cost_cny=float(item.get("cost_cny", 0)),
                    context=jsonable(item.get("context", {})),
                    error=item.get("error", ""),
                    error_hint=item.get("error_hint", ""),
                    code_key=code_key,
                    code=snippet.get("code", ""),
                    code_explain=jsonable(snippet.get("explain", [])),
                    metadata_=jsonable(item.get("metadata", {})),
                )
            )
            offset += duration
        created_traces.append(trace)
        db.flush()
        return trace

    # 1) Agent 成功链路
    agent_context = {
        "system_prompt": "你是售后客服智能体，先理解用户诉求，必要时查询知识库并生成可下载的工单摘要。",
        "history": [{"role": "user", "content": "我上周买的耳机左耳没声音"}],
        "app": {"name": "售后智能体", "kind": "agent", "model": "qwen-max", "temperature": 0.2},
        "available_skills": ["skill_kb_search · 知识库检索", "skill_calculate · 数据计算"],
        "available_tools": ["导出 Word 文档 · system", "订单查询 · http"],
        "retrieved_chunks": [
            {"source": "售后服务政策.pdf", "page": 3, "score": 0.8421, "content": "签收 7 日内出现非人为质量问题，支持无理由换新；7-15 日支持检测后换新。"},
            {"source": "售后服务政策.pdf", "page": 3, "score": 0.7963, "content": "换新需提供订单号与故障视频，审核通过后 48 小时内寄出。"},
        ],
    }
    t1 = add_trace(
        "agent",
        "售后换新政策 + 工单摘要",
        "耳机左耳没声音，三天前签收的，能换新吗？顺便帮我生成工单摘要。",
        "可以换新。您的订单签收不满 7 天，属于非人为质量问题，支持无理由换新。请提供订单号与故障视频，审核通过后 48 小时内寄出。工单摘要已生成，可下载 Word。",
        "success",
        "售后智能体",
        "agent",
        "售后服务知识库",
        "qwen-max",
        2.2,
        {"input": 5260, "output": 684, "total": 5944, "embedding": 46, "rerank": 320, "llm": 5578},
        0.0191,
        8420,
        agent_context,
        [
            {"span_type": "retrieval.embed", "name": "查询向量化", "code_key": "retrieval.embed", "duration_ms": 168, "tokens": {"input": 46, "output": 0, "total": 46}, "cost_cny": 0.000023, "input": {"query": "耳机左耳没声音 三天前签收 能换新吗"}, "output": {"model": "text-embedding-v3", "dim": 1024}, "gap": 0},
            {"span_type": "retrieval.search", "name": "向量召回 top-20", "code_key": "retrieval.search", "duration_ms": 42, "output": {"candidates": [{"source": "售后服务政策.pdf", "score": 0.8421}, {"source": "售后服务政策.pdf", "score": 0.7963}]}, "gap": 2},
            {"span_type": "retrieval.rerank", "name": "Rerank 精排 top-5", "code_key": "retrieval.rerank", "duration_ms": 210, "tokens": {"input": 320, "output": 0, "total": 320}, "cost_cny": 0.000256, "output": {"model": "gte-rerank", "kept": 5}, "gap": 2},
            {"span_type": "react.plan", "name": "规划 · 分析诉求并选择能力", "code_key": "agent.plan", "duration_ms": 12, "context": {"messages": 2, "tools": 2, "skills": 2}, "output": {"plan": ["查询换新政策", "确认签收时间是否在 7 天内", "生成工单摘要并导出"]}, "gap": 8},
            {"span_type": "react.thought", "name": "第 1 轮 · Thought", "code_key": "agent.thought", "duration_ms": 1860, "tokens": {"input": 2380, "output": 96, "total": 2476}, "cost_cny": 0.006634, "output": {"content": "", "reasoning": "用户问换新，需要先确认政策适用条件（签收 7 日内、非人为）。先检索知识库。", "tool_calls": [{"name": "skill_kb_search", "args": {"query": "签收 7 天内 耳机 换新 政策"}}]}, "gap": 4},
            {"span_type": "react.action", "name": "第 1 轮 · Action → 知识库检索", "code_key": "agent.action", "duration_ms": 3, "input": {"tool": "skill_kb_search", "args": {"query": "签收 7 天内 耳机 换新 政策"}}, "gap": 2},
            {"span_type": "skill.call", "name": "Skill · 知识库检索", "code_key": "agent.skill", "duration_ms": 534, "tokens": {"input": 480, "output": 0, "total": 480}, "cost_cny": 0.0024, "input": {"query": "签收 7 天内 耳机 换新 政策", "top_k": 5}, "output": {"chunks": 5, "top": "签收 7 日内出现非人为质量问题，支持无理由换新。"}, "metadata": {"skill": "skill_kb_search", "skill_label": "知识库检索"}},
            {"span_type": "react.observation", "name": "第 1 轮 · Observation", "code_key": "agent.observation", "duration_ms": 2, "output": {"content": "[1] 签收 7 日内出现非人为质量问题，支持无理由换新…（共 5 条）"}},
            {"span_type": "react.thought", "name": "第 2 轮 · Thought", "code_key": "agent.thought", "duration_ms": 1420, "tokens": {"input": 3120, "output": 88, "total": 3208}, "cost_cny": 0.008294, "output": {"content": "", "reasoning": "政策确认可换新。用户还要求工单摘要，调用系统工具导出 Word。", "tool_calls": [{"name": "tool_sys_export_word", "args": {"input": "## 售后工单\\n- 问题：耳机左耳无声\\n- 签收：3 天前\\n- 结论：符合 7 日换新"}}]}},
            {"span_type": "react.action", "name": "第 2 轮 · Action → 导出 Word", "code_key": "agent.action", "duration_ms": 2, "input": {"tool": "tool_sys_export_word", "args": {"input": "## 售后工单…"}}},
            {"span_type": "tool.call", "name": "Tool · 导出 Word 文档", "code_key": "agent.tool", "duration_ms": 426, "input": {"input": "## 售后工单…"}, "output": {"result": "已生成 Word 文档：a1b2c3.docx"}, "metadata": {"tool_type": "system"}},
            {"span_type": "react.observation", "name": "第 2 轮 · Observation", "code_key": "agent.observation", "duration_ms": 2, "output": {"content": "已生成 Word 文档：a1b2c3.docx"}},
            {"span_type": "react.thought", "name": "第 3 轮 · Thought（最终回答）", "code_key": "agent.thought", "duration_ms": 980, "tokens": {"input": 3410, "output": 500, "total": 3910}, "cost_cny": 0.012984, "output": {"content": "可以换新。您的订单签收不满 7 天…工单摘要已生成，可下载 Word。", "tool_calls": []}},
            {"span_type": "final.answer", "name": "Final Answer", "code_key": "agent.final", "duration_ms": 6, "output": {"content": "可以换新。您的订单签收不满 7 天，属于非人为质量问题，支持无理由换新…"}, "gap": 2},
        ],
    )

    # 2) Agent 异常链路
    t2 = add_trace(
        "agent",
        "订单查询工具超时",
        "帮我查一下订单 20261028001 什么时候发货？",
        "抱歉，订单查询工具暂时不可用，请稍后重试或联系人工客服。",
        "error",
        "售后智能体",
        "agent",
        "售后服务知识库",
        "qwen-plus",
        8.5,
        {"input": 3180, "output": 186, "total": 3366, "embedding": 0, "rerank": 0, "llm": 3366},
        0.002545,
        30560,
        {
            "system_prompt": "你是售后客服智能体，先理解用户诉求…",
            "history": [],
            "app": {"name": "售后智能体", "kind": "agent", "model": "qwen-plus"},
            "available_tools": ["订单查询 · http"],
        },
        [
            {"span_type": "react.plan", "name": "规划 · 查询订单", "code_key": "agent.plan", "duration_ms": 9, "output": {"plan": ["调用订单查询工具", "根据物流信息回答"]}},
            {"span_type": "react.thought", "name": "第 1 轮 · Thought", "code_key": "agent.thought", "duration_ms": 1200, "tokens": {"input": 1800, "output": 94, "total": 1894}, "cost_cny": 0.001628, "output": {"reasoning": "需要订单系统数据，调用订单查询工具。", "tool_calls": [{"name": "tool_order_query", "args": {"input": "订单号 20261028001"}}]}},
            {"span_type": "react.action", "name": "第 1 轮 · Action → 订单查询", "code_key": "agent.action", "duration_ms": 2, "input": {"tool": "tool_order_query", "args": {"input": "订单号 20261028001"}}},
            {"span_type": "tool.call", "name": "Tool · 订单查询", "code_key": "agent.tool", "status": "error", "duration_ms": 30000, "error": "工具调用失败: HTTPSConnectionPool(host='order.internal', port=443): Read timed out. (read timeout=30)", "error_hint": "上游模型/工具超时。可检查网络、调大超时时间，或切换备用服务商。", "input": {"input": "订单号 20261028001"}, "output": {"result": "工具执行失败: Read timed out"}, "metadata": {"tool_type": "http"}},
            {"span_type": "exception", "name": "异常 · 工具调用超时", "code_key": "exception.error", "status": "error", "duration_ms": 1, "error": "工具调用失败: Read timed out. (read timeout=30)", "error_hint": "订单系统 30 秒未响应；已自动降级为安抚话术，未重试。"},
            {"span_type": "react.observation", "name": "第 1 轮 · Observation", "code_key": "agent.observation", "duration_ms": 1, "output": {"content": "工具执行失败: Read timed out"}},
            {"span_type": "react.thought", "name": "第 2 轮 · Thought（最终回答）", "code_key": "agent.thought", "duration_ms": 700, "tokens": {"input": 1380, "output": 92, "total": 1472}, "cost_cny": 0.000917, "output": {"content": "抱歉，订单查询工具暂时不可用，请稍后重试或联系人工客服。", "tool_calls": []}},
            {"span_type": "final.answer", "name": "Final Answer", "code_key": "agent.final", "duration_ms": 3, "output": {"content": "抱歉，订单查询工具暂时不可用，请稍后重试或联系人工客服。"}},
        ],
        error="工具调用失败: Read timed out. (read timeout=30)",
    )

    # 3) 简易 RAG
    t3 = add_trace(
        "chat",
        "研发知识问答 · 检索链路",
        "系统的检索链路是怎么设计的？",
        "系统采用「向量召回 top-20 → Rerank 精排 top-5 → LLM 流式生成」的两阶段检索链路…",
        "success",
        "研发知识问答",
        "simple",
        "研发知识库",
        "qwen-max",
        27,
        {"input": 2860, "output": 420, "total": 3280, "embedding": 32, "rerank": 240, "llm": 3008},
        0.01117,
        4210,
        {
            "system_prompt": "你是企业知识助手，请根据参考资料回答，并标注来源编号。",
            "history": [],
            "retrieved_chunks": [
                {"source": "RAG 架构说明.md", "score": 0.9012, "content": "召回 top-20 后使用 gte-rerank 精排到 top-5，再交给 LLM 生成。"},
                {"source": "RAG 架构说明.md", "score": 0.8644, "content": "未配置 Rerank 时自动降级为纯向量召回，链路不中断。"},
            ],
        },
        [
            {"span_type": "retrieval.embed", "name": "查询向量化", "code_key": "retrieval.embed", "duration_ms": 142, "tokens": {"input": 32, "output": 0, "total": 32}, "cost_cny": 0.000016},
            {"span_type": "retrieval.search", "name": "向量召回 top-20", "code_key": "retrieval.search", "duration_ms": 38, "output": {"candidates": [{"source": "RAG 架构说明.md", "score": 0.9012}]}},
            {"span_type": "retrieval.rerank", "name": "Rerank 精排 top-5", "code_key": "retrieval.rerank", "duration_ms": 186, "tokens": {"input": 240, "output": 0, "total": 240}, "cost_cny": 0.000192},
            {"span_type": "context.assemble", "name": "上下文组装", "code_key": "chat.context", "duration_ms": 4, "input": {"history": 0, "contexts": 5, "query": "系统的检索链路是怎么设计的？"}, "output": {"prompt_chars": 3860}},
            {"span_type": "llm.call", "name": "LLM 流式生成", "code_key": "chat.llm", "duration_ms": 3800, "tokens": {"input": 2588, "output": 420, "total": 3008}, "cost_cny": 0.010243, "output": {"content": "系统采用「向量召回 top-20 → Rerank 精排 top-5 → LLM 流式生成」…"}},
            {"span_type": "final.answer", "name": "回答完成", "code_key": "chat.llm", "duration_ms": 2, "output": {"content": "系统采用「向量召回 top-20 → Rerank 精排 top-5 → LLM 流式生成」…"}},
        ],
    )

    # 4) Chat Flow
    t4 = add_trace(
        "chatflow",
        "客服流程 · 检索后判断",
        "发票抬头写错了能重开吗？",
        "可以重开。您需要在开票后 30 天内提交重开申请，并提供正确的抬头信息。",
        "success",
        "客服流程助手",
        "chatflow",
        "售后服务知识库",
        "qwen-plus",
        32,
        {"input": 2140, "output": 168, "total": 2308, "embedding": 21, "rerank": 0, "llm": 2287},
        0.003019,
        2680,
        {"flow": {"nodes": 5, "edges": 5}, "branch": "contains '30 天' = true"},
        [
            {"span_type": "flow.node", "name": "开始 · 接收问题", "code_key": "flow.node", "duration_ms": 1, "output": {"variables": {"input": "发票抬头写错了能重开吗？"}}},
            {"span_type": "flow.node", "name": "知识库检索 · 发票政策", "code_key": "retrieval.search", "duration_ms": 240, "tokens": {"input": 21, "output": 0, "total": 21}, "output": {"chunks": 3, "top": "开票后 30 天内可申请重开。"}},
            {"span_type": "flow.node", "name": "条件分支 · 是否命中 30 天", "code_key": "flow.node", "duration_ms": 1, "output": {"result": True, "next": "LLM 生成"}},
            {"span_type": "flow.node", "name": "LLM 生成 · 客服话术", "code_key": "flow.node", "duration_ms": 2100, "tokens": {"input": 2100, "output": 168, "total": 2268}, "cost_cny": 0.002016, "output": {"content": "可以重开。您需要在开票后 30 天内提交重开申请…"}},
            {"span_type": "flow.node", "name": "结束输出", "code_key": "flow.node", "duration_ms": 1, "output": {"content": "可以重开。您需要在开票后 30 天内提交重开申请…"}},
        ],
    )

    # 5) 构建成功
    t5 = add_trace(
        "kb_build",
        "员工手册 2026.pdf",
        "构建 员工手册 2026.pdf",
        "解析 → 分块 → Embedding → 入库完成，共 186 个分块",
        "success",
        "",
        "",
        "人事制度库",
        "text-embedding-v3",
        50,
        {"input": 186400, "output": 0, "total": 186400, "embedding": 186400, "rerank": 0, "llm": 0},
        0.0932,
        18240,
        {"document": "员工手册 2026.pdf", "strategy": "heading", "kb": "人事制度库", "embedding_model": "text-embedding-v3", "pages": 64, "ocr": False},
        [
            {"span_type": "build.parse", "name": "解析 · PDF 64 页", "code_key": "build.parse", "duration_ms": 4200, "input": {"file_type": "pdf", "size": 4832000}, "output": {"chars": 128400, "warnings": [], "tables": 12}},
            {"span_type": "build.chunk", "name": "分块 · 标题层级", "code_key": "build.chunk", "duration_ms": 860, "output": {"count": 186, "avg_chars": 690, "preview": ["# 第一章 总则…", "## 考勤管理…", "## 假期制度…"]}},
            {"span_type": "build.embed", "name": "Embedding · 186 条", "code_key": "build.embed", "duration_ms": 11800, "tokens": {"input": 186400, "output": 0, "total": 186400}, "cost_cny": 0.0932, "output": {"model": "text-embedding-v3", "batches": 3, "dim": 1024}},
            {"span_type": "build.index", "name": "向量入库", "code_key": "build.index", "duration_ms": 1380, "output": {"chunks": 186, "delete_old": 0}},
        ],
    )

    # 6) 构建失败
    t6 = add_trace(
        "kb_build",
        "扫描版合同.pdf",
        "构建 扫描版合同.pdf",
        "OCR 未配置，扫描件无法提取文字",
        "error",
        "",
        "",
        "合同库",
        "qwen-vl-plus",
        54,
        {"input": 0, "output": 0, "total": 0, "embedding": 0, "rerank": 0, "llm": 0},
        0.0,
        6300,
        {"document": "扫描版合同.pdf", "strategy": "smart", "kb": "合同库", "ocr": True},
        [
            {"span_type": "build.parse", "name": "解析 · 扫描件 OCR", "code_key": "build.parse", "status": "error", "duration_ms": 6200, "error": "OCR 失败：未配置可用的 qwen-vl 模型", "error_hint": "扫描件需要 OCR。请到「模型配置」启用通义并设置 qwen-vl-plus。"},
            {"span_type": "exception", "name": "异常 · OCR 未配置", "code_key": "exception.error", "status": "error", "duration_ms": 1, "error": "OCR 失败：未配置可用的 qwen-vl 模型", "error_hint": "扫描件需要 OCR。请到「模型配置」启用通义并设置 qwen-vl-plus。"},
        ],
        error="OCR 失败：未配置可用的 qwen-vl 模型",
    )

    # Case 回流
    def add_case(trace: TraceRun, label: str, note: str, tags: list[str], reference: str = "") -> EvalCase:
        case = EvalCase(
            id=uuid.uuid4().hex,
            question=trace.query,
            answer=trace.answer,
            reference_answer=reference,
            contexts=(trace.context or {}).get("retrieved_chunks", []),
            label=label,
            status="confirmed",
            app_name=trace.app_name,
            source="trace",
            trace_id=trace.id,
            tags=tags,
            note=note,
            created_by=created_by,
            created_at=trace.started_at + timedelta(minutes=3),
        )
        db.add(case)
        created_cases.append(case)
        return case

    c1 = add_case(t1, "good", "政策条款引用准确，工具调用完整，工单摘要可下载", ["售后", "换新", "工具调用"])
    c2 = add_case(t2, "bad", "订单工具 30s 超时；应更早降级并提示人工", ["售后", "超时", "降级"], reference="查询超时后应直接转人工，不应让用户等待 30 秒。")
    c3 = add_case(t3, "good", "检索链路解释清晰，引用来源正确", ["研发", "RAG"], reference="向量召回 top-20 → Rerank top-5 → LLM 生成，未配置 Rerank 自动降级。")
    c4 = add_case(t4, "good", "条件分支命中正确，话术符合政策", ["客服", "发票"])
    c5 = EvalCase(
        id=uuid.uuid4().hex,
        question="发票超过 30 天还能重开吗？",
        answer="可以重开，提交申请即可。",
        reference_answer="超过 30 天原则上不予重开，特殊情况需走审批。",
        contexts=(t4.context or {}).get("retrieved_chunks", []),
        label="bad",
        status="confirmed",
        app_name="客服流程助手",
        source="manual",
        trace_id="",
        tags=["客服", "发票", "边界条件"],
        note="遗漏「超过 30 天不予重开」的边界，属高风险错误。",
        created_by=created_by,
        created_at=now - timedelta(hours=30),
    )
    db.add(c5)
    created_cases.append(c5)

    db.flush()

    set1 = EvalSet(
        id=uuid.uuid4().hex,
        name="售后客服回归集",
        description="售后高频问题 + 工具超时等异常场景，作为发布前回归基线。",
        created_by=created_by,
        created_at=now - timedelta(days=2),
    )
    set2 = EvalSet(
        id=uuid.uuid4().hex,
        name="研发问答基线",
        description="研发知识库检索与解释类问题，覆盖 good / bad。",
        created_by=created_by,
        created_at=now - timedelta(days=1),
    )
    db.add_all([set1, set2])
    db.flush()
    for s, cases in ((set1, [c1, c2, c5]), (set2, [c3, c4])):
        for case in cases:
            db.add(EvalSetItem(id=uuid.uuid4().hex, set_id=s.id, case_id=case.id))

    db.commit()
    return {
        "created": True,
        "traces": len(created_traces),
        "cases": len(created_cases),
        "sets": 2,
        "message": "演示数据已载入：6 条链路、5 条 Case、2 个评测集",
    }
