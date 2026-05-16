# Tasks: AI Native Agent Runtime

**Input**: specs/ai-native-runtime/
**Prerequisites**: plan.md (required), spec.md (required for user stories)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5)

---

## Current Implementation Snapshot (2026-05-15)

The checklist below remains the target work queue. Current `main` is not a blank
slate, so future agents should treat these statuses as the baseline before
editing code:

- Implemented: Native Agent APIs, replay APIs, approval APIs, feedback APIs,
  badcase review / promotion APIs, run-level metrics columns, deterministic/Qwen
  provider fallback, text-based cross-session memory, extracted
  `BoundedReActLoop` skeleton, extracted `EvidenceAssessor`, extracted
  `ApprovalGate`, extracted `RecoveryManager`, extracted `TraceCollector`, and
  frontend workbench coverage for memory, badcase, approval, and scenario flows.
- Partial: runtime loop orchestration, recovery strategy selection, replay
  metrics, and memory injection exist but still need hardening. Metrics
  collection has been extracted to
  `app/agent_runtime/metrics_collector.py`; evidence classification has been
  extracted to `app/agent_runtime/evidence.py`, but conflict detection is still
  pending.
- Not started: proactive monitor, collaborative intervention, pgvector memory
  embeddings, badcase clustering, FAQ candidates, and per-step `agent_events`
  metric columns.
- Private planning files: `PLAN.md` and `specs/ai-native-runtime/plan.md` are
  local-only and must not be committed.

## Phase 1: Foundation (Blocking Prerequisites)

**Purpose**: Core infrastructure that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T001 [P] Create BoundedReActLoop skeleton in `app/agent_runtime/loop.py`
  - Define loop interface: `run(goal, budget) -> LoopResult`
  - Implement step counter and budget checking
  - Initially only call DeterministicDecisionProvider
- [x] T002 [P] Extract MetricsCollector from runtime.py to `app/agent_runtime/metrics_collector.py`
  - Current class lives inline in runtime.py (line 169)
  - Accept token_usage (JSON), cost_estimate (JSON), latency_ms, step_count
  - Persist to agent_runs table with real values (no more None)
- [ ] T003 [P] Add Alembic migration for agent_events + agent_feedback new columns
  - agent_events: evidence_quality, recovery_action, step_index, token_usage, cost_estimate
  - agent_feedback: correction, badcase_flag, original_report
  - Note: agent_runs already has token_usage (JSON), cost_estimate (JSON), step_count, decision_provider
- [ ] T004 Modify AgentRuntime to use BoundedReActLoop in `app/agent_runtime/runtime.py`
  - Replace 400+ line monolith `_run_orchestration` method
  - Keep external interface unchanged (SSE events compatible)

**Checkpoint**: Agent executes via new loop, metrics are non-None

---

## Phase 2: US1 — Bounded ReAct Diagnosis (P1) [MVP]

**Goal**: Agent executes bounded ReAct loop, produces final_report
**Independent Test**: Initiate diagnosis, verify >=2 tool calls + final_report

### Implementation

- [ ] T005 Implement observe phase in `app/agent_runtime/loop.py`
  - Collect goal, history, available_tools, context
  - Build DecisionContext
- [ ] T006 Implement decide phase in `app/agent_runtime/loop.py`
  - Call DecisionProvider.decide(context)
  - Validate decision (tool exists? params valid?)
  - Invalid decision -> recovery
- [ ] T007 Implement act phase in `app/agent_runtime/loop.py`
  - Call ToolExecutor.execute(decision)
  - Apply step_timeout (default 30s)
  - Timeout -> tool_failure event -> recovery
- [x] T008 Implement assess phase (EvidenceAssessment) in `app/agent_runtime/evidence.py`
  - Assess tool output quality: strong/moderate/weak/insufficient/conflict/error
  - Evidence conflict detection (two tools contradict)
  - Status: strong/partial/weak/empty/conflicting/error classification exists;
    runtime final-report path checks aggregated conflicts
- [ ] T009 Implement final_report phase in `app/agent_runtime/loop.py`
  - Call Synthesizer.synthesize(evidence_list)
  - Produce FinalReportContract (verified_facts + inferences)
  - Generate EVENT_FINAL_REPORT
