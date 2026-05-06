# Decision: Cases are created eagerly at incident-open time, not lazily after triage

**Status:** Active for v1.5.

**Date decided:** 2026-05-05 (during opensrm-saun.1.2 integration test
verification, when the test reached "Wait for respond → case" timeout).

**Context:** opensrm-saun.1.2. The integration test specifies that a
case row must appear in core's case store as soon as respond opens an
incident — not after triage runs.

## Decision

When `respond/worker.py` opens an `IncidentContext` (via
`open_from_snapshot` for the primary correlation-snapshot path or
`open_from_breach` for the fallback breach path), it **immediately**
calls `_create_case_for_incident` to POST a case to core. The case is
created concurrently with the incident-open transition, before any
agent (triage, investigation, communication, remediation) runs.

The case carries:

- `kind: "incident"`
- `underlying_verdict`: the breach verdict id (from
  `snap.data.parent_ids[0]` on the snapshot path; from `breach["id"]` on
  the fallback path) — load-bearing for the bench's lineage walk via
  `GET /verdicts/{id}/ancestors`, which only resolves verdict edges.
- `service`: the affected service (from snapshot domain or breach
  payload).
- `briefing`: the snapshot's `nl_summary` if present, else a
  structured `"{event_count} event(s) on {service}"` line.
- `blast_radius`: environment string for core's `_derive_priority`.
- `has_active_incident: True`.

If the case-creation POST fails, the incident still progresses through
the agent pipeline; the failure is logged but non-fatal (operators
investigating "why no case row" can find it in workers.log).

## Canonical alternative (rejected)

Wait for triage to complete, then create the case using triage's
verdict as the anchor. The case row appears in the bench queue after
the triage agent runs (typically a few seconds after incident open).

Rejected because:

- **Bench queue visibility latency.** Operators expect to see active
  incidents in the queue *now*, not "after the LLM-backed triage agent
  finishes." Lazy creation introduces a visible delay where the system
  has detected an incident but the operator's queue is empty —
  confusing during real outages.
- **Triage failure path becomes ambiguous.** If triage fails or hits
  step_timeout, lazy creation would leave the incident in a state where
  no case ever appears. Eager creation lets the operator see the case,
  notice triage didn't complete, and intervene.
- **Lineage anchoring works either way.** Eager anchors on the breach
  verdict directly; lazy would anchor on the triage verdict (which has
  the breach in its parent_ids). Both let bench's lineage walk reach
  the breach. Eager is one fewer indirection.

## What's routed to no-ops

The "skip case creation when no anchor" path. If the snapshot has no
`parent_ids` (cold-start, post-restart with empty session window, or
future snapshot kinds without QUALITY_SCORE events), respond logs
`respond_case_create_skipped_no_anchor` and continues without creating
a case. The incident still opens; the operator just won't see a row in
the bench queue until either (a) the breach-fallback path runs against
a later breach for the same service, or (b) a manual operator action
creates one.

This was a deliberate trade-off: fabricate a fake anchor (e.g. anchor on
the snapshot id, which is an assessment so the bench's lineage walk
404s) would be worse than leaving the operator a quiet logged warning
to act on.

## When the decision unwinds

Unlikely to unwind. The bench queue's UX is the load-bearing
constraint, and eager creation is the simplest way to satisfy it.

If unwound (e.g. if cases need richer metadata that only triage can
produce, and operators stop expecting immediate queue visibility), the
unwind is mechanical:

1. Remove the `_create_case_for_incident` call from `open_from_snapshot`
   and `open_from_breach`.
2. Move the call to the triage agent's success path in
   `respond/coordinator.py`.
3. Update integration test assertions to wait-triage-first, wait-case-after.

## Cross-references

Inline code comments that reference this decision (grep target:
"See docs/superpowers/decisions/eager-case-creation.md"):

- `nthlayer-workers/src/nthlayer_workers/respond/worker.py` —
  `_create_case_for_incident`, `open_from_snapshot` flow,
  `open_from_breach` flow
- `nthlayer-workers/src/nthlayer_workers/respond/worker_helpers.py` —
  `open_from_snapshot`'s `trigger_verdict_ids` setup
  (`[snap["id"], *parent_ids]`); `open_from_breach`'s
  `[breach["id"]]`

Related decisions:

- [`verdict-assessment-taxonomy-boundary.md`](verdict-assessment-taxonomy-boundary.md) —
  why the case must anchor on a verdict id (not the snapshot
  assessment id), so bench's lineage walk resolves.

Beads:

- `opensrm-saun.1.2` (closed) — the integration test that surfaced the
  case-creation requirement.
- `opensrm-saun.1` (closed parent) — the integration test that pins
  this behaviour: "Wait for respond → case" with a 60s budget after
  triage.
