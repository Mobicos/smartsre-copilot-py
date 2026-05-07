# Deployment Guide

SmartSRE Copilot can run as a local development stack or as a controlled
internal evaluation deployment. The current development baseline uses
PostgreSQL, Redis, Milvus, FastAPI, and Next.js.

## Local Development

Use `docker-compose.yml` as the shared template and copy it to
`docker-compose.local.yml` for personal port or service changes:

```bash
cp docker-compose.yml docker-compose.local.yml
docker compose -f docker-compose.local.yml up -d postgres redis standalone attu minio
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 9900
cd frontend
pnpm dev
```

Do not commit `docker-compose.local.yml`.

## Controlled Evaluation Baseline

For controlled internal evaluation deployments:

- Run FastAPI behind a reverse proxy.
- Run the Next.js frontend as a separate service.
- Use managed or backed-up PostgreSQL.
- Use Redis for queues and short-lived state.
- Use explicit CORS origins.
- Configure API keys server-side.
- Keep MCP credentials least-privilege.
- Run migrations before accepting traffic.

## Update Procedure

1. Read the change notes in the PR or deployment ticket.
1. Back up PostgreSQL.
1. Pull the target image or source revision.
1. Run database migrations.
1. Deploy workers before or with the API when queue schema changes.
1. Deploy the frontend when BFF/API contracts change.
1. Verify `/health`, `/docs`, Agent run creation, and frontend BFF routes.

## Rollback Procedure

1. Stop traffic at the reverse proxy when needed.
1. Roll back frontend and backend together if API contracts changed.
1. Run Alembic downgrade only when the change notes say it is safe.
1. Preserve `agent_events` and audit logs for postmortem review.
