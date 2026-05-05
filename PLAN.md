# SmartSRE Copilot Roadmap：Agentic Oncall 原生平台

## Summary

SmartSRE 的最佳演进方向是：用 FastAPI full-stack-template 做 Web/DB/CI 工程底座，用 Claude Code /
Harness Engineering 思想做原生 Agent Runtime，用 KOncall 思路做 SRE/Oncall 产品闭环，用
Token/Memory/Skill 工程控制成本和长期能力增长。最终产品不是普通 ChatBot，也不是工作流编排器，而是可观测、可评测、可治理、可恢复的
SRE Agentic Workbench。

版本边界必须按“闭环能力”定义，而不是按功能清单堆叠定义。当前版本已经具备最小 Native Agent
闭环雏形：用户能在前端选择场景并发起诊断，后端能围绕目标执行受治理的工具，产生可追踪事件、证据、报告、反馈和持久化记录。V2.0
不应再定义为“闭环起步版”，而应升级为 Decision Runtime：让 Agent
从“能跑完闭环”变成“能显式设定目标、拆解假设、排序行动、验证证据、处理异常、请求人工确认并产出可审计决策”的版本。

## Versioned Implementation Plan：Agent 可执行的 1.3 到 2.0 渐进路线

当前开源治理基线以 `1.3.0` 为准。后续开发必须按小版本渐进，不允许从 `1.5` 直接跳到 `2.0`。

### Execution Rules：所有智能体必须遵守

每个小版本都必须满足以下规则后才能进入下一个小版本：

- 先读本节的目标、前置条件、任务清单和完成定义。
- 只实现当前小版本范围，不顺手实现后续版本能力。
- 不提交 `.env`、`.claude/`、`docker-compose.local.yml`、IDE 文件、缓存、生成目录。
- 涉及数据库结构必须有 Alembic migration 和 downgrade。
- 涉及后端 API 必须补 API/contract 测试。
- 涉及前端必须走 Next.js BFF，不让浏览器直连 FastAPI。
- 涉及 Agent runtime 必须保证工具调用仍经过 ToolPolicyGate / ToolExecutor。
- 每个小版本结束前必须运行对应质量门，并在 PR 描述写明未运行项和原因。

标准质量门：

```bash
make verify
cd frontend
pnpm lint
pnpm typecheck
pnpm build
```

推荐版本流水线：

```text
1.3.0：Native Agent Workbench 基线
1.3.1：Agent Workbench 稳定性与文档收口
1.4.0：Compose 中间件拓扑重构
1.4.1：pgvector 默认向量层
1.4.2：MinIO/S3 对象存储
1.4.3：Redis 队列与 Agent resume 基础
1.4.4：Caddy 网关
1.4.5：OpenTelemetry / Grafana / Loki 观测栈
1.5.0：Knowledge Pipeline 稳定化
1.5.1：Replay Snapshot
1.5.2：AgentOps 最小指标
1.5.3：Scenario Regression
1.6.0：Tool Harness 标准化
1.6.1：Approval Workflow 基础
1.7.0：API Contract / OpenAPI / BFF 类型治理
1.7.1：前端 Workbench 可观测性增强
1.8.0：Decision Runtime Contract
1.8.1：Deterministic Decision Provider
1.8.2：Evidence-driven Report
1.9.0：LangGraph Runtime Skeleton
1.9.1：Qwen Decision Provider
1.9.2：Checkpoint Resume / Approval Resume
1.9.3：Decision Runtime E2E / Regression
2.0.0：LangGraph Decision Runtime 正式发布
```

### 1.3.0：Native Agent Workbench 基线

目标：把当前已接近完成的 Native Agent Workbench 正式定版。

前置条件：

- 当前 Agent API、SSE、history、run detail、tool policy 基本可用。
- 版本号仍可能不一致，需要统一。

任务清单：

1. 统一版本号：

   ```text
   pyproject.toml -> 1.3.0
   app/config.py -> 1.3.0
   app/__init__.py -> 1.3.0
   ```

1. README 标明 `1.3.0` 是 Native Agent Workbench baseline。

1. 保留并验证以下 API：

   ```text
   POST /api/agent/runs
   POST /api/agent/runs/stream
   GET  /api/agent/runs
   GET  /api/agent/runs/{run_id}
   GET  /api/agent/runs/{run_id}/events
   POST /api/agent/runs/{run_id}/feedback
   PATCH /api/tools/{tool_name}/policy
   ```

1. 保留并验证以下页面：

   ```text
   /agent
   /agent/history
   /agent/[runId]
   /agent/tools
   ```

1. 确认高风险工具只返回 `approval_required`，不自动执行。

1. 确认失败 run 会记录 `failed`、`error_message`、`error` event。

不做：

- 不迁移 pgvector。
- 不引入 MinIO/S3。
- 不引入 Caddy。
- 不引入 LangGraph Decision Runtime。

验证：

```bash
uv run python -m pytest tests/test_agent_runtime.py tests/test_agent_api.py tests/test_aiops_native_compat.py -q
make verify
cd frontend
pnpm lint
pnpm typecheck
pnpm build
```

完成定义：

- 版本号统一为 `1.3.0`。
- Agent Workbench 端到端可用。
- 质量门通过。
- 独立提交建议：`chore(release): mark native agent baseline as 1.3.0`。

### 1.3.1：Agent Workbench 稳定性与文档收口

