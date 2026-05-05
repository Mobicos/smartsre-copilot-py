# Architecture

SmartSRE Copilot is an SRE Agent workbench with a FastAPI backend, Next.js BFF
frontend, PostgreSQL persistence, Redis-backed tasks, vector search, and
optional MCP tool integrations.

## 1.3 Baseline

```text
Browser
  -> Next.js BFF
  -> FastAPI
      -> PostgreSQL
      -> Redis
      -> Milvus
      -> DashScope / Qwen
      -> MCP servers
```

## Core Boundaries

- Browser components call Next.js route handlers, not FastAPI directly.
- FastAPI owns authentication, persistence, Agent runtime, and tool governance.
- PostgreSQL is the system of record for runs, events, feedback, tasks, and
  policies.
- Redis is for background queues and short-lived state.
- Tool execution must go through ToolPolicyGate and ToolExecutor.
- MCP is the standard integration boundary for external observability systems.

## Native Agent Workbench

```text
Workspace
  -> Scene
  -> Goal
  -> Tool Policy
  -> Agent Runtime
  -> Tool Call
  -> Evidence
  -> Final Report
  -> Feedback
  -> Replayable Events
```

## Planned Evolution

- 1.4 moves the platform middleware toward PostgreSQL + pgvector, Redis, MinIO,
  Caddy, and OpenTelemetry.
- 1.5 stabilizes knowledge indexing, replay snapshots, and AgentOps metrics.
- 1.6 and 1.7 harden tool governance and API contracts.
- 1.8 and 1.9 introduce Decision Runtime contracts, providers, and LangGraph
  runtime release candidates.
- 2.0 enables LangGraph Decision Runtime by default.
