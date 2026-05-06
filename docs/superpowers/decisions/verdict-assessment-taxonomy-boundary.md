# Decision: Verdicts are decisions, assessments are continuous observations

**Status:** Stable. Foundational v1.5 distinction.

**Date decided:** 2026-05-02 (during opensrm-saun.1.2 integration test work,
formalised when removing the spurious `"assessment"` entry from
`VALID_VERDICT_TYPES`).

**Context:** opensrm-saun.1.2 (CloudEvents envelope contract mismatch).

## Decision

The `nthlayer-common` data model has two distinct primitives, and they
are **not** interchangeable:

- A **verdict** is a discrete decision made about a specific subject at
  a specific point in time. Examples: a triage agent's severity call;
  a quality_breach detection; an approval grant; an action_request.
  Verdicts go in the verdict store, get content-addressed hashes (in
  v2), participate in the lineage graph, and have outcomes resolved
  later.
- An **assessment** is a continuous observation of system state.
  Examples: a SLO status reading; a portfolio status roll-up; a
  correlation snapshot describing a session window of related events;
  a topology drift report. Assessments go in the assessment store and
  are read by downstream consumers as input to *their* decisions.

The defining test: **"Is this a judgment about something, or an
observation of something?"** Judgments are verdicts. Observations are
assessments.

Three concrete consequences for the type taxonomy:

1. **`correlation_snapshot`** is an assessment, not a verdict.
   correlate's session-window output describes "here's a window of
   events in this domain" — that's observation. The downstream respond
   module makes a *decision* (triage verdict) using the snapshot as
   input. The snapshot itself is not a decision.

2. **`topology_drift`** and **`contract_divergence`** are assessments
   for the same reason. They describe what's drifted/diverged; they
   don't decide what to do about it.

3. The string `"assessment"` was removed from `VALID_VERDICT_TYPES` in
   `nthlayer-common.verdicts.models`. It was a category error — there
   is no verdict type called "assessment", because assessments aren't
   verdicts.

Canonical sources of the type sets:

- `nthlayer_common.verdicts.models.VALID_VERDICT_TYPES` — the
  decisional taxonomy. Adding a new verdict type happens here.
- `nthlayer_common.cloudevents.ASSESSMENT_KINDS` — the observational
  taxonomy. Adding a new assessment kind happens here.
- `nthlayer_common.cloudevents._VERDICT_TYPES` re-exports
  `VALID_VERDICT_TYPES` to keep the wire format and the typed-column
  model in lockstep — adding a verdict type updates both surfaces in
  one place.

## Canonical alternative (rejected)

Collapse the two primitives into one ("everything is a verdict" or
"everything is an event"). The simplification appeals to anyone who
imports both the verdicts and assessments stores into the same call.

Rejected because:

- The lineage graph semantics differ. Verdicts have outcomes (confirmed,
  overridden, expired, ...). Assessments don't have outcomes — they're
  observations, not predictions. Modelling them the same way bakes a
  philosophical confusion into the schema.
- The retention policy differs. Verdicts that are referenced by surviving
  cases are preserved indefinitely; assessments expire on a 90-day
  default. Same model would force one policy or the other.
- The lineage walk semantics differ. `GET /verdicts/{id}/ancestors`
  walks verdict-to-verdict edges; assessments are reachable
  *transitively* through the verdicts that reference them. Collapsing
  would either bloat the verdict graph with non-decisions or hide
  assessments behind inaccessible edges.

## What's routed to no-ops

This decision is taxonomic. Nothing is no-op'd. The decision shaped
several v1.5 implementation details:

- correlate's `_emit_snapshot` calls `submit_assessment`, not
  `submit_verdict`.
- correlate's cold-path CLI (serve/replay) was migrated from
  pseudo-verdict emission to assessment emission in opensrm-saun.1.2.1.
- respond's `worker_helpers.open_from_snapshot` reads
  `snap.data.parent_ids` (the underlying QUALITY_SCORE verdict ids) so
  the verdict-ancestors API can reach the breach via verdict edges,
  bypassing the snapshot's assessment-ness.

## When the decision unwinds

Unlikely to unwind. The verdict/assessment split is a foundational
v1.5 architectural distinction adopted in
[`docs/specs/NTHLAYER-SERVE-MODE-v2.1.md`](../../specs/NTHLAYER-SERVE-MODE-v2.1.md)
and `NTHLAYER-LEARN-v1.md`. v2's content-addressing (IPLD CIDs) preserves
the split.

If a future version unifies them, the canonical-sources rule is the
single load-bearing pin: every other site reads `VALID_VERDICT_TYPES` and
`ASSESSMENT_KINDS`, so a unification touches just those two locations
plus the storage tier.

## Cross-references

Inline code comments that reference this decision (grep target:
"See docs/superpowers/decisions/verdict-assessment-taxonomy-boundary.md"):

- `nthlayer-common/src/nthlayer_common/verdicts/models.py` —
  `VALID_VERDICT_TYPES` definition (carries the prose explaining the
  category-error removal of `"assessment"`)
- `nthlayer-common/src/nthlayer_common/cloudevents.py` —
  `_VERDICT_TYPES` (imports from verdicts.models),
  `ASSESSMENT_KINDS` (canonical assessment taxonomy)
- `nthlayer-workers/src/nthlayer_workers/correlate/worker.py` —
  `_emit_snapshot` (assessment, not verdict)
- `nthlayer-workers/src/nthlayer_workers/correlate/snapshot/model.py` —
  `ModelInterface.interpret` (assessment emission, post saun.1.2.1)
- `nthlayer-workers/src/nthlayer_workers/respond/worker_helpers.py` —
  `open_from_snapshot` (reads parent_ids to bridge snapshot→breach
  lineage via verdict edges)

Related decisions:

- [`envelope-contract-auto-detect-to-mandatory.md`](envelope-contract-auto-detect-to-mandatory.md) —
  the wire format that distinguishes verdicts from assessments via
  CloudEvents `type` attribute (`io.nthlayer.verdict.*` vs
  `io.nthlayer.assessment.*`).

Specs:

- [`docs/specs/NTHLAYER-LEARN-v1.md`](../../specs/NTHLAYER-LEARN-v1.md) —
  verdict data primitive specification.
- [`docs/specs/NTHLAYER-SERVE-MODE-v2.1.md`](../../specs/NTHLAYER-SERVE-MODE-v2.1.md) —
  pipeline architecture using both primitives.

Beads:

- `opensrm-saun.1.2` (closed) — the integration test work that
  surfaced the `"assessment"` category error and prompted formalising
  this taxonomy.
- `opensrm-saun.1.2.1` (closed) — migrated correlate cold-path from
  pseudo-verdicts to assessments.
