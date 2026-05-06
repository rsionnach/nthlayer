# Decision: CloudEvents envelope is auto-detected in v1.5, mandatory in v2

**Status:** Active for v1.5. Reverses (tightens) post-v2.

**Date decided:** 2026-05-02 (during opensrm-saun.1.2 integration test work).

**Context:** opensrm-saun.1.2 (CloudEvents envelope contract mismatch
between respond and core).

## Decision

`nthlayer-core`'s `POST /verdicts` and `POST /assessments` endpoints
**auto-detect** whether the request body is a CloudEvents v1.0 envelope
or a raw record:

- Body has top-level `specversion` field → treat as envelope, unwrap the
  inner `data` payload, validate that.
- Body lacks `specversion` → treat as raw record, validate directly.

Workers send envelopes (per `wrap_verdict` / `wrap_assessment` in
`nthlayer-common.cloudevents`). Tests and pre-saun.1.2 callers can still
POST raw records during the v1.5 transition.

**Error contract** lets callers distinguish transport from domain
issues:

| Status | Error code | `envelope_version` | When |
|---|---|---|---|
| 400 | `envelope_invalid` | `null` | Cannot unwrap (missing CE attribute, wrong specversion, non-dict `data`) |
| 422 | `verdict_invalid` / `assessment_invalid` | `"1.0"` (envelope was good) or `null` (raw path) | Inner record fails field validation |
| 409 | `duplicate` | (n/a) | Inner record's `id` already exists |

The 400-vs-422 split exists so a worker debugging "my POST is rejected"
can immediately see whether it's a transport-level malformation or a
domain-level bad payload, without parsing the detail string.

## Canonical alternative (deferred to v2)

Make the CloudEvents envelope **mandatory** for `POST /verdicts` and
`POST /assessments`. Reject any body lacking `specversion` with
`400 envelope_required`. Require all callers (workers, integration tests,
external producers) to wrap.

This is the v2 target shape. v2 needs the envelope to be load-bearing
because:

- **Sigstore Rekor anchoring** (planned for v2). Rekor signs the
  envelope, not the inner record. A raw-record submission can't be
  anchored.
- **Sigstore signing** of authored verdicts. The envelope's
  `id`/`source`/`type` triple is the canonical reference; the inner
  record's `id` is a duplicate but the envelope's is what's signed.
- **Audit trail completeness.** Envelope-only mandates that every event
  has a `source` (who produced it) and a `time` (when), independent of
  what the inner record carries.

## What's routed to no-ops

In v1.5 the auto-detect path is fully active — nothing is no-op'd. The
deferred work is:

- **Rekor anchoring** (`rekor_anchors` table exists in core's schema
  but is empty in v1.5; never written to). Forward-compat only.
- **Sigstore signing.** `nthlayer-common.cloudevents` does not generate
  signatures.
- **Envelope-required strict mode.** No flag exists in v1.5 to reject
  raw-record submissions.

## When the decision unwinds

Post-v1.5, in the v2 implementation phase:

1. Add `NTHLAYER_ENVELOPE_REQUIRED` env flag to core (off by default in
   v1.5, on by default in v2).
2. Audit every `POST /verdicts` and `POST /assessments` caller:
   - All worker modules already use `wrap_verdict` / `wrap_assessment`
     (post `nthlayer-workers@f998699`). No changes needed.
   - Integration test infra (`test/integration-three-tier.sh`) doesn't
     POST directly. No changes needed.
   - Any external producers (post-v2 third-party integrations) get
     migration guidance from this doc.
3. Implement Rekor anchoring once the envelope is mandatory.
4. Implement Sigstore signing on the producer side.

Reversing this decision early (before v1.5 ships) would require
auditing every caller and is rejected as in-scope creep. The auto-detect
contract is forward-compatible: producers can wrap today and the
behaviour is identical to mandatory-envelope mode.

## Cross-references

Inline code comments that reference this decision (grep target:
"See docs/superpowers/decisions/envelope-contract-auto-detect-to-mandatory.md"):

- `nthlayer-core/src/nthlayer_core/server.py` — `post_verdict`,
  `post_assessment`, `_unwrap_envelope`, `_validate_required` helpers
- `nthlayer-common/src/nthlayer_common/cloudevents.py` — `wrap_verdict`,
  `wrap_assessment`, `parse_cloudevent`, `validate_cloudevent`
- `nthlayer-workers/src/nthlayer_workers/respond/verdict_submission.py` —
  `submit_verdict_to_core` (full envelope submission)

Related decisions:

- [`verdict-assessment-taxonomy-boundary.md`](verdict-assessment-taxonomy-boundary.md) —
  the wire-canonical naming (`type`, `created_at`) that the envelope
  inner-record validation expects.

Specs:

- [`docs/specs/NTHLAYER-TELEMETRY-ENVELOPE-v1.md`](../../specs/NTHLAYER-TELEMETRY-ENVELOPE-v1.md) —
  envelope format specification.

Beads:

- `opensrm-saun.1.2` (closed) — the integration test that surfaced the
  contract mismatch and prompted this decision.
