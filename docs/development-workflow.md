# Development Workflow

This repository uses a small but strict workflow for branch development,
GitHub Actions, pull requests, and merges. The goal is to keep `main`
deployable, make reviews predictable, and prevent local-only configuration from
leaking into shared history.

For the primary contributor contract, start with `CONTRIBUTING.md`. This file
provides the detailed workflow reference behind that contract.

## 1. Start From Main

Update `main` before starting work:

```bash
git switch main
git pull --ff-only origin main
```

Create a focused branch with a short kebab-case name:

```bash
git switch -c feature/native-agent-runtime
```

Recommended prefixes:

- `feature/` for user-facing capabilities.
- `fix/` for bug fixes or behavior corrections.
- `refactor/` for restructuring without intended behavior changes.
- `docs/` for documentation-only changes.
- `ci/` for GitHub Actions and check configuration.

## 2. Keep Changes Reviewable

Each branch should represent one product or engineering outcome. Avoid mixing
feature work, unrelated cleanup, dependency lock churn, and local environment
changes in one PR.

Dependency lock changes should be committed separately:

```text
chore(deps): update dependency lock file
```

Local-only files stay local. In particular, root-level
`docker-compose.local.yml` is ignored and should not be pushed.

## 3. Local Enforcement

Install repository hooks once per checkout:

```bash
make pre-commit-install
```

Before pushing backend, API, agent, infrastructure, or repository-governance
changes, run the non-mutating verification target:

```bash
make verify
```

This target mirrors the backend CI contract: compile, lint, format check, type
check, security scan, and tests. Use the narrower commands only when you are
iterating locally; `make verify` is the final local gate before pushing.

Do not bypass local hooks with `--no-verify` as a normal workflow. If a local
tool cannot run because of Docker, network, platform, or credential constraints,
record the exact command and failure reason in the PR and let GitHub Actions be
the shared final gate.

## 4. Commit Format

Use the project Conventional Commits format from `AGENTS.md`:

```text
<type>: <concise action summary>
<type>(<scope>): <concise action summary>
```

Allowed types:

- `feat`
- `fix`
- `ci`
- `chore`
- `docs`
- `test`
- `refactor`
- `perf`

Scopes are optional. Use them when they add useful context, especially for
dependency, CI, frontend, and infrastructure changes.

Examples:

```text
fix: resolve CI type check failures
ci(actions): resolve workflow permissions
chore(deps): bump cryptography from 46.0.5 to 46.0.7
chore(docker): bump postgres from 16.1 to 16.2
```

Dependency bump PRs must use these scopes:

```text
chore(deps): bump ...
chore(docker): bump ...
ci(actions): bump ...
```

## 5. Pull Request Rules

Open PRs early when CI feedback is useful. Use draft PRs for incomplete work.
Before requesting review, the PR must include:

- A compliant PR title, because squash merge uses it as the final commit
  subject.
- A summary of user or developer impact.
- Validation commands or a clear reason why local validation could not run.
- Risk and rollback notes.
- API contract notes when backend responses or request models change.
- Migration notes when persistence behavior changes.

## 6. GitHub Actions Contract

GitHub Actions is the final shared gate. CI must:

- Run on `main` pushes and pull requests.
- Cancel superseded PR runs.
- Use least-privilege permissions.
- Validate PR titles.
- Run backend compile, lint, format, type check, security scan, and tests.
- Run frontend lint, type check, and build when frontend changes are present or
  when the full workflow runs.
- Keep Dependabot security updates automatic, but still require CI and review
  before merge.
- Keep routine Dependabot version updates small enough to review: group
  production patch updates, group development minor or patch updates, and avoid
  broad production minor update batches.
- Treat high-impact backend runtime dependency minors as planned changes, not
  routine automation. This includes FastAPI, SSE, Pydantic, SQLAlchemy, Redis,
  PostgreSQL drivers, Milvus, LangChain/LangGraph, DashScope/OpenAI SDKs, and
  MCP tooling.
- Avoid automatic semver-major version updates.
- Treat runtime and infrastructure upgrades as dedicated change sets, not
  routine dependency cleanup.

Runtime version boundaries:

- Python application runtime: `3.11` through `3.13`; do not automatically move
  Docker runtime images to `3.14`.
- PostgreSQL: stay on the current supported major unless a dedicated migration
  PR validates upgrade and rollback.
- Redis, Milvus, etcd, and MinIO: patch updates may be automated, but minor or
  major upgrades require explicit local compose validation.

Local checks should match CI when the environment permits it:

```bash
uv run python -m compileall app mcp_servers tests
uv run python -m ruff check app mcp_servers tests
uv run python -m ruff format --check app mcp_servers tests
uv run python -m mypy app --ignore-missing-imports
uv run python -m bandit -r app -ll
uv run python -m pytest tests -q
```

For frontend changes:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm build
```

If local Docker, network, or platform constraints block a command, record the
exact reason in the PR and rely on GitHub Actions as the final verification
source.

## 7. Merge Strategy

Use squash merge for normal feature, fix, refactor, docs, and CI PRs. This
keeps `main` readable and ensures each merged PR has one clear commit.

Use merge commits only for intentionally stacked or long-running integration
branches where preserving branch topology matters.

Do not merge when required checks are failing, pending, or skipped unexpectedly.
Delete remote feature branches after merge unless they are intentional
integration branches.

## 8. AI Coding Agent Rules

AI agents working in this repository must:

- Read nearby code and project instructions before editing.
- Keep edits scoped to the requested outcome.
- Avoid committing secrets, `.env` files, local compose overrides, IDE files, or
  generated caches.
- Run the relevant quality gates before committing when the local environment
  permits it.
- Report exact commands and blockers instead of claiming unverified success.
- Use the same branch, PR, commit, and merge policies as human maintainers.
