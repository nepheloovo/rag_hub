"""评测集 API：线上 Case 回流池 + 评测集聚合 + JSONL 导出"""
from __future__ import annotations

import json
import uuid
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import Application, Chunk, EvalCase, EvalSet, EvalSetItem, TraceRun, User
from app.models.eval import EvalRun
from app.services.eval_runner import case_readiness, run_summary, start_run, step_run

router = APIRouter(prefix="/eval", tags=["评测集"])


def _case_dict(case: EvalCase, sets: list[dict] | None = None) -> dict:
    return {
        "id": case.id,
        "question": case.question,
        "answer": case.answer,
        "reference_answer": case.reference_answer,
        "expected_keywords": case.expected_keywords or [],
        "forbidden_keywords": case.forbidden_keywords or [],
        "require_citations": bool(case.require_citations),
        "readiness": case_readiness(case),
        "contexts": case.contexts or [],
        "label": case.label,
        "status": case.status,
        "app_id": case.app_id,
        "app_name": case.app_name,
        "source": case.source,
        "trace_id": case.trace_id,
        "tags": case.tags or [],
        "note": case.note,
        "created_by": case.created_by,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "sets": sets or [],
    }


def _set_case_ids(db: Session, set_id: str) -> list[str]:
    rows = (
        db.query(EvalSetItem.case_id)
        .filter(EvalSetItem.set_id == set_id)
        .order_by(EvalSetItem.added_at)
        .all()
    )
    return [r[0] for r in rows]


def _set_summary(db: Session, eval_set: EvalSet) -> dict:
    case_ids = _set_case_ids(db, eval_set.id)
    cases = db.query(EvalCase).filter(EvalCase.id.in_(case_ids)).all() if case_ids else []
    good = sum(1 for c in cases if c.label == "good")
    bad = sum(1 for c in cases if c.label == "bad")
    apps = sorted({c.app_name for c in cases if c.app_name})
    app = db.get(Application, eval_set.app_id) if eval_set.app_id else None
    latest = (
        db.query(EvalRun).filter(EvalRun.set_id == eval_set.id)
        .order_by(EvalRun.created_at.desc(), EvalRun.id.desc()).first()
    )
    return {
        "id": eval_set.id,
        "name": eval_set.name,
        "description": eval_set.description,
        "app_id": eval_set.app_id or "",
        "app_name": app.name if app else "",
        "is_release_gate": bool(eval_set.is_release_gate),
        "latest_run": run_summary(db, latest, include_results=False) if latest else None,
        "created_by": eval_set.created_by,
        "created_at": eval_set.created_at,
        "updated_at": eval_set.updated_at,
        "case_count": len(cases),
        "good_count": good,
        "bad_count": bad,
        "apps": apps,
        "tags": sorted({tag for c in cases for tag in (c.tags or [])})[:8],
    }


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cases = db.query(EvalCase).all()
    week_start = datetime.now(timezone.utc) - timedelta(days=7)
    sets = db.query(EvalSet).all()
    tag_counter: dict[str, int] = {}
    app_counter: dict[str, int] = {}
    for case in cases:
        for tag in case.tags or []:
            tag_counter[tag] = tag_counter.get(tag, 0) + 1
        key = case.app_name or "（无应用）"
        app_counter[key] = app_counter.get(key, 0) + 1
    return {
        "case_count": len(cases),
        "good_count": sum(1 for c in cases if c.label == "good"),
        "bad_count": sum(1 for c in cases if c.label == "bad"),
        "set_count": len(sets),
        "new_this_week": sum(1 for c in cases if c.created_at and c.created_at >= week_start),
        "unassigned": sum(
            1
            for c in cases
            if not db.query(EvalSetItem.id).filter(EvalSetItem.case_id == c.id).first()
        ),
        "top_tags": [{"tag": k, "count": v} for k, v in sorted(tag_counter.items(), key=lambda x: -x[1])[:8]],
        "top_apps": [{"app_name": k, "count": v} for k, v in sorted(app_counter.items(), key=lambda x: -x[1])[:8]],
    }


