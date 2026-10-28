"""工具执行：HTTP 工具 / 系统内置工具（导出 Word 等）"""
import os
import time
import uuid
from datetime import datetime, timezone

import httpx
from docx import Document
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Tool, ToolCallLog
from app.services.flow import render_template


class ToolError(Exception):
    """工具执行失败（可读信息）"""


SYSTEM_TOOLS = [
    {
        "id": "sys-export-word",
        "name": "导出 Word 文档",
        "description": "把 Markdown 内容按公司模板转为 .docx 文档",
        "tool_type": "system",
        "config": {"system_key": "export_word", "content_template": "{{input}}"},
        "status": "available",
    },
    {
        "id": "sys-web-search",
        "name": "联网搜索",
        "description": "实时检索公开网页信息（Beta，搜索服务尚未接入）",
        "tool_type": "system",
        "config": {"system_key": "web_search"},
        "status": "beta",
    },
]


def seed_system_tools(db: Session) -> None:
    for preset in SYSTEM_TOOLS:
        if not db.get(Tool, preset["id"]):
            db.add(Tool(**preset))
    db.commit()


def _export_word(content: str) -> str:
    """Markdown → docx（简化解析：标题/段落/列表），返回可下载文件名"""
    doc = Document()
    doc.add_heading("知枢生成文档", level=0)
    for raw_line in content.split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            doc.add_heading(line[4:], level=3)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=2)
        elif line.startswith("# "):
            doc.add_heading(line[2:], level=1)
        elif line.strip().startswith(("- ", "* ")):
            doc.add_paragraph(line.strip()[2:], style="List Bullet")
        else:
            doc.add_paragraph(line)
    fname = f"{uuid.uuid4().hex}.docx"
    out_dir = os.path.join(settings.upload_dir, "exports")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, fname)
    doc.save(path)
    return fname


def _run_system_tool(db: Session, tool: Tool, variables: dict) -> str:
    key = (tool.config or {}).get("system_key")
    if key == "export_word":
        template = (tool.config or {}).get("content_template", "{{input}}")
        content = render_template(template, variables)
        fname = _export_word(content)
        return f"已生成 Word 文档：{fname}\n（可通过工具下载入口获取文件）"
    if key == "web_search":
        return "（联网搜索为 Beta 状态，搜索服务尚未接入）"
    raise ToolError(f"未知系统工具: {key}")


def _run_http_tool(tool: Tool, variables: dict) -> str:
    cfg = tool.config or {}
    url = render_template(cfg.get("url", ""), variables)
    if not url:
        raise ToolError("工具未配置 URL")
    method = (cfg.get("method") or "GET").upper()
    headers = {}
    for item in cfg.get("headers") or []:
        k = render_template(item.get("key", ""), variables)
        v = render_template(item.get("value", ""), variables)
        if k:
            headers[k] = v
    body = render_template(cfg.get("body", ""), variables)
    try:
        resp = httpx.request(method, url, headers=headers, content=body or None, timeout=20)
        resp.raise_for_status()
        return resp.text[:4000]
    except Exception as e:  # noqa: BLE001
        raise ToolError(f"工具调用失败: {e}") from e


def execute_tool(db: Session, tool: Tool, variables: dict, app_id: str = "", app_name: str = "") -> str:
    """执行注册工具并记录调用统计"""
    start = time.monotonic()
    input_snippet = str(variables.get("input", ""))[:200]
    try:
        if tool.tool_type == "system":
            result = _run_system_tool(db, tool, variables)
        elif tool.tool_type == "http":
            result = _run_http_tool(tool, variables)
        else:
            raise ToolError(f"暂不支持的接入方式: {tool.tool_type}")
        status = "success"
    except Exception as e:  # noqa: BLE001
        result = f"工具执行失败: {e}"
        status = "error"
    duration = int((time.monotonic() - start) * 1000)
    tool.call_count = (tool.call_count or 0) + 1
    tool.last_called_at = datetime.now(timezone.utc)
    db.add(
        ToolCallLog(
            id=uuid.uuid4().hex,
            tool_id=tool.id,
            tool_name=tool.name,
            app_id=app_id,
            app_name=app_name,
            input_snippet=input_snippet,
            output_snippet=result[:200],
            duration_ms=duration,
            status=status,
        )
    )
    db.commit()
    return result
