# Feature Specification: AI Native Agent Runtime

**Feature Branch**: `feature/ai-native-runtime`
**Created**: 2026-05-13
**Status**: Draft
**Constitution**: [constitution.md](./constitution.md)

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

## Assumptions

- PostgreSQL 和 Redis 可用（docker-compose 已配置）
- DashScope Qwen API key 已配置（用于 QwenDecisionProvider）
- 现有 tool schema 和 ToolExecutor 接口不变
- 现有 SSE event 协议向后兼容
- MCP 服务（monitor/cls）可用于集成测试
