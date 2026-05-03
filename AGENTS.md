# AGENTS.md

Project instructions for AI coding agents and maintainers.

## Commit Style

Use the project Conventional Commits format:

```text
<type>: <concise action summary>
<type>(<scope>): <concise action summary>
```

Scopes are optional. Use them when they add useful context, especially for
automated dependency updates and CI/platform work.

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
ci(actions): enforce ruff format check
chore(deps): update dependency lock file
chore(docker): bump postgres from 16.1 to 16.2
ci: enforce ruff format check
docs: explain GitHub Actions workflow
```

Dependency bump PR titles must use these scopes:

```text
chore(deps): bump ...
chore(docker): bump ...
ci(actions): bump ...
```

PR titles must use the same format because squash merges use the PR title as
the final commit subject on `main`.

If a change contains unrelated dependency lock updates, split the lock update
into a separate commit named:

```text
chore(deps): update dependency lock file
```

## Branch Policy

- Create feature work from the latest `main`.
- Use short kebab-case branch names:
  - `feature/<capability>`
  - `fix/<problem>`
  - `refactor/<area>`
  - `docs/<topic>`
  - `ci/<workflow-topic>`
- Keep one branch focused on one product or engineering outcome.
- Do not mix large feature work, dependency churn, and unrelated cleanup in the
  same branch.
- Delete remote feature branches after the PR is merged unless the branch is a
  long-running integration branch.

## Pull Request Policy

- Prefer PRs that are reviewable in one sitting. If a PR needs multiple
  architectural topics, split it into stacked or follow-up PRs.
- PR descriptions must explain user/developer impact, validation evidence,
  operational risk, and rollback notes.
- Backend model or API contract changes must update the frontend BFF adapter in
  the same PR.
- Persistence changes must include migrations and mention rollback behavior.
- Local-only files must not be committed. Root-level `docker-compose.local.yml`
  is for local development overrides only.
- Draft PRs are allowed for early CI feedback, but do not merge draft or red PRs.

## Merge Policy

- Use squash merge for normal feature, fix, refactor, docs, and CI PRs.
- Use the PR title as the squash commit subject, and keep it compliant with the
  commit style above.
- Use merge commits only for intentionally stacked or long-running integration
  branches where preserving branch topology matters.
- Do not rebase or force-push shared branches unless everyone using the branch
  has agreed.
- Do not merge with failing or pending required checks.

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
- Dependabot version updates should group related dependencies and avoid
  automatic semver-major updates.
- Runtime and infrastructure major or minor upgrades, such as Python base
  images, PostgreSQL, Redis, Milvus, etcd, and MinIO, require a dedicated PR and
  explicit runtime validation.
- Commit dependency lock updates separately as:

```text
chore(deps): update dependency lock file
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
- Run frontend checks when `frontend/` exists and has a committed lock file.
- Use least-privilege workflow permissions.
- Cancel superseded PR workflow runs so reviewers see the latest signal.
- Validate PR titles so the final squash commit stays compliant.
- GitHub Actions is the final gate when local Docker, network, or platform
  constraints prevent running the full suite locally.
