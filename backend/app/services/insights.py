"""运营洞察：满意度 / 知识命中率 / 知识缺口聚类 / 最新差评

口径：
- 只统计应用对话（Conversation.app_id 非空），排除评测流量（role="eval"）
- 未命中 = 应用绑定了知识库，但 assistant 回答没有任何引用
- 知识缺口 = 未命中 + 被点踩的回答所对应的用户问题，按字面相似度聚类
"""
import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Application, Conversation, KnowledgeBase, Message
from app.models.chat import MessageFeedback
from app.models.observability import TraceRun

EVAL_ROLE = "eval"
CLUSTER_THRESHOLD = 0.5
MAX_GAPS = 50


# ---------- 聚类（纯函数） ----------

def normalize_question(text: str) -> str:
    return re.sub(r"[\s，。！？、,.!?；;：:「」“”\"'（）()]+", "", (text or "").lower())


def question_terms(text: str) -> set[str]:
    """汉字二元组 + 英文数字词；单字问题退化为单字"""
    norm = normalize_question(text)
    words = set(re.findall(r"[a-z0-9][a-z0-9_.-]*", norm))
    chinese = re.findall(r"[一-鿿]", norm)
    bigrams = {"".join(chinese[i:i + 2]) for i in range(len(chinese) - 1)}
    return words | bigrams or set(chinese)


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster_questions(items: list[dict], threshold: float = CLUSTER_THRESHOLD) -> list[dict]:
    """贪心聚类：按时间顺序归入第一个相似度达标的簇，簇代表为最早出现的问题。
    items: [{question, kind: "miss"|"dislike", app_name, kb_names, time}]"""
    clusters: list[dict] = []
    for item in sorted(items, key=lambda x: x["time"]):
        terms = question_terms(item["question"])
        if not terms:
            continue
        target = next((c for c in clusters if jaccard(terms, c["_terms"]) >= threshold), None)
        if target is None:
            target = {
                "key": normalize_question(item["question"])[:64],
                "question": item["question"].strip(),
                "count": 0, "dislike_count": 0, "miss_count": 0,
                "apps": [], "kb_names": [], "sample_questions": [],
                "last_time": item["time"], "_terms": terms,
            }
            clusters.append(target)
        target["count"] += 1
        target["dislike_count" if item["kind"] == "dislike" else "miss_count"] += 1
        target["last_time"] = max(target["last_time"], item["time"])
        if item.get("app_name") and item["app_name"] not in target["apps"]:
            target["apps"].append(item["app_name"])
        for name in item.get("kb_names") or []:
            if name not in target["kb_names"]:
                target["kb_names"].append(name)
        question = item["question"].strip()
        if question not in target["sample_questions"] and len(target["sample_questions"]) < 5:
            target["sample_questions"].append(question)
    for cluster in clusters:
        cluster.pop("_terms")
    return sorted(clusters, key=lambda c: (-c["count"], -c["dislike_count"]))


# ---------- 数据加载 ----------

def _app_index(db: Session) -> dict[str, Application]:
    return {app.id: app for app in db.query(Application).all()}


def _kb_names(db: Session) -> dict[str, str]:
    return dict(db.query(KnowledgeBase.id, KnowledgeBase.name).all())


def _app_conversations(db: Session, start: datetime, app_id: str | None = None):
    query = db.query(Conversation).filter(
        Conversation.app_id.isnot(None), Conversation.app_id != "",
        Conversation.role != EVAL_ROLE,
    )
    if app_id:
        query = query.filter(Conversation.app_id == app_id)
    convs = {c.id: c for c in query.all()}
    if not convs:
        return {}, []
    messages = (
        db.query(Message)
        .filter(Message.conv_id.in_(list(convs)), Message.created_at >= start)
        .order_by(Message.conv_id, Message.created_at)
        .all()
    )
    return convs, messages


def _ratings(db: Session, message_ids: list[str]) -> dict[str, dict]:
    """每条回答的反馈汇总：有点踩记 -1，否则有点赞记 1；附最新点踩原因"""
    if not message_ids:
        return {}
    result: dict[str, dict] = {}
    rows = (
        db.query(MessageFeedback)
        .filter(MessageFeedback.message_id.in_(message_ids))
        .order_by(MessageFeedback.updated_at)
        .all()
    )
    for fb in rows:
        entry = result.setdefault(fb.message_id, {"likes": 0, "dislikes": 0, "comment": ""})
        if fb.rating < 0:
            entry["dislikes"] += 1
            entry["comment"] = fb.comment or entry["comment"]
        else:
            entry["likes"] += 1
    return result


