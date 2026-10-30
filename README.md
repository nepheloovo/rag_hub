# 企业知识库中台 1.0

企业内部知识库中台通用版：支持**导入知识 → 构建知识库 → 在线对话**完整流程，对齐 FastGPT 使用体验。

## 功能清单

| 模块 | 功能 |
|---|---|
| 角色选择 | 管理员 / 知识库管理人员 / 使用者（1.0 无登录，前端角色切换 + 路由权限守卫） |
| **应用** | 三种类型：**问答应用**（RAG 问答+引用溯源）/ **智能客服**（客服人设+兜底话术+转人工提示）/ **报告分析**（对话式 Markdown 结构化报告）；应用 = 多知识库绑定 + LLM + 系统提示词 + 温度 + 引用开关 + 开场白 + 推荐问题，类型仅决定预设模板、创建后可自定义；管理员/知识库管理员可建管，使用者可用 |
| 知识导入 | Word(.docx) / PDF(文字+表格+图片，扫描件自动 OCR) / Markdown / 图片 / 表格(.xlsx/.csv)，单文件 ≤20MB，异步解析入库 |
| 知识库 | 多知识库管理、文档列表（解析状态轮询）、分块预览、测试检索（含 score） |
| 在线对话 | RAG：向量召回 top-20 → Rerank 精排 top-5 → LLM **SSE 流式**生成，答案带**引用溯源**（来源/页码/分数），多轮上下文，会话历史持久化 |
| 模型配置 | OpenRouter / AIHubmix / 通义 三服务商，各自配置 Embedding / Rerank / LLM 模型，全局默认模型，连通性测试 |
| OCR | 通义 qwen-vl 多模态（云端 API，无需本地模型） |
| 日志监测 | 对话查询内容、Token 消耗（分 embedding/rerank/llm）、使用时长、成功率、7 日趋势 |
| **可观测中心** | 一次调用一条 Trace：Agent ReAct 全量留痕（Plan/Thought/Action/Tool/Skill/Observation/Final）、工具与 Skill 状态、单步 Token/成本、完整上下文、Harness 异常；知识库构建四阶段、对话日志、计费消耗（按模型/应用/用途、单价可配）；节点可展开内部运行代码 + 逐段中文解释 |
| **评测集** | 线上 Case 回流（链路/日志一键 Good/Bad、手工录入）、Case 池筛选与批量归集、评测集创建/添加/移出、good/bad 分布、JSONL 导出 |

## 架构

```
浏览器 (Vue 3 SPA)
   │  HTTP / SSE
   ▼
Nginx（静态资源 + /api 反代，SSE 关闭缓冲）
   │
   ▼
FastAPI 后端 ──── LangChain RAG 链路 ──── 模型服务商（OpenRouter / AIHubmix / 通义）
   │   │
   │   ├── PostgreSQL 16 + pgvector（业务数据 + 向量）
   │   └── Redis ── Celery Worker（文档解析 / OCR / Embedding 异步任务）
   └── 本地卷（上传文件与解析产物）
```

- 三服务商均走 **OpenAI 兼容接口**，后端统一适配
- **Rerank 降级策略**：未配置或调用失败自动跳过精排，仅用向量召回（OpenRouter 无 Rerank 模型时链路仍可用）
- 未配置可用服务商时自动降级为**哈希伪向量 + 模拟流式 LLM**，保证全链路可自测（生产环境务必配置真实模型，可用 `ALLOW_FAKE_EMBEDDING=false` / `ALLOW_FAKE_LLM=false` 关闭）

## 快速开始（Docker Compose）

```bash
cd rag_zhongtai
docker compose up -d --build
# 打开 http://<服务器IP>:8080
```

| 服务 | 容器 | 端口 |
|---|---|---|
| 前端 + Nginx | rag-nginx | 8080 |
| FastAPI | rag-backend | 8000 |
| Celery Worker | rag-worker | - |
| PostgreSQL + pgvector | rag-postgres | 5432 |
| Redis | rag-redis | 6379 |

