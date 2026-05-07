# Repository Governance

SmartSRE uses repository rules as part of the product quality system. The goal
is to make the safe path the default path for maintainers, contributors, and AI
coding agents.

## Required GitHub Settings

Enable these settings before treating `main` as a protected integration branch:

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

## Publication Lock

SmartSRE Copilot is currently in development stage. Do not create public version
tags, GitHub publication artifacts, package publication automation, container
image publication automation, or long-running publication branches.

User-visible changes, operational notes, migration notes, and rollback guidance
belong in the PR body and the relevant project documentation while the project
is in development stage.

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
