# Contributing

This document is the primary contribution guide for all contributors, including
human maintainers and AI coding agents. Agent-specific execution rules live in
`AGENTS.md`; the full workflow reference lives in
`docs/development-workflow.md`.

## Required Workflow

Start every change from the latest `main` and use a focused branch:

```bash
git switch main
git pull --ff-only origin main
git switch -c docs/example-topic
```

Use short kebab-case branch names:

- `feature/<capability>`
- `fix/<problem>`
- `refactor/<area>`
- `docs/<topic>`
- `ci/<workflow-topic>`

Keep one branch focused on one product or engineering outcome. Do not mix large
feature work, dependency churn, local environment changes, and unrelated cleanup
in the same PR.

## Commit Messages

Use Conventional Commits:

```text
<type>(<scope>): <concise action summary>
```

Scopes are required. They keep commit history, PR titles, and squash-merge
subjects easy to scan across backend, frontend, infrastructure, and operations
work.

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
fix(ci): resolve type check failures
feat(agent): stream native agent runs
docs(local): explain compose workflow
ci(actions): enforce ruff format check
chore(deps): update dependency lock file
```

Allowed scopes:

```text
agent, aiops, api, chat, frontend, knowledge, mcp, persistence, worker,
docs, local, ci, actions, deps, docker, security, tests, tooling, repo
```

Dependency bump PR titles must use one of these scoped forms:

```text
chore(deps): bump ...
chore(docker): bump ...
ci(actions): bump ...
```

If a change contains unrelated dependency lock updates, split the lock update
into a separate commit named:

```text
chore(deps): update dependency lock file
```

## Local Enforcement

Install hooks once per checkout:

```bash
make pre-commit-install
```

Before pushing backend, API, agent, infrastructure, or repository-governance
changes, run:

```bash
make verify
```

`make verify` is non-mutating and mirrors the backend CI contract: compile,
lint, format check, type check, security scan, OpenAPI contract check, Compose
configuration check, coverage threshold, and tests.

For frontend changes under `frontend/`, also run:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm build
```

Do not bypass hooks with `--no-verify` as a normal workflow. If local Docker,
network, platform, or credential constraints block a command, record the exact
command and failure reason in the PR and rely on GitHub Actions as the final
shared gate.

## Pull Requests

Open a PR for shared work. Do not push directly to `main`.

Each PR must include:

- A compliant Conventional Commit title because squash merge uses it as the
  final commit subject on `main`.
- A summary of user or developer impact.
- Validation commands or a clear reason why local validation could not run.
- Operational risk and rollback notes.
- API contract notes when backend request or response models change.
- Migration and rollback notes when persistence behavior changes.

Draft PRs are allowed for early CI feedback. Do not merge draft PRs or PRs with
failing, pending, or unexpectedly skipped required checks.

## Releases

Release work must follow `docs/release-process.md`.

Release PRs must include:

- Version metadata updates in `pyproject.toml`, `app/config.py`, and
  `app/__init__.py`.
- `CHANGELOG.md` updates.
- Migration and rollback notes when persistence changes.
- Docker Compose or deployment notes when runtime services change.
- `docs/openapi.json` updates when backend routes, schemas, or auth contracts
  change.
- Validation evidence from backend and frontend quality gates.

Use tags in the form `vMAJOR.MINOR.PATCH`, for example `v1.3.0`.

## Merge Policy

Use squash merge for normal feature, fix, refactor, docs, and CI PRs. Keep the
PR title compliant because it becomes the final commit subject on `main`.

Use merge commits only for intentionally stacked or long-running integration
branches where preserving branch topology matters.

Delete remote feature branches after merge unless the branch is a deliberate
long-running integration branch.

## Dependency And Runtime Policy

- Keep backend dependencies in `pyproject.toml`.
- Keep `uv.lock` committed because this is an application repository.
- Keep frontend dependencies in `frontend/package.json`.
- Keep `frontend/pnpm-lock.yaml` committed for reproducible frontend installs.
- Do not mix lockfile-only churn into feature or fix commits.
- Dependabot security updates should remain automatic, but still require CI and
  review before merge.
- Dependabot routine version updates should prefer small, reviewable PRs:
  production patch updates may be grouped, development minor or patch updates
  may be grouped, and production minor updates should be isolated or planned.
- High-impact backend runtime dependencies, including FastAPI, SSE, Pydantic,
  SQLAlchemy, Redis, PostgreSQL drivers, Milvus, LangChain/LangGraph,
  DashScope/OpenAI SDKs, and MCP tooling, must not be batched into broad
  production minor update PRs.
- Dependabot should avoid automatic semver-major updates.
- Runtime and infrastructure major or minor upgrades, such as Python base
  images, PostgreSQL, Redis, Milvus, etcd, and MinIO, require a dedicated PR and
  explicit runtime validation.

## Code, Security, And Local Files

- Read nearby code before editing and follow existing project patterns.
- Prefer typed function boundaries for new or changed code.
- Keep `Any` and `cast` close to third-party integration boundaries.
- Use parameterized SQL. Do not interpolate user-controlled values into SQL.
- Avoid broad exception swallowing unless the fallback behavior is explicit and
  logged.
- Keep edits scoped to the requested task and avoid unrelated refactors.
- Do not commit secrets, `.env` files, `.venv/`, local compose overrides, IDE
  metadata, generated caches, uploads, local data, or Docker volumes.
- Root-level `docker-compose.local.yml` is for local development overrides only
  and must not be committed.

## Frontend Rules

- Keep the Next.js frontend in `frontend/` as a separate pnpm app with its own
  lock file.
- Do not commit `frontend/node_modules/`, `frontend/.next/`,
  `frontend/tsconfig.tsbuildinfo`, or local pnpm stores.
- Browser components should call local Next.js route handlers, not the FastAPI
  backend directly.
- Keep backend API keys server-side in Next.js route handlers. Never expose them
  through `NEXT_PUBLIC_*`.
- When backend request or response models change, update the frontend contract
  adapter or BFF route handler in the same PR.
