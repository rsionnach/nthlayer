# Decision: Production side-effects live in hot-path workers, not CLI commands

**Status:** Active for v1.5.

**Date decided:** 2026-05-02 (during opensrm-saun.1.2 integration test
work, when audit-trail writes were appearing in two places with
different shapes).

**Context:** opensrm-saun.1.2 (CloudEvents envelope contract mismatch)
and opensrm-saun.1.2.1 (correlate cold-path migration to assessments).

## Decision

For the v1.5 ecosystem, **production side-effects have a single canonical
surface: the hot-path worker modules.**

By "production side-effect" we mean:

- Writes to the content-addressed decision-record audit trail
  (`nthlayer-common.records`).
- Verdict / assessment submissions to nthlayer-core.
- Slack notifications to operator channels.
- Downstream pipeline triggering (e.g. respond consuming correlate's
  output).
- OTel events emitted as part of the canonical pipeline trace.

These all live in:

- `nthlayer-workers/src/nthlayer_workers/observe/worker.py` —
  ObserveCollectModule, ObserveDriftModule, ObserveTopologyModule.
- `nthlayer-workers/src/nthlayer_workers/measure/worker.py` —
  MeasureModule.
- `nthlayer-workers/src/nthlayer_workers/correlate/worker.py` —
  CorrelateSessionModule, CorrelateTopologyModule, CorrelateContractModule.
- `nthlayer-workers/src/nthlayer_workers/respond/worker.py` —
  RespondModule + supporting agents.
- `nthlayer-workers/src/nthlayer_workers/learn/worker.py` —
  LearnOutcomeModule, LearnRetrospectiveModule.

The CLI subcommands (`nthlayer-correlate {serve,replay,correlate}`,
`nthlayer-respond {replay,respond,...}`, `nthlayer-measure
{evaluate-once,...}`, `nthlayer-observe {collect,...}`) are **operator-
invoked ad-hoc tools**. They reuse common helpers (model invocation,
manifest loading, scoring math) but skip the persistent side effects
that the worker modules own.

## Canonical alternative (rejected)

Symmetric ownership: every CLI subcommand carries the full side-effect
machinery so a CLI invocation is operationally identical to a worker
cycle.

Rejected because:

- **Two surfaces for one job.** A "submit a verdict" path that runs in
  both worker.py and cli.py with subtly different code paths invites
  contradictory behaviour. We've already seen this once: the legacy
  CLI emitted `correlation` pseudo-verdicts while the hot path emitted
  `correlation_snapshot` assessments. opensrm-saun.1.2.1 fixed it by
  migrating the CLI to match the worker.
- **Notification storms.** A CLI run that's used for ad-hoc
  troubleshooting shouldn't page the on-call. If the CLI carried the
  notification surface, every dev run would either spam Slack or
  require a `--no-notify` opt-out per call.
- **Audit-trail confusion.** Decision records are a chained content-
  addressed log. CLI ad-hoc runs with full audit writes would
  interleave operator experiments with production records, making
  forensic queries harder.
- **Review burden.** During the consolidation phase (RM.1–RM.7 +
  Phase 3 worker module fills), doubling the side-effect surface
  doubles the review load and the test surface. Better to ship one
  canonical path and ship it well.

## What's routed to no-ops

CLI subcommands that previously carried side effects in the deprecated
standalone repos retain the call-sites but skip the production path:

- Decision-record writes (catches `AttributeError` on missing
  `write_decision_assessment` helper, logs warning, continues).
- Slack notifications (gated on a feature flag default-off in CLI mode).
- Downstream CLI-to-CLI triggering (allowlist-restricted to a small
  vetted argument set).

Detail: see [`legacy-cli-maintenance-mode.md`](legacy-cli-maintenance-mode.md).

## When the decision unwinds

Unlikely to fully unwind — the worker pipeline IS the v1.5 architecture
(Tier 2 of the three-tier model). The CLI surface might shrink (some
operator commands move into the bench TUI per Phase 4 work) but the
ownership rule holds.

If a specific CLI subcommand needs to participate in production audit
flows post-v1.5, the unwind is local to that command:

1. Implement the missing helper in `nthlayer-common` (e.g.
   `write_decision_assessment` for assessment-shaped audit chains).
2. Add the side-effect call to the CLI command, gated behind an
   explicit `--audit` flag (or env var) so the ad-hoc default stays
   side-effect-free.
3. Update [`legacy-cli-maintenance-mode.md`](legacy-cli-maintenance-mode.md)
   with the unwound path.

## Cross-references

Inline code comments that reference this decision (grep target:
"See docs/superpowers/decisions/hot-path-vs-cli-side-effect-ownership.md"):

- `nthlayer-workers/src/nthlayer_workers/correlate/cli.py` — `_serve_loop`,
  `replay_command`, `correlate_command` (no decision-record writes;
  no Slack on assessment path)
- `nthlayer-workers/src/nthlayer_workers/respond/cli.py` —
  replay path with mocked verdict store
- `nthlayer-workers/src/nthlayer_workers/measure/cli.py` —
  `cmd_evaluate_once` (writes to local stores via `_write_decision_record`
  helper but not the canonical worker path)

Related decisions:

- [`legacy-cli-maintenance-mode.md`](legacy-cli-maintenance-mode.md) —
  the specific list of what's routed to no-ops in the CLI surface.
- [`verdict-assessment-taxonomy-boundary.md`](verdict-assessment-taxonomy-boundary.md) —
  why the CLI's pseudo-verdict era ended (assessments are observations,
  not decisions; CLI replay/serve modes emit observations).

Specs:

- [`docs/specs/NTHLAYER-SERVE-MODE-v2.1.md`](../../specs/NTHLAYER-SERVE-MODE-v2.1.md) —
  Tier 2 worker pipeline specification.

Beads:

- `opensrm-saun.1.2` (closed) — the integration test work that pinned
  the worker pipeline as the canonical surface.
- `opensrm-saun.1.2.1` (closed) — migrated correlate cold-path; CLI
  side-effects routed to no-ops.
