"""分块增强：为每个分块抽取关键词、生成可由该分块回答的问答对

结果写入分块元数据（keywords / qa_pairs），并拼进向量化文本与全文检索字段，
使口语化提问和同义表达也能命中原文。关键词无模型时走规则抽取；问答对需要真实 LLM。
"""
import json
import re
from collections import Counter

from langchain_core.messages import HumanMessage

BATCH_SIZE = 6
MAX_CHUNK_CHARS = 1800
MAX_KEYWORDS = 8
MAX_QA = 5

_STOPWORDS = {
    "以及", "一个", "进行", "相关", "可以", "需要", "内容", "说明", "要求", "根据", "其中", "如果",
    "我们", "他们", "这个", "那个", "没有", "不是", "因为", "所以", "the", "and", "for", "with", "that", "this",
}


def rule_keywords(text: str, limit: int = MAX_KEYWORDS) -> list[str]:
    """无模型时的关键词：高频中文 2-4 字片段与英文/编号词，去掉常见虚词"""
    counter: Counter[str] = Counter()
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}|[A-Z0-9]{2,}[\-0-9A-Z]*", text):
        counter[word] += 2
    for run in re.findall(r"[一-鿿]{2,}", text):
        for size in (4, 3, 2):
            for index in range(len(run) - size + 1):
                counter[run[index:index + size]] += 1
    result: list[str] = []
    for word, count in counter.most_common():
        if count < 2 or word.lower() in _STOPWORDS or any(word in kept for kept in result):
            continue
        result.append(word)
        if len(result) >= limit:
            break
    return result


def clean_keywords(values) -> list[str]:
    result: list[str] = []
    for value in values if isinstance(values, list) else []:
        word = re.sub(r"\s+", " ", str(value or "")).strip(" ，,。；;")
        if word and len(word) <= 40 and word not in result:
            result.append(word)
    return result[:MAX_KEYWORDS]


def clean_qa(values, limit: int = MAX_QA) -> list[dict]:
    result: list[dict] = []
    for value in values if isinstance(values, list) else []:
        if not isinstance(value, dict):
            continue
        question = str(value.get("q") or value.get("question") or "").strip()
        answer = str(value.get("a") or value.get("answer") or "").strip()
        if question and answer and len(question) <= 300 and len(answer) <= 2000:
            result.append({"q": question, "a": answer})
    return result[:limit]


def _parse_items(raw: str) -> list[dict]:
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("模型没有返回 JSON 数组")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, list):
        raise ValueError("模型返回的不是数组")
    return [item for item in value if isinstance(item, dict)]


def _llm_batch(llm, contents: list[str], *, qa: bool, keywords: bool, qa_count: int) -> list[dict]:
    fields = []
    if keywords:
        fields.append('"keywords": 3 到 8 个能区分该片段的检索关键词')
    if qa:
        fields.append(f'"qa": 1 到 {qa_count} 组 {{"q": 用户可能的提问, "a": 仅依据该片段的回答}}')
    blocks = "\n\n".join(f"[片段 {i}]\n{c[:MAX_CHUNK_CHARS]}" for i, c in enumerate(contents))
    prompt = (
        "你是企业知识库的索引增强器。只能依据给定片段，不得补造事实；片段信息不足时返回空数组。\n"
        f"为每个片段输出一个对象，字段为 \"index\"（片段编号）、{'、'.join(fields)}。\n"
        "仅返回 JSON 数组，不要使用 Markdown。\n\n"
        f"{blocks}"
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content if hasattr(response, "content") else str(response)
    if isinstance(content, list):
        content = "".join(str(i.get("text", "")) if isinstance(i, dict) else str(i) for i in content)
    items = _parse_items(content)
    by_index = {int(i["index"]): i for i in items if str(i.get("index", "")).lstrip("-").isdigit()}
    if not by_index and len(items) == len(contents):  # 模型漏写 index 时按顺序对应
        by_index = dict(enumerate(items))
    return [by_index.get(i, {}) for i in range(len(contents))]


def enhance_chunks(db, chunks: list[dict], *, keywords: bool, qa: bool, llm_ref: str | None = None, qa_count: int = 3) -> dict:
    """原地为分块补充 keywords / qa_pairs。单批模型失败不中断导入：关键词退回规则抽取、问答对留空。
    返回 {"qa_pairs": 生成数量, "failed_batches": 失败批次, "simulated": 是否无真实模型}"""
    if not (keywords or qa):
        return {"qa_pairs": 0, "failed_batches": 0, "simulated": False}
    from app.services.chat import build_llm

    try:
        llm, is_fake, _model = build_llm(db, llm_ref=llm_ref or None, temperature=0)
    except RuntimeError:  # 未配置模型且禁用模拟：关键词走规则，问答对留空
        llm, is_fake = None, True
    qa_count = max(1, min(qa_count, MAX_QA))
    generated = failed = 0
    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        results: list[dict] = [{} for _ in batch]
        if not is_fake:
            try:
                results = _llm_batch(llm, [c["content"] for c in batch], qa=qa, keywords=keywords, qa_count=qa_count)
            except Exception:  # noqa: BLE001 —— 模型输出异常时降级，不中断导入
                failed += 1
        for chunk, result in zip(batch, results):
            if keywords:
                chunk["keywords"] = clean_keywords(result.get("keywords")) or rule_keywords(chunk["content"])
            if qa:
                pairs = clean_qa(result.get("qa"), qa_count)
                chunk["qa_pairs"] = pairs
                generated += len(pairs)
    return {"qa_pairs": generated, "failed_batches": failed, "simulated": is_fake}


def chunk_index_text(content: str, metadata: dict | None) -> str:
    """拼进向量化文本的增强内容；没有增强时返回原文"""
    meta = metadata or {}
    lines: list[str] = []
    if meta.get("keywords"):
        lines.append(f"[本段关键词] {'、'.join(meta['keywords'])}")
    pairs = meta.get("qa_pairs") or []
    if pairs:
        lines.append("[本段可回答的问题]")
        lines.extend(f"- {item['q']}" for item in pairs)
    return "\n".join([*lines, content]) if lines else content
