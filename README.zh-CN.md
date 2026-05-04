# SmartSRE Copilot

> 面向 SRE / On-call / AIOps 场景的智能运维助手，支持知识库问答、文档向量化、流式对话和可选 MCP 工具接入。

[English](README.md) | [简体中文](README.zh-CN.md)

[![Python](https://img.shields.io/badge/Python-3.11%20--%203.13-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic-orange.svg)](https://www.langchain.com/langgraph)
[![Next.js](https://img.shields.io/badge/Next.js-Frontend-black.svg)](https://nextjs.org/)
[![CI](https://github.com/Mobicos/SmartSRE-Copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/Mobicos/SmartSRE-Copilot/actions/workflows/ci.yml)

## 项目概览

SmartSRE Copilot 是一个面向企业内部运维场景的智能助手原型。后端基于 FastAPI、LangChain/LangGraph、DashScope/Qwen、PostgreSQL、Redis 和 Milvus；前端基于 Next.js，通过服务端 BFF 路由访问后端，避免把后端密钥暴露到浏览器。

核心能力：

- 基于上传 `.txt` 和 `.md` 文档的知识库问答。
- 流式对话和会话历史持久化。
- 支持失败重试的后台异步索引流水线。
- Planner / Executor / Replanner 模式的 AIOps 诊断流程。
- Native Agent 工作空间、场景、工具策略、轨迹回放和反馈 API。
- 可选 MCP 工具接入外部日志、指标和告警系统。

## 架构

```text
浏览器
  |
  v
Next.js 前端 (frontend/)
  |
  | 服务端路由代理 / BFF
  v
FastAPI 后端 (app/)
  |
  +-- 对话 / RAG ----------------> Qwen 对话模型
  |                                + 知识库检索工具
  |                                + 可选 MCP 工具
  |
  +-- 上传 / 索引 ---------------> Redis 队列
  |                                + 独立 worker
  |                                + DashScope Embedding
  |                                + Milvus collection: biz
  |
  +-- Native Agent 诊断 ---------> AgentRuntime
  |                                + ToolCatalog / ToolPolicy / ToolExecutor
  |                                + 轨迹事件
  |                                + 可选 MCP 工具
  |
  +-- 持久化 --------------------> PostgreSQL
```

## 技术栈

后端：

- FastAPI、Pydantic Settings、SSE
- LangChain、LangGraph、DashScope/Qwen
- PostgreSQL、Alembic、Redis、Milvus
- 支持 MCP 客户端接入外部工具服务
- Native Agent runtime、工具策略、场景和轨迹持久化

前端：

- Next.js、React、TypeScript
- 使用服务端 API Route 作为 BFF 层
- 提交 `pnpm-lock.yaml` 保证前端依赖可复现

## 目录结构

```text
app/              FastAPI 后端、Agent、服务层、持久化层
alembic/          PostgreSQL 数据库迁移
frontend/         Next.js 前端应用
mcp_servers/      本地/mock MCP 服务示例
tests/            后端测试
aiops-docs/       示例运维文档
uploads/          本地上传文件，Git 忽略
data/             本地数据文件，Git 忽略
volumes/          Docker 服务数据，Git 忽略
```

## 数据边界

本地应用数据默认保存在本地，除非你显式接入外部工具。

- 上传文件保存在 `uploads/`。
- 会话历史、任务状态、审计日志、AIOps 事件保存在 PostgreSQL。
- Native Agent 的空间、场景、工具策略、轨迹和反馈保存在 PostgreSQL。
- 文档向量保存在 Milvus。
- DashScope 会收到模型调用所需的 prompt 和 embedding 输入。
- MCP 是可选工具入口。腾讯云 CLS MCP 查询的是腾讯云 CLS 数据，不是本地 Postgres 或 Milvus 数据。

## 前置要求

- Python `3.11` 到 `3.13`
- 使用 `uv` 管理 Python 依赖
- Docker Desktop、OrbStack、Colima 或其他 Docker 运行时
- Node.js 和 `pnpm` 用于前端开发
- DashScope API key

```bash
python --version
uv --version
docker --version
node --version
pnpm --version
```

## 快速开始

### 1. 后端环境

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
cp .env.example .env
```

至少需要修改 `.env`：

```env
DASHSCOPE_API_KEY=your_dashscope_api_key
APP_API_KEY=replace_with_a_secure_key
ENVIRONMENT=dev
```

### 2. 启动基础设施

启动完整 Docker 栈：

```bash
docker compose up -d --build
```

这会启动 PostgreSQL、Redis、Milvus、Attu、MinIO、数据库迁移、后端 app 和 worker。

如果你采用“本地 Python 后端 + Docker 基础设施”的开发模式，可以只保留数据库、Redis、Milvus 等基础设施运行，然后用 `uv` 启动后端。项目根目录中的 `docker-compose.local.yml` 如果存在，通常是本地实验配置，不建议默认提交。

### 3. 执行数据库迁移

```bash
uv run alembic upgrade head
```

### 4. 本地启动后端

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 9900
```

如果 `TASK_DISPATCHER_MODE=detached`，需要另开终端启动索引 worker：

```bash
uv run python -m app.worker
```

### 5. 本地启动前端

```bash
cd frontend
pnpm install --frozen-lockfile
cp .env.example .env.local
pnpm dev
```

前端默认后端地址：

```text
SMARTSRE_BACKEND_URL=http://localhost:9900
```

如果后端启用了 API key 鉴权，只在 `frontend/.env.local` 中设置：

```env
SMARTSRE_API_KEY=your_backend_api_key
```

不要把后端密钥写到 `NEXT_PUBLIC_*` 环境变量里。

### 6. 打开服务

- 前端：[http://localhost:3000](http://localhost:3000)
- 后端 API：[http://localhost:9900](http://localhost:9900)
- 后端文档：[http://localhost:9900/docs](http://localhost:9900/docs)
- 健康检查：[http://localhost:9900/health](http://localhost:9900/health)
- Attu，如果使用默认 compose：[http://localhost:8000](http://localhost:8000)

## 配置说明

后端配置定义在 `app/config.py`，并从 `.env` 加载。

关键后端变量：

- `ENVIRONMENT`：`dev`、`prod` 或 `production`
- `DEBUG`：启用开发行为
- `HOST`、`PORT`：后端监听地址
- `CORS_ALLOWED_ORIGINS`：浏览器跨域白名单
- `APP_API_KEY` 或 `API_KEYS_JSON`：基于 API key 的访问控制
- `DASHSCOPE_API_KEY`：DashScope 模型访问凭证
- `DASHSCOPE_MODEL`、`RAG_MODEL`：对话模型
- `DASHSCOPE_EMBEDDING_MODEL`：Embedding 模型
- `POSTGRES_DSN`：PostgreSQL DSN
- `REDIS_URL`：Redis 连接串
- `TASK_QUEUE_BACKEND`：`redis` 或 `database`
- `TASK_DISPATCHER_MODE`：`embedded` 或 `detached`
- `MILVUS_HOST`、`MILVUS_PORT`：向量数据库连接
- `RAG_TOP_K`：检索结果数量
- `CHUNK_MAX_SIZE`、`CHUNK_OVERLAP`：文档切片配置
- `MCP_CLS_TRANSPORT`、`MCP_CLS_URL`：可选 CLS MCP 服务
- `MCP_MONITOR_TRANSPORT`、`MCP_MONITOR_URL`：可选 Monitor MCP 服务
- `MCP_TOOLS_LOAD_TIMEOUT_SECONDS`：工具发现超时时间

生产建议：

- 设置 `ENVIRONMENT=prod` 或 `ENVIRONMENT=production`。
- 配置明确的 `CORS_ALLOWED_ORIGINS`，不要使用 `*`。
- 配置 `APP_API_KEY` 或 `API_KEYS_JSON`。
- 不要把 `.env` 提交到 Git。
- 生产环境优先使用托管 PostgreSQL、Redis 和 Milvus/Zilliz。

## MCP 接入

MCP 是可选能力。知识库问答和文档 RAG 不依赖 MCP；AIOps 诊断在配置外部日志、指标、告警工具后可以调用 MCP。

最佳实践：

- 本地开发和生产环境优先使用本地或内网自建 MCP Server。
- 云厂商托管 SSE 更适合快速体验，除非有明确的稳定性保障，否则不建议作为正式链路的唯一依赖。
- 云账号密钥只放服务端环境变量。
- MCP 工具加载失败时，后端应明确提示工具不可用，不能让 Agent 编造工具。

本地 MCP 配置示例：

```env
MCP_CLS_TRANSPORT=streamable-http
MCP_CLS_URL=http://localhost:8003/mcp
MCP_MONITOR_TRANSPORT=streamable-http
MCP_MONITOR_URL=http://localhost:8004/mcp
MCP_TOOLS_LOAD_TIMEOUT_SECONDS=30
```

## API 概览

后端路由：

- `GET /health`：服务健康检查
- `POST /api/chat`：非流式对话
- `POST /api/chat_stream`：SSE 流式对话
- `GET /api/chat/sessions`：会话列表
- `GET /api/chat/session/{session_id}`：会话历史
- `POST /api/upload`：上传文档并创建索引任务
- `GET /api/index_tasks/{task_id}`：索引任务状态
- `POST /api/aiops`：SSE 流式 AIOps 诊断
- `GET /api/aiops/runs/{run_id}`：AIOps 运行摘要
- `GET /api/aiops/runs/{run_id}/events`：AIOps 运行事件
- `POST /api/workspaces`：创建 Native Agent 空间
- `GET /api/workspaces`：列出 Native Agent 空间
- `POST /api/scenes`：创建空间内诊断场景
- `GET /api/scenes`：列出场景，可通过 `workspace_id` 过滤
- `GET /api/scenes/{scene_id}`：查询场景详情、关联知识库和工具
- `GET /api/tools`：发现诊断工具和已持久化策略
- `PATCH /api/tools/{tool_name}/policy`：启用、禁用工具或配置审批要求
- `POST /api/agent/runs`：执行场景化 Native Agent 诊断
- `GET /api/agent/runs/{run_id}`：查询 Native Agent 运行摘要
- `GET /api/agent/runs/{run_id}/events`：回放 Native Agent 轨迹
- `POST /api/agent/runs/{run_id}/feedback`：提交点赞/点踩反馈

前端通过 `frontend/app/api/*` 的服务端路由代理后端，浏览器组件不应直接调用 FastAPI。

## 开发流程

推荐后端检查命令：

```bash
uv run python -m compileall app mcp_servers tests
uv run python -m ruff check app mcp_servers tests
uv run python -m ruff format --check app mcp_servers tests
uv run python -m mypy app --ignore-missing-imports
uv run python -m bandit -r app -ll
uv run python -m pytest tests -q
```

推荐前端检查命令：

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm build
```

常用 Make 命令：

```bash
make up
make down
make status
make verify
make db-upgrade
make test
make lint
make type-check
make security
```

开发规则：

- 开分支或 PR 前先阅读 `CONTRIBUTING.md`。
- 后端依赖以 `pyproject.toml` 为准，提交 `uv.lock`。
- 前端依赖以 `frontend/package.json` 为准，提交 `frontend/pnpm-lock.yaml`。
- 不要提交 `.env`、`.venv/`、`uploads/`、`data/`、`volumes/`、`frontend/node_modules/` 或 `frontend/.next/`。
- 后端 API 模型变化时，同步更新 `frontend/lib/api-contracts.ts` 或相关 BFF 路由适配层。

## 运行说明

文档索引：

```text
POST /api/upload
  -> 保存文件到 uploads/
  -> 创建索引任务
  -> 任务入队
  -> worker 读取文件
  -> 文档切片
  -> 生成 embedding
  -> 写入 Milvus
```

对话：

```text
Frontend chat
  -> Next.js BFF
  -> FastAPI /api/chat_stream
  -> RagAgentService
  -> retrieve_knowledge
  -> Milvus
  -> Qwen streaming response
```

AIOps：

```text
Frontend diagnose
  -> Next.js BFF
  -> FastAPI /api/aiops
  -> 兼容包装层
  -> AgentRuntime
  -> ToolExecutor
  -> Native Agent 轨迹 + AIOps 兼容运行事件
```

Native Agent V1：

```text
Workspace
  -> Scene
  -> 知识库 + MCP/本地工具
  -> AgentRuntime
  -> 工具策略校验
  -> 工具调用与结果
  -> 轨迹回放
  -> 反馈与运营分析输入
```

## 故障排查

后端无法启动：

- 检查 `PORT` 是否被占用。
- 检查 `.env` 配置。
- 确认 PostgreSQL 和 Milvus 可达。
- 执行 `uv run alembic upgrade head`。

上传成功但索引不完成：

- 检查 `TASK_DISPATCHER_MODE`。
- 如果是 `detached`，启动 `uv run python -m app.worker`。
- 检查 Redis 连接和索引任务状态接口。

MCP 工具不可用：

- 确认 MCP URL 和 transport 正确。
- 工具发现慢时提高 `MCP_TOOLS_LOAD_TIMEOUT_SECONDS`。
- 先独立测试 MCP Server，再排查 Agent。
- 腾讯 CLS MCP 查询的是腾讯 CLS 数据，不是本地应用数据。

前端无法访问后端：

- 检查 `frontend/.env.local`。
- 确认 `SMARTSRE_BACKEND_URL` 指向 FastAPI 服务。
- 如果后端启用了鉴权，在服务端配置 `SMARTSRE_API_KEY`。

## 安全最佳实践

- 所有密钥放环境变量或密钥管理系统。
- 不要把后端 API key 暴露给浏览器代码。
- 生产环境使用明确 CORS 白名单。
- MCP 云账号使用最小权限。
- 审计日志和 AIOps 运行事件使用持久化存储。
- 高风险工具通过工具策略要求审批；V1 遇到这类工具会返回 `approval_required`，不会直接执行。
- 多团队使用前先设计上传文档的权限边界。

## 贡献

人类开发者请先阅读 `CONTRIBUTING.md`，其中包含分支、提交、PR、质量门、
依赖和合并规范。

AI coding agent 还应在改动前阅读 `AGENTS.md`。

## 许可证

Apache License 2.0。详见 [LICENSE](LICENSE)。