- [ ] T010 Implement loop termination conditions in `app/agent_runtime/loop.py`
  - step_budget reached -> bounded_report
  - goal achieved (confidence > threshold) -> final_report
  - all tools failed -> handoff_summary
  - time_budget exceeded -> bounded_report

**Checkpoint**: Agent executes complete bounded ReAct loop

### Tests

- [x] T011 [P] Unit test: BoundedReActLoop budget enforcement in `tests/unit/test_runtime_foundation.py`
  - Test step_budget prevents infinite loop
  - Test time_budget timeout
  - Test token_budget exceeded
- [x] T012 [P] Unit test: EvidenceAssessment in `tests/unit/test_evidence.py`
  - Test strong/moderate/weak/insufficient/conflict/error assessment
  - Test evidence conflict detection
- [ ] T013 Integration test: Full loop execution in `tests/integration/test_react_loop.py`
  - Mock tool outputs, verify loop produces final_report
  - Mock tool timeout, verify recovery path

---

## Phase 3: US2 — Dual Provider Runtime (P1)

**Goal**: Deterministic and Qwen providers switchable at runtime
**Independent Test**: Change config, restart, verify both providers produce decisions

### Implementation

- [x] T014 Define DecisionProvider protocol in `app/agent_runtime/ports.py`
  - `decide(context: DecisionContext) -> AgentDecision`
  - `get_token_usage() -> TokenUsage`
  - `get_cost_estimate() -> float`
- [x] T015 Refactor DeterministicDecisionProvider in `app/agent_runtime/decision.py`
  - Implement DecisionProvider protocol
  - Return TokenUsage(0, 0) (no LLM call)
  - Status: deterministic provider now implements the port with zero token/cost metrics
- [x] T016 Refactor QwenDecisionProvider in `app/agent_runtime/decision.py`
  - Implement DecisionProvider protocol
  - Call LLM, return real TokenUsage
  - Record reasoning_summary
- [x] T017 Implement ProviderFactory in `app/agent_runtime/decision.py`
  - Create provider based on agent_decision_provider config
  - Support runtime switching (no restart needed)
- [ ] T018 Implement Provider Fallback in `app/agent_runtime/loop.py`
  - Qwen call fails -> auto-degrade to Deterministic
  - Record provider_fallback event
  - Notify frontend (SSE event)
  - Status: loop-level fallback and consumable fallback event cache implemented; runtime/SSE emission remains pending

**Checkpoint**: Both providers switchable at runtime, fallback reliable

### Tests

- [x] T019 [P] Unit test: ProviderFactory creation and switching in `tests/unit/test_decision.py`
  - Status: deterministic/qwen provider factory creation is covered in `tests/unit/test_decision_provider_ports.py`
- [x] T020 [P] Unit test: QwenDecisionProvider fallback in `tests/unit/test_decision.py`
  - Mock LLM failure -> verify degrade to deterministic
  - Status: loop fallback is covered in `tests/unit/test_runtime_foundation.py`; factory-created Qwen runtime fallback metrics are covered in `tests/unit/test_decision_provider_ports.py`

---

## Phase 4: US3 — AgentOps Real Metrics (P1)

**Goal**: Every run records real token/cost/latency
**Independent Test**: Execute run, verify agent_runs metrics are non-None JSON

### Implementation

- [x] T021 Rewrite MetricsCollector.collect_run_metrics() in `app/agent_runtime/metrics_collector.py`
  - Collect token_usage from DecisionProvider (as JSON dict)
  - Collect tool_call latency from ToolExecutor
  - Calculate cost_estimate = prompt_cost + completion_cost + tool_output_cost
  - Status: collector now exposes `collect_run_metrics()`, prefers provider token/cost events, aggregates tool execution latency, and falls back to heuristic estimates
- [ ] T022 Integrate MetricsCollector into BoundedReActLoop in `app/agent_runtime/loop.py`
  - Record step_metrics at each step
  - Persist to database at run completion
  - Status: `BoundedReActLoop` now records per-step token/cost metrics in `LoopStep`; runtime/run-store persistence remains pending
- [ ] T023 Add cost_per_step to agent_events table
  - Each step's token/cost independently trackable

