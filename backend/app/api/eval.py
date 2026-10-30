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
from app.models import EvalCase, EvalSet, EvalSetItem, TraceRun, User

router = APIRouter(prefix="/eval", tags=["评测集"])


def _case_dict(case: EvalCase, sets: list[dict] | None = None) -> dict:
    return {
        "id": case.id,
        "question": case.question,
        "answer": case.answer,
        "reference_answer": case.reference_answer,
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
    return {
        "id": eval_set.id,
        "name": eval_set.name,
        "description": eval_set.description,
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
    eval_set = EvalSet(
        id=uuid.uuid4().hex,
        name=data.name.strip(),
        description=data.description,
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
