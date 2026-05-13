# Data Model: AI Native Agent Runtime

**Date**: 2026-05-13
**Spec**: [spec.md](./spec.md)

## Existing Tables (Actual Schema)

### agent_runs

| Column | Type | Status | Description |
|--------|------|--------|-------------|
| run_id | VARCHAR | existing PK | Run identifier |
| workspace_id | VARCHAR | existing FK | Workspace |
| scene_id | VARCHAR | existing FK (nullable) | Scene |
| session_id | VARCHAR | existing | Session |
| status | VARCHAR | existing | running/completed/failed/handoff |
| goal | TEXT | existing | Agent diagnosis goal |
| final_report | TEXT | existing | Final report content |
| error_message | TEXT | existing | Error message if failed |
| runtime_version | VARCHAR | existing | Runtime version |
| trace_id | VARCHAR | existing | OpenTelemetry trace ID |
| model_name | VARCHAR | existing | LLM model name |
| decision_provider | VARCHAR | existing | Provider: deterministic/qwen |
| step_count | INTEGER | existing | Loop steps executed |
| tool_call_count | INTEGER | existing | Total tool calls |
| latency_ms | INTEGER | existing | Total latency |
| error_type | VARCHAR | existing | Error classification |
| approval_state | VARCHAR | existing | Approval state |
| retrieval_count | INTEGER | existing | Knowledge retrieval count |
| token_usage | JSON (dict) | existing | Token breakdown (prompt/completion/tool) |
| cost_estimate | JSON (dict) | existing | Cost breakdown |
| handoff_reason | TEXT | existing | Handoff reason |
| created_at | TIMESTAMP | existing | Run start time |
| updated_at | TIMESTAMP | existing | Last update |

**Note**: token_usage and cost_estimate are JSON dicts, not simple integers.
They already exist. The task is to make MetricsCollector write real values.

### agent_events

| Column | Type | Status | Description |
|--------|------|--------|-------------|
| id | BIGINT | existing PK (autoincrement) | Event ID |
| run_id | VARCHAR | existing FK | FK to agent_runs |
| event_type | VARCHAR | existing | decision/tool_call/evidence/approval/recovery/handoff/final_report |
| stage | VARCHAR | existing | Event stage |
| message | TEXT | existing | Event message |
| payload | TEXT | existing | Event-specific data (JSON string) |
| created_at | TIMESTAMP | existing | Event timestamp |

### New columns needed (Alembic migration required)

| Column | Type | Table | Description |
|--------|------|-------|-------------|
| evidence_quality | VARCHAR(20) | agent_events | strong/moderate/weak/insufficient/conflict/error |
| recovery_action | VARCHAR(50) | agent_events | retry_same_tool/try_alternative/downgrade_report/handoff |
| step_index | INTEGER | agent_events | Which loop step this event belongs to |
| token_usage | INTEGER | agent_events | Tokens consumed in this step |
| cost_estimate | DOUBLE PRECISION | agent_events | Cost of this step |

### agent_feedback

| Column | Type | Status | Description |
|--------|------|--------|-------------|
| feedback_id | VARCHAR | existing PK | Feedback ID |
| run_id | VARCHAR | existing FK | FK to agent_runs |
| rating | VARCHAR | existing | useful/useless/corrected |
| comment | TEXT | existing | User comment |
| created_at | TIMESTAMP | existing | Feedback timestamp |

### New columns needed (Alembic migration required)

| Column | Type | Table | Description |
|--------|------|-------|-------------|
| correction | TEXT | agent_feedback | User-provided correction text |
| badcase_flag | BOOLEAN | agent_feedback | Whether this is a badcase |
| original_report | TEXT | agent_feedback | Agent's original report for comparison |

## New Entities (In-Memory, Not Persisted)

### DecisionContext

Built during observe phase, passed to DecisionProvider:

```python
@dataclass
class DecisionContext:
    goal: str
    step_index: int
    budget: RuntimeBudget
    history: list[AgentDecision]
    evidence: list[EvidenceItem]
    available_tools: list[ToolSchema]
    knowledge_context: list[KnowledgeItem]
    confidence: float
```

### AgentDecision

Output of decide phase:

```python
@dataclass
class AgentDecision:
    action_type: ActionType  # observe/call_tool/ask_approval/recover/final_report/handoff
    tool_name: str | None
    arguments: dict[str, Any] | None
    reasoning_summary: str
    confidence: float
    rationale: str
    expected_evidence: str
```

### ToolResult

Output of act phase:

```python
@dataclass
class ToolResult:
    tool_name: str
    success: bool
    output: Any
    latency_ms: float
    error: str | None
    token_usage: TokenUsage | None
```

### EvidenceItem

Output of assess phase (replaces minimal version in state.py):

```python
class EvidenceQuality(Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"
    CONFLICT = "conflict"
    ERROR = "error"

@dataclass
class EvidenceItem:
    quality: EvidenceQuality
    content: str
    source_tool: str
    step_index: int
    raw_output: Any
    confidence: float
```

### RecoveryAction

Output of recovery phase:

```python
class RecoveryStrategy(Enum):
    RETRY_SAME_TOOL = "retry_same_tool"
    TRY_ALTERNATIVE = "try_alternative"
    DOWNGRADE_REPORT = "downgrade_report"
    HANDOFF = "handoff"

@dataclass
class RecoveryAction:
    strategy: RecoveryStrategy
    reason: str
    next_step: str
    evidence_so_far: list[EvidenceItem]
```

### RuntimeBudget

```python
@dataclass
class RuntimeBudget:
    max_steps: int = 8
    max_tokens: int = 50000
    max_time_seconds: float = 120.0
    remaining_steps: int = 8
    remaining_tokens: int = 50000
    remaining_time: float = 120.0
    total_tokens_used: int = 0
    total_cost: float = 0.0
```

### LoopResult

```python
class LoopTerminationReason(Enum):
    GOAL_ACHIEVED = "goal_achieved"
    STEP_BUDGET_EXCEEDED = "step_budget_exceeded"
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"
    TIME_BUDGET_EXCEEDED = "time_budget_exceeded"
    ALL_TOOLS_FAILED = "all_tools_failed"
    RECOVERY_EXHAUSTED = "recovery_exhausted"

@dataclass
class LoopResult:
    termination_reason: LoopTerminationReason
    final_report: FinalReportContract | None
    evidence: list[EvidenceItem]
    decisions: list[AgentDecision]
    events: list[AgentEvent]
    metrics: RunMetrics
```

### TokenUsage

```python
@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    tool_output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""

    def __post_init__(self):
        self.total_tokens = self.prompt_tokens + self.completion_tokens
```

### RunMetrics

```python
@dataclass
class RunMetrics:
    token_usage: TokenUsage
    cost_estimate: float
    latency_ms: float
    step_count: int
    tool_call_count: int
    recovery_count: int
    provider: str
```
