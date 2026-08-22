# `apps/web` — Next.js frontend

Next.js 16 (App Router). Talks to the API at `api.<domain>` in deployment and
`localhost:8000` locally — both same-site, so the session cookie works without
third-party-cookie exemptions.

The TypeScript API client in `src/lib/api/` is **generated** from the backend's
OpenAPI schema and must not be hand-edited. CI regenerates it and fails the
build if the committed output has drifted.

Scaffolded in Phase 4.