**Checkpoint**: AgentOps metrics fully trackable

### Tests

- [x] T024 [P] Unit test: MetricsCollector.collect_run_metrics in `tests/unit/test_metrics.py`
  - Verify token_usage is non-empty JSON dict
  - Verify cost_estimate is non-empty JSON dict
  - Verify step_count matches actual steps
  - Status: provider metrics and tool latency aggregation are covered in `tests/unit/test_metrics.py`

---

## Phase 5: US4 — Evidence Loop with Recovery (P2)

**Goal**: Insufficient evidence triggers recovery, no forged conclusions
**Independent Test**: Mock tool returning empty result, verify recovery path

### Implementation

- [ ] T025 Implement RecoveryManager in `app/agent_runtime/recovery.py`
  - Recovery strategies: retry_same_tool, try_alternative, downgrade_report, handoff
  - Select strategy based on evidence_quality
  - Status: basic strategy selection and failure boundary extracted; loop integration pending
- [ ] T026 Implement ApprovalGate in `app/agent_runtime/approval.py`
  - change/destructive tools -> pending_approval
  - Wait for human approve/reject (with timeout)
  - Timeout -> auto-reject + handoff
  - Status: approval pause gate extracted; resume / expiry remains in application services
- [ ] T027 Integrate RecoveryManager into BoundedReActLoop in `app/agent_runtime/loop.py`
  - assess phase finds insufficient -> recovery
  - recovery attempt still insufficient -> bounded_report or handoff
- [ ] T028 Implement HandoffSummary generation in `app/agent_runtime/synthesizer.py`
  - Collected evidence + failed tools + suggested next steps
  - Send via SSE to frontend

**Checkpoint**: Agent recovers from anomalies, no forged conclusions

### Tests

- [ ] T029 [P] Unit test: RecoveryManager strategy selection in `tests/unit/test_recovery.py`
- [ ] T030 Integration test: Full recovery path in `tests/integration/test_recovery.py`
  - Mock empty result -> verify retry -> verify downgrade_report
  - Mock consecutive failures -> verify handoff

---

## Phase 6: US5 — Feedback → Knowledge Loop (P3)

**Goal**: User feedback crystallizes into knowledge, forming closed loop
**Independent Test**: Submit feedback, verify badcase pool has new record

### Implementation

- [ ] T031 Implement FeedbackCollector in `app/application/feedback_service.py`
  - Accept rating + correction
  - Write to agent_feedback table (with badcase_flag, correction, original_report)
  - Set badcase_flag based on rating
- [ ] T032 Implement BadcaseClusterer in `app/application/badcase_service.py`
  - Cluster badcases by similarity (embedding similarity)
  - Accumulate >=5 -> generate FAQ candidate
- [ ] T033 Implement FAQApprovalWorkflow
  - FAQ candidate -> human confirm -> persist to knowledge base
  - After confirmation, link to knowledge base

**Checkpoint**: Feedback loop operational

### Tests

- [ ] T034 [P] Integration test: feedback -> badcase -> FAQ flow in `tests/integration/test_feedback_loop.py`

---

## Phase 7: Observability & Polish

- [x] T035 Implement TraceCollector in `app/agent_runtime/trace_collector.py`
  - Each loop step produces OpenTelemetry span
  - Attributes: step_index, tool_name, evidence_quality, token_usage, cost
  - Status: optional span collector extracted; tool-call and loop-step spans wired
- [x] T036 Integrate TraceCollector into BoundedReActLoop in `app/agent_runtime/loop.py`
- [ ] T037 [P] Update golden scenario eval tests in `tests/agent_scenarios/`
  - 6 golden scenarios all pass regression eval
- [ ] T038 Update CLAUDE.md and `docs/` architecture documentation

---

## Phase 8: US6 — Proactive Monitor (P2)

**Goal**: Agent 主动探测环境异常，自动触发诊断 run
**Independent Test**: Mock 异常指标，验证自动创建 run + 告警推送

### Implementation

- [ ] T039 [P] Implement ProactiveMonitor in `app/agent_runtime/proactive.py`
  - 按 configurable interval 周期执行探测
  - 调用 MCP 工具获取环境指标（CPU、内存、响应时间等）
  - 异常判定：指标超过阈值或偏离基线
