# Architecture Decision Records

An ADR captures a decision that was **expensive to make and would be expensive
to reverse** — the kind of thing where, six months later, someone (probably you)
asks "why on earth is it like this?"

## What earns an ADR

- A choice between viable alternatives, where the losing option was genuinely
  defensible.
- A constraint that will look arbitrary to anyone who wasn't in the room.
- A decision that shapes code we haven't written yet.

Routine choices — a library version, a file layout — do not earn one. If the
answer to "why?" is obvious from the code, there is nothing to record.

## Format

Numbered, immutable, and append-only. An ADR is a record of what was decided
*at that time*, so we don't rewrite history: when a decision changes, write a
new ADR and mark the old one `Superseded by ADR-NNNN`.

```markdown
# ADR-NNNN: Short title in the imperative

- **Status:** Proposed | Accepted | Superseded by ADR-NNNN
- **Date:** YYYY-MM-DD

## Context
The forces at play. What makes this decision necessary and non-obvious.

## Decision
What we're doing, stated plainly.

## Consequences
What this makes easy, what it makes hard, and what we're accepting as a cost.
The honest downsides go here — an ADR with no downsides is marketing.

## Alternatives considered
What else was on the table and why it lost.
```

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-technology-stack.md) | Technology stack | Accepted |
| [0002](0002-job-lifecycle.md) | Background job lifecycle | Accepted |
