# Tasks: AI Native Agent Runtime

**Input**: specs/ai-native-runtime/
**Prerequisites**: plan.md (required), spec.md (required for user stories)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5)

---

## Phase 1: Foundation (Blocking Prerequisites)

**Purpose**: Core infrastructure that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [ ] T001 [P] Create BoundedReActLoop skeleton in `app/agent_runtime/loop.py`
  - Define loop interface: `run(goal, budget) -> LoopResult`
  - Implement step counter and budget checking
  - Initially only call DeterministicDecisionProvider
- [ ] T002 [P] Extract MetricsCollector from runtime.py to `app/agent_runtime/metrics_collector.py`
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
- [ ] T008 Implement assess phase (EvidenceAssessment) in `app/agent_runtime/evidence.py`
  - Assess tool output quality: strong/moderate/weak/insufficient/conflict/error
  - Evidence conflict detection (two tools contradict)
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

- [ ] T011 [P] Unit test: BoundedReActLoop budget enforcement in `tests/unit/test_loop.py`
  - Test step_budget prevents infinite loop
  - Test time_budget timeout
  - Test token_budget exceeded
- [ ] T012 [P] Unit test: EvidenceAssessment in `tests/unit/test_evidence.py`
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

- [ ] T014 Define DecisionProvider protocol in `app/agent_runtime/ports.py`
  - `decide(context: DecisionContext) -> AgentDecision`
  - `get_token_usage() -> TokenUsage`
  - `get_cost_estimate() -> float`
- [ ] T015 Refactor DeterministicDecisionProvider in `app/agent_runtime/decision.py`
  - Implement DecisionProvider protocol
  - Return TokenUsage(0, 0) (no LLM call)
- [ ] T016 Refactor QwenDecisionProvider in `app/agent_runtime/decision.py`
  - Implement DecisionProvider protocol
  - Call LLM, return real TokenUsage
  - Record reasoning_summary
- [ ] T017 Implement ProviderFactory in `app/agent_runtime/decision.py`
  - Create provider based on agent_decision_provider config
  - Support runtime switching (no restart needed)
- [ ] T018 Implement Provider Fallback in `app/agent_runtime/loop.py`
  - Qwen call fails -> auto-degrade to Deterministic
  - Record provider_fallback event
  - Notify frontend (SSE event)

**Checkpoint**: Both providers switchable at runtime, fallback reliable

### Tests

- [ ] T019 [P] Unit test: ProviderFactory creation and switching in `tests/unit/test_decision.py`
- [ ] T020 [P] Unit test: QwenDecisionProvider fallback in `tests/unit/test_decision.py`
  - Mock LLM failure -> verify degrade to deterministic

---

## Phase 4: US3 — AgentOps Real Metrics (P1)

**Goal**: Every run records real token/cost/latency
**Independent Test**: Execute run, verify agent_runs metrics are non-None JSON

### Implementation

- [ ] T021 Rewrite MetricsCollector.collect_run_metrics() in `app/agent_runtime/metrics_collector.py`
  - Collect token_usage from DecisionProvider (as JSON dict)
  - Collect tool_call latency from ToolExecutor
  - Calculate cost_estimate = prompt_cost + completion_cost + tool_output_cost
- [ ] T022 Integrate MetricsCollector into BoundedReActLoop in `app/agent_runtime/loop.py`
  - Record step_metrics at each step
  - Persist to database at run completion
- [ ] T023 Add cost_per_step to agent_events table
  - Each step's token/cost independently trackable

**Checkpoint**: AgentOps metrics fully trackable

### Tests

- [ ] T024 [P] Unit test: MetricsCollector.collect_run_metrics in `tests/unit/test_metrics.py`
  - Verify token_usage is non-empty JSON dict
  - Verify cost_estimate is non-empty JSON dict
  - Verify step_count matches actual steps

---

## Phase 5: US4 — Evidence Loop with Recovery (P2)

**Goal**: Insufficient evidence triggers recovery, no forged conclusions
**Independent Test**: Mock tool returning empty result, verify recovery path

### Implementation

- [ ] T025 Implement RecoveryManager in `app/agent_runtime/recovery.py`
  - Recovery strategies: retry_same_tool, try_alternative, downgrade_report, handoff
  - Select strategy based on evidence_quality
- [ ] T026 Implement ApprovalGate in `app/agent_runtime/approval.py`
  - change/destructive tools -> pending_approval
  - Wait for human approve/reject (with timeout)
  - Timeout -> auto-reject + handoff
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

- [ ] T035 Implement TraceCollector in `app/agent_runtime/trace_collector.py`
  - Each loop step produces OpenTelemetry span
  - Attributes: step_index, tool_name, evidence_quality, token_usage, cost
- [ ] T036 Integrate TraceCollector into BoundedReActLoop in `app/agent_runtime/loop.py`
- [ ] T037 [P] Update golden scenario eval tests in `tests/agent_scenarios/`
  - 6 golden scenarios all pass regression eval
- [ ] T038 Update CLAUDE.md and `docs/` architecture documentation

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

### Parallel Opportunities

- Phase 1: T001, T002, T003 can run in parallel
- Phase 2+3+4: Can run in parallel after Phase 1 (different files)
- Within each phase: tasks marked [P] can run in parallel

### MVP Checkpoint

After Phase 1 + Phase 2 + Phase 4:
- Agent executes bounded ReAct loop
- Real metrics recorded
- Can demonstrate to stakeholders

**Estimated MVP effort**: 4-6 days

### Full Delivery

All 7 phases:
- Complete AI-native runtime with recovery and feedback loop
- OpenTelemetry observability
- 6 golden scenarios passing

**Estimated full effort**: 9-13 days
