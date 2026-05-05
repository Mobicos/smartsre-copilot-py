# Security Guide

This guide complements `SECURITY.md` with operational security expectations.

## Secrets

- Keep `.env` files local.
- Use server-side environment variables for DashScope, MCP, database, Redis, and
  object storage credentials.
- Never expose backend credentials through `NEXT_PUBLIC_*`.
- Rotate credentials if they are pasted into logs, screenshots, issues, or pull
  requests.

## API Access

- Configure `APP_API_KEY` or `API_KEYS_JSON` for non-local deployments.
- Use explicit `CORS_ALLOWED_ORIGINS` in production.
- Avoid wildcard CORS outside local development.
- Keep browser components behind Next.js BFF routes.

## Agent And Tool Safety

- All tool calls must pass through ToolPolicyGate and ToolExecutor.
- High-risk tools should require approval.
- Change or destructive tools must not run automatically in production.
- MCP tools should use least-privilege cloud credentials.

## Data Handling

- Uploaded documents may be sent to embedding providers.
- Model prompts may include user questions, retrieved snippets, tool summaries,
  and run context.
- Store audit logs and Agent events in durable storage.
- Do not store private chain-of-thought.

## Production Checklist

- [ ] `ENVIRONMENT=production`
- [ ] Explicit CORS origins configured
- [ ] Backend API key configured
- [ ] DashScope key configured server-side only
- [ ] PostgreSQL credentials are not default placeholders
- [ ] Redis is not exposed publicly
- [ ] MCP credentials are scoped to read-only or diagnostic use where possible
- [ ] Logs do not include secrets
- [ ] High-risk tools require approval
