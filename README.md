# AI Interviewer (RAG)

A retrieval-augmented interview practice tool. Upload your resume, a target job
description, and company research; it conducts a technical or behavioral
interview grounded in *your* experience and *that* role, then grades your
answers against rubrics and produces a report.

> **Status:** Phase 0 — foundations. Not yet runnable. See
> [`docs/adr/`](docs/adr/) for architecture decisions.

## Why this exists

Generic mock-interview tools ask generic questions. This one retrieves from your
actual corpus, so it can ask *"you mentioned Kafka at your last role — walk me
through a failure you debugged"* instead of *"tell me about a challenge."*

## Stack

| Layer | Choice |
|---|---|
| API | Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2 |
| Data | Postgres 17 + pgvector (vectors, relational data, and full-text in one database) |
| Blobs | S3-compatible object storage (MinIO locally) |
| Jobs | Postgres-backed queue, `FOR UPDATE SKIP LOCKED` with lease + reclaim |
| Web | Next.js 16 (App Router), TypeScript, Tailwind |
| Embeddings | `bge-small-en-v1.5` via fastembed — local, deterministic, CPU |
| LLM | Anthropic Claude |

## Repository layout

```
apps/
  api/          FastAPI service + ingestion worker
  web/          Next.js frontend
docs/
  adr/          Architecture Decision Records
```

## Getting started

Not yet — the Compose stack lands in Phase 0 PR 3. Once it does:

```bash
cp .env.example .env    # then fill in the blanks
docker compose up -d
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for branch naming, commit conventions,
and the review flow. `main` is protected: all work arrives via pull request
with green CI.

## License

MIT — see [LICENSE](LICENSE).
