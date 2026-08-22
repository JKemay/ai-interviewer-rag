## What and why

<!-- The diff shows what changed. Explain why it needed to change, and why
     this approach over the obvious alternative. -->

## How to verify

<!-- Commands or steps a reviewer runs to confirm this works. "Ran the tests"
     is not verification; the tests run themselves in CI. -->

## Risk

<!-- What could this break? What did you consider and decide against?
     "None" is a valid answer if it's true. -->

## Checklist

- [ ] Self-reviewed the diff
- [ ] Tests cover the failure paths, not just the happy path
- [ ] No secrets, credentials, or document text in code, fixtures, or logs
- [ ] ADR added if this makes a decision that would be expensive to reverse
- [ ] `openapi.json` regenerated if any response model changed
