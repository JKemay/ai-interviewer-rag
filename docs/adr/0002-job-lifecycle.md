# ADR-0002: Background job lifecycle

- **Status:** Accepted
- **Date:** 2026-08-22

## Context

Document ingestion — verifying uploaded bytes, parsing, chunking, embedding —
cannot run inside a request. It is slow, it runs untrusted-input parsers that
need resource limits, and it must survive a process restart partway through.

Blob deletion has the same shape for a different reason: Postgres and object
storage cannot commit atomically, so "delete the row and delete the object" is
two operations that can partially fail.

Both need a queue. `SKIP LOCKED` is frequently presented as the answer, but it
is only the *claim* mechanism — it says nothing about what happens when a worker
dies holding a job. The lifecycle around it is the actual design.

## Decision

A `job` table in Postgres, drained by a separate worker process.

### Claiming

```sql
UPDATE job SET status = 'running', locked_at = now(), locked_by = $worker,
               attempts = attempts + 1
WHERE id = (
  SELECT id FROM job
  WHERE status = 'pending' AND run_after <= now()
  ORDER BY run_after
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
RETURNING *;
```

`SKIP LOCKED` lets concurrent workers step over rows another worker has locked
instead of blocking behind them.

### Leasing and recovery

A claimed job carries `locked_at` and `locked_by`. A worker that is killed —
OOM, deploy, crash — leaves its job in `running` forever. So a lease expiry
reclaims jobs whose `locked_at` is older than the lease:

```sql
UPDATE job SET status = 'pending', locked_at = NULL, locked_by = NULL
WHERE status = 'running' AND locked_at < now() - interval '15 minutes';
```

The lease must exceed the slowest legitimate job, or a long job gets reclaimed
and run twice concurrently. Long-running jobs heartbeat `locked_at`.

### Retries and dead-lettering

Failures increment `attempts` and reschedule with exponential backoff and
jitter — `run_after = now() + base * 2^attempts ± jitter`. Jitter matters
because a dependency outage fails every in-flight job at once, and without it
they all retry simultaneously and fail again together.

Past `max_attempts` the job moves to `failed` and stops. A poison job — a
malformed PDF that crashes the parser every time — must not retry forever;
`failed` is a queryable state that surfaces in monitoring.

### Idempotency

Every job carries an idempotency key (`document_id` plus job type). Reclaim and
retry both mean a job can run more than once, so handlers are written so that a
second run is harmless: chunks are upserted on `(document_id, ordinal)`, not
appended, and blob deletion treats "already gone" as success.

**At-least-once, not exactly-once.** Exactly-once across a database and an
object store is not achievable without distributed transactions; idempotent
handlers make at-least-once sufficient.

### Observability

`attempts`, `locked_by`, `run_after`, and `last_error` are columns, so "what is
stuck and why" is a SQL query. Queue depth and oldest-pending-age are the two
metrics that matter: depth alone looks fine while one job starves at the front.

## Consequences

**Good.** No Redis or broker to operate, back up, or secure. Jobs enqueue in the
same transaction as the data change that caused them, so there is no window
where a document exists with no ingestion job — which is what makes the deletion
outbox correct. The full queue is inspectable with `psql`.

**Bad.** Polling has latency the queue depth does not justify at low volume;
`LISTEN`/`NOTIFY` can reduce it later. Throughput ceilings are far lower than a
real broker — irrelevant here, disqualifying at high volume. Long transactions
in the same database can interact badly with queue contention.

**Accepted risk.** The lease duration is a tuning parameter with a bad failure
mode on both sides: too short duplicates work, too long delays recovery. It is a
configuration value with a documented rationale, not a magic number.

## Alternatives considered

**Celery + Redis.** Mature and featureful, but adds a broker and a result
backend to operate and secure, and loses transactional enqueue — the thing that
makes the outbox pattern work.

**Cloud queue (SQS and similar).** Managed and durable, same loss of
transactional enqueue, plus a provider dependency in local development.

**In-process background tasks (FastAPI `BackgroundTasks`).** No durability
whatsoever: a restart loses the work silently, with no record it existed.
