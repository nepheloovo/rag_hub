"""分块策略引擎：9 种策略（对齐知枢原型）

返回统一结构：[{"content": str, "heading": str, "page": int, "kind": "chunk"|"parent"|"child",
"parent_group": str|None, "extra": dict}]
"""
import math
import re
import uuid

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app.config import settings

STRATEGY_LABELS = {
    "smart": "智能分块：识别标题和段落结构，自动递归切分到合适长度（推荐默认）",
    "heading": "按标题层级：按 Markdown/Word 的 H1–H3 切分，每块保留标题路径",
    "separator": "自定义分隔符：按指定符号切分，如空行、### 或「第X条」",
    "fixed": "固定长度：按字符数和重叠量机械切分",
    "parent_child": "父子分块：小块用于精准召回，命中后返回所在大块",
    "semantic": "语义分块：相邻段落向量相似度突变处断开，按主题切分",
    "qa_split": "问答对拆分：由模型从文档提取「问题-答案」对",
    "page": "按页切分：PDF 一页一块，保留页码",
    "table_row": "表格按行：Excel/CSV 每行一块，表头作为上下文",
}



def normalize_chunk_config(config: dict | None, default_strategy: str = "smart") -> dict:
    """逐文件切块配置归一化：非法值回退默认，数值夹到合理区间"""
    raw = config if isinstance(config, dict) else {}
    strategy = raw.get("strategy") if raw.get("strategy") in STRATEGY_LABELS else default_strategy
    if strategy not in STRATEGY_LABELS:
        strategy = "smart"

    def _int(key: str, default: int, low: int, high: int) -> int:
        try:
            return max(low, min(high, int(raw.get(key, default))))
        except (TypeError, ValueError):
            return default

    chunk_size = _int("chunk_size", settings.chunk_size, 100, 4000)
    return {
        "strategy": strategy,
        "chunk_size": chunk_size,
        "chunk_overlap": _int("chunk_overlap", min(settings.chunk_overlap, chunk_size // 2), 0, chunk_size // 2),
        "separator": str(raw.get("separator") or "")[:50],
        "enhance_keywords": bool(raw.get("enhance_keywords")),
        "enhance_qa": bool(raw.get("enhance_qa")),
    }


PAGE_MARK_RE = re.compile(r"<!--\s*第\s*(\d+)\s*页(?:\(OCR\))?\s*-->")
TABLE_RE = re.compile(r"\|[^\n]+\|\n\|[\s\-|]+\|\n((?:\|[^\n]*\|\n?)+)", re.M)


def _fixed_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "，", " ", ""]
    )


def _heading_split(markdown: str, chunk_size: int, chunk_overlap: int) -> list[dict]:
    """标题层级 + 段内递归二次切分"""
    text_splitter = _fixed_splitter(chunk_size, chunk_overlap)
    chunks: list[dict] = []
    try:
        md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
            strip_headers=False,
        )
        sections = md_splitter.split_text(markdown)
    except Exception:  # noqa: BLE001
        sections = []
    for sec in sections:
        heading = sec.metadata.get("h1") or sec.metadata.get("h2") or sec.metadata.get("h3") or ""
        for piece in text_splitter.split_text(sec.page_content):
            if piece.strip():
                chunks.append({"content": piece, "heading": heading})
    return chunks


def _page_extract(text: str) -> tuple[str, int]:
    m = PAGE_MARK_RE.search(text)
    if m:
        return PAGE_MARK_RE.sub("", text).strip(), int(m.group(1))
    return text, 0


def _split_by_page(markdown: str, chunk_size: int, chunk_overlap: int) -> list[dict]:
    """按页切分：以页注释为边界，超长页再按固定长度二次切分"""
    parts = PAGE_MARK_RE.split(markdown)
    # parts 交错：[前缀, 页码1, 内容1, 页码2, 内容2, ...]
    chunks: list[dict] = []
    text_splitter = _fixed_splitter(chunk_size, chunk_overlap)
    i = 0
    page = 0
    while i < len(parts):
        seg = parts[i]
        if i > 0:
            try:
                page = int(parts[i - 1])
            except ValueError:
                page = page
        if seg.strip():
            if len(seg) <= chunk_size * 2:
                chunks.append({"content": seg.strip(), "heading": "", "page": page})
            else:
                for piece in text_splitter.split_text(seg):
                    chunks.append({"content": piece, "heading": "", "page": page})
        i += 2
    return chunks