数据持久化于 Docker 卷（`pgdata`、`rag_data`），重启不丢失。

## 模型服务商配置指南（管理员）

进入「模型配置」页：

1. **通义千问**：阿里云百炼获取 API Key → 填入启用。预设 embedding `text-embedding-v3/v4`、Rerank `gte-rerank`、LLM `qwen-max/plus/turbo`，OCR 默认用通义 `qwen-vl-plus`
2. **OpenRouter**：opennrouter.ai 获取 Key → 启用。LLM 丰富；embedding 可选；**无 Rerank 模型**（对话链路自动降级，不影响使用）
3. **AIHubmix**：aihubmix.com 获取 Key → 启用。三类模型均有，Rerank 用 `bge-reranker-v2-m3`
4. 在「全局默认模型」中选择默认的 Embedding / Rerank / LLM

> ⚠️ **向量维度**：`EMBEDDING_DIM` 必须与所选 embedding 模型一致（通义 v3/v4 默认 1024）。更换维度不同的模型后，需重建 chunks 表（`DROP TABLE chunks` 后重启后端自动重建）并重新解析文档。

## 角色与权限

| 角色 | 权限 |
|---|---|
| 管理员 | 全部功能 + 模型配置 + 日志监测 |
| 知识库管理人员 | 知识库创建、文档导入与管理、测试检索、对话 |
| 使用者 | 仅对话 |

## 开发指南

```bash
# 基础设施
docker compose up -d postgres redis

# 后端（详见 backend/README.md）
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
.venv/bin/celery -A app.celery_app.celery_app worker --loglevel=info

# 前端（dev server，/api 代理到 8000）
cd frontend
npm install && npm run dev   # http://localhost:5173

# 测试（使用独立测试库 rag_zhongtai_test）
cd backend && .venv/bin/python -m pytest tests/ -v   # 55 用例
```

## 目录结构

```
rag_zhongtai/
├── docker-compose.yml      # 完整部署编排
├── backend/                # FastAPI + LangChain + Celery
│   ├── app/
│   │   ├── api/            # providers / knowledge / chat(SSE) / logs
│   │   ├── models/         # SQLAlchemy 模型（含 pgvector）
│   │   ├── services/       # parsing(5 种解析器+OCR) / retrieval / rerank / chat / embedding
│   │   └── worker/         # Celery 解析任务
│   └── tests/              # pytest 55 用例
└── frontend/               # Vue 3 + Naive UI
    └── src/
        ├── api/            # 接口层（SSE 解析 / 上传进度）
        └── views/          # 角色选择 / 对话 / 知识库 / 模型配置 / 日志
```

## 可观测与评测集

- 设计文档：`docs/可观测与评测集设计.md`
- 数据模型：`trace_runs` / `trace_spans` / `model_prices` / `eval_cases` / `eval_sets` / `eval_set_items`
- 页面：`/app/observability`（总览 / 调用链 / 对话日志 / 计费消耗 / 知识库构建）、`/app/observability/traces/:id`、`/app/eval`、`/app/eval/:id`
- 旧库兼容：启动时自动执行 `ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS trace_id`，历史日志无 Trace 仍可手工回流 Case
- 首次体验可在观测页点击「载入演示数据」，会写入 6 条链路、5 条 Case、2 个评测集（均可重复点击，不会重复写入）

## 已知限制（1.0）

- 未接入登录认证，角色由前端选择（已按角色过滤菜单与路由）
- PDF 表格提取依赖 PyMuPDF 结构识别，复杂排版可能不完整（扫描件表格走 OCR 兜底）
- 单机部署，pgvector 无分布式；超大规模知识库建议后续迁移 Qdrant/Milvus
- 伪向量/模拟 LLM 仅供自测，无语义能力
