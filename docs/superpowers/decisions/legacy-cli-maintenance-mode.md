# Decision: Legacy CLI subcommands run in maintenance mode for v1.5

**Status:** Active for v1.5. Reverses post-v1.5.

**Date decided:** 2026-05-02 (during opensrm-saun.1.2 integration test work).

**Context:** opensrm-saun.1.2 (CloudEvents envelope contract mismatch).

## Decision

Several CLI subcommands inherited from the deprecated standalone repos
(`nthlayer-correlate`, `nthlayer-respond`) keep running in v1.5 but with
their **production side-effects routed to no-ops**:

- `nthlayer-correlate serve` — continuous snapshot generation
- `nthlayer-correlate replay` — scenario fixture replay
- `nthlayer-correlate correlate` — live triggered correlation
- `nthlayer-respond replay` — scenario fixture replay

The CLI surface stays callable so operator muscle memory and existing
scripts don't break. The judgment logic (model interpretation, scenario
parsing, verdict shape) still runs and writes to the local stores. What's
routed to no-ops:

- **Decision-record writes** to the content-addressed audit chain
  (`nthlayer-common.records`). The `write_decision_assessment` helper that
  CLI commands need to participate doesn't exist yet; the bridge code
  catches `AttributeError` and silently skips, leaving a `# TODO(post-v1.5)`
  marker.
- **Slack notifications.** The notifier module exists for the verdict
  shape; the CLI emits assessments now (per opensrm-saun.1.2.1) and the
  assessment-shaped Slack block builder hasn't been written. The
  notification call is gated on a feature flag that's off by default in
  CLI mode.
- **Downstream pipeline triggering** (CLI invoking another CLI). The
  worker pipeline owns the canonical chain in v1.5; CLI replay/serve
  modes don't trigger downstream components. The legacy
  `--respond-args` forwarding code path is preserved but allowlist-gated
  to a small set of pre-vetted argument names.

The hot-path **worker** modules (`correlate/worker.py`, `respond/worker.py`,
`measure/worker.py`, `observe/worker.py`, `learn/worker.py`) carry the full
production side-effect responsibility. They are the canonical surface
for v1.5.

## Canonical alternative (rejected for v1.5)

Make the CLI commands first-class citizens of the v1.5 pipeline by
porting each missing capability:

1. Implement `write_decision_assessment(store, *, agent, ...)` in
   `nthlayer-common.records` so CLI emissions chain into the audit
   trail.
2. Add an assessment-shaped Slack block builder so CLI runs notify the
   same channels worker runs do.
3. Wire the legacy CLI-to-CLI forwarding into the worker pipeline so the
   chain is consistent regardless of entry point.

Rejected for v1.5 because the worker pipeline is the v1.5 architectural
surface (Tier 2, per the three-tier decision). Doubling the
side-effect surface during the consolidation phase risks contradictory
behaviour between CLI and worker paths and consumes review effort that
should land features for shipping.

## What's routed to no-ops

| Site | Behaviour in v1.5 | What unblocks it |
|---|---|---|
| `nthlayer-correlate serve/replay/correlate` decision-record write | Skipped silently; logger.warning at startup. | `write_decision_assessment` helper in `nthlayer-common.records` |
| `nthlayer-correlate correlate` Slack notification | Skipped; no warning (assessment path doesn't have a builder yet) | Assessment-shaped Slack block builder in `nthlayer-correlate.notifications` |
| `nthlayer-respond replay` Slack notification | Skipped; gated on env var (off by default) | Same as above |
| `nthlayer-respond replay` decision-record write | Skipped silently | Same `write_decision_assessment` helper |
| `nthlayer-correlate correlate` `--respond-args` forwarding | Allowlist-restricted to `{specs-dir, config, notify}` | Worker pipeline owns triggering in v1.5; full forwarding unlikely to come back |

## When the decision unwinds

Post-v1.5, when the worker pipeline's behaviour stabilises and the
helpers above are written:

1. Implement `write_decision_assessment` (track separately).
2. Implement assessment-shaped Slack block builders.
3. Re-enable the no-op'd side effects in CLI commands by removing the
   guards.
4. Decide whether the CLI commands continue to exist (operator workflows)
   or are deprecated in favour of bench operator surfaces.

If the decision is reversed, the inline pointer comments at the affected
code sites need updating in lockstep with this document.

## Cross-references

Inline code comments that reference this decision (grep target:
"See docs/superpowers/decisions/legacy-cli-maintenance-mode.md"):

- `nthlayer-workers/src/nthlayer_workers/correlate/cli.py` — `_serve_loop`,
  `replay_command`, `correlate_command`
- `nthlayer-workers/src/nthlayer_workers/respond/cli.py` — `_build_incident_context`
  no-model path
- `nthlayer-workers/src/nthlayer_workers/correlate/snapshot/model.py` —
  `ModelInterface.interpret` (assessment emission, opensrm-saun.1.2.1)

Related decisions:

- [`hot-path-vs-cli-side-effect-ownership.md`](hot-path-vs-cli-side-effect-ownership.md) —
  the broader principle that production side-effects live in workers.
- [`verdict-assessment-taxonomy-boundary.md`](verdict-assessment-taxonomy-boundary.md) —
  why correlate's CLI emits assessments instead of pseudo-verdicts now.

Beads:

- `opensrm-saun.1.2` (closed) — the CloudEvents envelope work that surfaced this maintenance-mode pattern.
- `opensrm-saun.1.2.1` (closed) — migrated correlate cold-path from
  pseudo-verdicts to assessments; left CLI side-effects no-op'd.
