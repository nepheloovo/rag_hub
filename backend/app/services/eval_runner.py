"""同步评测运行：复用应用对话核心消费 SSE，再按显式规则判定。"""
from __future__ import annotations

import json
import re
import uuid

import anyio
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Application, AuditLog, EvalCase, EvalSet, EvalSetItem
from app.models.eval import EvalRun


def case_readiness(case: EvalCase) -> str:
    ready = bool((case.question or "").strip()) and bool(
        (case.reference_answer or "").strip()
        or case.expected_keywords or case.forbidden_keywords or case.require_citations
    )
    return "ready" if ready else "needs_standard"


def ready_cases(db: Session, set_id: str) -> list[EvalCase]:
    cases = (
        db.query(EvalCase)
        .join(EvalSetItem, EvalSetItem.case_id == EvalCase.id)
        .filter(EvalSetItem.set_id == set_id)
        .order_by(EvalSetItem.added_at, EvalSetItem.id)
        .all()
    )
    return [case for case in cases if case_readiness(case) == "ready"]


def run_summary(db: Session, run: EvalRun, include_results: bool = True) -> dict:
    from app.services.app_release import app_fingerprint

    app = db.get(Application, run.app_id)
    return {
        "id": run.id,
        "status": run.status,
        "passed_count": run.passed_count,
        "failed_count": run.failed_count,
        "total_count": run.total_count,
        "done_count": len(run.results or []),
        "simulated": run.simulated,
        "created_at": run.created_at,
        "matches_draft": bool(app and app_fingerprint(app) == run.fingerprint),
        "results": (run.results or []) if include_results else [],
    }


def run_application(app: Application, question: str) -> dict:
    """同步路由在线程池执行；StreamingResponse 的异步迭代器在本线程消费。"""
    from app.api.apps import app_chat_response
    from app.schemas.application import AppChatRequest
    from app.services.app_release import snapshot_app

    runtime = Application(id=app.id, **snapshot_app(app))
    response = app_chat_response(
        app.id, AppChatRequest(query=question, draft=True), source="eval", application=runtime
    )

    async def consume() -> dict:
        buffer = ""
        done = None
        async for piece in response.body_iterator:
            buffer += piece.decode("utf-8") if isinstance(piece, bytes) else piece
            while "\n\n" in buffer:
                frame, buffer = buffer.split("\n\n", 1)
                event = ""
                data_lines = []
                for line in frame.splitlines():
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                if event in ("done", "error"):
                    data = json.loads("\n".join(data_lines))
                    if event == "error":
                        raise RuntimeError(data.get("message") or data.get("detail") or data.get("error") or "应用运行失败")
                    done = data
        if done is None:
            raise RuntimeError("应用未返回完成事件")
        return done

    return anyio.run(consume)


def evaluate_case(app: Application, case: EvalCase) -> dict:
    result = {
        "case_id": case.id, "question": case.question, "passed": False,
        "reasons": [], "output": "", "refs_count": 0, "simulated": False,
    }
    try:
        answer = run_application(app, case.question)
        output = answer.get("answer") or ""
        result.update(
            output=output, refs_count=len(answer.get("refs") or []),
            simulated=bool((answer.get("models") or {}).get("fake")),
        )
        lowered = output.lower()
        missing = [word for word in (case.expected_keywords or []) if word.lower() not in lowered]
        forbidden = [word for word in (case.forbidden_keywords or []) if word.lower() in lowered]
        reasons = result["reasons"]
        if missing:
            reasons.append(f"缺少期望关键词：{'、'.join(missing)}")
        if forbidden:
            reasons.append(f"包含禁止关键词：{'、'.join(forbidden)}")
        if case.require_citations and not result["refs_count"]:
            reasons.append("没有引用来源")
        explicit = bool(case.expected_keywords or case.forbidden_keywords or case.require_citations)
        if case.label == "bad" and case.reference_answer and not explicit:
            normalize = lambda value: re.sub(r"\s+", "", value).lower()
            if normalize(output) != normalize(case.reference_answer):
                reasons.append("输出与标准答案不一致")
        result["passed"] = not reasons
    except Exception as exc:  # 单条异常保留结果，继续评测其余 Case
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        result["reasons"] = [str(detail) or type(exc).__name__]
    return result


def start_run(db: Session, eval_set: EvalSet, actor: str) -> EvalRun:
    from app.services.app_release import app_fingerprint

    if not eval_set.app_id:
        raise HTTPException(status_code=422, detail="评测集尚未绑定应用")
    app = db.get(Application, eval_set.app_id)
    if not app:
        raise HTTPException(status_code=404, detail="绑定的应用不存在")
    cases = ready_cases(db, eval_set.id)
    if not cases:
        raise HTTPException(status_code=409, detail="评测集没有可运行 Case，请先补齐评测标准")
    run = EvalRun(
        id=uuid.uuid4().hex, set_id=eval_set.id, app_id=app.id,
        fingerprint=app_fingerprint(app), status="running", total_count=len(cases),
        case_ids=[case.id for case in cases], results=[], created_by=actor,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def step_run(db: Session, eval_set: EvalSet, run_id: str, user) -> EvalRun:
    from app.services.app_release import app_fingerprint

    # 一个运行串行推进，重复请求在提交后读取已完成进度。
    run = (
        db.query(EvalRun).filter(EvalRun.id == run_id, EvalRun.set_id == eval_set.id)
        .with_for_update().populate_existing().first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="评测运行不存在")
    app = db.get(Application, run.app_id)
    if not app:
        raise HTTPException(status_code=404, detail="绑定的应用不存在")
    db.refresh(app)
    if eval_set.app_id != run.app_id or app_fingerprint(app) != run.fingerprint:
        raise HTTPException(status_code=409, detail="应用草稿在评测过程中被修改，请重新开始评测")
    if run.status != "running":
        return run
    done = {result["case_id"] for result in (run.results or [])}
    remaining = [case_id for case_id in run.case_ids if case_id not in done]
    if remaining:
        case = db.get(EvalCase, remaining[0])
        if case and case_readiness(case) == "ready":
            result = evaluate_case(app, case)
        else:
            result = {
                "case_id": remaining[0], "question": case.question if case else "",
                "passed": False, "reasons": ["评测 Case 已被删除或缺少标准，请重新开始评测"],
                "output": "", "refs_count": 0, "simulated": False,
            }
        run.results = [*(run.results or []), result]
        run.simulated = run.simulated or result["simulated"]
        run.passed_count = sum(bool(item["passed"]) for item in run.results)
        run.failed_count = len(run.results) - run.passed_count
    if len(remaining) <= 1:
        run.status = "failed" if run.failed_count else "success"
        db.add(AuditLog(
            id=uuid.uuid4().hex, actor=user.username, role=user.role,
            action="eval.run", target=eval_set.id,
            detail=json.dumps({"passed": run.passed_count, "failed": run.failed_count}, ensure_ascii=False),
        ))
    db.commit()
    db.refresh(run)
    return run