def _qa_pairs(db: Session, start: datetime, app_id: str | None = None) -> list[dict]:
    """把会话消息配成 (用户问题, 助手回答)，附应用与命中信息"""
    convs, messages = _app_conversations(db, start, app_id)
    apps = _app_index(db)
    pairs = []
    last_question: dict[str, Message] = {}
    for msg in messages:
        if msg.role == "user":
            last_question[msg.conv_id] = msg
            continue
        if msg.role != "assistant":
            continue
        conv = convs.get(msg.conv_id)
        app = apps.get(conv.app_id) if conv else None
        question = last_question.get(msg.conv_id)
        pairs.append({
            "message": msg,
            "question": question.content if question else "",
            "app": app,
            "has_kb": bool(app and app.kb_ids),
            "hit": bool(msg.refs),
        })
    return pairs


# ---------- 对外接口 ----------

def feedback_overview(db: Session, days: int = 30) -> dict:
    start = datetime.now() - timedelta(days=days)
    pairs = _qa_pairs(db, start)
    ratings = _ratings(db, [p["message"].id for p in pairs])
    likes = sum(r["likes"] for r in ratings.values())
    dislikes = sum(r["dislikes"] for r in ratings.values())
    kb_pairs = [p for p in pairs if p["has_kb"]]
    hits = sum(1 for p in kb_pairs if p["hit"])
    return {
        "satisfaction": round(likes / (likes + dislikes) * 100, 1) if likes + dislikes else None,
        "like_count": likes,
        "dislike_count": dislikes,
        "hit_rate": round(hits / len(kb_pairs) * 100, 1) if kb_pairs else None,
        "miss_count": len(kb_pairs) - hits,
    }


def knowledge_gaps(db: Session, days: int = 30, app_id: str | None = None) -> list[dict]:
    start = datetime.now() - timedelta(days=days)
    pairs = _qa_pairs(db, start, app_id)
    ratings = _ratings(db, [p["message"].id for p in pairs])
    kb_names = _kb_names(db)
    items = []
    for p in pairs:
        if not p["question"].strip():
            continue
        disliked = ratings.get(p["message"].id, {}).get("dislikes", 0) > 0
        missed = p["has_kb"] and not p["hit"]
        if not (disliked or missed):
            continue
        app = p["app"]
        items.append({
            "question": p["question"],
            "kind": "dislike" if disliked else "miss",
            "app_name": app.name if app else "",
            "kb_names": [kb_names[k] for k in (app.kb_ids if app else []) if k in kb_names],
            "kb_ids": [k for k in (app.kb_ids if app else []) if k in kb_names],
            "time": p["message"].created_at,
        })
    clusters = cluster_questions(items)[:MAX_GAPS]
    # 建议补充的知识库带上 id，前端直接用于下拉默认值
    name_to_id = {v: k for k, v in kb_names.items()}
    for cluster in clusters:
        cluster["kb_ids"] = [name_to_id[n] for n in cluster["kb_names"] if n in name_to_id]
    return clusters


def bad_feedback(db: Session, limit: int = 20) -> list[dict]:
    rows = (
        db.query(MessageFeedback, Message, Conversation)
        .join(Message, Message.id == MessageFeedback.message_id)
        .join(Conversation, Conversation.id == Message.conv_id)
        .filter(MessageFeedback.rating < 0, Conversation.role != EVAL_ROLE)
        .order_by(MessageFeedback.updated_at.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return []
    apps = _app_index(db)
    message_ids = [m.id for _, m, _ in rows]
    traces = dict(
        db.query(TraceRun.message_id, TraceRun.id).filter(TraceRun.message_id.in_(message_ids)).all()
    )
    result = []
    for fb, msg, conv in rows:
        question = (
            db.query(Message.content)
            .filter(Message.conv_id == conv.id, Message.role == "user", Message.created_at <= msg.created_at)
            .order_by(Message.created_at.desc())
            .limit(1)
            .scalar()
        )
        app = apps.get(conv.app_id or "")
        result.append({
            "message_id": msg.id,
            "trace_id": traces.get(msg.id, ""),
            "app_id": conv.app_id or "",
            "app_name": app.name if app else "",
            "question": question or "",
            "answer": msg.content or "",
            "comment": fb.comment or "",
            "user_id": fb.user_id,
            "time": fb.updated_at,
        })
    return result


def trace_feedback(db: Session, trace_ids: list[str]) -> dict[str, int]:
    """日志行反馈标记：trace → 回答 → 评分汇总（-1 / 1）"""
    ids = [t for t in trace_ids if t]
    if not ids:
        return {}
    pairs = db.query(TraceRun.id, TraceRun.message_id).filter(
        TraceRun.id.in_(ids), TraceRun.message_id.isnot(None), TraceRun.message_id != ""
    ).all()
    ratings = _ratings(db, [m for _, m in pairs])
    result = {}
    for trace_id, message_id in pairs:
        r = ratings.get(message_id)
        if r:
            result[trace_id] = -1 if r["dislikes"] else 1
    return result
