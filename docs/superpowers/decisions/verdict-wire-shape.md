# Decision: the canonical verdict wire shape, its relations, and the legacy stores

**Status:** DECIDED 2026-11-23 (Rob), under opensrm-7t3q. The follow-up beads
listed below carry the implementation.

**Context:** opensrm-7t3q, raised by the 2026-11-01 shape review (S1/S3) and
re-verified against `main` on 2026-11-23 (common adaa35b, core 485e83e,
workers c27d7e5, bench 45dc236, adapter 9bb1993). It builds on
[decision-source-of-truth.md](decision-source-of-truth.md) (opensrm-5lxs): core's
store is the store of record, keyed on `nthlayer.decision.id`, which is not
the verdict id. Related: opensrm-vmnc, opensrm-ikpq, opensrm-jmy.20,
[legacy-cli-maintenance-mode.md](legacy-cli-maintenance-mode.md),
[envelope-contract-auto-detect-to-mandatory.md](envelope-contract-auto-detect-to-mandatory.md),
[verdict-assessment-taxonomy-boundary.md](verdict-assessment-taxonomy-boundary.md).

## The problem, measured

**Four shapes reach `POST /verdicts`.**

| producer | shape | site |
|---|---|---|
| workers respond | `wrap_verdict(to_dict(verdict))` | `respond/verdict_submission.py:40-47` |
| workers measure | a hand-built flat dict `{id, created_at, type, service, parent_ids, data}`, wrapped | `measure/worker.py:258-335`, `measure/thresholds/phase.py:302-313` |
| core itself | a hand-built `outcome_resolution` dict, no `outcome` object | nthlayer-core `server.py:372-383` |
| bench | raw `to_dict(verdict)`, no envelope | `sre/reasoning_capture.py:224` |

Core checks only that `id`, `type` and `created_at` are present
(`server.py:276-280`); it checks neither the type set nor the body, and
stores the dict as sent. Reading a verdict back assumes the full shape:
`from_dict` requires `version`, `producer`, `subject` and `judgment`
(common `verdicts/serialise.py:84-92`), so `POST /verdicts/{id}/override` on a
measure or `outcome_resolution` verdict most likely fails with an unhandled
error (inferred, not reproduced).

**Outcomes never reach the original.** `POST /verdicts/{id}/outcome` writes an
`outcome_resolution` child and leaves the original untouched
(`server.py:350-396`), while `/override` mutates the original's outcome in
place by compare-and-swap (`server.py:399-457`, `store.py:258-327`). Learn
skips `outcome_resolution` records and treats a missing outcome as pending
(`learn/worker.py:33-62`), so an original with an outcome still reads
pending.

**`parent_ids` carries five relations in one untyped list:** the chain
predecessor, or the trigger ids when there is no chain (respond,
`agents/base.py:209-216`); the evaluated assessment as evidence (measure,
`worker.py:263`, an assessment id, sometimes the empty string); the breaches
that caused an `autonomy_change` (`worker.py:322`); the original an outcome
resolves (`server.py:377`); and the case verdict an operator note annotates
(bench, `reasoning_capture.py:206`). Core indexes all of them as one
transitive lineage (`store.py:393-420`), and its ancestor and descendant
queries join to `verdicts` (`store.py:464-495`), so assessment ancestors
drop out silently.

**Two `Verdict` dataclasses.** `verdicts.models.Verdict` (the wire and store
shape, `verdicts/models.py:158-174`) and `records.models.Verdict` (the
hash-chained decision record, `records/models.py:126-143`). The only link is
`records/verdict_bridge.write_decision_verdict`, filled by respond when a
`decision_store` is set, which worker mode never does
(`respond/worker.py:202-209`).

**Three verdict stores.** Core's `Store` is the live store of record. Common's
`SQLiteVerdictStore` and `SQLiteDecisionRecordStore` are reached only from the
workers CLIs. Checked 2026-11-23: no worker path writes to the records store
(`observe/incident.py` has no non-test caller, learn's retrospective write is
reached only from the CLI, and respond's `decision_store` is unset in worker
mode). opensrm-jmy.20 proposed unifying `SQLiteVerdictStore`'s schema with
core's.

No normative verdict schema exists in OpenSRM. A1 §4.1 defines the
`nthlayer.decision` event attributes, not the verdict record.

## Decision

1. **`verdicts.Verdict.to_dict` is the one wire shape.** The CloudEvents
   envelope stays auto-detect (its own decision record). Two conditions:
   - **An optional `decision_id`** (`nthlayer.decision.id`) joins the shape
     before enforcement lands. A verdict that is a decision carries it.
   - **Enforcement follows evidence, not a date.** Until then core logs and
     counts every `POST /verdicts` that would fail `from_dict`, by producer.
     Enforcement flips once that count has been zero across a release.

