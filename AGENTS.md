# AGENTS.md

Project instructions for AI coding agents and maintainers.

## Commit Style

Use this simplified Conventional Commits format:

```text
<type>: <concise action summary>
```

Do not use scoped commits such as `fix(ci): ...`.

Allowed types:

- `feat`: user-facing feature
- `fix`: bug fix, CI failure fix, or behavior correction
- `ci`: CI workflow or check configuration only
- `chore`: dependency, tooling, generated metadata, or maintenance work
- `docs`: documentation only
- `test`: tests only
- `refactor`: code restructuring without behavior change
- `perf`: performance improvement

Examples:

```text
fix: resolve CI type check failures
ci: enforce ruff format check
chore: update dependency lock file
docs: explain GitHub Actions workflow
```

## Quality Gates

Before committing code changes, run the project quality gates when the local
environment permits it:

```powershell
python -m compileall app mcp_servers tests
python -m ruff check app mcp_servers tests
python -m ruff format --check app mcp_servers tests
python -m mypy app --ignore-missing-imports
python -m bandit -r app -ll
python -m pytest tests -q
```

For frontend changes under `frontend/`, run the frontend gates as well:

```powershell
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm build
```

If a local environment issue prevents a command from running, record the exact
reason and rely on GitHub Actions as the final verification source.

## Dependency Policy

- Keep `pyproject.toml` as the source of declared dependencies.
- Keep `uv.lock` committed because this is an application repository.
- Do not mix lockfile-only churn into feature or fix commits.
- Commit dependency lock updates separately as:

```text
chore: update dependency lock file
```

## Code Style

- Read nearby code before editing and follow existing project patterns.
- Prefer typed function boundaries for new or changed code.
- Keep `Any` and `cast` close to third-party integration boundaries.
- Do not let weak third-party types spread into business logic.
- Use parameterized SQL. Do not interpolate user-controlled values into SQL.
- Avoid broad exception swallowing unless the fallback behavior is explicit and logged.
- Keep edits scoped to the requested task and avoid unrelated refactors.

## Frontend Policy

- Keep the Next.js frontend in `frontend/` as a separate pnpm workspace-style app with its own lock file.
- Do not commit `frontend/node_modules/`, `frontend/.next/`, `frontend/tsconfig.tsbuildinfo`, or local pnpm stores.
- Do not use `typescript.ignoreBuildErrors` in `next.config.mjs`; type errors must fail builds.
- Browser components should call local Next.js route handlers, not the FastAPI backend directly.
- Keep backend API keys server-side in Next.js route handlers. Never expose them through `NEXT_PUBLIC_*`.
- Keep FastAPI response-envelope parsing in `frontend/lib/api-contracts.ts` or BFF route handlers.
- When backend request or response models change, update the frontend contract adapter in the same change.
- Prefer server-side BFF adapters for compatibility with legacy backend field names such as `Id` and `Question`.

## CI Policy

CI should be stricter than local habits:

- Do not skip tests when the `tests/` directory is missing.
- Keep the Python matrix aligned with the supported version range.
- Run lint, format check, type check, security scan, and tests.
- Prefer locked dependency installs once CI is migrated to `uv`.
