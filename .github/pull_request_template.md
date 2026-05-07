## Summary

Describe the purpose of this change and the main user or developer impact.

PR title must use the repository commit style because squash merge uses it as
the final commit subject:

```text
<type>(<scope>): <concise action summary>
```

Allowed types: `feat`, `fix`, `ci`, `chore`, `docs`, `test`, `refactor`, `perf`.
Scopes are required and must use one of:

```text
agent, aiops, api, chat, frontend, knowledge, mcp, persistence, worker,
docs, local, ci, actions, deps, docker, security, tests, tooling, repo
```

Dependency bump PRs must use one of:

```text
chore(deps): bump ...
chore(docker): bump ...
ci(actions): bump ...
```

## Changes

-

## Validation

- [ ] PR title follows the repository commit style
- [ ] Ran the relevant local checks
- [ ] Updated docs if behavior or setup changed
- [ ] Confirmed no secrets or local-only files are included
- [ ] Confirmed backend API contract changes are reflected in the frontend BFF
  layer
- [ ] Updated `docs/openapi.json` when backend routes, schemas, or auth
  contracts changed
- [ ] Confirmed database or queue changes include migration and rollback notes
- [ ] Reviewed `SECURITY.md` impact for auth, secret, tool, or data-flow changes

Validation details:

```text
Paste commands run, screenshots, or notes here.
```

## Risks

- Operational risk:
- Rollback plan:
- Follow-up work:

## Related

Issue / discussion / context:

-
