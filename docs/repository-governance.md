# Repository Governance

SmartSRE uses repository rules as part of the product quality system. The goal
is to make the safe path the default path for maintainers, contributors, and AI
coding agents.

## Required GitHub Settings

Enable these settings before treating `main` as a protected release branch:

- Protect `main` with required pull requests before merging.
- Require at least one approving review.
- Require review from CODEOWNERS for owned paths.
- Require status checks to pass before merging.
- Require branches to be up to date before merging when GitHub reports stale CI
  results.
- Require conversation resolution before merging.
- Block force pushes and branch deletion on `main`.
- Restrict direct pushes to `main` to repository administrators only, and prefer
  no direct pushes even for administrators.
- Keep squash merge enabled and use the PR title as the final commit subject.
- Keep merge commits disabled unless an integration branch explicitly needs
  topology preservation.
- Keep rebase merge disabled for normal feature work.

Required checks should include:

- `Pull Request Title`
- `Backend Quality Checks`
- `Frontend Quality Checks`
- `Docker Build Smoke`
- `Dependency Review`
- `CodeQL / Analyze`

## Release Checklist

Before creating a release tag:

- Update all version metadata in one change.
- Update `CHANGELOG.md` with user-facing changes, operational notes, and
  migration or rollback guidance.
- Run `make verify`.
- Run frontend gates when `frontend/` changed.
- Confirm GitHub Actions is green on the release PR.
- Merge by squash with a compliant Conventional Commit subject.
- Create an annotated tag named `vMAJOR.MINOR.PATCH`.
- Let `.github/workflows/release.yml` build the Python package, scan the image,
  push GHCR tags, and create GitHub Releases notes.

## Issue Labels

Recommended labels are defined in `.github/labels.yml`. Keep them synchronized
with GitHub when repository settings are changed.

Baseline label groups:

- Type: `type:bug`, `type:feature`, `type:docs`, `type:security`,
  `type:question`
- Area: `area:agent`, `area:api`, `area:frontend`, `area:infra`, `area:docs`
- Priority: `priority:p0`, `priority:p1`, `priority:p2`
- Contributor experience: `good first issue`, `help wanted`
- Lifecycle: `status:needs-triage`, `status:blocked`, `status:ready`

## Maintainer Rhythm

- Triage new issues weekly.
- Review dependency PRs in small batches.
- Merge security updates before routine dependency updates.
- Keep large architecture changes behind roadmap issues or design documents.
- Close stale support questions only after pointing users to `SUPPORT.md`.