- [ ] T040 [P] Implement AlertDeduplicator in `app/agent_runtime/proactive.py`
  - 指标 + 时间窗口去重（suppress_interval 可配置，默认 30min）
  - 去重状态持久化到 Redis（跨进程共享）
- [ ] T041 Implement AutoDiagnosis trigger in `app/agent_runtime/proactive.py`
  - 异常检测到后自动创建 AgentRun，goal 为"异常指标根因分析"
  - 复用 BoundedReActLoop 执行诊断
  - run metadata 标记 `source=proactive`
- [ ] T042 Implement ProactiveAlert push via SSE in `app/api/routes/agent.py`
  - 新增 SSE 事件类型 `EVENT_PROACTIVE_ALERT`
  - 推送内容：异常指标摘要 + run_id + 跳转链接
  - 前端新增 alert toast / notification panel
- [ ] T043 Implement degraded fallback in `app/agent_runtime/proactive.py`
  - 外部监控数据源不可用时，降级到本地 MCP monitor_server 探测
  - 记录 degraded_event

### Tests

- [ ] T044 [P] Unit test: AlertDeduplicator suppression logic in `tests/unit/test_proactive.py`
  - Test: same metric within suppress_interval -> suppressed
  - Test: same metric after suppress_interval -> not suppressed
  - Test: different metric within interval -> not suppressed
- [ ] T045 Integration test: full proactive flow in `tests/integration/test_proactive.py`
  - Mock MCP tool returning abnormal metrics -> verify auto run created
  - Mock MCP tool failure -> verify degraded path

---

## Phase 9: US7 — Cross-session Memory (P2)

**Goal**: Agent 拥有跨会话记忆，新 run 自动检索相关历史结论
**Independent Test**: 两次相似 run，验证第二次引用了第一次的结论

### Implementation

- [ ] T046 [P] Implement MemoryStore in `app/infrastructure/memory_store.py`
  - 接口：`store(run_id, conclusion, embedding, metadata)`
  - 接口：`retrieve(query_embedding, top_k) -> list[MemoryItem]`
  - 存储：复用 pgvector（`knowledge_chunks` 表扩展或新建 `agent_memory` 表）
  - Alembic migration: 新建 `agent_memory` 表（run_id, conclusion_text, embedding vector(1024), confidence, validation_count, created_at）
- [ ] T047 [P] Implement MemoryExtractor in `app/agent_runtime/memory_extractor.py`
  - run 结束时从 final_report 提取关键结论（根因、证据、解决方案）
  - 调用 text-embedding-v4 生成向量
  - 写入 MemoryStore
- [ ] T048 Implement MemoryRetriever in `app/agent_runtime/memory_retriever.py`
  - 新 run 启动时，将 goal 向量化，检索 top-k=5 相关历史结论
  - 相似度阈值：cosine > 0.7 才注入 context
  - 返回 `list[MemoryItem]`（含 run_id, conclusion, similarity, confidence）
- [ ] T049 Integrate memory into BoundedReActLoop in `app/agent_runtime/loop.py`
  - observe 阶段调用 MemoryRetriever，历史结论注入 DecisionContext
  - 历史结论附带 `confidence_boost`：被后续 run 验证过的结论权重提升
  - MemoryRetriever 失败时降级（不阻塞主流程）
- [ ] T050 Implement MemoryValidator in `app/agent_runtime/memory_store.py`
  - 当前 run 的结论验证了某历史结论时，`validation_count += 1`
  - confidence = base_confidence * (1 + 0.1 * validation_count)

### Tests

- [ ] T051 [P] Unit test: MemoryStore retrieve with similarity threshold in `tests/unit/test_memory.py`
  - Test: high similarity -> returned
  - Test: below threshold -> not returned
  - Test: empty store -> empty list
- [ ] T052 [P] Unit test: MemoryExtractor from final_report in `tests/unit/test_memory.py`
  - Test: extract root cause, evidence, solution from structured report
- [ ] T053 Integration test: full memory cycle in `tests/integration/test_memory.py`
  - Store conclusion from run #1 -> retrieve in run #2 -> verify context injection

