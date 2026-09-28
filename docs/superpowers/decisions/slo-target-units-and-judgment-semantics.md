# Decision: SLO target units, and what `target` means for a judgment SLO

**Status:** PROPOSED — not yet decided. Sections 1 and 2 are recommended for
ratification; section 3 needs an OpenSRM spec decision before any parser work.

**Date drafted:** 2026-09-28, during opensrm-ocvu.

**Context:** opensrm-ocvu (v1 and v2 parsers disagree on target units),
sharpened during opensrm-fxln (measure's judgment breach check). Related:
opensrm-5fff (the original convention decision), opensrm-47tt (why the v2
archetypes could not reveal this).

## The problem, measured

The same SLO, meaning the same thing, parses to different numbers depending on
which manifest format it is written in.

```
classical (availability)
  v1  spec.slos.availability.target        -> 99.9
  v2  OpenSLO objectives[].target          -> 0.999
  relationship: x100, a clean scale factor

judgment (reversal_rate)
  v1  spec.slos.reversal_rate.target                   -> 98.5
  v2  spec.judgment_slo[].target.maximum_reversal_rate -> 0.05
  relationship: NOT a scale factor
```

v1 states "at least 98.5% of decisions are NOT reversed". v2 states "at most 5%
ARE reversed". These are complementary quantities, and `(1 - 0.05) * 100 = 95`,
which is not 98.5. **The two formats describe the same constraint from opposite
sides**, so `target * 100` fixes classical and silently corrupts judgment.

`nthlayer-common` already knows the v2 value is wrong: `TargetConventionWarning`
fires on every v2 manifest carrying a normal OpenSLO objective. The validator is
correctly flagging the parser's own output. Nothing acts on the warning, and the
unconverted value flows on — which is the silent-wrong-answer shape, not a
loud failure.

### Why it survived

The v2 archetypes cannot be parsed at all (opensrm-47tt), so nothing exercised
the v2 target path.

### What it already cost

`opensrm-fxln` fixed measure's judgment breach check to compare a 0-100 target
against a scaled SLI, and shipped in nthlayer-workers 2.0.0. That fix is correct
for v1 and inoperative for v2 through no fault of its own. Measured against
current `main`:

```
v2 judgment manifest, target: {maximum_reversal_rate: 0.05}
  parsed SLODefinition.target = 0.05
  Prometheus rate 0.08  ->  sli_pct = 92.0
  breach = sli_pct < target = 92.0 < 0.05 = False      <- cannot breach
  with the canonical reading (5.0 -> 95.0) it would be True
```

So workers 2.0.0's changelog claims a fix that does not hold for v2 judgment
SLOs. That is not a regression introduced here; it is this defect one layer up.

## What the industry does

Checked against the specifications rather than recalled.

| system | field | unit |
|---|---|---|
| OpenSLO | `target` **or** `targetPercent` | fraction `[0,1)` **or** percent `[0,100)`, exactly one |
| Sloth | `objective` | percentage 0-100 (`objective: 99.9`) |
| Google Cloud Monitoring | `goal` | fraction, "the fraction of service that must be good", `0 < goal <= 0.999` |
| Google SRE book | prose | percentage ("99.9% availability") |

The split is predictable: **machine and API surfaces use fractions; human and
config surfaces use percentages.**

The load-bearing finding is that **OpenSLO supports both, as two named fields.**
So `nthlayer-common` hard rule 1 — 0-100 internally, 0.0-1.0 on the OpenSLO
surface, conversion at the boundary — is not an nthlayer idiosyncrasy. It is the
mainstream pattern, and the spec we embed makes the dual representation
first-class.

**For judgment SLOs there is no standard at all.** Sloth, OpenSLO, Google and
Datadog all model exactly one thing: the fraction of good events. None has a
concept of maximum calibration error or maximum drift. Emerging 2026 practice
(Grafana's agent-SLO work, LLM quality-SLO patterns) expresses AI quality as a
**floor on a goodness score** — "answer quality >= 0.85, error budget 150 wrong
answers per 1,000 sampled" — not as a ceiling on a badness rate. That is v1's
shape, not v2's.

## The eight judgment types are not commensurable

From `opensrm/spec/v2/schema.json`. `Ratio` is defined there as
`{"type": "number", "minimum": 0, "maximum": 1,
"description": "Ratio value (0.0 - 1.0), not a percentage"}` — so v2's choice is
explicit and deliberate, not an oversight.

| v2 target field | schema type | polarity | has a complement? |
|---|---|---|---|
| `maximum_reversal_rate` | Ratio | max | yes — a rate |
| `maximum_failure_rate` | Ratio | max | yes — a rate |
| `maximum_escalation_rate` | Ratio | max | yes — a rate |
| `desired_outcome_rate` | Ratio | **min** | already a floor |
| `maximum_drift` | Ratio | max | **no** — an error magnitude |
| `maximum_variance_from_overall` | Ratio | max | **no** — an error magnitude |
| `maximum_expected_calibration_error` | Ratio | max | **no** — an error magnitude |
| `maximum_brier_score` | number (unbounded) | max | **no**, and not a ratio |

This table is the actual decision. It rules out both of the options
`opensrm-ocvu` was filed with:

- **"target is always an SLI threshold, 0-100"** is not implementable. `1 - drift`
  is meaningless; a Brier score has no percentage form. It would require
  inventing semantics the spec does not define — which is how this class of
  defect arrives.
- **"invert the v2 value"** is wrong for `desired_outcome_rate`, which is already
  a floor, and meaningless for the four error magnitudes.

## Decision

Three separate rulings, because the three groups are genuinely different.

### 1. Classical SLOs — convert inbound. No design decision needed.

`parser/v2` multiplies an OpenSLO `objectives[].target` by 100 when populating
`SLODefinition.target`. Hard rule 1 already mandates this; only the inbound
boundary was missing. The outbound one has always been correct:
`nthlayer_generate/slos/pipeline.py:192` does `target=slo_def.target / 100.0`
inside `_build_slo_from_manifest` (verified 2026-09-28).

**Additionally, accept `targetPercent`.** OpenSLO defines it and we currently
ignore it, so a spec-legal manifest using `targetPercent: 99.9` is silently
mis-parsed today. Accepting both — and rejecting a manifest that sets both, as
OpenSLO requires — is spec-faithful rather than an nthlayer rule.

### 2. Judgment RATES — SLI floor, 0-100, converted by complement.

Applies to `reversal_rate`, `high_confidence_failure`, `escalation`, `outcomes`.

`SLODefinition.target` for these means **"how good must this be"**, 0-100. Four
independent lines of evidence agree: v1's reading, `nthlayer-common` hard rule 1,
`measure/worker.py:242`'s existing assumption, and the emerging industry practice
of expressing AI quality as a floor on a goodness score.

v2's `maximum_*_rate` converts as `(1 - rate) * 100`. `desired_outcome_rate` is
already a floor and converts as `rate * 100` — it must NOT be complemented.

### 3. Judgment ERROR MAGNITUDES — not SLO targets. Needs a spec decision.

Applies to `calibration`, `segments`, `stability`, and any type whose target is
`maximum_drift`, `maximum_variance_from_overall`,
`maximum_expected_calibration_error` or `maximum_brier_score`.

These are not fractions of good events. They have no complement, no error budget,
and in every standard surveyed they would not be SLOs at all — they are
monitored metrics with thresholds. **Forcing them into a single float field with
one convention is what makes a universal rule impossible.**

This document does not decide their representation, because it is an OpenSRM
question rather than a parser question. The options, for whoever takes it:

- **3a.** A separate field — `SLODefinition.threshold` with an explicit unit —
  leaving `target` to mean only "SLI floor, 0-100". Cleanest semantically;
  touches every consumer.
- **3b.** `SLODefinition` carries a `target_kind` discriminator
  (`sli_floor` / `error_ceiling` / `duration_ceiling`) set by whichever parser
  produced the value, and consumers dispatch on it. Exactly the shape that
  worked for `query_kind` in opensrm-fxln: the comparison rule travels with the
  value. Must have no default — a wrong default here is silent.
- **3c.** These stop being SLOs in OpenSRM and become a distinct manifest
  concept. Largest spec change; most honest about what they are.

## Canonical alternative — and why it is rejected

**"Normalise everything to v2's reading: ratios 0-1 throughout."**

It has real support: the v2 schema says "not a percentage" explicitly, the
`maximum_*` field names are unambiguous, and Google's API uses fractions.

Rejected because the cost is disproportionate and the benefit is presentational.
It would rewrite `nthlayer-common` hard rule 1, `measure/worker.py:242`, the
`measure` adapter shipped in workers 2.0.0 this morning — forcing a second
workers release — and every consumer comparing a target to a measured value. It
would also put us on the opposite side of Sloth, the SRE book, OpenSLO's own
`targetPercent`, and the emerging AI-quality practice, all of which favour a
human-facing percentage. And it still would not solve section 3: error
magnitudes are not ratios of good events whichever unit is chosen.

## What is routed to no-ops

Shipping sections 1 and 2 without section 3 leaves the error-magnitude judgment
types parsing as they do today: a bare `Ratio` in `SLODefinition.target`, with
`TargetConventionWarning` firing. That is unchanged behaviour, not new breakage,
but it means:

- `calibration`, `segments` and `stability` SLOs remain unusable for breach
  decisions via `SLODefinition.target`.
- `TargetConventionWarning` will still fire for them, so "the warning no longer
  fires on a valid v2 manifest" (opensrm-ocvu's acceptance criterion) can only be
  met for classical and rate SLOs until section 3 lands.

That partial state must be recorded on the bead rather than discovered later.

## When this decision unwinds

- **OpenSLO drops `targetPercent`,** or standardises on fractions only. Section 1's
  dual acceptance would become dead code; the internal convention could stay.
- **A standard emerges for AI-quality SLOs** that models error magnitudes with
  error budgets. Section 3 should follow it rather than the local choice.
- **`measure/worker.py` stops assuming 0-100.** Section 2's main incumbent
  argument weakens; re-derive it from the other three.
- **A judgment type is added whose target is a duration.** `maximum_age` already
  exists in the v2 schema; if it reaches `SLODefinition.target` it breaks the
  "0-100 SLI floor" reading immediately, and section 3 becomes urgent.

## Cross-references

- Beads: `opensrm-ocvu` (this), `opensrm-fxln` (the measure fix this affects),
  `opensrm-5fff` (the original convention), `opensrm-47tt` (why the v2
  archetypes hid it), `opensrm-vrpa` (the judgment-type vocabulary, adjacent
  and also an `opensrm` spec question).
- Code: `nthlayer-common/src/nthlayer_common/manifest/parser/v2.py` (inbound
  boundary, the fix site), `manifest/target_validation.py`
  (`TargetConventionWarning`), `slo_models.py:94` (whose comment says "Target
  percentage" beside a `0.9995` example — itself worth correcting),
  `nthlayer-workers/src/nthlayer_workers/measure/worker.py:242`,
  `measure/adapters/prometheus.py` (the fxln breach dispatch),
  `nthlayer-generate` `src/nthlayer_generate/slos/pipeline.py:192` (outbound
  boundary, already correct — divides by 100 inside
  `_build_slo_from_manifest`).

  Note `slo_models.py` performs no conversion in either direction: it stores
  whatever it is given, and `error_budget()` returns `1.0 - self.target`, which
  is only meaningful for a ratio. So the "OpenSLO surface uses 0.0-1.0" half of
  hard rule 1 is enforced by convention and by that one subtraction, not by any
  conversion code. Anything handing it a percentage gets a negative error budget
  and no warning.
- Verified while drafting (2026-09-28): `measure/worker.py:242`'s
  `current_pct = current_value * 100`, citing opensrm-5fff.1;
  `maximum_age` present in `opensrm/spec/v2/schema.json`;
  the generate outbound division above. The v1/v2 divergence and the
  cannot-breach arithmetic were both reproduced directly against current `main`.
- Rules: `nthlayer-common` CLAUDE.md hard rule 1;
  `nthlayer-workers` CLAUDE.md hard rule 9.
- External: OpenSLO specification (`target` / `targetPercent`); Sloth
  (`objective`, percentage); Google Cloud Monitoring `ServiceLevelObjective.goal`
  (fraction, `0 < goal <= 0.999`); Grafana's agent-SLO / hallucination-budget
  work for the emerging AI-quality practice.
