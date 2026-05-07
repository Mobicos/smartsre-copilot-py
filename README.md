# SmartSRE Copilot

> AI-powered SRE assistant with knowledge-grounded chat, AIOps diagnosis, and
> native agent workbench.

[English](README.md) | [简体中文](README.zh-CN.md)

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic-orange.svg)](https://www.langchain.com/langgraph)
[![Next.js](https://img.shields.io/badge/Next.js-Frontend-black.svg)](https://nextjs.org/)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![CI](https://github.com/Mobicos/SmartSRE-Copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/Mobicos/SmartSRE-Copilot/actions/workflows/ci.yml)

## Overview

SmartSRE Copilot is a development-stage Native Agent Workbench for building an
internal SRE assistant. The backend is a FastAPI service with LangChain/
LangGraph agents, DashScope/Qwen models, PostgreSQL persistence, Redis-backed
background tasks, and Milvus vector search. The frontend is a modern Next.js app
that talks to the backend through server-side route handlers.

Core capabilities:

- Knowledge-grounded chat over uploaded `.txt` and `.md` documents.
- Streaming chat responses and persisted conversation history.
- Background indexing pipeline with retryable tasks.
- Plan-Execute-Replan AIOps diagnosis workflow.
- Native Agent workspace, scene, tool policy, trajectory replay, and feedback
  APIs.
- Optional MCP tool integration for external logs, metrics, and alert systems.

## Project Status

SmartSRE Copilot is an early open source project in active development. It is
suitable for local development, internal evaluation, and controlled prototype
deployments. Public version tags, GitHub publication artifacts, package
publication, and container publication are intentionally disabled while core
Agent capabilities, product flows, and validation coverage are still being
completed.

## Architecture

```text
Browser
  |
  v
Next.js frontend (frontend/)
  |
  | server-side route handlers / BFF
  v
FastAPI backend (app/)
  |
  +-- Chat / RAG ----------------> Qwen Chat model
  |                                + retrieve_knowledge tool
  |                                + optional MCP tools
  |
  +-- Upload / indexing ---------> Redis queue
  |                                + worker
  |                                + DashScope embeddings
  |                                + Milvus collection: biz
  |
  +-- Native Agent diagnosis ----> AgentRuntime
  |                                + ToolCatalog / ToolPolicy / ToolExecutor
  |                                + trajectory events
  |                                + optional MCP tools
  |
  +-- Persistence ---------------> PostgreSQL
```

## Tech Stack

Backend:

- FastAPI, Pydantic Settings, Server-Sent Events
- LangChain, LangGraph, Qwen via DashScope
- PostgreSQL, Alembic, Redis, Milvus
- MCP client support for external tool servers
- Native Agent runtime, tool policy, scene, and trajectory persistence

Frontend:

- Next.js, React, TypeScript
- Server-side API route handlers as a BFF layer
- pnpm lockfile committed for reproducible frontend installs

## Repository Layout

```text
app/              FastAPI backend, agents, services, persistence
alembic/          PostgreSQL schema migrations
frontend/         Next.js frontend application
mcp_servers/      Local/mock MCP server examples
tests/            Backend tests
aiops-docs/       Sample operational documents
uploads/          Local uploaded files, ignored by Git
data/             Local data files, ignored by Git
volumes/          Docker service data, ignored by Git
```

## Data Ownership

Local application data stays local unless you explicitly connect external tools.

- Uploaded files are stored under `uploads/`.
- Chat history, task status, audit logs, and AIOps run events are stored in
  PostgreSQL.
- Native Agent workspaces, scenes, tool policies, trajectories, and feedback are
  stored in PostgreSQL.
- Document vectors are stored in Milvus.
- DashScope receives prompts and embedding inputs required for model calls.
- MCP tools are optional. A Tencent Cloud CLS MCP server queries Tencent CLS
  data, not local Postgres or Milvus data.

## Prerequisites

- Python `3.11+`
- `uv` for Python dependency management
- Docker Desktop, OrbStack, Colima, or another Docker runtime
- Node.js and `pnpm` for frontend development
- DashScope API key

```bash
python --version
uv --version
docker --version
node --version
pnpm --version
```

## Quick Start

### 1. Backend Environment

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
cp .env.example .env
```

Edit `.env` and set at least:

```env
DASHSCOPE_API_KEY=your_dashscope_api_key
APP_API_KEY=replace_with_a_secure_key
ENVIRONMENT=dev
```

### 2. Start Infrastructure

**Option A: Full Docker Stack (recommended for testing)**

```bash
docker compose up -d --build
```

This starts all services: PostgreSQL (5432), Redis (6379), Milvus (19530), Attu
(8000), MinIO (9000/9001), migrations, backend app (9900), and worker.

**Option B: Local Development (recommended for development)**

Use `docker-compose.yml` as the shared template, then copy it to an ignored
`docker-compose.local.yml` for personal machine overrides. This keeps one source
of truth for the project compose stack while still letting each developer change
ports, volumes, or service scope locally.

1. Copy the shared compose template:

   ```bash
   cp docker-compose.yml docker-compose.local.yml
   ```

1. Edit `docker-compose.local.yml` for your machine.

   Common local changes:

   - Change exposed ports if PostgreSQL, Redis, Milvus, Attu, or MinIO conflict
     with services already running on your machine.
   - Remove or comment out `app`, `worker`, and `migrate` if you prefer running
     Python locally with `uv`.
   - Keep service names such as `postgres`, `redis`, and `standalone` unchanged
     if other compose services still depend on them.

1. Start the local compose stack:

   ```bash
   docker compose -f docker-compose.local.yml up -d
   ```

   If you only need infrastructure for local Python development, start those
   services directly:

   ```bash
   docker compose -f docker-compose.local.yml up -d postgres redis standalone attu minio
   ```

1. Update your `.env` to match your local exposed ports.

   Example when local ports are shifted to avoid conflicts:

   ```env
   POSTGRES_DSN=postgresql://smartsre:smartsre@localhost:5433/smartsre
   REDIS_URL=redis://localhost:6380/0
   MILVUS_HOST=localhost
   MILVUS_PORT=19531
   ```

1. Run backend and frontend locally with `uv` and `pnpm` (see steps 3-5 below).

**Note**: `docker-compose.local.yml` is ignored by Git and should be treated as
local-only configuration. Do not commit personal port mappings, local paths, or
machine-specific service deletions.

### 3. Run Database Migrations

```bash
uv run alembic upgrade head
```

### 4. Run Backend Locally

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 9900
```

If `TASK_DISPATCHER_MODE=detached`, start the indexing worker in another
terminal:

```bash
uv run python -m app.worker
```

### 5. Run Frontend Locally

```bash
cd frontend
pnpm install --frozen-lockfile
cp .env.example .env.local
pnpm dev
```

Default frontend backend target:

```text
SMARTSRE_BACKEND_URL=http://localhost:9900
```

If backend API key auth is enabled, set this only in `frontend/.env.local`:

```env
SMARTSRE_API_KEY=your_backend_api_key
```

Do not expose backend secrets through `NEXT_PUBLIC_*`.

### 6. Open the Services

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend API: [http://localhost:9900](http://localhost:9900)
- Backend docs: [http://localhost:9900/docs](http://localhost:9900/docs)
- Health check: [http://localhost:9900/health](http://localhost:9900/health)
- Attu, if using default compose: [http://localhost:8000](http://localhost:8000)

## Configuration

Backend settings are defined in `app/config.py` and loaded from `.env`.

Key backend variables:

- `ENVIRONMENT`: `dev`, `prod`, or `production`
- `DEBUG`: enable development behavior
- `HOST`, `PORT`: backend bind address
- `CORS_ALLOWED_ORIGINS`: explicit allowlist for browser origins
- `APP_API_KEY` or `API_KEYS_JSON`: API key based access control
- `DASHSCOPE_API_KEY`: DashScope model access
- `DASHSCOPE_MODEL`, `RAG_MODEL`: chat models
- `DASHSCOPE_EMBEDDING_MODEL`: embedding model
- `POSTGRES_DSN`: PostgreSQL DSN
- `REDIS_URL`: Redis connection string
- `TASK_QUEUE_BACKEND`: `redis` or `database`
- `TASK_DISPATCHER_MODE`: `embedded` or `detached`
- `MILVUS_HOST`, `MILVUS_PORT`: vector database connection
- `RAG_TOP_K`: retrieval result count
- `CHUNK_MAX_SIZE`, `CHUNK_OVERLAP`: document splitting
- `MCP_CLS_TRANSPORT`, `MCP_CLS_URL`: optional CLS MCP server
- `MCP_MONITOR_TRANSPORT`, `MCP_MONITOR_URL`: optional monitor MCP server
- `MCP_TOOLS_LOAD_TIMEOUT_SECONDS`: tool discovery timeout

Production guidance:

- Set `ENVIRONMENT=prod` or `ENVIRONMENT=production`.
- Configure explicit `CORS_ALLOWED_ORIGINS`; do not use `*`.
- Configure `APP_API_KEY` or `API_KEYS_JSON`.
- Keep `.env` out of Git.
- Prefer managed PostgreSQL, Redis, and Milvus/Zilliz for production.

## MCP Integration

MCP is optional. The application works without MCP for knowledge-base chat and
document RAG. AIOps workflows can use MCP tools when external log, metrics, and
alert systems are configured.

Recommended practices:

- Use local or internal self-hosted MCP servers for development and production.
- Treat cloud-hosted MCP SSE endpoints as quick evaluation links unless you have
  clear operational guarantees.
- Keep cloud credentials in server-side environment variables only.
- If MCP tools fail to load, the backend should report unavailable tools instead
  of inventing tool names.

Example local MCP settings:

```env
MCP_CLS_TRANSPORT=streamable-http
MCP_CLS_URL=http://localhost:8003/mcp
MCP_MONITOR_TRANSPORT=streamable-http
MCP_MONITOR_URL=http://localhost:8004/mcp
MCP_TOOLS_LOAD_TIMEOUT_SECONDS=30
```

## API Summary

Backend routes:

- `GET /health`: service health
- `POST /api/chat`: non-streaming chat
- `POST /api/chat_stream`: streaming chat via SSE
- `GET /api/chat/sessions`: persisted chat sessions
- `GET /api/chat/session/{session_id}`: session history
- `POST /api/upload`: upload and enqueue document indexing
- `GET /api/index_tasks/{task_id}`: indexing task status
- `POST /api/aiops`: streaming AIOps diagnosis via SSE
- `GET /api/aiops/runs/{run_id}`: AIOps run summary
- `GET /api/aiops/runs/{run_id}/events`: AIOps run events
- `POST /api/workspaces`: create a Native Agent workspace
- `GET /api/workspaces`: list Native Agent workspaces
- `POST /api/scenes`: create a workspace-scoped diagnosis scene
- `GET /api/scenes`: list scenes, optionally filtered by `workspace_id`
- `GET /api/scenes/{scene_id}`: fetch scene detail, linked knowledge bases, and
  tools
- `GET /api/tools`: discover diagnosis tools and persisted policies
- `PATCH /api/tools/{tool_name}/policy`: enable, disable, or require approval
  for a tool
- `POST /api/agent/runs`: run a scene-scoped Native Agent diagnosis
- `GET /api/agent/runs/{run_id}`: fetch a Native Agent run summary
- `GET /api/agent/runs/{run_id}/events`: replay a Native Agent trajectory
- `POST /api/agent/runs/{run_id}/feedback`: capture thumbs-up/down feedback

The frontend calls server-side handlers under `frontend/app/api/*`; browser
components should not call FastAPI directly.

## Development Workflow

Recommended backend commands:

```bash
uv run python -m compileall app mcp_servers tests
uv run python -m ruff check app mcp_servers tests
uv run python -m ruff format --check app mcp_servers tests
uv run python -m mypy app --ignore-missing-imports
uv run python -m bandit -r app -ll
uv run python -m pytest tests -q
```

Recommended frontend commands:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm build
```

Common Make targets:

```bash
make up
make down
make status
make verify
make db-upgrade
make test
make lint
make type-check
make security
```

Development rules:

- Read `CONTRIBUTING.md` before opening a branch or PR.
- Keep backend dependencies in `pyproject.toml`; commit `uv.lock`.
- Keep frontend dependencies in `frontend/package.json`; commit
  `frontend/pnpm-lock.yaml`.
- Do not commit `.env`, `.venv/`, `uploads/`, `data/`, `volumes/`,
  `frontend/node_modules/`, or `frontend/.next/`.
- When backend API models change, update `frontend/lib/api-contracts.ts` or the
  relevant BFF route adapter in the same change.

## Open Source Governance

- `CONTRIBUTING.md`: human and AI contributor workflow.
- `AGENTS.md`: AI coding agent execution rules.
- `SECURITY.md`: private vulnerability reporting and security expectations.
- `CODE_OF_CONDUCT.md`: community behavior expectations.
- `SUPPORT.md`: support boundaries and issue guidance.
- `MAINTAINERS.md`: maintainer responsibilities and repository authority.
- `docs/repository-governance.md`: branch protection, labels, and maintainer
  operating rules.
- `docs/architecture.md`: current architecture and planned evolution.
- `docs/deployment.md`: local and production deployment guidance.
- `docs/security.md`: operational security checklist.
- `docs/openapi.json`: generated FastAPI contract for SDK and BFF governance.

## Operational Notes

Document indexing:

```text
POST /api/upload
  -> save file under uploads/
  -> create indexing task
  -> enqueue task
  -> worker reads file
  -> split text
  -> embed chunks
  -> write vectors to Milvus
```

Chat:

```text
Frontend chat
  -> Next.js BFF
  -> FastAPI /api/chat_stream
  -> RagAgentService
  -> retrieve_knowledge
  -> Milvus
  -> Qwen streaming response
```

AIOps:

```text
Frontend diagnose
  -> Next.js BFF
  -> FastAPI /api/aiops
  -> compatibility wrapper
  -> AgentRuntime
  -> ToolExecutor
  -> persisted Native Agent trajectory + AIOps-compatible run events
```

Native Agent V1:

```text
Workspace
  -> Scene
  -> Knowledge bases + MCP/local tools
  -> AgentRuntime
  -> Tool policy checks
  -> Tool calls and results
  -> Trajectory replay
  -> Feedback and analytics inputs
```

## Troubleshooting

Backend cannot start:

- Check `PORT` availability.
- Verify `.env` values.
- Ensure PostgreSQL and Milvus are reachable.
- Run `uv run alembic upgrade head`.

Upload succeeds but indexing never completes:

- Check `TASK_DISPATCHER_MODE`.
- If `detached`, start `uv run python -m app.worker`.
- Check Redis connectivity and task status endpoint.

MCP tools unavailable:

- Confirm MCP URL and transport are correct.
- Increase `MCP_TOOLS_LOAD_TIMEOUT_SECONDS` if tool discovery is slow.
- Test the MCP server independently before blaming the Agent.
- Remember that Tencent CLS MCP queries Tencent CLS data, not local app data.

Frontend cannot reach backend:

- Check `frontend/.env.local`.
- Ensure `SMARTSRE_BACKEND_URL` points to the FastAPI service.
- If backend auth is enabled, set `SMARTSRE_API_KEY` server-side only.

## Security Best Practices

- Keep all secrets in environment variables or a secret manager.
- Do not expose backend API keys to browser code.
- Use explicit CORS origins in production.
- Use least-privilege cloud credentials for MCP servers.
- Store audit logs and AIOps run events in durable storage.
- Require approval for high-risk tools through tool policies; V1 reports
  `approval_required` instead of executing those tools.
- Review uploaded document access rules before exposing the app to multiple
  teams.

Report vulnerabilities privately by following `SECURITY.md`.

## Contributing

Read `CONTRIBUTING.md` for the human contributor workflow, commit style, branch
policy, PR rules, quality gates, publication lock, and dependency policy.

AI coding agents should also read `AGENTS.md` before making changes.

Do not create public version tags, GitHub publication artifacts, or package and
container publication automation while the project is in development stage.

## License

Apache License 2.0. See [LICENSE](LICENSE).
