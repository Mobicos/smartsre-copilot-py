# SmartSRE Constitution

**Version**: 1.0.0 | **Ratified**: 2026-05-13 | **Last Amended**: 2026-05-13

## Core Principles

### I. Agent-First Architecture
All user value paths MUST go through Agent Runtime. Traditional CRUD is only
allowed for administrative features (users, config, permissions). Core diagnosis
paths MUST NOT bypass the Agent.

### II. Bounded Autonomy
Agents MUST operate within explicit step budget, token budget, and time budget.
Exceeding any budget MUST trigger recovery or handoff. Infinite loops are forbidden.
Hard defaults: max_steps=8, max_tokens=50000, max_time=120s.

### III. Observable Decisions
Every Agent decision MUST produce a traceable event. Decision traces without
observability MUST NOT enter production. Traces MUST cover: decision, tool_call,
evidence, approval, recovery, handoff.

### IV. Human-in-the-Loop Safety
High-risk tools (change/destructive) MUST halt at approval. Low-confidence
conclusions MUST be annotated with evidence source or trigger handoff.
Agents MUST NOT execute destructive operations without human approval.

### V. Evidence Grounding
All Agent conclusions MUST have evidence backing. Evidence sources: tool output,
knowledge citation, or explicitly marked as inference. Root cause conclusions
without evidence are forbidden.

### VI. Dual Provider Runtime
Decision Providers MUST support runtime switching via configuration.
Deterministic (no-LLM) and Qwen (LLM-backed) providers MUST share the same
interface contract. LLM unavailability MUST trigger automatic fallback.

### VII. Knowledge as Feedback Loop
User feedback MUST flow into knowledge: feedback -> badcase -> FAQ -> improved
interception. Knowledge entry MUST require human confirmation. Unconfirmed
knowledge MUST NOT enter the core knowledge base.

### VIII. Test-First for Agent
Agent behavior changes MUST have scenario evals written first (failing), then
implemented, then verified passing. Golden scenarios are the regression baseline.

## Quality Gates

Before any merge to main:

1. `make verify` passes (compile + lint + format + type + security + test)
2. Agent scenario eval passes (minimum 3 golden scenarios)
3. OpenTelemetry trace complete (decision + tool_call + evidence)
4. `token_usage` and `cost_estimate` fields are non-None in test runs
5. No high-risk tool executes without approval in tests

## Governance

This constitution supersedes all other development practices. Amendments require:
1. Documented rationale
2. Updated acceptance criteria
3. Migration plan for existing code

All PRs and reviews MUST verify compliance with these principles.
