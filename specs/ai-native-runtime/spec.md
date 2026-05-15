# Feature Specification: AI Native Agent Runtime

**Feature Branch**: `feature/ai-native-runtime`
**Created**: 2026-05-13
**Status**: Draft / Implementation In Progress
**Constitution**: [constitution.md](./constitution.md)

## Implementation Status (2026-05-15)

This specification is still the target contract for the AI Native Runtime. The
current codebase has implemented several supporting capabilities, but it has not
yet reached the full completion state described here.

Implemented or mostly implemented:

- Native Agent run APIs, replay APIs, approval APIs, feedback APIs, and badcase
  review / promotion APIs exist.
- `BoundedReActLoop` exists as an isolated loop skeleton with step, time, and
  token budget boundaries, but it is not yet wired into `AgentRuntime.run()`.
- `agent_runs` already stores runtime metrics fields such as `runtime_version`,
  `trace_id`, `decision_provider`, `step_count`, `token_usage`, and
  `cost_estimate`.
- `MetricsCollector` is isolated in `app/agent_runtime/metrics_collector.py` and
  persists non-empty heuristic token / cost metrics for deterministic runs.
- `EvidenceAssessor` is isolated in `app/agent_runtime/evidence.py` for current
  tool-result quality classification and handoff reason mapping.
- `ApprovalGate` is isolated in `app/agent_runtime/approval.py` for high-risk
  tool pause semantics.
- `RecoveryManager` is isolated in `app/agent_runtime/recovery.py` for
  cancellation, timeout, and unexpected-error failure boundaries.
- `TraceCollector` is isolated in `app/agent_runtime/trace_collector.py` and
  guards runtime spans without making OpenTelemetry a hard dependency.
- Deterministic and Qwen decision providers share the current decision runtime,
  and Qwen failures emit `provider_fallback` before falling back.
- Cross-session memory exists as text memory and is injected through
  `memory_context` events.
- Badcase feedback, review, and knowledge-promotion queueing are available.

Partially implemented:

- The production runtime loop is still orchestrated inside
  `app/agent_runtime/runtime.py`; the extracted `BoundedReActLoop` skeleton must
  still be integrated.
- Evidence assessment has a dedicated module, but conflict detection and richer
  evidence coverage rules still need to be implemented.
- Recovery strategy selection is still basic; richer retry / alternative /
  downgrade decisions remain pending.
- Replay exposes metrics, memory, approval, badcase, and recovery events, but
  per-step `agent_events` metric columns are not persisted yet.
- Agent memory does not yet use pgvector embeddings for semantic retrieval.

Not implemented yet:

- Proactive monitor, alert deduplication, and automatic diagnosis triggers.
- Collaborative intervention APIs and frontend controls.
- Grafana dashboard artifacts for AgentOps.
- Full pgvector-backed memory retrieval and badcase clustering / FAQ candidate
  workflow.

Local-only planning files such as `PLAN.md` and
`specs/ai-native-runtime/plan.md` must stay untracked.

## User Scenarios & Testing

### US1 — Bounded ReAct Diagnosis (Priority: P1)

用户输入一个问题（如"线上服务响应慢"），Agent 自动执行：
observe → decide → act（调工具）→ observe（评估证据）→ decide（继续或结束）
→ final_report。整个过程在 step budget 内完成。

**Why this priority**: 这是 AI 原生的核心能力，没有循环的 Agent 只是脚本。

**Independent Test**: 发起一个诊断 run，验证 Agent 至少执行 2 步工具调用，
并在 step budget 内产出 final_report。

**Acceptance Scenarios**:

1. **Given** 用户发起诊断，**When** Agent 执行 3 步工具调用，**Then**
   产出包含 evidence 和 recommendation 的 final_report
2. **Given** Agent 执行达到 max_steps，**When** 未达成 goal，**Then**
   产出 bounded_report（含已收集证据 + 未完成原因）
3. **Given** Agent 调用工具超时，**When** 工具在 step_timeout 内未返回，
   **Then** 进入 recovery 分支，记录 tool_failure event，继续下一步

---

