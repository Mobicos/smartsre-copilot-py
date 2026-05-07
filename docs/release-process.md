# Release Process

SmartSRE Copilot public releases are paused.

Do not create version tags, GitHub Releases, GHCR release images, or release
branches until the native Agent 1.0 scope is complete, feature-complete, and
validated by the required backend, frontend, Agent, integration, and deployment
checks.

The first official release will be re-evaluated as `1.0.0` after that readiness
review. Until then, version metadata should remain a development snapshot and
all user-visible work should be tracked under `CHANGELOG.md` `Unreleased`.

SmartSRE Copilot will use Semantic Versioning and Conventional Commits after
public releases resume.

## Versioning

- Patch releases fix bugs, security issues, documentation mistakes, or CI
  regressions without changing public behavior.
- Minor releases add compatible user-facing features, APIs, or operational
  capabilities.
- Major releases may change runtime contracts, persistence shape, or deployment
  expectations.

Current development line:

```text
0.1.0.dev0: pre-release development snapshot
1.0.0: first official release after native Agent readiness is complete
```

## Release Checklist

Release execution is blocked while the pause above is active. When release work
resumes:

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

1. Restore `.github/workflows/release.yml` only after the maintainer explicitly
   approves release automation.

## Tag Format

Use `vMAJOR.MINOR.PATCH`, for example:

```text
v1.0.0
```

## Rollback Notes

Every release PR should explain:

- Whether database downgrade is safe.
- Whether frontend and backend must be deployed together.
- Whether worker queues or background tasks need draining.
- Whether any new services are required in Docker Compose.
- Whether the GHCR image can be rolled back to the previous release tag without
  database or configuration changes.
