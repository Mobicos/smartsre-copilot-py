# Security Policy

## Supported Versions

SmartSRE Copilot is currently in development stage. Security fixes target the
latest `main` branch unless maintainers announce otherwise.

## Reporting a Vulnerability

Do not open public issues for vulnerabilities, leaked credentials, or
exploitable security findings.

Report security issues privately by contacting the maintainers listed in
`MAINTAINERS.md`, or by using GitHub private vulnerability reporting if it is
enabled for the repository.

Please include:

- A concise description of the vulnerability.
- Reproduction steps or a proof of concept.
- Impacted versions, branches, or deployment modes.
- Any known mitigations.

## Security Expectations

- Do not commit `.env` files, API keys, cloud credentials, database passwords,
  local compose overrides, or generated caches.
- Keep backend API keys server-side. Never expose them through `NEXT_PUBLIC_*`
  or browser-visible configuration.
- Use explicit CORS origins in production.
- Keep high-risk tools behind approval policies.
- Treat MCP credentials as server-side secrets.

## Dependency And Runtime Updates

Security dependency updates should remain small, reviewable, and CI-gated.
Runtime or infrastructure upgrades with operational risk require a dedicated PR
with validation and rollback notes.
