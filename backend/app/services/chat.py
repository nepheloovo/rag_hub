"""对话服务：LangChain LCEL 生成链（检索→上下文组装→LLM 流式）+ 无 Key 时的模拟 LLM 降级"""
from typing import Iterator

from langchain_core.language_models.llms import LLM
from langchain_core.outputs import GenerationChunk
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.services.llm_client import resolve_default_model, resolve_model_ref

DEFAULT_SYSTEM_PROMPT = (
    "你是企业知识助手，请根据提供的参考资料回答用户问题。\n"
    "要求：\n"
    "1. 仅依据参考资料回答，引用时注明来源编号，如 [1]；\n"
    "2. 资料中没有的信息，明确说明「资料中未提及」，不得编造；\n"
    "3. 回答简洁、准确，使用中文。"
)

HUMAN_TEMPLATE = (
    "历史对话：\n{history}\n\n"
    "参考资料：\n{contexts}\n\n"
    "用户问题：{question}\n\n请回答："
)


def format_contexts(chunks: list) -> str:
    """将检索到的分块格式化为带编号的参考资料"""
    parts = []
    for i, item in enumerate(chunks, start=1):
        meta = item.chunk.metadata_ or {}
        source = meta.get("source", "")
        page = meta.get("page", 0)
        parts.append(f"[{i}] {item.chunk.content}\n（来源：{source} 第 {page} 页）")
    return "\n\n".join(parts)


def format_history(messages: list[tuple[str, str]]) -> str:
    if not messages:
        return "（无）"
    lines = []
    for role, content in messages:
        speaker = "用户" if role == "user" else "助手"
        lines.append(f"{speaker}：{content}")
    return "\n".join(lines)


class FakeStreamingLLM(LLM):
    """未配置真实 LLM 时的模拟模型：流式输出并引用检索内容，保证全链路可自测"""

    model: str = "fake-echo-llm"

    @property
    def _llm_type(self) -> str:
        return "fake-echo"

    def _call(self, prompt: str, stop=None, **kwargs):
        return self._answer(prompt)

    def _stream(self, prompt: str, stop=None, **kwargs) -> Iterator[GenerationChunk]:
        for piece in _split_stream(self._answer(prompt)):
            yield GenerationChunk(text=piece)

    def _answer(self, prompt: str) -> str:
        # 从提示词中截取参考资料与问题，构造可读的模拟回答
        question = ""
        contexts = []
        if "用户问题：" in prompt:
            question = prompt.split("用户问题：")[-1].split("请回答")[0].strip()
        if "参考资料：" in prompt:
            ctx_block = prompt.split("参考资料：")[1].split("历史对话")[0]
            for line in ctx_block.split("\n\n"):
                line = line.strip()
                if line.startswith("[") and "（来源" in line:
                    contexts.append(line)
        body = "\n".join(contexts[:2])
        return (
            f"【模拟回答 · 未配置真实 LLM】\n\n"
            f"你问的是：{question}\n\n"
            f"根据知识库检索到的相关资料：\n{body}\n\n"
            f"（在「模型配置」启用服务商并配置 LLM 后，此处将由真实模型生成回答。）"
        )


def _split_stream(text: str, size: int = 12) -> Iterator[str]:
    for i in range(0, len(text), size):
        yield text[i : i + size]


def build_llm(db: Session, llm_ref: str | None = None, temperature: float | None = None):
    """返回 (chain, is_fake, model_name)；chain 输入 {history, contexts, question}，流式输出"""
    found = None
    if llm_ref:
        found = resolve_model_ref(db, llm_ref, "llm")
    if not found:
        found = resolve_default_model(db, "llm")
    if found:
        provider, model = found
        llm = ChatOpenAI(
            model=model,
            openai_api_base=provider.base_url,
            openai_api_key=provider.api_key,
            temperature=temperature if temperature is not None else 0.2,
            streaming=True,
            model_kwargs={"stream_options": {"include_usage": True}},
            max_retries=1,
            timeout=60,
        )
        return llm, False, model
    if not settings.allow_fake_llm:
        raise RuntimeError("未配置可用的 LLM 模型，且已禁用模拟模型降级")
    return FakeStreamingLLM(), True, "fake-echo-llm"


def stream_answer(
    db: Session,
    query: str,
    history_messages: list[tuple[str, str]],
    contexts: list,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    llm_ref: str | None = None,
    temperature: float | None = None,
):
    """流式生成回答；yield (chunk, is_fake, model_name)"""
    llm, is_fake, model_name = build_llm(db, llm_ref=llm_ref, temperature=temperature)
    prompt = ChatPromptTemplate.from_messages(
        [("system", system_prompt), ("human", HUMAN_TEMPLATE)]
    )
    chain = prompt | llm
    inputs = {
        "history": format_history(history_messages),
        "contexts": format_contexts(contexts),
        "question": query,
    }
    for chunk in chain.stream(inputs):
        yield chunk, is_fake, model_name
