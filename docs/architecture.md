# Architecture

SmartSRE Copilot is an SRE Agent workbench with a FastAPI backend, Next.js BFF
frontend, PostgreSQL persistence, Redis-backed tasks, vector search, and
optional MCP tool integrations.

## Current Development Baseline

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

## Development Direction

- Move the platform middleware toward PostgreSQL + pgvector, Redis, MinIO,
  Caddy, and OpenTelemetry.
- Stabilize knowledge indexing, replay snapshots, and AgentOps metrics.
- Harden tool governance, approval flows, and API contracts.
- Introduce Decision Runtime contracts, deterministic providers, and LangGraph
  runtime hardening.
- Enable the native Agent decision runtime by default when the product and
  validation scope is complete.