目标：在不改变架构的前提下，让 1.3 基线更容易被开发、启动、复盘。

任务清单：

1. README 补充本地启动路径：Docker 基础设施 + 本地 `uv` + 前端 `pnpm`。
1. README 明确 `docker-compose.yml` 是共享模板，`docker-compose.local.yml` 是本地忽略文件。
1. 补充 Agent Workbench 使用说明。
1. 补充 Tool Policy 风险说明。
1. 补充常见错误排查：`.env`、Milvus、Postgres、Redis、SSE、前端 BFF。
1. 统一 `PLAN.md` 与 README 对 1.3 的描述。

验证：

```bash
git diff --check
```

完成定义：

- 新开发者能按 README 启动 1.3。
- 文档不再暗示当前已经是 2.0。
- 独立提交建议：`docs(agent): document native agent workbench baseline`。

### 1.4.0：Compose 中间件拓扑重构

目标：先重构容器拓扑，不改应用数据层默认实现。

目标架构：

```text
Caddy
  -> Next.js BFF
  -> FastAPI API
      -> PostgreSQL 18
      -> Redis 8
      -> MinIO / S3
      -> MCP Servers
      -> DashScope/Qwen
      -> OpenTelemetry Collector
          -> Prometheus
          -> Grafana
          -> Loki
```

任务清单：

1. 保留 `postgres`、`redis`、`app`、`worker`。
1. 新增 `frontend` 服务，如果当前生产 compose 还没有前端服务。
1. 新增 `minio`，但应用代码先不强依赖。
1. 新增 `caddy`，但本版本可以先不作为唯一入口。
1. 新增 observability
   profile：`otel-collector`、`prometheus`、`grafana`、`loki`、`alloy`。
1. 将 `milvus`、`etcd`、`attu` 移入 `vector-milvus` profile。
1. 更新 README compose 命令。
1. 保持本地开发仍可只启动基础设施。

不做：

- 不改知识库代码默认向量层。
- 不改上传文件存储逻辑。
- 不要求观测指标完整。

验证：

```bash
docker compose config
docker compose up -d postgres redis minio
docker compose --profile vector-milvus config
docker compose --profile observability config
```

完成定义：

- 默认 compose 不再强制启动 Milvus。
- profile 配置可解析。
- 独立提交建议：`chore(docker): align compose with platform middleware stack`。

### 1.4.1：pgvector 默认向量层

目标：把默认向量检索从 Milvus 切换为 PostgreSQL + pgvector，同时保留 Milvus 适配可能。

任务清单：

1. 新增配置：

   ```env
   VECTOR_STORE_BACKEND=pgvector
   VECTOR_DIMENSION=1024
   VECTOR_INDEX_TYPE=hnsw
   ```

1. 新增 pgvector migration：

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

1. 新增知识库表：

   ```text
   knowledge_documents
   knowledge_chunks
   knowledge_embeddings
   ```

1. 新增 `VectorStorePort`。

1. 实现 `PgVectorStoreAdapter`。

1. 将现有 Milvus 路径收敛为 `MilvusVectorStoreAdapter`。

1. 索引服务默认写 pgvector。

1. 检索服务默认读 pgvector。

1. README 写清楚 `pgvector` 与 `milvus` 切换方式。

验证：

```bash
uv run alembic upgrade head
uv run python -m pytest tests/test_vector_store_pgvector.py tests/test_indexing_tasks.py -q
make verify
```

完成定义：

- 无 Milvus 时索引和检索可用。
- pgvector 查询返回 chunk、metadata、score。
- Milvus profile 仍可作为兼容路径。
- 独立提交建议：`feat(vector): add pgvector as default vector store`。

### 1.4.2：MinIO/S3 对象存储

目标：把上传文件、解析结果、证据快照、报告附件从本地文件系统迁移到对象存储抽象。

任务清单：

1. 新增配置：

   ```env
   OBJECT_STORAGE_BACKEND=minio
   S3_ENDPOINT_URL=http://localhost:9000
   S3_BUCKET=smartsre
   S3_ACCESS_KEY=minioadmin
   S3_SECRET_KEY=minioadmin
   ```

1. 新增 `ObjectStoragePort`。

1. 实现 `MinioObjectStorageAdapter`。

1. 预留 `S3ObjectStorageAdapter`。

1. 上传 API 写入对象存储。

1. Postgres 保存 object key、sha256、content type、size。

1. indexing task 从对象存储读取原始文件。

1. 删除文档时清理 object、chunk、embedding。

对象路径规范：

```text
uploads/raw/{workspace_id}/{document_id}/{filename}
uploads/parsed/{workspace_id}/{document_id}.json
agent/evidence/{run_id}/{evidence_id}.json
agent/reports/{run_id}/report.md
exports/{workspace_id}/{export_id}
```

验证：

```bash
uv run python -m pytest tests/test_object_storage.py tests/test_file_api.py tests/test_indexing_tasks.py -q
make verify
```

完成定义：

- 上传后 MinIO 有对象。
- 数据库有文档 metadata。
- 重复文件可以用 sha256 识别。
- 独立提交建议：`feat(storage): add object storage for knowledge files`。

### 1.4.3：Redis 队列与 Agent Resume 基础

目标：Redis 负责后台任务、短期通知和 resume queue，但不保存最终事实。

任务清单：

1. 明确 Redis 用途：

   ```text
   indexing queue
   agent resume queue
   SSE pub/sub
   short-lived cache
   rate limit counter
   ```

