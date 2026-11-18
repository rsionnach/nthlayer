# Decision: the source of truth for decisions and their rates

**Status:** DECIDED 2026-11-18 (Rob), under opensrm-5lxs. The implementation
is in the follow-up beads listed below; until they land, the interim
described under "What's routed to no-ops" holds.

**Context:** opensrm-5lxs, raised by the 2026-11-01 shape review (S2) and
re-verified against `main` on 2026-11-18. Related: opensrm-wo62.3 (shared
metrics contract), opensrm-jc4l (duplicate delivery overcounts the §4.5
counters), opensrm-r860 (the joined §4.5 series), opensrm-taz2 (the
collector's confidence gauge), opensrm-vgub (measure reads `nthlayer_*`).
Spec: OpenSRM Telemetry Addendum A1, §4.1 to §4.6
(`opensrm/OPENSRM-TELEMETRY-ADDENDUM-v2.md`).

## The problem, measured

A decision reaches NthLayer by two routes, and nothing makes them one record.

- **As a verdict.** `POST /verdicts` checks `id`, `type` and `created_at` and
  stores it (nthlayer-core `server.py:256-294`). Core exports no metrics.
- **As A1 §4 events.** `nthlayer.decision`, `nthlayer.reversal` and
  `nthlayer.outcome` are counted by the front-door collector
  (`test/otel-collector.yaml:66-95`) into `nthlayer_decisions_total`,
  `nthlayer_reversals_total` and `nthlayer_outcomes_total`. The connectors
  are stateless: they count events, not decisions, so §4.6 C1 (dedupe on
  `nthlayer.decision.id`) and C2 (reversed once) do not hold. No production
  component emits `nthlayer.decision`; only `test/fake-service.py` does,
  and it never posts to core.

The override-adapter is the one partial link. It writes one masked override
both ways: `nthlayer.reversal` with `decision_id` set from the event (common
`overrides/models.py:132`), and `POST /verdicts/{id}/override`, which core
rejects unless the body's `decision_id` equals the path's verdict id
(`server.py:432-437`). Both writes fail open, so they can diverge silently,
and the override path treats a decision id and a verdict id as the same
thing.

Five computations are called a reversal rate, over three denominators:

| site | quantity | denominator |
|---|---|---|
| workers measure (`measure/adapters/prometheus.py:231-252`) | `nthlayer_reversals_total / nthlayer_decisions_total` (A1) | all decisions (events, in practice) |
| common `AccuracyReport` (`verdicts/models.py:178-189`, `sqlite_store.py:262-319`) | overridden / resolved | resolved verdicts only |
| workers respond `nthlayer_verdict_reversal_rate` (`respond/metrics.py:72-100`) | overridden / resolved, 7d and 30d | resolved verdicts in a local SQLite file |
| workers `JudgmentSLOChecker` (`measure/calibration/slos.py:47-67`) | distinct overridden evals / all evals | grader evaluations |
| workers correlate `downstream_reversal_rate` (`correlate/verdict_chain.py:158`) | over verdict chains | chain members |

The respond gauge and `AccuracyReport` read local SQLite stores, not core's
(`respond/cli.py:544-545`, `measure/cli.py:433-440`); core's `Store.accuracy`
raises `NotImplementedError` (`store.py:329-338`).

Generate compiles `ai_gate_*` recording rules that measure never reads
(`recording_rules/manifest_builder.py:544-732`), and common's threshold
contract names `gen_ai_*` series (`manifest/threshold_series.py:38-62`):
three name families for one quantity, with A1 §4.5 naming the third. That
is opensrm-wo62.3's job and is not decided here.

## Decision

1. **Core's store is the store of record for decisions, keyed on
   `nthlayer.decision.id`.** Two ways in, one table: verdicts posted by
   NthLayer components, and §4 events ingested from any application. C1 to
   C6 are computed once, from the store, for both.

2. **`nthlayer.decision.id` is not the verdict id.** Per A1 §4.1 it is the
   decision record's id, which SHOULD be its content-addressed id. A verdict
   that is a decision carries it; not every verdict type is a decision
   record.

3. **The §4.6 computation runs in core, behind a read endpoint.** That
   covers C1 dedupe, C2, C3 (outcome in effect), C4 (orphans excluded and
   reported, late joins), C5 and C6. It runs in core because C3's tie-break
   (equal `Timestamp`s: the one received last by the store of record)
   depends on the store's receipt order, which only core has.

4. **Measure evaluates and exports the `nthlayer_*` series** from that
   endpoint. Core gets no `/metrics`: it stays the Tier 1 API and store.

5. **A1's reversals over all decisions is the only quantity named reversal
   rate.** The resolved-only figures are renamed or retired per site; a
   kept one must not have "reversal rate" in its name.

## Canonical alternative (rejected)

- **The OTel events as the record**, counted by a collector, with measure
  keeping a join store fed from the events (opensrm-r860's original shape).
  Rejected: verdicts would keep their own rates beside the event counts,
  which is the two-denominator problem this record exists to end, and a join
  store in measure cannot reproduce C3's tie-break without the receipt order
  of the store of record.
- **Both routes kept, tied by id, with a reconciler.** Rejected: it keeps
  two records of one decision and adds a component whose only job is to
  report that they disagree.
- **A `/metrics` endpoint on core.** Rejected: it puts metric evaluation in
  Tier 1. The computation core alone can do (C1 to C6) goes behind a read
  endpoint, and evaluation and export stay in measure.
- **The verdict id as `nthlayer.decision.id`.** Rejected: A1 §4.1 defines it
  as the decision record's content-addressed id, and verdict types that are
  not decisions would otherwise be counted as decisions.

## What's routed to no-ops

The interim, not the design:

- **Event-only producers** are counted by the front-door collector and
  reported as approximate (A1 N5) until core ingests §4 events
  (opensrm-z9uo). Duplicate delivery overcounts those counters
  (opensrm-jc4l).
- **High-confidence failures** in measure still read the pre-A1
  `gen_ai_overrides_hcf_total` / `gen_ai_decisions_total` counters
  (`prometheus.py:244-258`) until opensrm-r860 moves them onto the
  endpoint.
- **The override path** still keys a reversal on the verdict id, and the
  adapter's two writes can still diverge (opensrm-vmnc).
- **The resolved-only rates** keep their current names until opensrm-l0ki
  (workers) and opensrm-qgtz (common) rename or retire them.

## When the decision unwinds

Revisit if a deployment needs decisions counted where core cannot see them
(an air-gapped producer with only a collector), or if C3's tie-break is
amended in A1 so that it no longer depends on the store's receipt order. In
the first case the collector-side counts would stop being interim and become
a supported mode, and N5 reporting would carry the difference; in the second
the computation could move to measure. Either way the single name "reversal
rate" for reversals over all decisions stands.

## Cross-references

- Spec: A1 §4.1 (`nthlayer.decision.id`), §4.5 (series names, N1 to N5),
  §4.6 (C1 to C6), in `opensrm/OPENSRM-TELEMETRY-ADDENDUM-v2.md`.
- Follow-up beads:
  - opensrm-z9uo: core ingests §4 events, keyed on `nthlayer.decision.id`.
  - opensrm-ikpq: core read endpoint computing C1 to C6.
  - opensrm-vmnc (cross): a decision verdict carries
    `nthlayer.decision.id`; the override path and the adapter's dual write.
  - opensrm-l0ki: rename or retire the workers' resolved-only rates.
  - opensrm-qgtz: rename or retire `AccuracyReport`'s rate (common).
  - opensrm-r860: re-scoped to the measure side; depends on opensrm-ikpq.
- Related: opensrm-wo62.3 (one source for series names), opensrm-jc4l,
  opensrm-7t3q (the canonical verdict wire shape).
- Related decision:
  [verdict-assessment-taxonomy-boundary.md](verdict-assessment-taxonomy-boundary.md)
  (verdicts are decisions, assessments are observations).
