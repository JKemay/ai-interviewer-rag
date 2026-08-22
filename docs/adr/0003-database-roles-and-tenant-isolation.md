# ADR-0003: Database roles and tenant isolation

- **Status:** Accepted
- **Date:** 2026-08-22

## Context

ADR-0001 committed to owner-scoped access enforced in three independent layers:
composite foreign keys in the schema, a required `owner_id` argument in the
repository layer, and Row-Level Security in the database.

That model assumed every database connection acts on behalf of exactly one
owner. The ingestion worker breaks the assumption: it drains a **global** queue,
so it must see jobs belonging to every owner in order to claim one at all.

The naive fixes are both wrong. Giving the application role cross-tenant reach
destroys the guarantee for the one role that is directly exposed to user input.
Giving the worker `BYPASSRLS` removes the backstop precisely where untrusted
documents are parsed.

Soft deletion adds a second wrinkle. Deleted rows must be invisible to the
application, but the purge job must be able to see them — otherwise nothing can
ever remove them.

## Decision

### Three roles, distinguished by capability

| Role | Owns tables | `BYPASSRLS` | Connection | Sees |
| --- | --- | --- | --- | --- |
| `ai_migrator` | yes | no | direct (never pooled) | nothing at runtime — see below |
| `ai_app` | no | no | pooled | its own tenant, non-deleted rows only |
| `ai_worker` | no | no | pooled | all queue jobs; tenant data only after scoping itself |

`ai_migrator` runs DDL and nothing else. Alembic uses it over Neon's **direct**
connection, because DDL and advisory locks misbehave under transaction pooling.

`ai_app` serves HTTP requests. Every request wraps its work in a transaction
opening with `SET LOCAL app.owner_id`.

`ai_worker` drains the queue. It claims a job with cross-tenant visibility, then
**sets `app.owner_id` from the claimed job's `owner_id` before touching any user
data.** Cross-tenant reach is confined to the `job` table; every other table is
scoped exactly as it is for `ai_app`.

### Fail closed when the owner is unset

```sql
CREATE FUNCTION app_current_owner() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT nullif(current_setting('app.owner_id', true), '')::uuid
$$;
```

Unset returns `NULL`, and `owner_id = NULL` is `NULL`, not `true` — so a query
that forgot to scope itself returns **no rows** rather than every row. The
mistake shows up as an empty result during development, not as a data leak in
production.

### Policies are per-role, so the difference is visible in the schema

```sql
-- Application: own tenant, active rows only.
CREATE POLICY document_app ON document FOR ALL TO ai_app
  USING      (owner_id = app_current_owner() AND deleted_at IS NULL)
  WITH CHECK (owner_id = app_current_owner());

-- Worker: same tenant scoping, but soft-deleted rows remain visible because
-- purging them is its job.
CREATE POLICY document_worker ON document FOR ALL TO ai_worker
  USING      (owner_id = app_current_owner())
  WITH CHECK (owner_id = app_current_owner());

-- The queue is the single documented exception to tenant scoping.
CREATE POLICY job_worker ON job FOR ALL TO ai_worker USING (true);
```

`WITH CHECK` is what stops a caller writing a row *belonging to someone else*;
`USING` only governs reads and which rows an update may target.

### Authentication is the second exception, and it is unavoidable

Tenant scoping assumes the owner is already known. Authentication is the step
that *establishes* it, so two lookups necessarily run before `app.owner_id`
exists: resolving a session cookie to an owner, and resolving an email address
to a user during login. Under an owner-scoped policy both return zero rows, and
nobody can ever log in.

Dropping RLS on `app_user` and `session_token` would fix it by removing the
protection from the two tables that matter most. Instead, each lookup gets a
`SECURITY DEFINER` function — executed with the privileges of its owner
(`ai_migrator`) rather than the caller — granted only to `ai_app`:

```sql
CREATE FUNCTION auth_resolve_session(p_token_hash bytea)
RETURNS TABLE (session_id uuid, owner_id uuid)
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = pg_catalog, public, pg_temp   -- see below
AS $$
  SELECT id, owner_id
  FROM session_token
  WHERE token_hash = p_token_hash
    AND revoked_at IS NULL
    AND expires_at > now()
$$;
```

Three properties make this narrow rather than a backdoor:

- It takes a **hash of an unguessable token**, so calling it without already
  possessing a valid session yields nothing.
- It returns **identifiers only** — never row contents.
- `SET search_path` is mandatory. Without it, a caller who can create objects in
  a schema earlier on the search path can shadow a table or operator the
  function body references, and have it executed with the definer's privileges.
  This is the classic `SECURITY DEFINER` privilege-escalation bug.

`app_user` and `session_token` keep ordinary owner-scoped policies for every
other operation: listing your own sessions, revoking them, updating your
password.

### Soft deletion lives in the policy, not only in queries

The application's predicate `deleted_at IS NULL` sits in the RLS policy as well
as in repository queries. Forgetting the filter in one hand-written query is
then a bug that returns too few rows, never one that resurfaces deleted PII.

### `FORCE ROW LEVEL SECURITY`, with no policy for the migration role

Every table is `FORCE`d, and `ai_migrator` is granted no policy.

A table owner is normally exempt from its own policies. Without `FORCE`, an
application that accidentally connected as the owning role would bypass RLS
entirely and expose every tenant — a silent, total failure. With `FORCE` and no
owner policy, the same misconfiguration returns zero rows: loud, immediate, and
impossible to ship past a smoke test.

## Consequences

**Good.** Capability outside tenant scoping exists in exactly two places — the
`job` queue and the two authentication lookups — and both are declared in the
schema rather than implied by application code. The unset-owner
default is empty, not universal. Deleted rows cannot leak through a forgotten
predicate.

**Bad.** Three sets of credentials to manage instead of one. Every policy is
written twice, once per role, and a table added without both policies is
invisible to whichever role was missed. Data-backfilling migrations are blocked
by design: one must temporarily `ALTER TABLE ... NO FORCE ROW LEVEL SECURITY`,
which is deliberate friction, visible in the migration diff, and reviewable.

**Accepted risk.** The worker sets `app.owner_id` in application code. If a
handler queried user data before scoping itself, it would see nothing (fail
closed) rather than everything — but the job would fail confusingly. A shared
helper owns that transition so no handler opens a session by hand.

## Alternatives considered

**`BYPASSRLS` on the worker.** One role, no queue exception. Rejected: it
disables the backstop in the process that parses untrusted uploads, which is
where a parser bug is most likely to become a data-access bug.

**Cross-tenant job access for the application role.** Rejected: it weakens the
guarantee for the role directly reachable by an attacker, to serve a background
process that has no HTTP surface at all.

**A separate queue database.** True isolation of the exception, at the cost of
losing transactional enqueue — the property that makes the deletion outbox in
ADR-0002 correct.

**Application-only tenant filtering, no RLS.** Simpler and one role, but a
single forgotten `WHERE owner_id = ...` becomes a cross-tenant data leak with
nothing behind it.