1. 新增配置：

   ```env
   AGENT_RESUME_QUEUE=smartsre:agent:resume
   INDEXING_QUEUE=smartsre:indexing:queue
   ```

1. indexing queue 保持或迁移到 Redis。

1. 新增 agent resume queue 的生产者和消费者接口。

1. approval approve 后只写 resume task，不直接在 API 请求里执行长任务。

1. Redis 断开不影响 Postgres 里的 run/event/approval 事实状态。

验证：

```bash
uv run python -m pytest tests/test_indexing_tasks.py tests/test_agent_resume_queue.py -q
make verify
```

完成定义：

- Redis 重启不丢最终事实。
- resume task 可入队/出队。
- 独立提交建议：`feat(queue): add redis-backed agent resume queue`。

### 1.4.4：Caddy 网关

目标：让本地和生产入口更接近真实部署。

任务清单：

1. 新增 `Caddyfile`。
1. 配置 `/` 转发到 Next.js。
1. 配置 `/api/*` 转发到 FastAPI。
1. 配置 `/health` 转发到 FastAPI。
1. 配置压缩、安全响应头、request id 透传。
1. README 增加 Caddy 入口说明。
1. 生产环境禁止 wildcard CORS。

验证：

```bash
docker compose config
docker compose up -d caddy frontend app
```

完成定义：

- 浏览器可以通过 Caddy 访问前端。
- BFF 可以通过 Caddy 或内部网络访问 API。
- 独立提交建议：`feat(edge): add caddy gateway`。

### 1.4.5：OpenTelemetry / Grafana / Loki 观测栈

目标：建立最小 AgentOps 观测底座，但不要求完整 GenAI tracing。

任务清单：

1. 配置 `otel-collector`。

1. 配置 `prometheus` scrape。

1. 配置 `grafana` datasource。

1. 配置 `loki` 和 `alloy`。

1. FastAPI 增加 trace id middleware。

1. worker 日志带 run_id / trace_id。

1. 暴露基础 metrics：

   ```text
   agent_run_count
   agent_run_latency_ms
   agent_run_status_count
   tool_call_count
   tool_error_count
   approval_pending_count
   indexing_queue_depth
   retrieval_latency_ms
   llm_latency_ms
   ```

验证：

```bash
docker compose --profile observability up -d
uv run python -m pytest tests/test_observability.py -q
make verify
```

完成定义：

- FastAPI 请求有 trace_id。
- Prometheus 能抓基础指标。
- Loki 能查 app / worker 日志。
- 独立提交建议：`feat(observability): add opentelemetry middleware stack`。

### 1.5.0：Knowledge Pipeline 稳定化

目标：把上传、解析、切分、embedding、pgvector 查询做成稳定闭环。

任务清单：

1. 文件上传进入对象存储。
1. 创建 indexing task。
1. worker 读取对象存储。
1. 文档解析。
1. 文档切分。
1. DashScope embedding。
1. chunk 和 embedding 写入 pgvector。
1. 检索返回 citation。
1. 支持 workspace / knowledge_base filter。
1. 支持失败重试和 failed_permanently。

验证：

```bash
uv run python -m pytest tests/test_indexing_tasks.py tests/test_vector_store_pgvector.py tests/test_knowledge_api.py -q
make verify
```

完成定义：

- 从上传到检索全链路可用。
- 检索结果带 citation。
- 独立提交建议：`feat(knowledge): stabilize pgvector indexing pipeline`。

### 1.5.1：Replay Snapshot

目标：每次 Agent run 可以被复盘，但还不做 deterministic replay。

任务清单：

1. 新增 replay 聚合服务。

1. 聚合 run metadata。

1. 聚合 events。

1. 聚合 tool inputs / outputs。

1. 聚合 knowledge citations。

1. 聚合 final report。

1. 聚合 feedback。

1. 新增 API：

   ```text
   GET /api/agent/runs/{run_id}/replay
   ```

验证：

```bash
uv run python -m pytest tests/test_agent_replay.py tests/test_agent_api.py -q
make verify
```

完成定义：

- run detail 可以从 replay API 一次性拿到复盘快照。
- replay 是只读聚合，不改变 run 状态。
- 独立提交建议：`feat(agent): add replayable run snapshots`。

### 1.5.2：AgentOps 最小指标

目标：每次 run 都能被定位、度量和分类。

任务清单：

1. `agent_runs` 或 run metadata 记录：

   ```text
   runtime_version
   trace_id
   model_name
   step_count
   tool_call_count
   latency_ms
   error_type
   approval_state
   retrieval_count
   token_usage
   ```

1. token 不可得时允许为空。

1. cost 不可得时允许为空。

1. 日志禁止打印 secrets。

1. 大 tool output 进入摘要或截断。

验证：

```bash
uv run python -m pytest tests/test_agent_runtime_metrics.py tests/test_agent_api.py -q
make verify
```

完成定义：

- run 列表或详情能看到基础运行指标。
- error_type 可用于失败分类。
- 独立提交建议：`feat(agentops): record native agent run metrics`。

### 1.5.3：Scenario Regression

目标：不依赖真实云 MCP、不依赖真实 LLM，建立 Agent 行为回归。

任务清单：

1. 新增场景测试目录。

1. 构造 mock tools。

1. 构造 mock tool outputs。