def _split_by_separator(markdown: str, chunk_size: int, separator: str) -> list[dict]:
    """自定义分隔符切分，超长段再按固定长度二次切分"""
    sep_re = re.compile(separator) if separator else re.compile(r"\n\n+")
    pieces = [p.strip() for p in sep_re.split(markdown) if p.strip()]
    text_splitter = _fixed_splitter(chunk_size, 0)
    chunks: list[dict] = []
    for piece in pieces:
        if len(piece) <= chunk_size:
            chunks.append({"content": piece, "heading": ""})
        else:
            for sub in text_splitter.split_text(piece):
                chunks.append({"content": sub, "heading": ""})
    return chunks


def _split_by_table_rows(markdown: str, chunk_size: int) -> list[dict]:
    """表格按行：每行一块，表头作为上下文；非表格内容回退标题策略"""
    chunks: list[dict] = []
    remaining = markdown
    for m in TABLE_RE.finditer(markdown):
        # 表格前的普通文本回退标题策略
        pre = remaining[: m.start()]
        if pre.strip():
            chunks.extend(_heading_split(pre, chunk_size, 0))
        table_text = m.group(0)
        lines = [l.strip() for l in table_text.split("\n") if l.strip()]
        if len(lines) >= 2:
            header = lines[0]
            for row in lines[2:]:  # 跳过表头与分隔行
                chunks.append({"content": f"{header}\n{row}", "heading": ""})
        remaining = markdown[m.end():]
    if remaining.strip():
        chunks.extend(_heading_split(remaining, chunk_size, 0))
    return chunks


def _split_parent_child(markdown: str, chunk_size: int, chunk_overlap: int) -> list[dict]:
    """父子分块：大块(parent) + 小块(child)，child 引用 parent_group"""
    parents = _heading_split(markdown, chunk_size * 3, 0) or _fixed_splitter(
        chunk_size * 3, 0
    ).split_text(markdown)
    child_splitter = _fixed_splitter(chunk_size, chunk_overlap)
    result: list[dict] = []
    for parent in parents:
        group = uuid.uuid4().hex[:12]
        content = parent["content"] if isinstance(parent, dict) else parent
        heading = parent["heading"] if isinstance(parent, dict) else ""
        result.append(
            {"content": content, "heading": heading, "kind": "parent", "parent_group": group}
        )
        for child in child_splitter.split_text(content):
            if child.strip():
                result.append(
                    {"content": child, "heading": heading, "kind": "child", "parent_group": group}
                )
    return result


