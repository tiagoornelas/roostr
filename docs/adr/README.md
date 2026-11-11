# Architecture Decision Records (ADR)

This folder contains Architecture Decision Records — lightweight documents that capture important technical decisions, their context, and rationale.

## Format

Each ADR is a markdown file named `NNN-short-title.md` (zero-padded, sequential):

```markdown
# ADR-NNN: Short Title

- **Status:** proposed | accepted | deprecated | superseded by [ADR-NNN](./NNN-short-title.md)
- **Date:** YYYY-MM-DD

## Context

What is the issue motivating this decision?

## Decision

What is the change that we are proposing and/or doing?

## Consequences

What becomes easier or harder as a result of this decision?
```

## A committed ADR is immutable

Once an ADR is merged, its body is a record of what was decided **at that date** — not a description of current behaviour. Do not rewrite it, not even to fix an example that no longer reflects the code.

Only two things may change in a committed ADR:

1. **`Status`** — e.g. `accepted` → `superseded by [ADR-NNN](...)`. Keep the index table below in sync.
2. **An `Amendments` list appended to the header**, one entry per change:

   ```markdown
   - **Amendments:**
     - YYYY-MM-DD — [ADR-NNN](./NNN-short-title.md): what changed, and where the current guidance now lives.
   ```

Anything else — a new decision, a reversal, a widened contract — is a **new ADR** that supersedes or amends the old one.

**Where current behaviour is documented.** Prescriptive guidance belongs in `docs/rules/` and the README, which are meant to be updated as the system evolves.

## Index

| #   | Title                                                                                                   | Status   | Date       |
| --- | ------------------------------------------------------------------------------------------------------- | -------- | ---------- |
| 001 | [Clean Architecture and Local-First Foundation](./001-clean-architecture-and-local-first.md)             | accepted | 2026-11-08 |
| 002 | [AI-Accessible CLI Interface for Autonomous Manipulation](./002-ai-accessible-cli-interface.md)        | accepted | 2026-11-11 |