1. 覆盖 golden scenarios：

   ```text
   cpu_high
   http_5xx_spike
   slow_response
   disk_full
   dependency_failure
   ```

1. 覆盖 failure scenarios：

   ```text
   empty_knowledge
   tool_error
   approval_required
   disabled_tool
   forbidden_tool
   ```

验证：

```bash
uv run python -m pytest tests/agent_scenarios -q
make verify
```

完成定义：

- Agent 不编造证据。
- 禁用和高风险工具不会被执行。
- 独立提交建议：`test(agent): add native agent scenario regression`。

### 1.6.0：Tool Harness 标准化

目标：先把工具治理做稳，再进入决策 runtime。

统一 tool schema：

```text
name
description
input_schema
scope
risk_level
capability
timeout_seconds
retry_count
approval_required
owner
data_boundary
side_effect
```

任务清单：

1. 新增 `ToolSchema`。
1. ToolCatalog 返回标准 schema。
1. ToolPolicyGate 合并 registry schema 和 DB policy。
1. ToolExecutor 执行前校验 input schema。
1. ToolExecutor 执行前校验 capability。
1. ToolExecutor 执行前校验 risk / approval。
1. ToolExecutor 增加 timeout。
1. ToolExecutor 增加有限 retry。
1. destructive 工具默认禁止自动执行。

验证：

```bash
uv run python -m pytest tests/test_tool_harness.py tests/test_agent_tool_schema.py -q
make verify
```

完成定义：

- 所有工具调用经过统一 schema 和 policy。
- LLM 或 runtime 没有裸调工具的路径。
- 独立提交建议：`feat(agent): standardize tool harness schema`。

### 1.6.1：Approval Workflow 基础

目标：把 `approval_required` 从“结果状态”升级为“可管理审批记录”，但不要求完整 LangGraph resume。

任务清单：

1. 新增 `agent_approvals` 表。

1. 新增 approval repository。

1. 高风险工具创建 pending approval。

1. run 状态支持 `waiting_approval`。

1. 新增 API：

   ```text
   GET  /api/agent/runs/{run_id}/approvals
   POST /api/agent/runs/{run_id}/approvals/{approval_id}/approve
   POST /api/agent/runs/{run_id}/approvals/{approval_id}/reject
   ```

1. approve 只更新状态和发送 resume task。

1. reject 生成 event，不执行工具。

验证：

```bash
uv run python -m pytest tests/test_agent_approvals.py tests/test_agent_approval_api.py -q
make verify
```

完成定义：

- 高风险动作有 pending approval。
- reject 不执行工具。
- approve 产生 resume task，但完整恢复执行放到 1.9.2。
- 独立提交建议：`feat(agent): add approval workflow foundation`。

### 1.7.0：API Contract / OpenAPI / BFF 类型治理

目标：让后端 schema、Next.js BFF、前端类型可验证。

任务清单：

1. 所有新增 API 使用 Pydantic request / response model。
1. 新增 OpenAPI export 脚本。
1. CI 检查 OpenAPI diff。
1. 前端集中管理 BFF contract 类型。
1. BFF 统一解析后端 envelope。
1. 后端 API 变更必须同步 BFF。
1. 新增 contract tests。

验证：

```bash
uv run python -m pytest tests/test_agent_openapi_contract.py tests/test_agent_api.py -q
cd frontend
pnpm typecheck
pnpm build
```

完成定义：

- API schema 变更可被 CI 捕获。
- 前端不再散落重复类型。
- 独立提交建议：`feat(api): add openapi contract checks for agent APIs`。

### 1.7.1：前端 Workbench 可观测性增强

目标：前端能展示 1.x 现有 runtime 的更多可复盘信息，为 2.0 UI 打底。

任务清单：

1. Run Detail 展示 replay snapshot。
1. Timeline 展示 event type、stage、message、payload 摘要。
1. Tool result 显示 status、approval_state、error。
1. History 显示 runtime_version、trace_id、approval_state。
1. Tools 页面展示 tool schema 字段。
1. Approvals 页面展示 pending / approved / rejected。

