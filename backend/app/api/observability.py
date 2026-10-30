"""可观测 API：概览、链路、构建、计费、回流、演示数据"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Integer, func, text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.database import get_db
from app.models import (
    Application,
    EvalCase,
    EvalSet,
    EvalSetItem,
    ModelPrice,
    TraceRun,
    TraceSpan,
    User,
)
from app.services.observability import PRICE_SEEDS, seed_demo_observability, seed_prices

router = APIRouter(prefix="/observability", tags=["可观测"])


def _trace_dict(trace: TraceRun, include_context: bool = False) -> dict:
    data = {
        "id": trace.id,
        "trace_type": trace.trace_type,
        "title": trace.title,
        "query": trace.query,
        "answer": trace.answer,
        "status": trace.status,
        "app_id": trace.app_id,
        "app_name": trace.app_name,
        "app_kind": trace.app_kind,
        "kb_id": trace.kb_id,
        "kb_name": trace.kb_name,
        "conversation_id": trace.conversation_id,
        "message_id": trace.message_id,
        "role": trace.role,
        "source": trace.source,
        "model": trace.model,
        "models": trace.models or {},
        "tokens": trace.tokens or {},
        "cost_cny": round(float(trace.cost_cny or 0), 6),
        "duration_ms": trace.duration_ms,
        "span_count": trace.span_count,
        "started_at": trace.started_at,
        "error": trace.error,
        "metadata": trace.metadata_ or {},
    }
    if include_context:
        data["context"] = trace.context or {}
    return data


def _span_dict(span: TraceSpan) -> dict:
    return {
        "id": span.id,
        "trace_id": span.trace_id,
        "parent_id": span.parent_id,
        "seq": span.seq,
        "depth": span.depth,
        "span_type": span.span_type,
        "name": span.name,
        "status": span.status,
        "started_offset_ms": span.started_offset_ms,
        "duration_ms": span.duration_ms,
        "input": span.input,
        "output": span.output,
        "tokens": span.tokens or {},
        "cost_cny": round(float(span.cost_cny or 0), 6),
        "context": span.context or {},
        "error": span.error,
        "error_hint": span.error_hint,
        "code_key": span.code_key,
        "code": span.code,
        "code_explain": span.code_explain or [],
        "metadata": span.metadata_ or {},
    }


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    values = sorted(values)
    idx = min(len(values) - 1, max(0, int(round((p / 100) * (len(values) - 1)))))
    return int(values[idx])


@router.get("/overview")
def overview(
    days: int = Query(7, ge=1, le=60),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = datetime.now()
    start = now - timedelta(days=days)
    # 评测流量不计入运行健康度（计费仍保留评测消耗，属于真实成本）
    runs = db.query(TraceRun).filter(
        TraceRun.started_at >= start, func.coalesce(TraceRun.source, "") != "eval"
    ).all()
    total = len(runs)
    errors = sum(1 for r in runs if r.status == "error")
    degraded = sum(1 for r in runs if r.status == "degraded")
    success = sum(1 for r in runs if r.status == "success")
    durations = [r.duration_ms or 0 for r in runs]
    tokens = sum(int((r.tokens or {}).get("total", 0) or 0) for r in runs)
    cost = sum(float(r.cost_cny or 0) for r in runs)

    # 按天趋势
    dates = [(now - timedelta(days=i)).date() for i in range(days - 1, -1, -1)]
    trend = []
    for day in dates:
        day_runs = [r for r in runs if r.started_at and r.started_at.date() == day]
        trend.append(
            {
                "date": str(day),
                "total": len(day_runs),
                "success": sum(1 for r in day_runs if r.status == "success"),
                "error": sum(1 for r in day_runs if r.status == "error"),
                "tokens": sum(int((r.tokens or {}).get("total", 0) or 0) for r in day_runs),
                "cost_cny": round(sum(float(r.cost_cny or 0) for r in day_runs), 6),
            }
        )

    # 类型分布
    type_rows = (
        db.query(TraceRun.trace_type, func.count(TraceRun.id))
        .filter(TraceRun.started_at >= start)
        .group_by(TraceRun.trace_type)
        .all()
    )
    # 应用 Top
    app_rows = (
        db.query(
            TraceRun.app_name,
            func.count(TraceRun.id),
            func.coalesce(func.sum(TraceRun.cost_cny), 0),
        )
        .filter(TraceRun.started_at >= start, TraceRun.trace_type != "kb_build")
        .group_by(TraceRun.app_name)
        .order_by(func.count(TraceRun.id).desc())
        .limit(6)
        .all()
    )
    # Skill / Tool 调用
    tool_calls = (
        db.query(func.count(TraceSpan.id))
        .join(TraceRun, TraceRun.id == TraceSpan.trace_id)
        .filter(TraceRun.started_at >= start, TraceSpan.span_type.in_(("tool.call", "skill.call")))
        .scalar()
        or 0
    )
    tool_errors = (
        db.query(func.count(TraceSpan.id))
        .join(TraceRun, TraceRun.id == TraceSpan.trace_id)
        .filter(
            TraceRun.started_at >= start,
            TraceSpan.span_type.in_(("tool.call", "skill.call")),
            TraceSpan.status == "error",
        )
        .scalar()
        or 0
    )
    skill_rows = (
        db.query(TraceSpan.name, func.count(TraceSpan.id))
        .join(TraceRun, TraceRun.id == TraceSpan.trace_id)
        .filter(TraceRun.started_at >= start, TraceSpan.span_type == "skill.call")
        .group_by(TraceSpan.name)
        .order_by(func.count(TraceSpan.id).desc())
        .all()
    )

    return {
        "days": days,
        "total": total,
        "success": success,
        "error": errors,
        "degraded": degraded,
        "success_rate": round(success / total * 100, 1) if total else 100.0,
        "p95_duration_ms": _percentile(durations, 95),
        "avg_duration_ms": int(sum(durations) / total) if total else 0,
        "tokens": tokens,
        "cost_cny": round(cost, 4),
        "agent_runs": sum(1 for r in runs if r.trace_type == "agent"),
        "tool_calls": int(tool_calls),
        "tool_errors": int(tool_errors),
        "trend": trend,
        "types": [{"type": t, "count": c} for t, c in type_rows],
        "top_apps": [
            {"app_name": name or "（未命名）", "count": count, "cost_cny": round(float(cost or 0), 4)}
            for name, count, cost in app_rows
        ],
        "skills": [
            {"name": str(name or "未知 Skill").replace("Skill · ", ""), "count": count}
            for name, count in skill_rows
        ],
    }


@router.get("/traces")
def list_traces(
    trace_type: str | None = None,
    status: str | None = None,
    app_id: str | None = None,
    kb_id: str | None = None,
    source: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(TraceRun)
    if trace_type:
        query = query.filter(TraceRun.trace_type == trace_type)
    if status:
        query = query.filter(TraceRun.status == status)
    if app_id:
        query = query.filter(TraceRun.app_id == app_id)
    if kb_id:
        query = query.filter(TraceRun.kb_id == kb_id)
    if source:
        query = query.filter(TraceRun.source == source)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (TraceRun.query.ilike(like)) | (TraceRun.title.ilike(like)) | (TraceRun.answer.ilike(like))
        )
    total = query.count()
    rows = (
        query.order_by(TraceRun.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    # 关联 Case 标记，列表上直接展示「已回流」
    ids = [r.id for r in rows]
    case_rows = (
        db.query(EvalCase.trace_id, EvalCase.label, EvalCase.id)
        .filter(EvalCase.trace_id.in_(ids))
        .all()
        if ids
        else []
    )
    case_map: dict[str, list] = {}
    for trace_id, label, case_id in case_rows:
        case_map.setdefault(trace_id, []).append({"id": case_id, "label": label})
    items = []
    for row in rows:
        item = _trace_dict(row)
        item["cases"] = case_map.get(row.id, [])
        items.append(item)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/traces/{trace_id}")
def get_trace(
    trace_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trace = db.get(TraceRun, trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="链路不存在")
    spans = (
        db.query(TraceSpan)
        .filter(TraceSpan.trace_id == trace_id)
        .order_by(TraceSpan.seq)
        .all()
    )
    cases = (
        db.query(EvalCase)
        .filter(EvalCase.trace_id == trace_id)
        .order_by(EvalCase.created_at.desc())
        .all()
    )
    data = _trace_dict(trace, include_context=True)
    data["spans"] = [_span_dict(s) for s in spans]
    data["cases"] = [
        {
            "id": c.id,
            "label": c.label,
            "note": c.note,
            "tags": c.tags or [],
            "created_at": c.created_at,
        }
        for c in cases
    ]
    data["metrics"] = {
        "llm_tokens": int((trace.tokens or {}).get("llm", 0) or 0),
        "embedding_tokens": int((trace.tokens or {}).get("embedding", 0) or 0),
        "rerank_tokens": int((trace.tokens or {}).get("rerank", 0) or 0),
    }
    return data


@router.get("/builds")
def list_builds(
    kb_id: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(TraceRun).filter(TraceRun.trace_type == "kb_build")
    if kb_id:
        query = query.filter(TraceRun.kb_id == kb_id)
    if status:
        query = query.filter(TraceRun.status == status)
    total = query.count()
    rows = (
        query.order_by(TraceRun.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = []
    for row in rows:
        stages = (
            db.query(TraceSpan)
            .filter(TraceSpan.trace_id == row.id)
            .order_by(TraceSpan.seq)
            .all()
        )
        item = _trace_dict(row)
        item["stages"] = [_span_dict(s) for s in stages]
        items.append(item)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/billing")
def billing(
    days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = datetime.now()
    start = now - timedelta(days=days)
    runs = db.query(TraceRun).filter(TraceRun.started_at >= start).all()
    total_cost = round(sum(float(r.cost_cny or 0) for r in runs), 4)
    total_tokens = sum(int((r.tokens or {}).get("total", 0) or 0) for r in runs)

    by_day = []
    for i in range(days - 1, -1, -1):
        day = (now - timedelta(days=i)).date()
        day_runs = [r for r in runs if r.started_at and r.started_at.date() == day]
        by_day.append(
            {
                "date": str(day),
                "cost_cny": round(sum(float(r.cost_cny or 0) for r in day_runs), 4),
                "input": sum(int((r.tokens or {}).get("input", 0) or 0) for r in day_runs),
                "output": sum(int((r.tokens or {}).get("output", 0) or 0) for r in day_runs),
                "calls": len(day_runs),
            }
        )

    app_map: dict[str, dict] = {}
    for r in runs:
        key = r.app_name or ("知识库构建" if r.trace_type == "kb_build" else "（无应用）")
        row = app_map.setdefault(key, {"app_name": key, "calls": 0, "cost_cny": 0.0, "tokens": 0})
        row["calls"] += 1
        row["cost_cny"] = round(row["cost_cny"] + float(r.cost_cny or 0), 4)
        row["tokens"] += int((r.tokens or {}).get("total", 0) or 0)

    purpose_map: dict[str, dict] = {}
    for r in runs:
        key = r.trace_type
        row = purpose_map.setdefault(key, {"type": key, "calls": 0, "cost_cny": 0.0, "tokens": 0})
        row["calls"] += 1
        row["cost_cny"] = round(row["cost_cny"] + float(r.cost_cny or 0), 4)
        row["tokens"] += int((r.tokens or {}).get("total", 0) or 0)

    # 按模型：使用 span 上记录的 tokens.model 聚合，能拆出 embedding / rerank / LLM
    span_rows = (
        db.query(TraceSpan.tokens, TraceSpan.cost_cny, TraceRun.model)
        .join(TraceRun, TraceRun.id == TraceSpan.trace_id)
        .filter(TraceRun.started_at >= start)
        .all()
    )
    model_map: dict[str, dict] = {}
    for tokens, cost, trace_model in span_rows:
        tokens = tokens or {}
        if not (tokens.get("total") or tokens.get("input") or tokens.get("output")):
            continue
        model = tokens.get("model") or trace_model or "未知模型"
        row = model_map.setdefault(
            model, {"model": model, "cost_cny": 0.0, "input": 0, "output": 0, "spans": 0}
        )
        row["cost_cny"] = round(row["cost_cny"] + float(cost or 0), 4)
        row["input"] += int(tokens.get("input", 0) or 0)
        row["output"] += int(tokens.get("output", 0) or 0)
        row["spans"] += 1
    by_model = sorted(model_map.values(), key=lambda x: x["cost_cny"], reverse=True)

    return {
        "days": days,
        "total_cost_cny": total_cost,
        "total_tokens": total_tokens,
        "by_day": by_day,
        "by_app": sorted(app_map.values(), key=lambda x: x["cost_cny"], reverse=True),
        "by_model": by_model,
        "by_purpose": sorted(purpose_map.values(), key=lambda x: x["cost_cny"], reverse=True),
        "calls": len(runs),
    }


@router.get("/prices")
def list_prices(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    seed_prices(db)
    rows = db.query(ModelPrice).order_by(ModelPrice.model).all()
    return [
        {
            "model": r.model,
            "input_price": r.input_price,
            "output_price": r.output_price,
            "currency": r.currency,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


class PriceUpdate(BaseModel):
    input_price: float = Field(ge=0)
    output_price: float = Field(ge=0)


@router.put("/prices/{model}")
def update_price(
    model: str,
    data: PriceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("platform_admin")),
):
    row = db.get(ModelPrice, model)
    if not row:
        row = ModelPrice(model=model, input_price=data.input_price, output_price=data.output_price)
        db.add(row)
    else:
        row.input_price = data.input_price
        row.output_price = data.output_price
    db.commit()
    return {"ok": True}


class ToCaseRequest(BaseModel):
    label: str = "good"
    note: str = ""
    tags: list[str] = []
    reference_answer: str = ""
    set_id: str = ""


@router.post("/traces/{trace_id}/to-case")
def trace_to_case(
    trace_id: str,
    data: ToCaseRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trace = db.get(TraceRun, trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="链路不存在")
    if data.label not in ("good", "bad"):
        raise HTTPException(status_code=422, detail="标签必须是 good / bad")
    case = (
        db.query(EvalCase)
        .filter(EvalCase.trace_id == trace_id, EvalCase.source == "trace")
        .first()
    )
    if case:
        case.label = data.label
        case.note = data.note or case.note
        case.tags = data.tags or case.tags
        case.reference_answer = data.reference_answer or case.reference_answer
        case.status = "confirmed"
    else:
        case = EvalCase(
            id=uuid.uuid4().hex,
            question=trace.query,
            answer=trace.answer,
            reference_answer=data.reference_answer,
            contexts=(trace.context or {}).get("retrieved_chunks", []),
            label=data.label,
            status="confirmed",
            app_id=trace.app_id,
            app_name=trace.app_name,
            source="trace",
            trace_id=trace.id,
            tags=data.tags,
            note=data.note,
            created_by=user.display_name or user.username,
        )
        db.add(case)
    db.flush()
    added = False
    if data.set_id:
        eval_set = db.get(EvalSet, data.set_id)
        if not eval_set:
            raise HTTPException(status_code=404, detail="评测集不存在")
        exists = (
            db.query(EvalSetItem)
            .filter(EvalSetItem.set_id == data.set_id, EvalSetItem.case_id == case.id)
            .first()
        )
        if not exists:
            db.add(EvalSetItem(id=uuid.uuid4().hex, set_id=data.set_id, case_id=case.id))
            added = True
    db.commit()
    return {"case_id": case.id, "label": case.label, "added_to_set": added}


@router.post("/demo")
def load_demo(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("platform_admin", "app_developer")),
):
    seed_prices(db)
    return seed_demo_observability(db, created_by=user.display_name or user.username)
