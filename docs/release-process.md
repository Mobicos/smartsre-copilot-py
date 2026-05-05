# Release Process

SmartSRE Copilot uses Semantic Versioning and Conventional Commits.

## Versioning

- Patch releases fix bugs, security issues, documentation mistakes, or CI
  regressions without changing public behavior.
- Minor releases add compatible user-facing features, APIs, or operational
  capabilities.
- Major releases may change runtime contracts, persistence shape, or deployment
  expectations.

Current planned release line:

```text
1.3.x: Native Agent Workbench baseline
1.4.x: Platform middleware modernization
1.5.x: Knowledge, replay, and AgentOps stabilization
1.6.x: Tool harness and approval foundation
1.7.x: API contract and frontend workbench governance
1.8.x: Decision Runtime contracts and deterministic provider
1.9.x: LangGraph runtime release candidates
2.0.x: LangGraph Decision Runtime
```

## Release Checklist

1. Start from latest `main`.

1. Confirm the changelog has an entry for the release.

1. Update version metadata in `pyproject.toml`, `app/config.py`, and
   `app/__init__.py`.

1. Run backend quality gates:

   ```bash
   make verify
   ```

1. Run frontend quality gates when frontend files changed:

   ```bash
   cd frontend
   pnpm install --frozen-lockfile
   pnpm lint
   pnpm typecheck
   pnpm build
   ```

1. Confirm migrations have upgrade and rollback notes.

1. Confirm Docker Compose startup instructions still match the code.

1. Confirm the generated OpenAPI contract is current:

   ```bash
   uv run python scripts/export_openapi.py --check
   ```

1. Open a PR with validation evidence and rollback notes.

1. Squash merge only after required checks pass.

1. Create a signed or annotated tag when release signing is configured.

1. Let `.github/workflows/release.yml` create the GitHub Release, build the
   Python package, scan the Docker image, and publish GHCR image tags.

## Tag Format

Use `vMAJOR.MINOR.PATCH`, for example:

```text
v1.3.0
```

## Rollback Notes

Every release PR should explain:

- Whether database downgrade is safe.
- Whether frontend and backend must be deployed together.
- Whether worker queues or background tasks need draining.
- Whether any new services are required in Docker Compose.
- Whether the GHCR image can be rolled back to the previous release tag without
  database or configuration changes.