---

## Phase 10: US8 — Collaborative Intervention (P3)

**Goal**: 人工可在 Agent 执行过程中随时介入，修改决策和计划
**Independent Test**: Agent 执行中注入额外证据，验证下一步决策体现

### Implementation

- [ ] T054 [P] Define InterventionAPI in `app/api/routes/agent.py`
  - `POST /api/v1/agent/runs/{run_id}/intervene`
  - Body: `{ type: "inject_evidence" | "replace_tool_call" | "modify_goal", payload: ... }`
  - 校验：run 必须处于 `running` 状态
- [ ] T055 [P] Implement InterventionStore in `app/platform/persistence/repositories.py`
  - 写入 `agent_events` 表，event_type = `intervention`
  - 持久化 intervention 类型和 payload
- [ ] T056 Implement InterventionBridge in `app/agent_runtime/intervention.py`
  - BoundedReActLoop 每步 observe 前检查 pending interventions
  - `inject_evidence`: 证据追加到 DecisionContext.extra_evidence
  - `replace_tool_call`: 覆盖当前 step 的 AgentDecision
  - `modify_goal`: 更新 run.goal（需人工确认）
  - 所有 intervention 记录到 agent_events
- [ ] T057 Implement low-confidence auto-handoff in `app/agent_runtime/loop.py`
  - 连续 N 步（default=3）置信度 < 0.3 时，Agent 自动暂停
  - 发出 `EVENT_HUMAN_HANDOFF` SSE 事件，携带已收集证据 + 失败原因
  - 等待人工通过 InterventionAPI 注入指导或替换工具
  - 超时（default=120s）未收到干预 -> 产出 bounded_report
- [ ] T058 [P] Add frontend intervention controls in `frontend/components/agent/`
  - Agent 运行中显示"注入证据"和"替换工具"按钮
  - 人工干预后实时反映到 Agent 事件时间线
  - handoff 状态显示等待提示 + 超时倒计时

### Tests

- [ ] T059 [P] Unit test: InterventionBridge injection in `tests/unit/test_intervention.py`
  - Test: inject_evidence -> DecisionContext.extra_evidence contains payload
  - Test: replace_tool_call -> AgentDecision overwritten
  - Test: intervention recorded as agent_event
- [ ] T060 Integration test: collaborative flow in `tests/integration/test_intervention.py`
  - Start run -> inject evidence mid-execution -> verify next decision uses evidence
  - 3 low-confidence steps -> verify auto-handoff triggered

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundation)**: No dependencies - can start immediately
- **Phase 2 (US1 ReAct Loop)**: Depends on Phase 1
- **Phase 3 (US2 Dual Provider)**: Depends on Phase 1
- **Phase 4 (US3 Metrics)**: Depends on Phase 1
- **Phase 5 (US4 Recovery)**: Depends on Phase 2 (US1)
- **Phase 6 (US5 Feedback)**: Depends on Phase 4 (US3)
- **Phase 7 (Observability)**: Depends on all above
- **Phase 8 (US6 Proactive Monitor)**: Depends on Phase 2 (US1), Phase 4 (US3)
- **Phase 9 (US7 Cross-session Memory)**: Depends on Phase 1 (Foundation), Phase 3 (US2)
- **Phase 10 (US8 Collaborative Intervention)**: Depends on Phase 2 (US1), Phase 5 (US4)

### Parallel Opportunities

- Phase 1: T001, T002, T003 can run in parallel
- Phase 2+3+4: Can run in parallel after Phase 1 (different files)
- Phase 8+9: Can run in parallel after their dependencies (different files)
- Within each phase: tasks marked [P] can run in parallel

### MVP Checkpoint

After Phase 1 + Phase 2 + Phase 4:
- Agent executes bounded ReAct loop
- Real metrics recorded
- Can demonstrate to stakeholders

**Estimated MVP effort**: 4-6 days

### Full Delivery

All 10 phases:
- Complete AI-native runtime with recovery and feedback loop
- OpenTelemetry observability
- Proactive monitoring and cross-session memory
- Collaborative intervention support
- 8 golden scenarios passing

**Estimated full effort**: 14-18 days
