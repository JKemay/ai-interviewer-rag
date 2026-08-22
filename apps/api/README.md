# `apps/api` — FastAPI service and ingestion worker

Two processes, one codebase and one dependency set:

- **API** — HTTP surface. Serves the frontend, holds the authorization choke
  point, and streams interview turns over SSE. Never parses uploaded documents.
- **Worker** — drains the Postgres-backed job queue: document verification,
  parsing, chunking, embedding, and blob deletion. Runs untrusted-input parsers
  under resource limits, isolated from the request path.

They are deployed separately with different resource profiles, because parsing a
PDF and serving a health check have nothing in common.

Scaffolded in Phase 0 PR 2 (tooling) and PR 4 (application skeleton).