验证：

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm build
```

完成定义：

- 2.0 前端页面结构已经准备好。
- 仍兼容 1.x runtime events。
- 独立提交建议：`feat(frontend): improve agent workbench observability`。

### 1.8.0：Decision Runtime Contract

目标：只定义 2.0 决策模型，不接 LangGraph。

新增模型：

```text
RuntimeBudget
AgentGoalContract
AgentDecision
EvidenceAssessment
RecoveryDecision
AgentDecisionState
```

任务清单：

1. 定义 action types：

   ```text
   observe
   call_tool
   ask_approval
   recover
   final_report
   handoff
   ```

1. 定义 evidence quality：

   ```text
   strong
   partial
   weak
   empty
   conflicting
   error
   ```

1. 定义 run status：

   ```text
   running
   waiting_approval
   completed
   failed
   handoff_required
   cancelled
   ```

1. 禁止保存私有 chain-of-thought。

1. 只保存 `reasoning_summary`、decision、evidence、tool input/output。

验证：

```bash
uv run python -m pytest tests/test_agent_decision_models.py -q
make verify
```

完成定义：

- 决策模型可序列化、可校验、可写 event payload。
- 独立提交建议：`feat(agent): add decision runtime contracts`。

### 1.8.1：Deterministic Decision Provider

目标：先用确定性 provider 跑通决策流程，避免一开始依赖 LLM。

任务清单：

1. 定义 `DecisionProvider` protocol。
1. 实现 `DeterministicDecisionProvider`。
1. 有未调用工具时返回 `call_tool`。
1. 无工具时返回 `handoff`。
1. 有 strong evidence 时返回 `final_report`。
1. 连续空证据时返回 `recover`。
1. 超预算时返回 `handoff`。

验证：

```bash
uv run python -m pytest tests/test_agent_decision_provider.py -q
make verify
```

完成定义：

- 不调用 LLM 也能生成结构化 decision。
- 后续 LangGraph 可以先接 deterministic provider。
- 独立提交建议：`feat(agent): add deterministic decision provider`。

### 1.8.2：Evidence-driven Report

目标：报告先升级为证据驱动格式，再接入 LangGraph。

报告结构：

```text
目标
成功条件
已确认事实
关键证据
推断结论
不确定项
已执行动作
未执行动作
恢复与降级
建议下一步
```

任务清单：

1. 新增 report synthesizer v2。
1. 无证据时禁止输出确定根因。
1. 工具失败必须说明。
1. 审批拒绝必须说明。
1. 低置信必须 handoff。
1. 证据冲突必须说明。

验证：

```bash
uv run python -m pytest tests/test_agent_report_synthesizer_v2.py -q
make verify
```

完成定义：

- 1.x runtime 也可以使用更严谨报告格式。
- 独立提交建议：`feat(agent): generate evidence-driven reports`。

### 1.9.0：LangGraph Runtime Skeleton

目标：接入 LangGraph 骨架，但先使用 deterministic provider，不接 Qwen。

图结构：

```text
initialize
  -> observe
  -> decide
  -> validate_decision
  -> act
  -> evaluate_evidence
  -> route_next
  -> recover
  -> final_report
