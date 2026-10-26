# 企业知识库中台 —— 后端

## 技术栈

FastAPI + LangChain + Celery + PostgreSQL(pgvector) + Redis，Python 3.12。

## 启动步骤

### 1. 基础设施（PostgreSQL + Redis）

```bash
docker compose up -d   # 项目根目录
docker exec rag-postgres psql -U rag -d rag_zhongtai -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 2. Python 环境

```bash
cd backend
python3 -m venv --copies .venv
# 本机开发环境注意：若使用带团队签名的 Python（如 DSH 内置运行时），需对 venv 内解释器做 ad-hoc 重签：
codesign -f -s - .venv/bin/python .venv/bin/python3 .venv/bin/python3.12
.venv/bin/pip install -r requirements.txt
```

### 3. 启动服务

```bash
# API（端口 8000）
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# Celery Worker（线程池：任务以网络 I/O 为主；macOS spawn 下 prefork 有上游 bug）
.venv/bin/celery -A app.celery_app.celery_app worker --loglevel=info
```

### 4. 自测

```bash
.venv/bin/python -m pytest tests/ -v
```

## 前端

```
cd frontend
npm install
npm run dev   # http://localhost:5173，/api 代理到后端 8000
```

前端已对接真实 API（`src/api/`）：对话 SSE 流式、知识库/文档管理（含上传进度与解析状态轮询）、测试检索、模型配置、日志监测。

## 测试

```bash
# 后端（使用独立测试库 rag_zhongtai_test，不影响开发数据）
.venv/bin/python -m pytest tests/ -v
```

## API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/providers` | 服务商列表 |
| POST | `/api/providers` | 新建服务商 |
| PUT | `/api/providers/{id}` | 更新（models 仅合并显式传入类别） |
| DELETE | `/api/providers/{id}` | 删除 |
| POST | `/api/providers/{id}/test` | 连通性测试（OpenAI 兼容 /models） |
| GET/PUT | `/api/providers/defaults/models` | 全局默认 embedding/rerank/llm |
| GET/POST | `/api/knowledge-bases` | 知识库列表（含文档/分块数）/ 新建 |
| GET/PUT/DELETE | `/api/knowledge-bases/{id}` | 知识库详情/更新/删除 |
| GET | `/api/knowledge-bases/{id}/test-retrieval?q=` | 测试检索（含模型信息，不入库） |
| POST | `/api/knowledge-bases/{id}/documents` | 上传文档（Word/PDF/md/图片/表格，≤20MB） |
| GET | `/api/knowledge-bases/{id}/documents` | 文档列表 |
| DELETE | `/api/documents/{id}` | 删除文档及其分块 |
| POST | `/api/documents/{id}/reparse` | 重新解析 |
| GET | `/api/documents/{id}/chunks` | 分块预览（分页） |
| POST | `/api/chat` | 流式问答（SSE：delta / done / error） |
| GET/POST | `/api/conversations` | 会话列表（可按知识库/应用）/ 新建 |
| GET/POST | `/api/apps` | 应用列表 / 新建（类型决定预设模板） |
| GET/PUT/DELETE | `/api/apps/{id}` | 应用详情/更新/删除（删除级联会话） |
| POST | `/api/apps/{id}/chat` | 应用级流式对话（多库检索/应用提示词/客服兜底） |
| GET | `/api/conversations/{id}/messages` | 会话消息（含引用） |
| DELETE | `/api/conversations/{id}` | 删除会话 |
| GET | `/api/logs` | 日志列表（角色/知识库/状态/关键词过滤） |
| GET | `/api/logs/stats` | 统计（今日对话/Token/平均时长/成功率 + 7 日趋势） |

## 对话链路（RAG）

向量召回 top-20（pgvector 余弦）→ Rerank 精排 top-5（未配置/失败自动降级）→ 组装上下文与历史 → LLM **流式生成（SSE）** → 返回**引用溯源**（来源/页码/分数）。回答、引用、Token 明细与时长同时落库至日志。

## 导入管道

上传 → Celery 异步任务：解析为统一 Markdown → 按标题分块 → embedding → 写入 pgvector。

- **PDF**：文字 + 表格 + 内嵌图片（OCR 描述后随页参与检索）；无文字层自动判定为扫描件，整页云端 OCR
- **Word**：正文/标题/表格按文档顺序；内嵌图片 OCR 后附于文末
- **图片**：通义 qwen-vl OCR + 内容理解
- **表格**：xlsx/csv 转 Markdown 表格
- **OCR**：走通义多模态（云端 API）；未配置 Key 时图片失败、PDF 内嵌图片跳过，均给出可读错误

启动时自动建表并预置三个服务商（通义/OpenRouter/AIHubmix）与默认模型（默认走通义）。

## 已知注意事项

- **Rerank 降级**：`default_rerank` 为空时对话链路自动跳过精排（OpenRouter 无 Rerank 模型）；Rerank 调用失败同样自动降级为纯向量召回。
- **Celery 池类型**：已固化 `worker_pool=threads`，见 `app/celery_app.py` 注释。
- **向量维度**：`EMBEDDING_DIM` 需与所选 embedding 模型一致（通义 v3/v4 默认 1024）；更换模型需同步调整并重建 chunks 表。
- **伪向量/模拟 LLM 降级**：未配置可用服务商时自动使用哈希伪向量与模拟流式 LLM，保证链路可自测但不具备语义能力；生产环境请配置真实模型（可用 `ALLOW_FAKE_EMBEDDING`/`ALLOW_FAKE_LLM` 关闭）。