### US2 — Dual Provider Runtime (Priority: P1)

Agent Decision Provider 支持运行时切换。Deterministic provider 按规则选择工具，
Qwen provider 用 LLM 推理选择工具。切换通过 config 的 agent_decision_provider
字段控制，无需改代码。

**Why this priority**: 双 provider 是可控演进的基础，先用 Deterministic 保证
稳定，再切换 LLM 验证效果。

**Independent Test**: 修改 agent_decision_provider 为 "qwen"，重启服务，
验证同一个 golden scenario 在两种 provider 下都能产出 final_report。

**Acceptance Scenarios**:

1. **Given** agent_decision_provider="deterministic"，**When** 发起诊断，
   **Then** Agent 按预定义规则选择工具，不调用 LLM
2. **Given** agent_decision_provider="qwen"，**When** 发起诊断，
   **Then** Agent 通过 Qwen LLM 推理选择工具，产出 reasoning_summary
3. **Given** Qwen API 不可用，**When** agent_decision_provider="qwen"，
   **Then** 自动降级到 deterministic，记录 provider_fallback event

---

### US3 — AgentOps Real Metrics (Priority: P1)

每次 Agent run 必须记录真实的 token_usage、cost_estimate、latency、
step_count。MetricsCollector 不再写 None。

**Why this priority**: 没有真实指标，AgentOps 就是空话，无法做成本优化
和性能调优。

**Independent Test**: 执行一个 Agent run，查询 agent_runs 表，验证
token_usage 和 cost_estimate 为非空 JSON。

**Acceptance Scenarios**:

1. **Given** Agent 执行一次 run，**When** run 完成，**Then**
   agent_runs 表中 token_usage (JSON) 含 prompt_tokens/completion_tokens，
   cost_estimate (JSON) 含 total_cost，均非 None
2. **Given** Agent 调用了 3 次 LLM，**When** 统计 token，
   **Then** token_usage.prompt_tokens + token_usage.completion_tokens > 0
3. **Given** Agent 调用了 2 个工具，**When** 统计 tool_calls，
   **Then** tool_call_count = 2, 每个工具的 latency 独立记录

---

### US4 — Evidence Loop with Recovery (Priority: P2)

Agent 执行工具后必须评估证据质量。证据不足时进入 recovery 分支：
重试、换工具、降级报告、或 handoff。不允许在无证据时伪造结论。

**Why this priority**: 证据循环是决策质量的保障，没有它 Agent 会输出
无根据的结论。

**Independent Test**: Mock 一个工具返回空结果，验证 Agent 进入 recovery，
不产出伪造的根因结论。

**Acceptance Scenarios**:

1. **Given** 工具返回空结果，**When** Agent 评估证据，**Then**
   证据质量为 insufficient，进入 recovery
2. **Given** 连续 3 次工具调用失败，**When** 达到 recovery 上限，
   **Then** 产出 handoff summary（已查证据 + 失败原因 + 建议下一步）
3. **Given** 证据冲突（两个工具给出矛盾结果），**When** Agent 评估，
   **Then** 标注 conflict，请求人工确认或增加工具验证

---

### US5 — Feedback → Knowledge Loop (Priority: P3)

用户对 Agent 报告的反馈（有用/无用/修正）沉淀为知识。
高频无用反馈触发 badcase 分析，经人工确认后补充 FAQ。

**Why this priority**: 知识闭环是长期价值增长的引擎。

**Independent Test**: 提交一条"无用"反馈 + 修正内容，验证 badcase 池
有新记录，且可被查询。

**Acceptance Scenarios**:

1. **Given** 用户标记报告"无用"并提供修正，**When** 反馈提交，
   **Then** agent_feedback 表有新记录，correction 非空，badcase_flag=True
2. **Given** 同一类型 badcase 累计 5 次，**When** 触发聚类，
   **Then** 生成 FAQ candidate，等待人工确认
3. **Given** 人工确认 FAQ，**When** 入库，**Then** 后续相似查询
   可命中该 FAQ

---

### US6 — Proactive Monitor (Priority: P2)