```

任务清单：

1. 新增 `AgentDecisionRuntime`。
1. 使用 `StateGraph`。
1. 使用 `DatabaseCheckpointSaver`。
1. `thread_id = run_id`。
1. `checkpoint_ns = agent-v2`。
1. `AgentRuntime.run()` 可通过配置切到 new runtime。
1. API 和 SSE shape 保持兼容。
1. 先只接 deterministic provider。

验证：

```bash
uv run python -m pytest tests/test_agent_decision_runtime.py tests/test_agent_api.py -q
make verify
```

完成定义：

- LangGraph runtime 可以跑通一次 run。
- 不依赖 LLM。
- 不破坏现有 API。
- 独立提交建议：`feat(agent): add langgraph decision runtime skeleton`。

### 1.9.1：Qwen Decision Provider

目标：把 LLM 决策作为 provider 接入，但所有输出必须结构化校验。

任务清单：

1. 实现 `QwenDecisionProvider`。
1. Prompt 要求只输出 JSON。
1. 不允许 Markdown 包裹 JSON。
1. 不允许输出 chain-of-thought。
1. 只能选择 available tools。
1. 必须给 `confidence`。
1. 必须给 `expected_evidence`。
1. 非法 JSON 进入 recovery。
1. 未知工具进入 recovery。
1. 低置信进入 recovery。

验证：

```bash
uv run python -m pytest tests/test_qwen_decision_provider.py tests/test_agent_decision_runtime.py -q
make verify
```

完成定义：

- Qwen provider 可以被 mock 测试。
- 非法输出不会导致 run 崩溃。
- 独立提交建议：`feat(agent): add qwen decision provider`。

### 1.9.2：Checkpoint Resume / Approval Resume

目标：approve 后从 checkpoint 恢复，不重新生成高风险动作。

任务清单：

1. approval approve 后写入 Redis resume queue。
1. worker 消费 resume task。
1. 从 LangGraph checkpoint 恢复。
1. 只执行被审批的原 decision。
1. 不重新调用 LLM 生成高风险动作。
1. reject 后进入 handoff / final_report。
1. expired approval 进入 handoff。

验证：

```bash
uv run python -m pytest tests/test_agent_approval_resume.py tests/test_agent_approvals.py -q
make verify
```

完成定义：

- approval resume 具备 durable execution 语义。
- 高风险动作不会被重复生成或越权执行。
- 独立提交建议：`feat(agent): resume approved actions from checkpoints`。

### 1.9.3：Decision Runtime E2E / Regression

目标：在发布 2.0 前完成端到端和回归保护。

任务清单：

1. 增加后端 regression：

   ```text
   valid decision
   invalid JSON
   unknown tool
   disabled tool
   forbidden tool
   approval required
   tool timeout
   empty evidence
   budget exhausted
   ```

1. 增加前端 E2E：

   ```text
   发起诊断
   查看 history
   查看 run detail
   查看 decisions/evidence
   审批 high risk action
   拒绝 approval
   ```

1. CI 增加 migration upgrade/downgrade smoke。

1. CI 增加 OpenAPI contract check。

验证：

```bash
make verify
cd frontend
pnpm lint
pnpm typecheck
pnpm build
pnpm e2e
```

完成定义：

- 2.0 关键路径有回归保护。
- 前端能完成最小诊断闭环。
- 独立提交建议：`test(agent): add decision runtime regression scenarios`。

### 2.0.0：LangGraph Decision Runtime 正式发布

目标：把 1.9 系列稳定能力汇总为正式 2.0 发布。

发布任务：

1. 默认启用 LangGraph Decision Runtime。

1. 版本号更新：

   ```text
   pyproject.toml -> 2.0.0
   app/config.py -> 2.0.0
   app/__init__.py -> 2.0.0
   README -> 2.0
   PLAN -> 2.0 completed
   ```

1. README 更新 Decision Runtime 架构说明。

1. README 更新中间件架构说明。

1. README 更新运行、测试、回滚命令。

1. PR 描述必须包含用户影响、API 兼容性、migration、回滚策略、验证结果。

最终质量门：

```bash
make verify
cd frontend
pnpm lint
pnpm typecheck
pnpm build
pnpm e2e
```

完成定义：

- 默认 runtime 是 LangGraph Decision Runtime。
- 旧 Agent API 兼容。
- approval resume 可用。
- evidence-driven report 可用。
- replay / metrics / trace 可用。
- 独立提交建议：`chore(release): bump version to 2.0.0`。

### Rollback Strategy

`1.4.x` 中间件回滚：

- pgvector 失败：临时切回 Milvus adapter。
- MinIO 失败：暂停文件索引，保留 metadata。
- Caddy 失败：直接访问 Next.js / FastAPI。
- OTel 失败：关闭 observability profile，不影响主链路。

`1.9.x` / `2.0.0` runtime 回滚：

- 通过配置临时切回 1.x AgentRuntime。
- revert 相关 PR。
- 保留 `agent_events`。
- `agent_decisions`、`agent_evidence`、`agent_approvals` 可只读保留。
- 必要时执行 Alembic downgrade。

### Implementation Guardrails

智能体执行时必须遵守：

- 不在中间件阶段顺手改 Decision Runtime。
- 不在 Decision Runtime 阶段顺手重构 compose。
- 不绕过 BFF 让前端直接调用 FastAPI。
- 不让 LLM 直接执行工具。
- 不持久化私有 chain-of-thought。
- 不在报告中编造工具证据。
- 不把 Redis 当事实源。
- 不把 MinIO 当 metadata 源。
- 不把 Milvus 作为默认必需依赖。

## External Learning：Agentic AI Guide 可吸收原则

参考：https://yeasy.gitbook.io/agentic_ai_guide

可吸收但需要按 SmartSRE 场景改造的点：

- 从 ChatBot 走向 Agent 的关键不是“会说”，而是感知、规划、记忆、行动和反馈闭环；SmartSRE 应继续坚持“单 Agent + 强
  Harness + 强 Eval”优先。
- ReAct 可作为 V2.0 的运行时骨架，但不能直接持久化私有 chain-of-thought；落地形式应是
  `observe -> decide -> act -> observe -> recover/final_report`，只保存结构化
  decision、证据、工具输入输出和安全摘要。
- 静态编排和自主编排不是二选一。SRE 场景应使用混合模式：明确 SOP/黄金路径走确定性 workflow，未知问题走 bounded Agent
  loop。
- AgentOps 必须成为产品底座：Tracing、Metrics、Logs、Eval、成本、错误边界、安全治理和上线检查清单都应是一等公民。
- Evaluation 需要分层：代码评估器验证工具调用和状态变化，模型评估器验证开放式报告质量，人工评估器校准复杂事故结论。
- Eval 要区分 Capability Eval 和 Regression Eval：前者探索新能力上限，后者保护已验证路径不退化。
- Tool Use 必须标准化：工具是 Agent 的“手”和“眼”，所有工具都要有 schema、权限、风险、超时、重试、审计、approval 和
  sandbox 边界。
- 成本治理要前置：每次 run 记录 token、step、tool_call、latency、cache 命中和
  Cost/Request，避免长上下文、多轮工具调用和多 Agent 通信导致成本失控。
- 上下文工程要避免无限累积：使用滑动窗口、摘要、静态前缀缓存、语义缓存和按需工具说明加载。
- 多 Agent 不是早期目标。只有当单 Agent harness、eval、replay、approval 和成本监控稳定后，才引入明确分工的子
  Agent。

## External Learning：Agentic Design Patterns 可吸收原则

参考：https://adp.xindoo.xyz/

ADP 的价值不在于把每章都做成一个功能，而是帮助 SmartSRE 把 Agent Runtime 拆成更稳定的工程能力：

- 目标设定和监控应成为 V2.0 核心：每次 run 必须显式记录
  `goal`、`success_criteria`、`stop_condition`、`progress_state` 和
  `confidence`，而不是只保存用户输入和最终回答。
- 规划不是一次性大纲，而是可更新的假设队列：每一步都要能说明当前假设、证据缺口、下一步动作和为什么优先做它。
- 优先级排序必须进入 runtime：事故诊断要支持 P0/P1/P2 任务、证据优先级、工具风险优先级和预算优先级，避免 Agent
  在低价值工具调用上空转。
- 异常处理和恢复必须显式建模：非法 JSON、工具超时、无证据、证据冲突、重复调用、低置信度、预算耗尽都要进入 recovery 分支。
- 人机协同不是后期 UI，而是安全边界：高风险动作、低置信结论、跨系统变更、敏感数据访问必须进入 pending approval 或 handoff。
- Guardrails 应覆盖输入、工具、输出、权限、数据边界和成本边界；尤其是 SRE 场景，禁止 Agent 未经审批直接执行变更类或破坏性操作。
- 评估和监控应跟 runtime 同步建设：每次决策都要产生可追踪 trace，后续才能做 replay、badcase、regression eval
  和成本优化。
- 多 Agent 协作、A2A、探索发现应后置。SmartSRE 先把单 Agent 的目标、决策、恢复、审批、评估闭环做扎实，再扩展多 Agent。

## Roadmap

### V1.x Current Baseline：Native Agent 闭环基线（当前状态）

目标：承认当前项目已经不是普通 “RAG Chat + AIOps 接口”，而是具备最小闭环雏形的 Native SRE Agent Workbench。

当前已形成或正在形成这条链路：

```text
Workspace
  -> Scene
  -> Goal
  -> Plan / Hypothesis
  -> Governed Tool Call
  -> Evidence
  -> Final Report
  -> Feedback
  -> Persisted Run / Replayable Events