def _split_semantic(markdown: str, chunk_size: int, db=None, max_paragraphs: int = 400) -> list[dict]:
    """语义分块：相邻段落向量相似度突变处断开"""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", markdown) if p.strip()]
    if len(paragraphs) <= 1:
        return _heading_split(markdown, chunk_size, 0)
    paragraphs = paragraphs[:max_paragraphs]

    # 段落向量
    try:
        if db is None:
            raise RuntimeError("no db")
        from app.services.embedding import get_embedding_service

        vectors = get_embedding_service(db).embed_texts(paragraphs)
    except Exception:  # noqa: BLE001 —— 无 embedding 时回退标题策略
        return _heading_split(markdown, chunk_size, 0)

    def cos(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1
        nb = math.sqrt(sum(y * y for y in b)) or 1
        return dot / (na * nb)

    sims = [cos(vectors[i], vectors[i + 1]) for i in range(len(paragraphs) - 1)]
    mean = sum(sims) / len(sims)
    # 阈值：相似度低于均值减去 0.5 倍标准差处断开
    std = math.sqrt(sum((s - mean) ** 2 for s in sims) / len(sims))
    threshold = max(0.0, mean - 0.6 * std)

    chunks: list[dict] = []
    buf = [paragraphs[0]]
    for i, s in enumerate(sims):
        if s < threshold and buf:
            chunks.append({"content": "\n\n".join(buf), "heading": ""})
            buf = [paragraphs[i + 1]]
        else:
            buf.append(paragraphs[i + 1])
    if buf:
        chunks.append({"content": "\n\n".join(buf), "heading": ""})

    # 合并过小块、拆开过大块
    text_splitter = _fixed_splitter(chunk_size, 0)
    final: list[dict] = []
    merged = ""
    for c in chunks:
        if len(merged) + len(c["content"]) <= chunk_size:
            merged = (merged + "\n\n" + c["content"]).strip()
        else:
            if merged:
                final.append({"content": merged, "heading": ""})
            merged = c["content"]
    if merged:
        final.append({"content": merged, "heading": ""})
    for i in range(len(final) - 1, -1, -1):
        if len(final[i]["content"]) > chunk_size * 2:
            expanded = [{"content": p, "heading": ""} for p in text_splitter.split_text(final[i]["content"])]
            final[i : i + 1] = expanded
    return final


def _split_qa_pairs(markdown: str, chunk_size: int, db=None) -> list[dict]:
    """问答对拆分：由 LLM 提取 Q-A 对；无 LLM 时回退标题策略"""
    try:
        if db is None:
            raise RuntimeError("no db")
        from app.services.chat import build_llm
        from langchain_core.prompts import ChatPromptTemplate

        llm, _, _ = build_llm(db, temperature=0.1)
        chain = ChatPromptTemplate.from_messages([("human", "{input}")]) | llm

        pairs: list[dict] = []
        # 分段处理长文档
        segments = [markdown[i : i + 4000] for i in range(0, len(markdown), 4000)] or [markdown]
        for seg in segments:
            if not seg.strip():
                continue
            prompt = (
                "从以下文档内容中提取「问题-答案」对（FAQ）。只输出 JSON 数组，"
                '每项格式 {"q": "问题", "a": "答案"}；没有可提取的问答对则输出 []。\n\n'
                f"文档内容：\n{seg}"
            )
            resp = chain.invoke({"input": prompt})
            text = resp if isinstance(resp, str) else (resp.content if hasattr(resp, "content") else str(resp))
            import json as _json

            try:
                data = _json.loads(text)
            except Exception:  # noqa: BLE001
                start, end = text.find("["), text.rfind("]")
                try:
                    data = _json.loads(text[start : end + 1]) if start >= 0 and end > start else []
                except Exception:  # noqa: BLE001
                    data = []
            for item in data:
                if isinstance(item, dict) and item.get("q"):
                    pairs.append(item)
        if pairs:
            chunks = []
            for p in pairs:
                content = f"问：{p['q']}\n答：{p.get('a', '')}".strip()
                if content:
                    chunks.append({"content": content, "heading": ""})
            return chunks
    except Exception:  # noqa: BLE001
        pass
    return _heading_split(markdown, chunk_size, 0)


def split_markdown(
    markdown: str,
    strategy: str = "smart",
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    separator: str = "",
    db=None,
) -> list[dict]:
    """按策略切分，返回统一结构（content/heading/page/kind/parent_group）"""
    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = chunk_overlap or settings.chunk_overlap
    if chunk_overlap >= chunk_size:
        chunk_overlap = max(0, chunk_size // 4)  # 防御：overlap 不得大于等于 size

    if strategy == "page":
        chunks = _split_by_page(markdown, chunk_size, chunk_overlap)
    elif strategy == "separator":
        chunks = _split_by_separator(markdown, chunk_size, separator)
    elif strategy == "table_row":
        chunks = _split_by_table_rows(markdown, chunk_size)
    elif strategy == "parent_child":
        chunks = _split_parent_child(markdown, chunk_size, chunk_overlap)
    elif strategy == "semantic":
        chunks = _split_semantic(markdown, chunk_size, db)
    elif strategy == "qa_split":
        chunks = _split_qa_pairs(markdown, chunk_size, db)
    elif strategy == "fixed":
        chunks = [
            {"content": p, "heading": ""}
            for p in _fixed_splitter(chunk_size, chunk_overlap).split_text(markdown)
            if p.strip()
        ]
    else:  # smart / heading
        chunks = _heading_split(markdown, chunk_size, chunk_overlap)

    if not chunks:
        chunks = [
            {"content": p, "heading": ""}
            for p in _fixed_splitter(chunk_size, chunk_overlap).split_text(markdown)
            if p.strip()
        ]

    # 归一化：补充 page/kind/parent_group 字段并剔除页码注释
    for c in chunks:
        content, page = _page_extract(c.get("content", ""))
        c["content"] = content.strip()
        c["page"] = c.get("page") or page
        c.setdefault("heading", "")
        c.setdefault("kind", "chunk")
        c.setdefault("parent_group", None)
    return [c for c in chunks if c["content"]]
