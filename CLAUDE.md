# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

All development conventions are in `CONTRIBUTING.md` and `AGENTS.md`. Read them
before committing, creating PRs, or making architectural changes.

## Quick Commands

```bash
# Backend quality gate (non-mutating, mirrors CI)
make verify

# Run tests with coverage
uv run pytest tests/ -v --cov=app --cov-report=term-missing

# Run a single test file
uv run pytest tests/unit/test_decision.py -v

# Run a single test by name
uv run pytest tests/ -k "test_tool_policy_gate_allows_readonly" -v

# Lint and format (mutating)
make fix

# Type check
uv run mypy app scripts --ignore-missing-imports

# Frontend quality gate
cd frontend && pnpm install --frozen-lockfile && pnpm lint && pnpm typecheck && pnpm build

# Database migrations
uv run alembic upgrade head              # apply
uv run alembic revision -m "description" # generate new migration

# Dev server with hot reload
make dev
```

## Architecture

### Dependency Injection

The project uses **constructor injection** from a centralized composition root.
`app/api/providers.py` defines `AppContainer` (singleton via `lru_cache`) with
`@cached_property` services. FastAPI `Depends()` wires them into route handlers.

`AppSettings` (frozen dataclass in `app/core/config.py`) is the configuration
interface. Components receive it via constructor, never import the global `config`
singleton directly. Production entry point: `AppSettings.from_env()`.

### Agent Runtime (Hexagonal Architecture)

`app/agent_runtime/ports.py` defines Protocol interfaces (`SceneStore`,
`AgentRunStore`, `ToolPolicyStore`). Infrastructure adapters implement them.

Core flow:
```text
AgentRuntime (runtime.py)
  -> AgentOrchestrator
    -> AgentDecisionRuntime (decision.py) -- LangGraph StateGraph
      -> DecisionProvider (DeterministicDecisionProvider or QwenDecisionProvider)
    -> ToolExecutor (tool_executor.py) -- policy-gated tool calls
    -> EvidenceAssessment -- validates tool results
    -> Synthesizer (synthesizer.py) -- builds final report
```

The decision graph is currently **single-pass** (evaluate_evidence -> END).
The config key `agent_decision_provider` switches between `"deterministic"`
(no LLM) and `"qwen"` (LLM-backed via DashScope).

### MCP Tool Servers

Two FastMCP servers in `mcp_servers/`:
- `monitor_server.py` (port 8004) -- simulated monitoring: CPU, memory, disk, process info
- `cls_server.py` (port 8003) -- Tencent Cloud CLS log queries

`app/infrastructure/tools/mcp_client.py` loads MCP tools with timeout-protected
fallback. `app/infrastructure/tools/registry.py` merges local + MCP tools per
scope (chat/diagnosis) with deduplication.

### Config Dual Source

Two config systems coexist:
- `app/config.py` -- Pydantic `BaseSettings` singleton (120+ fields, reads `.env`)
- `app/core/config.py` -- `AppSettings` frozen dataclass, `from_env()` bridges to the singleton

New code should use `AppSettings` via constructor injection. The global singleton
in `app/config.py` exists for backward compatibility.

### Task Dispatching

Dual-mode: `embedded` (in-process asyncio, default for dev) or `detached`
(Redis-backed worker process). Configured via `task_dispatcher_mode`.
The `worker` service in docker-compose runs the detached consumer.

### Data Layer

SQLModel + SQLAlchemy with Alembic. Key tables: `AgentRun`, `AgentEvent`,
`AgentFeedback`, `Workspace`, `Scene`, `SceneTool`, `ToolPolicy`, `KnowledgeBase`.
`UnitOfWork` in `app/platform/persistence/` provides explicit transaction boundaries.
Database uses psycopg3 with connection pool monitoring.

LangGraph checkpointing uses PostgreSQL via `DatabaseCheckpointSaver`
(`app/infrastructure/checkpoint_store.py`) with tables: `agent_checkpoints`,
`agent_checkpoint_writes`, `agent_checkpoint_blobs`.

### Frontend

Next.js 16 + React 19 + TypeScript 5.9 + Tailwind CSS 4 + shadcn/ui.
State: Zustand. E2E: Playwright (tests in `tests/e2e/`).

Browser components call local Next.js BFF route handlers, never FastAPI directly.
Backend API keys stay server-side. SSE uses custom POST-based streaming
(`parseSSE()` + `useEventStream()` hook), not EventSource GET.

### API Routing

Prefix: `/api/v1/` (canonical) with `/api/` backward-compat alias (hidden from
OpenAPI). Health check at `/health` (not under `/api/v1/`).

### Docker Compose

14 services, 4 profiles: default (core), vector-milvus, gateway (frontend+caddy),
observability (otel+prometheus+grafana+loki).

## PR Creation

When creating a pull request with `gh pr create`:

### Step 1: Read the diff

```bash
git diff main...HEAD --stat
git diff main...HEAD
git log main...HEAD --oneline
```

### Step 2: Write the body from the diff

NEVER copy `.github/pull_request_template.md` verbatim. Every section must
contain content derived from the actual changes.

**Summary** — 2-3 sentences naming the specific problem or feature:
- Good: "Add HMAC-based API key fingerprinting to replace plaintext key
  prefixes in audit logs"
- Bad: "Improve security" / "Harden runtime"

**Changes** — bullet list, each referencing a specific file or function:
- Good: "`app/security/auth.py` — replace `x_api_key[:8]` subject with HMAC
  fingerprint"
- Bad: "Updated auth module"

**Validation** — only check `[x]` for checks actually run.

**Risks** — concrete risk of THIS change:
- Good: "Low — auth subject identifiers change format; existing audit logs
  retain old format"
- Bad: "Operational risk: none"

If a section does not apply, write "N/A — ..." not the template placeholder.