```

当前基线需要继续稳定的范围：

- 修复 AIOps 输入链路：前端用户输入必须进入后端 diagnosis goal，禁止固定默认任务假诊断。
- 接入 Native Agent 前端：新增 Agent Console、BFF routes、run events、run
  history、feedback。
- 建立 workspace、scene、tool policy、run、event、feedback 的产品闭环。
- 固化 runtime contract：统一 run status、event taxonomy、tool result schema、error
  shape、SSE event shape。
- 固化 tool harness：所有工具必须有 name、description、input schema、risk level、required
  capability、timeout、retry、approval policy。
- 高风险工具不直接执行，必须返回 approval_required 或进入 pending approval。
- 修复文档乱码：README、PLAN、注释、日志统一 UTF-8 或英文。
- 建立 Agent eval 基线：先用固定工具输出做 deterministic tests，不直接测试模型“聪不聪明”。
- 建立 AgentOps 最小闭环：每次 run 至少记录
  trace_id、model、tokens、tool_calls、latency、error_type、cost_estimate、approval_state。

V1.x 不追求完全自主。它可以使用 deterministic planner 或静态 workflow，只要闭环可用、可审计、可复盘、可回归。

### V2.0 Decision Runtime：目标驱动的结构化决策版本

目标：把当前“能完成闭环”的 Agent，升级为“能解释目标、规划假设、排序行动、验证证据、恢复异常、请求人工确认”的决策系统。

V2.0 必须闭合这条决策链路：

```text
Goal
  -> Success Criteria / Stop Condition
  -> Observation
  -> Hypothesis Queue
  -> Prioritized Decision
  -> Governed Tool Call
  -> Evidence Validation
  -> Recovery / Approval / Continue
  -> Final Report / Handoff
