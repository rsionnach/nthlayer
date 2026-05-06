# Architectural decisions

Durable records of architectural decisions made during NthLayer ecosystem
development. Each decision has its own markdown file with a consistent
structure:

1. **Decision** — what was decided and the context.
2. **Canonical alternative** — what was rejected, and why.
3. **What's routed to no-ops** — concrete implementation gaps that
   shipped with the decision (so future readers know what's deferred
   versus what's intentional behaviour).
4. **When the decision unwinds** — the conditions under which this
   decision should be revisited or reversed, and the mechanical
   unwinding steps.
5. **Cross-references** — code sites that reference this decision via
   `See docs/superpowers/decisions/<file>.md` inline comments, related
   decision docs, related specs, related beads.

## Why this format

Inline code comments rot. Bead descriptions are time-bound (closed bead
≠ frozen reasoning). Spec docs describe the canonical state, not the
choices that produced it. Decision docs sit between: durable, structured,
linked to both the code that implements them and the beads that
prompted them.

## When to write one

Write a decision doc when:

- An architectural choice has a non-obvious rationale.
- The same code surface looks "wrong" without context (e.g.
  divergent conventions, no-op'd side-effects, deliberately deferred
  features).
- Reversing the decision would require coordinated changes across
  multiple files or repos.

Skip when:

- The choice is documented adequately in a spec or in inline comments.
- The reasoning is implicit in the code's structure.
- The decision is operational hygiene (e.g. dependency pin choices
  go in CHANGELOG entries, not here).

## Current decisions

| File | Status | Subject |
|---|---|---|
| [legacy-cli-maintenance-mode.md](legacy-cli-maintenance-mode.md) | Active for v1.5 | Legacy CLI subcommands' side-effects routed to no-ops |
| [envelope-contract-auto-detect-to-mandatory.md](envelope-contract-auto-detect-to-mandatory.md) | Active for v1.5 | CloudEvents envelope auto-detect on POST /verdicts + /assessments |
| [verdict-assessment-taxonomy-boundary.md](verdict-assessment-taxonomy-boundary.md) | Stable | Verdicts are decisions, assessments are observations |
| [eager-case-creation.md](eager-case-creation.md) | Active for v1.5 | Cases created at incident-open, before triage runs |
| [hot-path-vs-cli-side-effect-ownership.md](hot-path-vs-cli-side-effect-ownership.md) | Active for v1.5 | Worker modules own production side-effects; CLI is ad-hoc only |

## Linking from code

Use the exact string `See docs/superpowers/decisions/<file>.md` so a
single grep across the ecosystem finds every reference. When a decision
unwinds, that grep is the audit trail of which sites need updating in
lockstep with the doc.

## Linking from beads

Reference decisions in bead descriptions when the bead's resolution
embodies the decision. Beads close; the doc remains the durable
artifact.
