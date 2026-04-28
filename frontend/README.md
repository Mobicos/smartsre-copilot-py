# SmartSRE Copilot Frontend

Next.js frontend for the SmartSRE Copilot backend. Browser code talks to local
Next.js route handlers under `app/api/*`; those handlers proxy the FastAPI
service and keep backend credentials server-side.

## Local Development

```powershell
pnpm install --frozen-lockfile
Copy-Item .env.example .env.local
pnpm dev
```

Default backend target:

```text
SMARTSRE_BACKEND_URL=http://localhost:9900
```

Set `SMARTSRE_API_KEY` in `.env.local` only when the FastAPI backend requires an
API key. Do not expose backend secrets through `NEXT_PUBLIC_*` variables.

## Quality Gates

Run these before committing frontend changes:

```powershell
pnpm lint
pnpm typecheck
pnpm build
```

If `pnpm build` fails locally with `spawn EPERM` on Windows, rerun it outside the
sandbox or rely on GitHub Actions for final Linux verification.