```

V2.0 范围：

- 引入
  `AgentDecisionLoop`：`observe -> decide -> act -> observe -> recover/final_report`。
- 每次 run
  显式记录目标治理字段：`goal`、`success_criteria`、`stop_condition`、`progress_state`、`confidence`、`budget`。
- LLM 只输出结构化 decision，不直接绕过 runtime 调工具。
- 决策字段使用
  `reasoning_summary`、`action_type`、`tool_name`、`arguments`、`rationale`、`confidence`、`success_criteria`、`expected_evidence`、`final_report`，不要持久化私有
  chain-of-thought。
- Runtime 负责校验 decision：工具是否存在、参数是否合法、权限是否满足、是否需要 approval、是否超过 step/token/time
  budget。
- 建立优先级模型：P0/P1/P2 诊断任务、证据优先级、工具风险优先级、成本预算优先级和人工介入优先级。
- 支持安全 fallback：非法 JSON、非法工具、低置信度、工具不可用、max steps reached、证据不足时生成 bounded report
  或 handoff summary。
- 新增 approval workflow：高风险工具进入 pending approval，批准后继续执行，拒绝后安全结束。
- 使用混合编排策略：已知 SOP 场景走静态 workflow；未知诊断走 bounded Agent loop；高风险动作必须停在 approval。
- 增加 recover 分支：工具失败、结果为空、证据冲突、重复调用、低置信度、预算耗尽时进入恢复策略，而不是继续盲目调用工具。
- 建立决策可观测性：每次 decision、tool_call、evidence、approval、recovery、handoff 都要有 event 和
  trace/span。
- 建立决策质量指标：goal_completion、evidence_coverage、false_root_cause、unnecessary_tool_call、handoff_quality、cost_per_run。

V2.0 不以“多 Agent”或“更复杂模型”为成功标准，而以单 Agent 决策闭环是否可控、可恢复、可审计、可评估为成功标准。

### V2.1 Knowledge / Skills：把 SRE 经验变成可加载能力

- 建立 SRE Skill 体系：CPU high、memory leak、disk full、slow response、service
  unavailable、deploy regression、queue backlog。
- Skill 不是普通文档，而是包含触发条件、诊断步骤、推荐工具、证据要求、风险提示、报告模板。
- Knowledge pipeline 支持 FAQ、SOP、历史事故、历史 Agent run、群聊/工单摘要。
- Retrieval 升级为：query rewrite -> scene routing -> vector recall -> rerank ->
  confidence gate -> cite evidence。
- 低置信检索不强答；生成“缺少证据 + 建议下一步”。
- 历史 run 通过人工确认后沉淀为 FAQ/SOP/Skill，形成 Oncall 学习闭环。
- 引入上下文压缩策略：静态系统提示、工具摘要、scene context、run history 分层管理，长会话使用滑动窗口 + 摘要。
- 引入语义缓存：FAQ、重复告警、常见 SOP 问题可在高置信命中时直接返回可追踪答案，降低延迟和 token 成本。

### V2.2 Replay / Eval / Observability：让 Agent 可复盘、可回归

- 支持 run replay：固定 tool outputs 后可重放完整事件轨迹和最终报告。
- 建立 golden scenario eval：CPU high、5xx spike、slow response、disk full、发布回滚、依赖故障。
- Eval 只测行为，不测文案：是否调用正确工具、是否引用证据、是否承认未知、是否避免伪造根因。
- 引入 badcase workflow：用户反馈、人工接管、错误结论、工具失败都进入 badcase 池。
- 建立 OpenTelemetry GenAI 观测：run、LLM call、tool
  call、retrieval、guardrail、approval、handoff 都有 trace/span。
- Agent Console 展示计划、工具轨迹、证据链、审批、失败原因、最终报告。
- 建立 Eval Harness 术语和数据结构：Task、Trial、Grader、Trace、Outcome、Eval Suite。
- 建立三类 grader：代码 grader 验证工具调用/状态变化，模型 grader 评审报告质量，人工 grader 校准高风险事故结论。
- 建立两套 eval：Capability Eval 用来探索新能力，Regression Eval 用来保护已验证黄金路径。
- 建立成本与性能指标：P50/P95 latency、step count、input/output token、tool output
  token、cache hit rate、Cost/Request。

### V2.3 MCP / Tool Ecosystem / Analytics：从 Copilot 到 Oncall 平台

- MCP 作为工具接入主协议，本地工具和远程工具走同一治理模型。
- 工具市场化：日志、指标、Trace、告警、发布、配置、CMDB、工单、知识库。
- Analytics 聚合高频问题、重复告警、低质量 SOP、工具失败率、知识缺口、token 成本。
- 输出团队治理建议：哪些问题应该补文档、补监控、补自动化、修平台能力。
- 支持 handoff：Agent 没把握时自动生成转人工摘要，包括已查证据、失败工具、下一步建议。
- 引入 Tool Registry 分级：readonly、diagnostic、change、destructive 四类工具使用不同权限、approval
  和审计策略。
- 对云 MCP
  工具建立运行保障字段：owner、SLO、timeout、rate_limit、data_boundary、credential_scope、fallback。

### V3 Long-running / Multi-agent：最后再做多 Agent

- 在单 Agent harness 稳定后，引入后台任务、子 Agent、任务图、长运行 checkpoint。
- 多 Agent 只用于明确分工：log investigator、metric investigator、release
  investigator、knowledge summarizer。
- 主 Agent 负责调度和最终结论，子 Agent 只负责收集证据，避免多 Agent 互相编故事。
- 支持长任务恢复、暂停、人工介入、任务取消、超时降级。
- 多 Agent 启用前必须先满足：单 Agent eval 稳定、trace 完整、成本可归因、失败可恢复、人工审批链路可用。

## Engineering Baseline

- Web/API/DB/CI 对齐 FastAPI full-stack-template：SQLModel、SQLAlchemy
  Session、Alembic、Docker Compose、pytest、GitHub Actions、OpenAPI contract。
- Agent Runtime 不绑定单一模型厂商；通过 provider adapter 支持 Qwen/OpenAI-compatible/其他模型。
- 前端只调用 Next.js BFF route，不直接暴露后端密钥或模型密钥。
- 所有 Agent 结果必须可追踪到 event、tool output、knowledge citation 或明确标注为推断。
- 高风险动作默认 human approval；生产环境禁止无鉴权、通配 CORS、裸工具调用。
- Token 预算成为一等公民：每次 run 记录 prompt token、tool output token、retrieval
  token、summary token 和压缩策略。
- AgentOps 指标成为发布门禁：没有 trace、eval、成本估算、approval 事件和错误分类的 Agent 功能不得进入生产。
- Prompt/Context 资产版本化：system prompt、tool description、skill template、retrieval
  policy、grader rubric 都要可追踪版本。

## Test Plan

- Unit tests：decision parser、policy gate、tool schema、guardrail、approval、report
  fallback。
- Contract tests：Native Agent API、SSE events、BFF adapters、MCP tool schema。
- Integration tests：workspace -> scene -> tool policy -> run -> events ->
  feedback。
- Scenario evals：用固定 mock observability data 验证 Agent 行为。
- Replay tests：固定事件和工具输出，验证结果可复现。
- Failure tests：LLM 非法 JSON、工具超时、权限不足、知识库空、MCP 不可用、低置信度。
- E2E smoke：只保留 3-5 条黄金路径，不测试 UI 文案和 CSS 细节。
- Cost tests：固定场景下断言 step/token/tool_call 不超过预算，防止死循环和上下文膨胀。
- Security tests：越权工具、需要审批工具、敏感输出、跨租户数据边界、MCP 凭证范围必须覆盖。

## Assumptions

- FastAPI 模板是工程地基，不是 Agent 架构答案。
- Claude Code / Harness Engineering 是 Agent Runtime 主要参考。
- KOncall 是产品形态主要参考。
- AWS Token/Harness 思路用于上下文、记忆、Skill 和成本治理。
- Agentic AI Guide 用作通用方法论参考，具体落地必须以 SmartSRE 的 SRE/Oncall 场景、证据链、审批和生产安全为准。
- 当前优先级是“单 Agent + 强 Harness + 强 Eval”，不是一开始就做多 Agent。
