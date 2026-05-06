# SLO target convention decision (opensrm-pa2w.followup)

**Date:** 2026-05-06
**Decision:** 0-100 percentage canonical for `manifest.SLODefinition.target`.
**Bead:** opensrm-5fff (decision); migration work tracked separately.

## Context

Three subsystems consume `manifest.SLODefinition.target` with incompatible
arithmetic for the same value. Discovered during the opensrm-pa2w audit
(2026-05-06):

| Consumer | Convention | Example |
|---|---|---|
| `observe.collector` (worker SLO collector) | 0–100 percentage | availability `target=99.9` |
| `measure.worker` (judgment SLOs) | 0.0–1.0 ratio | reversal_rate `target=0.985` |
| `nthlayer_common.slo_models.SLO` (OpenSLO model — separate dataclass) | 0.0–1.0 ratio | OpenSLO standard |

The concrete bug surfaced by the audit: with fraud-detect's post-xte
`target=98.5` on the reversal_rate judgment SLO, observe computes the
correct error budget (1.5%) but `measure._classify_budget_consumption`
computes `budget = 1.0 - 98.5 = -97.5`, hits the `if budget <= 0: return
critical` guard, and returns `critical` for every breach regardless of
actual severity. The integration test passed because severity assertions
were not precise. No single value satisfied both subsystems' arithmetic.

opensrm-pa2w shipped a load-time `TargetConventionWarning` as mitigation
(heuristic flag, never rejects). This decision unwinds the divergence at
the source.

## Options considered

1. **0-100 percentage canonical** (chosen)
2. **0.0-1.0 ratio canonical**
3. **Explicit `target_unit` field on `SLODefinition`**

## Decision: Option 1

### Reasoning

- **Lowest blast radius.** Every existing demo manifest already uses
  percentage (`availability: 99.9`, `reversal_rate: 98.5` post-xte).
  Options 2/3 require rewriting every existing spec.
- **Operator intuition.** SREs read "99.9" as 99.9% availability
  instantly; "0.999" requires mental conversion. NthLayer optimises for
  readability under incident pressure. The `target=0.015` value on
  reversal_rate confused a contributor in opensrm-xte — that is
  evidence the ratio convention is less intuitive when authoring.
- **OpenSLO compatibility preserved at the boundary.**
  `nthlayer_common.slo_models.SLO` (OpenSLO surface) stays ratio;
  `nthlayer_common.manifest.SLODefinition` becomes percentage canonical.
  Conversion happens at the integration point, making the boundary
  explicit rather than blurring it across subsystems.
- **Effort.** ~2 sessions vs ~3 for Option 2 (every demo spec migrated)
  vs ~2-3 sessions plus a schema bump for Option 3.

### Trade-offs accepted

- **Internal arithmetic less elegant.** `(100 - target) / 100` reads less
  naturally than `1.0 - target`. Accepted for the readability and
  migration-effort wins.
- **External OpenSLO authors context-switch when writing NthLayer
  manifests.** Mitigated by clear convention documentation and explicit
  boundary conversion in the OpenSLO bridge code path.

## Migration plan

The migration work lands under a new follow-up bead with R5 review. Tasks:

1. **measure arithmetic rewrite.** Convert
   `measure.worker._classify_budget_consumption`,
   `_classify_variance`, and `_classify_calibration` from ratio to
   percentage convention. Update governance severity classification to
   match.
2. **measure test fixtures.** Update judgment-SLO test targets
   (e.g. `0.985` → `98.5`, `0.99` → `99.0`) to match the canonical
   convention.
3. **OpenSLO boundary conversion.** Add explicit conversion in the
   path where `manifest.SLODefinition` flows into
   `slo_models.SLO` (OpenSLO consumer). The conversion is
   `slo_models.SLO.target = manifest.SLODefinition.target / 100.0`.
4. **Demo specs audit.** Walk every demo manifest and confirm targets
   are percentage. Most should already be correct (post-xte fraud-detect
   reversal_rate is `98.5`). Any stragglers using ratio get migrated.
5. **target_validation.py update.** The opensrm-pa2w validator currently
   warns on cross-convention mismatches with a heuristic. Post-migration
   it enforces the canonical convention: warn on any judgment SLO target
   `<1.0` (likely ratio author error), warn on any classical SLO target
   `<1.0`. The "divergence" prose disappears from the warning text.
6. **Regression test.** Lock the fraud-detect reversal_rate severity
   classification — given the manifest and a specific breach magnitude,
   assert the severity is the expected gradation (not always "critical").
   This test proves the migration fixed the original symptom and
   prevents re-divergence.
7. **Documentation update.** The `nthlayer-common/CLAUDE.md` "SLO
   target convention" section currently captures the divergence
   honestly. Post-migration it documents the new state: "all
   NthLayer-internal consumers use 0-100 percentage; OpenSLO surface
   uses 0.0-1.0 ratio with explicit boundary conversion in the bridge."

R5 review runs across all four passes (correctness, clarity, edge
cases, excellence) before close, with emphasis on the regression test
proving the original bug is fixed.

## When the decision unwinds

Unlikely to unwind unless OpenSLO compatibility becomes a hard
external requirement (third-party manifest authors expecting ratio
convention). If unwound:

1. Migrate `manifest.SLODefinition.target` arithmetic across observe
   and measure to ratio.
2. Migrate every demo spec from percentage to ratio.
3. Remove the boundary conversion in the OpenSLO bridge.
4. Update `target_validation.py` to invert its heuristic.
5. Update this doc and the CLAUDE.md convention sections.

## Cross-references

Beads:

- `opensrm-pa2w` (closed) — mitigation work that surfaced the
  three-way divergence and shipped the load-time warning.
- `opensrm-xte` (closed) — original symptom that exposed the
  mismatch.
- `opensrm-ol4` (closed) — downstream of xte (explanation engine).
- `opensrm-5fff` — this decision; migration tracked under follow-up
  bead.

Code paths affected (migration touches these):

- `nthlayer-workers/src/nthlayer_workers/measure/worker.py` —
  `_classify_budget_consumption`, `_classify_variance`,
  `_classify_calibration`, plus governance severity rules.
- `nthlayer-workers/src/nthlayer_workers/observe/slo/collector.py` —
  no change (already percentage).
- `nthlayer-common/src/nthlayer_common/manifest/target_validation.py` —
  heuristic flips from "warn cross-convention" to "warn ratio in
  manifest target".
- `nthlayer-common/src/nthlayer_common/slo_models.py` (or wherever
  the OpenSLO bridge lives) — explicit `target / 100.0` conversion at
  the boundary.
- `nthlayer/demo/specs/` — audit and migrate any ratio-shaped targets.
- `nthlayer-common/CLAUDE.md` — replace divergence prose with
  canonical-convention prose.