Agent 不再等待用户发起诊断。系统通过定时任务周期性探测环境状态，
发现异常时自动触发诊断 run，将结果推送至告警通道。

**Why this priority**: 主动感知是 AI 原生产品的核心特征。
被动响应的 Agent 只是工具，主动发现问题的 Agent 才是伙伴。

**Independent Test**: 启动 ProactiveMonitor，Mock 一个异常指标，
验证系统自动发起诊断 run 并产生告警事件。

**Acceptance Scenarios**:

1. **Given** ProactiveMonitor 启动，**When** 周期探测发现指标异常（如 CPU > 90%），
   **Then** 自动创建诊断 run，goal 为"异常指标根因分析"
2. **Given** 自动诊断 run 完成，**When** 产出 final_report，
   **Then** 通过 SSE 推送告警事件到前端，含报告摘要 + 跳转链接
3. **Given** 同一指标在上一轮已告警，**When** 周期探测再次触发，
   **Then** 去重（suppress_interval 内不重复告警），避免告警风暴
4. **Given** ProactiveMonitor 配置了监控数据源（Prometheus/Grafana API），
   **When** 数据源不可用，**Then** 降级为本地 MCP 工具探测，记录 degraded_event

---

### US7 — Cross-session Memory (Priority: P2)

Agent 拥有跨会话的持久记忆。每次诊断 run 的关键结论（根因、证据、解决方案）
向量化存储，新 run 启动时自动检索相关历史，辅助决策。

**Why this priority**: 没有记忆的 Agent 每次都从零开始，无法积累经验。
跨会话记忆是"越用越聪明"的基础设施。

**Independent Test**: 执行两次相似诊断 run，验证第二次 run 的决策上下文中
包含第一次 run 的历史结论引用。

**Acceptance Scenarios**:

1. **Given** 历史 run #1 诊断出"慢响应根因是连接池耗尽"，**When** 新 run #2
   发起"服务响应慢"诊断，**Then** Agent 在 observe 阶段检索到 run #1 的结论，
   优先验证连接池状态
2. **Given** 向量化存储中无相关历史，**When** 新 run 启动，
   **Then** MemoryRetriever 返回空列表，Agent 正常执行（不阻塞）
3. **Given** MemoryRetriever 检索到 3 条相关历史，**When** 构建 DecisionContext，
   **Then** 历史结论作为 context 注入，附带相似度分数和原始 run_id
4. **Given** 历史 run 的结论被后续 run 验证为正确，**When** 再次触发记忆检索，
   **Then** 该结论的 confidence 权重提升（经验强化）

---

### US8 — Collaborative Intervention (Priority: P3)

Agent 执行过程中，人工介入不限于审批 gate，而是可以随时接管决策、
修改计划、提供额外上下文。Agent 与人形成实时协作关系。

**Why this priority**: 审批是"允许/禁止"的二元决策，
协作是"我们一起想办法"的智能交互。这是 AI 原生产品的终极形态。

**Independent Test**: Agent 正在执行诊断，人工通过 API 注入额外证据，
验证 Agent 将新证据纳入后续决策。

**Acceptance Scenarios**:

1. **Given** Agent 正在执行 observe → decide 循环，**When** 人工通过
   intervention API 注入"已知该服务刚做过发布"，**Then** Agent 在下一步
   的 DecisionContext 中包含该信息，优先检查发布相关指标
2. **Given** Agent 即将执行一个低置信度的工具调用，**When** 人工通过
   intervention API 替换为另一个工具（含参数），**Then** Agent 执行替换后的
   工具调用，记录 intervention_event
3. **Given** Agent 产出 final_report，**When** 人工在报告页面追加修正结论，
   **Then** 修正内容关联到原始 run，写入 agent_feedback（correction 非空）
4. **Given** Agent 连续 3 步置信度低于阈值，**When** 无人工干预，
   **Then** Agent 主动发起 human_handoff，暂停执行等待人工指导

---

## Requirements

### Functional Requirements

- **FR-001**: AgentRuntime MUST 执行 Bounded Re Act Loop：
  observe → decide → act → observe → recover/final_report
