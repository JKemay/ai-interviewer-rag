# Contributing

Solo project, team conventions. The point is that the workflow survives contact
with a second person — and with you, six months from now, having forgotten
everything.

## Local setup

```bash
cp .env.example .env          # then fill in the generated secrets
docker compose up -d          # postgres, minio, api
cd apps/api && uv sync
uv run pre-commit install     # once per clone
```

Verify the stack:

```bash
curl localhost:8000/healthz   # {"status":"ok"}
docker compose ps             # all services healthy
```

## Branches

Cut every branch from a freshly pulled `main`:

```bash
git switch main && git pull
git switch -c feat/short-description
```

**Those two lines are not ceremony.** `main` is squash-merged, so merging a PR
replaces your commits with one *new* commit. A branch cut from a stale `main`
still carries the originals, and Git treats them as unrelated work — you get
conflicts in files nobody actually edited twice. If it happens, don't resolve
them by hand; replant the branch instead:

```bash
git rebase --onto origin/main <last-commit-already-on-main>
```

Prefixes: `feat/`, `fix/`, `chore/`, `docs/`, `ci/`, `refactor/`, `test/`.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/):
`type(scope): imperative summary`.

Small and logical — a reviewer should be able to read the commit sequence and
follow the reasoning. The body explains **why**; the diff already shows what.
When a change fixes a non-obvious bug, describe the failure mode, because that
is the part nobody can reconstruct later.

## Pull requests

1. CI must be green. All three checks are required and `main` is protected
   against direct pushes, including for admins.
2. Your branch must be up to date with `main` before merging (`strict` mode).
   Use the **Update branch** button or rebase.
3. Self-review the diff first. You will find something.
4. Squash merge; the branch deletes itself.

Required approvals is deliberately **0** — GitHub does not allow approving your
own PR, so requiring one would deadlock a single-maintainer repository. The PR
gate is still enforced; only the human approval is unavailable.

## Tests

Coverage must stay at or above 80%, but the number is a floor, not a goal.
Prefer tests that pin behaviour someone might plausibly break:

- Authorization **negative** tests — proving user A cannot reach user B's data.
- Failure paths — a 500 that leaks a connection string is a security bug, and
  only a test that asserts on the response body will catch it.
- Invariants that look like ceremony until they aren't — `/healthz` checking no
  dependencies, the OpenAPI schema matching the code.

Real examples of bugs caught this way live in `apps/api/tests/`.

## Architecture decisions

A decision that was expensive to make and would be expensive to reverse gets an
ADR in [`docs/adr/`](docs/adr/). Routine choices do not. See that directory's
README for the format and the bar.

## Security

- Never commit a real `.env`. `detect-private-key` runs pre-commit, but the only
  reliable defence is not pasting secrets into files.
- Uploaded documents and candidate answers are **untrusted input**, including
  when they reach the language model. Treat them as data, never instructions.
- Logs must never contain document text. Resumes are PII.
