"""工具 API：注册/管理/测试/调用统计"""
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Application, Tool, ToolCallLog
from app.services.tools import execute_tool

router = APIRouter(prefix="/tools", tags=["工具"])


def _get_tool(db: Session, tool_id: str) -> Tool:
    tool = db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    return tool


@router.get("")
def list_tools(db: Session = Depends(get_db)):
    tools = db.query(Tool).order_by(Tool.created_at).all()
    apps = db.query(Application).all()
    result = []
    for t in tools:
        item = {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "tool_type": t.tool_type,
            "status": t.status,
            "enabled": t.enabled,
            "call_count": t.call_count or 0,
            "last_called_at": t.last_called_at,
            "used_by_apps": [],
            "created_at": t.created_at,
        }
        # 统计引用该工具的应用（扫描流程 tool 节点）
        for a in apps:
            nodes = ((a.flow or {}).get("nodes")) or []
            if any(n.get("type") == "tool" and (n.get("data") or {}).get("tool_ref") == t.id for n in nodes):
                item["used_by_apps"].append(a.name)
        result.append(item)
    return result


@router.post("", status_code=201)
def create_tool(data: dict, db: Session = Depends(get_db)):
    if not data.get("name"):
        raise HTTPException(status_code=422, detail="工具名称不能为空")
    tool_type = data.get("tool_type", "http")
    if tool_type not in ("http", "system"):
        tool_type = "http"
    tool = Tool(
        id=uuid.uuid4().hex,
        name=data["name"],
        description=data.get("description", ""),
        tool_type=tool_type,
        config=data.get("config") or {},
    )
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return tool


@router.put("/{tool_id}")
def update_tool(tool_id: str, data: dict, db: Session = Depends(get_db)):
    tool = _get_tool(db, tool_id)
    for field in ("name", "description", "config", "status", "enabled"):
        if field in data:
            setattr(tool, field, data[field])
    db.commit()
    db.refresh(tool)
    return tool


@router.delete("/{tool_id}", status_code=204)
def delete_tool(tool_id: str, db: Session = Depends(get_db)):
    tool = _get_tool(db, tool_id)
    db.delete(tool)
    db.commit()


@router.post("/{tool_id}/test")
def test_tool(tool_id: str, data: dict | None = None, db: Session = Depends(get_db)):
    """试运行工具：input 作为 {{input}} 变量"""
    tool = _get_tool(db, tool_id)
    variables = {"input": (data or {}).get("input", "测试输入")}
    result = execute_tool(db, tool, variables)
    return {"result": result}


@router.get("/{tool_id}/logs")
def tool_logs(tool_id: str, limit: int = 20, db: Session = Depends(get_db)):
    return (
        db.query(ToolCallLog)
        .filter(ToolCallLog.tool_id == tool_id)
        .order_by(ToolCallLog.time.desc())
        .limit(limit)
        .all()
    )


@router.get("/exports/{filename}")
def download_export(filename: str):
    """下载系统工具（导出 Word）生成的文件"""
    path = os.path.join(settings.upload_dir, "exports", filename)
    if not os.path.exists(path) or ".." in filename:
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=filename, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