2. **An outcome is a child, never a mutation.** The `outcome_resolution`
   child is the record; `/outcome` never changes the original. For each
   decision, core derives two values from its children:
   - **reversed**, counted once (A1 §4.6 C2);
   - **the outcome in effect**: the latest by `Timestamp`, ties broken by
     receipt order (C3).

   Core returns that derived state on `GET /verdicts/{id}` and on list
   reads. No reader joins, and the original stops reading pending. Core may
   cache the derived state, but only as a value recomputed from the
   children. `/override`'s in-place mutation, and its rule that
   `decision_id` equals the verdict id, conflict with this and with 5lxs.
   They go in a follow-up bead.

3. **`parent_ids` is verdict-to-verdict chain lineage only.** Every other
   relation is a typed entry `{kind, id, target_kind}` drawn from a closed
   set of kinds. `target_kind` is `verdict` or `assessment`. Assessment ids
   never go in `parent_ids`.

   | kind | from → to | keeps the target alive under retention |
   |---|---|---|
   | `outcome_of` | outcome child → the decision it resolves | yes |
   | `reverses` | reversal child → the decision it reverses | yes |
   | `annotates` | note → the verdict it annotates | yes |
   | `cause` | verdict → a verdict that caused it | yes |
   | `evidence` | verdict → the assessment or verdict it was judged on | no |
   | `trigger` | verdict → the assessment or verdict that started its run | no |

   Retention keeps a verdict alive while it has a younger chain descendant,
   a younger child naming it by a kind marked yes, or a case that references
   it. `evidence` and `trigger` targets are mostly assessments, which follow
   their own retention.

4. **The legacy stores retire with the legacy CLIs; the hashing does not.**
   `SQLiteVerdictStore` and the records store stay in maintenance mode for
   the CLIs and go when the CLIs go. `canonical_json` and `compute_hash`
   stay in common, because they define the content-addressed decision id
   (5lxs decision 2). Workers' hard rule 5 is reworded when the records
   store goes. `records.Verdict` is renamed `DecisionRecord` now, with no
   converter beyond the existing bridge. opensrm-jmy.20 is closed as
   superseded.

## Canonical alternative (rejected)

- **Two typed shapes,** a lightweight event verdict for measure and outcomes
  beside the full decision shape. Rejected: every reader would have to
  branch on shape, and one shape is cheaper to enforce at core.
- **A mandatory envelope now.** Rejected for this record. The envelope has
  its own decision, and bench's raw POST passes either way once the body is
  canonical.
- **Mutating the original on `/outcome`,** as `/override` does. Rejected: C3
  needs every outcome and its receipt order, and an in-place outcome keeps
  only the last one.
- **Leaving outcomes as children that readers join.** Rejected: each reader
  would re-implement C2 and C3, which is the problem 5lxs exists to end.
- **One `parent_ids` list with its meanings documented.** Rejected: core
  cannot index or retain by meaning, and assessment ids would still vanish
  from verdict lineage.
- **Unifying `SQLiteVerdictStore` with core's schema** (opensrm-jmy.20).
  Rejected: it keeps a second store of record alive with nothing on the
  worker path to justify it.

## What's routed to no-ops

Until the follow-ups land:

- Core keeps accepting all four shapes. The non-canonical ones are only
  logged and counted (opensrm-5gpu).
- Originals with an outcome still read pending (opensrm-5lo1).
- `/override` still mutates in place and keys on the verdict id
  (opensrm-9pz6, opensrm-vmnc).
- `parent_ids` still carries every relation, and assessment ancestors still
  drop out of lineage queries (opensrm-gz58).

## When the decision unwinds

Revisit if OpenSRM gains a normative verdict schema that differs from
`to_dict`: the spec then wins, and core enforces the spec's shape instead.
Revisit the retention column if a relation kind turns out to be needed for
audit after its source is gone. Revisit the legacy stores if a supported
offline mode (no core) is ever wanted; that would be a new decision, not a
reversal of this one.

## Cross-references

- Follow-up beads:
  - opensrm-duy9 (common): optional `decision_id` and typed relations on the
    shape. Lands first.
  - opensrm-5gpu (core): log and count non-canonical POSTs by producer.
  - opensrm-8qnc (core): enforce `to_dict` at `POST /verdicts`. Blocked on
    5gpu's count and on the producer beads.
  - opensrm-5lo1 (core): the outcome child in the canonical shape, and the
    derived reversed and outcome-in-effect state on reads.
  - opensrm-9pz6 (core): `/override` records a `reverses` child.
  - opensrm-gz58 (core): lineage from `parent_ids` only, relations indexed by
    kind, retention by kind.
  - opensrm-bdpr (workers): measure verdicts in the canonical shape.
  - opensrm-fl8y (bench): `operator_note` as an `annotates` relation.
  - opensrm-fv4z (cross): rename `records.Verdict` to `DecisionRecord`.
  - opensrm-mnft (cross): retire the legacy stores with the CLIs, keeping
    the hashing.
- Closed as superseded: opensrm-jmy.20.
- Not decided here: OpenSRM RBAC §9's example verdict shape
  (`opensrm/OPENSRM-RBAC-EXTENSION.md:532-560`) matches neither dataclass.