@router.get("/cases")
def list_cases(
    label: str | None = None,
    status: str | None = None,
    source: str | None = None,
    app_id: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(EvalCase)
    if label:
        query = query.filter(EvalCase.label == label)
    if status:
        query = query.filter(EvalCase.status == status)
    if source:
        query = query.filter(EvalCase.source == source)
    if app_id:
        query = query.filter(EvalCase.app_id == app_id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (EvalCase.question.ilike(like))
            | (EvalCase.answer.ilike(like))
            | (EvalCase.note.ilike(like))
            | (EvalCase.reference_answer.ilike(like))
        )
    total = query.count()
    rows = (
        query.order_by(EvalCase.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    ids = [c.id for c in rows]
    memberships: dict[str, list[dict]] = {}
    if ids:
        rows_set = (
            db.query(EvalSetItem.case_id, EvalSet.id, EvalSet.name)
            .join(EvalSet, EvalSet.id == EvalSetItem.set_id)
            .filter(EvalSetItem.case_id.in_(ids))
            .all()
        )
        for case_id, set_id, set_name in rows_set:
            memberships.setdefault(case_id, []).append({"id": set_id, "name": set_name})
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_case_dict(c, memberships.get(c.id, [])) for c in rows],
    }


class CaseCreate(BaseModel):
    trace_id: str = ""
    question: str = ""
    answer: str = ""
    reference_answer: str = ""
    expected_keywords: list[str] = Field(default_factory=list)
    forbidden_keywords: list[str] = Field(default_factory=list)
    require_citations: bool = False
    contexts: list = Field(default_factory=list)
    label: str = "good"
    status: str = "candidate"
    app_id: str = ""
    app_name: str = ""
    source: str = "manual"
    tags: list[str] = Field(default_factory=list)
    note: str = ""
    set_id: str = ""


@router.post("/cases", status_code=201)
def create_case(
    data: CaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if data.label not in ("good", "bad"):
        raise HTTPException(status_code=422, detail="标签必须是 good / bad")

    trace = db.get(TraceRun, data.trace_id) if data.trace_id else None
    if trace:
        existing = (
            db.query(EvalCase)
            .filter(EvalCase.trace_id == trace.id, EvalCase.source == "trace")
            .first()
        )
        if existing:
            existing.label = data.label
            existing.note = data.note or existing.note
            existing.tags = data.tags or existing.tags
            existing.reference_answer = data.reference_answer or existing.reference_answer
            existing.status = "confirmed"
            case = existing
            created = False
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
            created = True
    else:
        if not data.question.strip():
            raise HTTPException(status_code=422, detail="请填写问题，或关联一条 Trace")
        case = EvalCase(
            id=uuid.uuid4().hex,
            question=data.question.strip(),
            answer=data.answer,
            reference_answer=data.reference_answer,
            contexts=data.contexts,
            label=data.label,
            status=data.status if data.status in ("candidate", "confirmed") else "candidate",
            app_id=data.app_id,
            app_name=data.app_name,
            source=data.source or "manual",
            trace_id=data.trace_id,
            tags=data.tags,
            note=data.note,
            created_by=user.display_name or user.username,
        )
        db.add(case)
        created = True

    # Trace 回流与手工新增共用判定字段；重复回流仅覆盖显式提供的规则。
    for field in ("expected_keywords", "forbidden_keywords", "require_citations"):
        if created or field in data.model_fields_set:
            setattr(case, field, getattr(data, field))
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
    db.refresh(case)
    return {"case": _case_dict(case), "created": created, "added_to_set": added}


class CaseUpdate(BaseModel):
    question: str | None = None
    answer: str | None = None
    reference_answer: str | None = None
    expected_keywords: list[str] | None = None
    forbidden_keywords: list[str] | None = None
    require_citations: bool | None = None
    label: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    note: str | None = None


@router.patch("/cases/{case_id}")
def update_case(
    case_id: str,
    data: CaseUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case = db.get(EvalCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case 不存在")
    payload = data.model_dump(exclude_unset=True)
    if "label" in payload and payload["label"] not in ("good", "bad"):
        raise HTTPException(status_code=422, detail="标签必须是 good / bad")
    for key, value in payload.items():
        if value is not None:
            setattr(case, key, value)
    db.commit()
    db.refresh(case)
    return _case_dict(case)


@router.delete("/cases/{case_id}", status_code=204)
def delete_case(
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case = db.get(EvalCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case 不存在")
    db.query(EvalSetItem).filter(EvalSetItem.case_id == case_id).delete()
    db.delete(case)
    db.commit()


class SetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    case_ids: list[str] = Field(default_factory=list)
    app_id: str = ""
    is_release_gate: bool = False


@router.get("/sets")
def list_sets(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sets = db.query(EvalSet).order_by(EvalSet.updated_at.desc(), EvalSet.created_at.desc()).all()
    return [_set_summary(db, s) for s in sets]


@router.post("/sets", status_code=201)
def create_set(
    data: SetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not data.name.strip():
        raise HTTPException(status_code=422, detail="评测集名称不能为空")
    if data.app_id and not db.get(Application, data.app_id):
        raise HTTPException(status_code=404, detail="应用不存在")
    eval_set = EvalSet(
        id=uuid.uuid4().hex,
        name=data.name.strip(),
        description=data.description,
        app_id=data.app_id,
        is_release_gate=data.is_release_gate,
        created_by=user.display_name or user.username,
    )
    db.add(eval_set)
    db.flush()
    for case_id in dict.fromkeys(data.case_ids):
        if db.get(EvalCase, case_id):
            db.add(EvalSetItem(id=uuid.uuid4().hex, set_id=eval_set.id, case_id=case_id))
    db.commit()
    db.refresh(eval_set)
    return _set_summary(db, eval_set)


@router.get("/sets/{set_id}")
def get_set(
    set_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    eval_set = db.get(EvalSet, set_id)
    if not eval_set:
        raise HTTPException(status_code=404, detail="评测集不存在")
    case_ids = _set_case_ids(db, set_id)
    cases = db.query(EvalCase).filter(EvalCase.id.in_(case_ids)).all() if case_ids else []
    order = {cid: idx for idx, cid in enumerate(case_ids)}
    cases.sort(key=lambda c: order.get(c.id, 999))
    data = _set_summary(db, eval_set)
    data["cases"] = [_case_dict(c) for c in cases]
    return data


class SetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    app_id: str | None = None
    is_release_gate: bool | None = None


@router.patch("/sets/{set_id}")
def update_set(
    set_id: str,
    data: SetUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    eval_set = db.get(EvalSet, set_id)
    if not eval_set:
        raise HTTPException(status_code=404, detail="评测集不存在")
    if data.name is not None and not data.name.strip():
        raise HTTPException(status_code=422, detail="评测集名称不能为空")
    if data.app_id and not db.get(Application, data.app_id):
        raise HTTPException(status_code=404, detail="应用不存在")
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(eval_set, key, value)
    eval_set.updated_at = datetime.now()
    db.commit()
    return _set_summary(db, eval_set)


@router.delete("/sets/{set_id}", status_code=204)
def delete_set(
    set_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    eval_set = db.get(EvalSet, set_id)
    if not eval_set:
        raise HTTPException(status_code=404, detail="评测集不存在")
    db.query(EvalSetItem).filter(EvalSetItem.set_id == set_id).delete()
    db.delete(eval_set)
    db.commit()


class SetCasesRequest(BaseModel):
    case_ids: list[str] = Field(default_factory=list)


@router.post("/sets/{set_id}/cases")
def add_cases(
    set_id: str,
    data: SetCasesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    eval_set = db.get(EvalSet, set_id)
    if not eval_set:
        raise HTTPException(status_code=404, detail="评测集不存在")
    existing = set(_set_case_ids(db, set_id))
    added = 0
    for case_id in dict.fromkeys(data.case_ids):
        if case_id in existing or not db.get(EvalCase, case_id):
            continue
        db.add(EvalSetItem(id=uuid.uuid4().hex, set_id=set_id, case_id=case_id))
        added += 1
    eval_set.updated_at = datetime.now()
    db.commit()
    return {"added": added, "set": _set_summary(db, eval_set)}


@router.delete("/sets/{set_id}/cases/{case_id}", status_code=204)
def remove_case(
    set_id: str,
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = (
        db.query(EvalSetItem)
        .filter(EvalSetItem.set_id == set_id, EvalSetItem.case_id == case_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="该 Case 不在评测集中")
    db.delete(item)
    eval_set = db.get(EvalSet, set_id)
    if eval_set:
        eval_set.updated_at = datetime.now()
    db.commit()


@router.get("/sets/{set_id}/export")
def export_set(
    set_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    eval_set = db.get(EvalSet, set_id)
    if not eval_set:
        raise HTTPException(status_code=404, detail="评测集不存在")
    case_ids = _set_case_ids(db, set_id)
    cases = db.query(EvalCase).filter(EvalCase.id.in_(case_ids)).all() if case_ids else []
    lines = []
    for case in cases:
        lines.append(
            json.dumps(
                {
                    "id": case.id,
                    "question": case.question,
                    "answer": case.answer,
                    "reference_answer": case.reference_answer,
                    "expected_keywords": case.expected_keywords or [],
                    "forbidden_keywords": case.forbidden_keywords or [],
                    "require_citations": bool(case.require_citations),
                    "contexts": case.contexts or [],
                    "label": case.label,
                    "app_name": case.app_name,
                    "tags": case.tags or [],
                    "note": case.note,
                    "source": case.source,
                    "trace_id": case.trace_id,
                },
                ensure_ascii=False,
            )
        )
    filename = f"{eval_set.name}-评测集.jsonl"
    return Response(
        content="\n".join(lines),
        media_type="application/x-ndjson; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=eval-set.jsonl; filename*=UTF-8''{quote(filename)}"
        },
    )


def _get_set(db: Session, set_id: str) -> EvalSet:
    eval_set = db.get(EvalSet, set_id)
    if not eval_set:
        raise HTTPException(status_code=404, detail="评测集不存在")
    return eval_set


@router.post("/sets/{set_id}/runs", status_code=201)
def create_run(
    set_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    run = start_run(db, _get_set(db, set_id), user.display_name or user.username)
    return run_summary(db, run)


@router.post("/sets/{set_id}/runs/{run_id}/step")
def advance_run(
    set_id: str, run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    run = step_run(db, _get_set(db, set_id), run_id, user)
    return run_summary(db, run)


@router.post("/sets/{set_id}/run")
def run_set(
    set_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    eval_set = _get_set(db, set_id)
    run = start_run(db, eval_set, user.display_name or user.username)
    while run.status == "running":
        run = step_run(db, eval_set, run.id, user)
    return run_summary(db, run)


@router.get("/sets/{set_id}/runs")
def list_runs(
    set_id: str, limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_set(db, set_id)
    runs = (
        db.query(EvalRun).filter(EvalRun.set_id == set_id)
        .order_by(EvalRun.created_at.desc(), EvalRun.id.desc()).limit(limit).all()
    )
    return [run_summary(db, run, include_results=False) for run in runs]


@router.get("/design-rules")
def design_rules(
    app_id: str = "", db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    from app.services.eval_design import DESIGN_RULES, app_scene, default_rule_keys

    app = db.get(Application, app_id) if app_id else None
    if app_id and not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    return {
        "rules": [{key: item[key] for key in ("key", "name", "description", "scenes")} for item in DESIGN_RULES],
        "default_keys": default_rule_keys(app_scene(app) if app else "qa", bool(app and app.kb_ids)),
    }


class AiDesignRequest(BaseModel):
    app_id: str
    set_id: str | None = None
    set_name: str | None = Field(None, max_length=128)
    rule_keys: list[str] = Field(default_factory=list)
    directions: str = ""
    count: int = Field(10, ge=1, le=30)


@router.post("/ai-design")
def ai_design(
    data: AiDesignRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    from app.services.eval_design import design_cases

    app = db.get(Application, data.app_id)
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    eval_set = _get_set(db, data.set_id) if data.set_id else None
    if eval_set and eval_set.app_id and eval_set.app_id != app.id:
        raise HTTPException(status_code=409, detail="目标评测集已绑定其他应用")
    samples = (
        db.query(Chunk.content).filter(Chunk.kb_id.in_(app.kb_ids or []))
        .order_by(func.random()).limit(6).all()
    ) if app.kb_ids else []
    try:
        designed, simulated = design_cases(
            db, app, rule_keys=list(dict.fromkeys(data.rule_keys)), directions=data.directions,
            count=data.count, knowledge_samples=[row[0] for row in samples],
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    actor = user.display_name or user.username
    if not eval_set:
        eval_set = EvalSet(
            id=uuid.uuid4().hex, name=(data.set_name or "").strip() or f"{app.name} · AI 设计评测集"[:128],
            app_id=app.id, created_by=actor,
        )
        db.add(eval_set)
        db.flush()
    elif not eval_set.app_id:
        eval_set.app_id = app.id
    cases = []
    for item in designed:
        case = EvalCase(
            id=uuid.uuid4().hex, **item, app_id=app.id, app_name=app.name,
            source="ai", status="confirmed", label="good", created_by=actor,
        )
        db.add(case)
        db.flush()
        db.add(EvalSetItem(id=uuid.uuid4().hex, set_id=eval_set.id, case_id=case.id))
        cases.append(case)
    eval_set.updated_at = datetime.now()
    db.commit()
    return {"set": _set_summary(db, eval_set), "cases": [_case_dict(case) for case in cases], "simulated": simulated}
