"""发布快照、校验与质量门禁；运行对象始终独立于草稿 Session。"""
import copy
import hashlib
import json
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.application import Application, AppVersion
from app.models.eval import EvalRun, EvalSet
from app.models.knowledge import KnowledgeBase
from app.models.provider import Provider

BUILDER_ROLES = ("platform_admin", "app_developer", "kb_admin")
SNAPSHOT_FIELDS = (
    "name", "description", "app_type", "app_kind", "category", "kb_ids", "llm_ref",
    "system_prompt", "temperature", "show_refs", "opening", "suggested_questions",
    "fallback_reply", "transfer_hint", "flow",
)


def snapshot_app(app: Application) -> dict:
    return {key: copy.deepcopy(getattr(app, key)) for key in SNAPSHOT_FIELDS}


def snapshot_fingerprint(snapshot: dict) -> str:
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def app_fingerprint(app: Application) -> str:
    return snapshot_fingerprint(snapshot_app(app))


def published_version(db: Session, app: Application) -> AppVersion | None:
    version = db.get(AppVersion, app.published_version_id) if app.published_version_id else None
    return version if version and version.app_id == app.id else None


def draft_dirty(db: Session, app: Application) -> bool:
    version = published_version(db, app)
    return not version or app_fingerprint(app) != version.fingerprint


def runtime_app(
    db: Session, app: Application, *, draft: bool = False, builder: bool = False,
    public: bool = False,
) -> Application:
    if draft and not builder:
        raise HTTPException(status_code=403, detail="当前角色无权限调试应用草稿")
    version = published_version(db, app)
    if public and (app.status != "published" or not app.publish_enabled or not version):
        raise HTTPException(status_code=404, detail="应用未发布或不存在")
    if draft:
        snapshot = snapshot_app(app)
    elif app.status == "published" and version:
        snapshot = copy.deepcopy(version.snapshot)
    elif builder and not public:
        snapshot = snapshot_app(app)
    else:
        detail = "应用已下线" if app.status == "offline" else "应用尚未发布"
        raise HTTPException(status_code=409, detail=detail)
    return Application(
        id=app.id, **snapshot, status=app.status,
        published_version_id=app.published_version_id, version=app.version,
        publish_enabled=app.publish_enabled, visitor_daily_limit=app.visitor_daily_limit,
    )


def validate_release(db: Session, app: Application) -> list[str]:
    issues = []
    if not (app.name or "").strip():
        issues.append("应用名称不能为空")
    for kb_id in app.kb_ids or []:
        if not db.get(KnowledgeBase, kb_id):
            issues.append(f"绑定的知识库 {kb_id} 不存在")
    if app.llm_ref:
        provider_id, separator, model = app.llm_ref.partition(":")
        provider = db.get(Provider, provider_id) if separator and model else None
        if not provider:
            issues.append("LLM 引用的服务商不存在或格式无效")
        elif not provider.enabled:
            issues.append(f"LLM 服务商「{provider.name}」未启用")
    if app.app_kind == "chatflow":
        from app.services.flow import validate_flow

        try:
            issues.extend(validate_flow(app.flow))
        except (KeyError, TypeError, AttributeError, ValueError):
            issues.append("流程格式不正确，请检查节点和连线配置")
    return issues


def release_check(db: Session, app: Application) -> dict:
    from app.services.eval_runner import ready_cases, run_summary

    issues = validate_release(db, app)
    fingerprint = app_fingerprint(app)
    gates = []
    sets = db.query(EvalSet).filter(
        EvalSet.app_id == app.id, EvalSet.is_release_gate.is_(True)
    ).order_by(EvalSet.created_at, EvalSet.id).all()
    for eval_set in sets:
        latest = db.query(EvalRun).filter(EvalRun.set_id == eval_set.id).order_by(
            EvalRun.created_at.desc(), EvalRun.id.desc()
        ).first()
        count = len(ready_cases(db, eval_set.id))
        if not count:
            reason = "评测集没有可运行的 Case，请先补齐评测标准"
        elif not latest:
            reason = "尚未运行评测，请先运行并确保全部通过"
        elif latest.app_id != app.id or latest.fingerprint != fingerprint:
            reason = "最近评测结果不是基于当前草稿，请重新运行"
        elif latest.status == "running":
            reason = "最近一次评测尚未完成"
        elif latest.status != "success" or latest.failed_count or latest.passed_count < count:
            reason = "最近一次评测未全部通过或未覆盖全部可运行 Case"
        else:
            reason = "当前草稿的全部可运行 Case 已通过"
        passed = bool(
            count and latest and latest.app_id == app.id and latest.fingerprint == fingerprint
            and latest.status == "success" and latest.failed_count == 0
            and latest.passed_count >= count
        )
        gates.append({
            "set_id": eval_set.id, "set_name": eval_set.name, "passed": passed,
            "reason": reason, "latest_run": run_summary(db, latest) if latest else None,
        })
    return {
        "issues": issues, "gates": gates,
        "can_release": not issues and all(gate["passed"] for gate in gates),
        "draft_dirty": draft_dirty(db, app),
    }


def migrate_app_releases(db: Session) -> None:
    """旧库发布状态幂等回填，启动完成后业务端即可使用版本快照。"""
    apps = db.query(Application).filter(
        Application.status.in_(("published", "reviewing"))
    ).with_for_update().all()
    for app in apps:
        if app.status == "reviewing":
            app.status = "draft"
        elif not app.published_version_id:
            latest = db.query(AppVersion).filter(AppVersion.app_id == app.id).order_by(
                AppVersion.version.desc()
            ).first()
            snapshot = snapshot_app(app)
            version = AppVersion(
                id=uuid.uuid4().hex, app_id=app.id, version=(latest.version if latest else 0) + 1,
                snapshot=snapshot, fingerprint=snapshot_fingerprint(snapshot),
                release_notes="旧版已发布应用自动迁移", created_by="系统",
            )
            db.add(version)
            app.published_version_id = version.id
    db.commit()