- **FR-002**: AgentRuntime MUST enforce step budget（默认 max_steps=8）
- **FR-003**: AgentRuntime MUST enforce token budget（默认 max_tokens=50000）
- **FR-004**: AgentRuntime MUST enforce time budget（默认 max_time=120s）
- **FR-005**: DecisionProvider MUST 支持 runtime 切换（deterministic/qwen）
- **FR-006**: MetricsCollector MUST 记录 token_usage (JSON), cost_estimate (JSON),
  latency_ms, step_count, tool_call_count（非 None）
- **FR-007**: EvidenceAssessment MUST 评估每个工具输出的质量
  （strong/moderate/weak/insufficient/conflict/error）
- **FR-008**: RecoveryManager MUST 处理：工具超时、空结果、证据冲突、
  重复调用、低置信度、预算耗尽
- **FR-009**: ApprovalGate MUST 阻止 change/destructive 工具直到人工批准
- **FR-010**: FeedbackService MUST 将用户反馈持久化到 agent_feedback 表
- **FR-011**: Agent run MUST 产生 OpenTelemetry trace（decision + tool_call
  + evidence + approval + recovery + handoff）
- **FR-012**: Provider fallback MUST 在 LLM 不可用时自动降级到 deterministic
- **FR-013**: ProactiveMonitor MUST 按配置的 interval 周期探测环境指标
- **FR-014**: ProactiveMonitor MUST 实现告警去重，suppress_interval 内同一指标不重复触发
- **FR-015**: ProactiveMonitor MUST 在数据源不可用时降级到本地 MCP 工具
- **FR-016**: MemoryRetriever MUST 将每次 run 的关键结论向量化存储
- **FR-017**: MemoryRetriever MUST 在新 run 启动时检索 top-k 相关历史结论
- **FR-018**: MemoryRetriever MUST 将历史结论作为 context 注入 DecisionContext
- **FR-019**: InterventionAPI MUST 支持人工在 Agent 执行中途注入额外证据
- **FR-020**: InterventionAPI MUST 支持人工替换 Agent 即将执行的工具调用
- **FR-021**: Agent MUST 在连续低置信度时主动发起 human_handoff
- **FR-022**: Agent MUST 记录所有 intervention_event 到 agent_events 表

### Key Entities

- **AgentRun**: 一次完整的 Agent 执行（goal, budget, status, metrics）
- **AgentDecision**: 单次决策（action_type, tool_name, arguments, confidence）
- **AgentEvent**: 执行过程中的事件（decision, tool_call, evidence, recovery...）
- **AgentEvidence**: 工具输出的评估结果（quality, content, source_tool）
- **AgentFeedback**: 用户反馈（rating, correction, badcase_flag）

## Success Criteria

- **SC-001**: Agent 在 max_steps=8 内完成诊断并产出 final_report（100%）
- **SC-002**: token_usage (JSON) 和 cost_estimate (JSON) 在每次 run 后非 None（100%）
- **SC-003**: 工具超时时 Agent 进入 recovery 而非崩溃（100%）
- **SC-004**: Deterministic 和 Qwen provider 产出格式一致的 decision
- **SC-005**: 6 个 golden scenario 全部通过 regression eval
- **SC-006**: P95 latency < 120s（step_budget=8 内）

- **SC-007**: ProactiveMonitor 在异常检测后 30s 内自动发起诊断 run
- **SC-008**: 同一指标 suppress_interval 内去重率 100%
- **SC-009**: MemoryRetriever 检索延迟 < 200ms（top-k=5, 向量维度 1024）
- **SC-010**: 人工干预后 Agent 在下一步决策中体现干预内容（100%）
- **SC-011**: 连续 3 步低置信度时 Agent 自动发起 handoff（100%）

## Assumptions

- PostgreSQL 和 Redis 可用（docker-compose 已配置）
- DashScope Qwen API key 已配置（用于 QwenDecisionProvider）
- 现有 tool schema 和 ToolExecutor 接口不变
- 现有 SSE event 协议向后兼容
- MCP 服务（monitor/cls）可用于集成测试
