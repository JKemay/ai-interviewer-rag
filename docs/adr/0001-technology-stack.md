# ADR-0001: Technology stack

- **Status:** Accepted
- **Date:** 2026-08-22

## Context

Greenfield build of a retrieval-augmented interview tool: documents are ingested
and chunked, chunks are embedded and retrieved, and a language model conducts
and grades an interview grounded in them. It is a personal-scale product built
to production practices, deployed to a real environment on a hobby budget.

The choices below were contested. Conventional ones (FastAPI, Alembic, Tailwind)
are not recorded here — if the answer to "why?" is obvious from the code, there
is nothing to write down.

## Decision 1 — Postgres with pgvector as the only datastore

Relational data, vector embeddings, and full-text search all live in one
Postgres instance rather than pairing Postgres with a dedicated vector database.

**Why.** Every retrieval query in this system is filtered by owner before it is
ranked. With a separate vector store, that filter lives on the other side of a
network boundary: either fetch candidate IDs from Postgres and pass them to the
vector store, or over-fetch from the vector store and filter afterwards. The
first adds a round trip to every query; the second silently degrades recall,
because the top-k you asked for is computed before the filter is applied. Owner
scoping is also a security boundary here, and a boundary enforced across two
systems is one that can drift.

Operationally: one backup, one restore, one migration path, one set of
credentials, and transactional consistency between a chunk and its embedding.

**Consequences.** We accept lower ceilings than a dedicated engine — no
distributed sharding, fewer index types, and pgvector's HNSW is less tunable
than a purpose-built store. At personal scale this is irrelevant; at large
multi-tenant scale it would need revisiting. Postgres becomes a single point of
failure, which is already true of the relational data.

**Alternatives.** Pinecone (managed, but a second vendor, a second bill, and
network-boundary filtering); Qdrant/Weaviate self-hosted (another service to
operate for no benefit at this size).

## Decision 2 — Local embedding model, behind an interface

`bge-small-en-v1.5` via fastembed (384 dimensions, ONNX, CPU), reached through
an `EmbeddingProvider` interface.

**Why.** Embeddings must be *identical* across every environment. A vector
indexed on one machine and queried from another are compared directly; if the
two environments produce different vectors, retrieval degrades in a way that
looks like bad relevance rather than a bug. That constraint means the model is
chosen by the smallest environment that has to run it — a CPU-only production
container — not the largest.

A local model also removes an API key, a network call on every ingest and query,
and a third-party dependency from CI. Anthropic provides no embeddings API, so a
hosted embedding model would mean a second AI vendor purely for this.

**Consequences.** Retrieval quality is below what a larger hosted model would
give. The interface exists so that is a one-file change — but a change that
requires re-embedding the entire corpus, and re-running the retrieval evaluation
before and after. A GPU accelerates that bulk re-embedding locally; it is
explicitly *not* part of the deployed architecture.

This choice is provisional. It is a baseline to be measured against once the
retrieval evaluation harness exists, not a commitment.

**Alternatives.** Voyage AI (better quality, API key, network dependency in CI);
OpenAI embeddings (a second AI vendor for one function).

## Decision 3 — Opaque session cookies, not JWTs

Argon2id password hashing, with sessions as random opaque tokens stored
server-side and sent in an `HttpOnly; Secure; SameSite=Lax` cookie.

**Why.** Server-side sessions are revocable. Logging out, or responding to a
compromised account, is a `DELETE` — the token is dead on the next request. A
JWT is valid until it expires no matter what you do, so revocation means adding
a server-side denylist, at which point you have session storage anyway, plus a
signing key to rotate and a family of algorithm-confusion bugs to avoid.

Opaque tokens carry no claims, so nothing about the user is readable from a
stolen cookie, and there is no temptation to trust unverified token contents.

**Consequences.** Every authenticated request hits the session store. At this
scale that is one indexed primary-key lookup against a database the request was
going to touch regardless. Horizontal scaling requires shared session storage —
which is Postgres, already shared.

**Alternatives.** JWT access tokens with refresh rotation (industry-common,
materially more machinery to get right, and the failure modes are silent).

## Decision 4 — Single repository, two applications

`apps/api` and `apps/web` in one repository.

**Why.** The API's OpenAPI schema generates the frontend's TypeScript client. In
split repositories, a response-model change and its client update are two PRs
that can merge in either order, and the window between them is a broken
frontend. In one repository they are one atomic commit, and CI can *prove* they
agree — which is what the schema drift check does.

**Consequences.** CI runs both applications' jobs on every PR, including changes
that touch only one. Deployment must select per application. Neither matters
at this size.

## Decision 5 — Next.js 16

**Why.** 16.x is Active LTS. 15.x entered Maintenance LTS and reaches end of
life in October 2026 — scaffolding a new project onto it would start on a branch
receiving only critical fixes, months from expiry.

## Decision 6 — Hosting: Neon, Fly.io, Vercel

**Why.** Neon's branching maps onto staging and production without paying for
two databases. Fly runs a container without a Kubernetes tax. Vercel hosts
Next.js on the free tier. Total infrastructure cost is a few dollars a month;
the dominant and variable cost is language-model usage, which is why per-run
token and wall-clock budgets are a feature rather than an afterthought.

**Consequences.** Three providers to configure. Fly is not free — small
always-on machines carry explicit monthly compute pricing.
