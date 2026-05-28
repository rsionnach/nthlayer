# `financial_impact` on SpecRecommendation Design (opensrm-jmy.23)

**Status:** Design-locked. Reframed as document-level metadata (not per-recommendation) during jmy.6 brainstorming follow-up; volume_source / failure_mode / per-rec-vs-per-document questions resolved by existing precedent in `nthlayer-workers/learn/retrospective.py::_compute_financial_impact` (jmy.1).

**Foundation:**
- `nthlayer-workers/src/nthlayer_workers/learn/retrospective.py::_compute_financial_impact` (lines 197–319, jmy.1): already produces the figure during `build_retrospective()` and stores it on the retrospective verdict's `metadata.custom["financial_impact"]` (line 147).
- `nthlayer-common/src/nthlayer_common/outcomes.py::FinancialImpact` (lines 22–35): canonical dataclass — `estimated: float`, `currency: str`, `decisions_affected: int`, `failure_mode: FailureMode`, `volume_source: VolumeSource`.
- `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py::SpecRecommendation` (lines 112–163, jmy.2): document carrying `metadata` (incident, generated_by, generated_at, confidence, requires_human_review) + `recommendations: list[Recommendation]`. Today's `Recommendation` has an unpopulated `financial_impact: str | None` field at line 106 — a placeholder that no engine writes.

---

## 1. Problem statement

`build_retrospective()` already computes a financial impact figure for the incident and persists it on the retrospective verdict's `metadata.custom["financial_impact"]`. The downstream `RecommendationPlan` artefact (jmy.6) has no path for that figure — operators reading `plan.yaml` see no money number even though one exists upstream. jmy.2 added a stub `financial_impact: str | None` on `Recommendation` but no producer fills it, no consumer reads it, and the wrong type (string) and wrong placement (per-recommendation) make it actively misleading. jmy.23 wires the existing figure through.

---

## 2. Design decision

### 2.1 Placement: top-level metadata, not per-recommendation

Move `financial_impact: FinancialImpact | None = None` to the `SpecRecommendation` dataclass (the document), NOT the `Recommendation` dataclass (the item). Drop the existing-but-unpopulated `financial_impact: str | None = None` from `Recommendation` at `recommendations.py:106`.

Rationale: the figure is whole-incident — `_compute_financial_impact` aggregates across the blast radius (retrospective.py:229–306) and returns one number per incident. Per-recommendation attribution would require splitting the aggregate by recommendation type, which is a future modelling decision (see § 4). The document-level placement matches where retrospective metadata already lives in jmy.1.

### 2.2 YAML shape: dataclass-native names

Emit under `metadata.financial_impact` using Python attribute names from `FinancialImpact`:

```yaml
metadata:
  incident: inc-2026-05-21-001
  generated_by: nthlayer-learn
  generated_at: 2026-05-28T10:00:00+00:00
  confidence: 0.65
  requires_human_review: true
  financial_impact:
    estimated: 5400.0
    currency: USD
    decisions_affected: 1200
    failure_mode: false_negative
    volume_source: metric
recommendations:
  - id: rec-abc123
    ...
```

Rationale: consistency with the existing retrospective `metadata.custom["financial_impact"]` shape produced by `_compute_financial_impact` (retrospective.py:313–319) — operators see the same field names in both places. Field names are `financial_impact`, `estimated`, `decisions_affected`, `failure_mode`, `volume_source` — NOT the bead-body's `estimated_impact` / `amount`. The bead text will be reconciled to the dataclass.

### 2.3 Propagation, not recomputation

`analyze_incident()` in `recommendations.py` reads `retrospective_data.get("financial_impact")` and propagates it onto the returned `SpecRecommendation`. No new compute path. No new inputs threaded through (no `specs_dir`, `blast_radius`, `duration_minutes` plumbing into `analyze_incident`). The CLI `recommendations` subcommand (jmy.6) — specifically the `_build_plan_from_incident` stub at `cli.py:215–226` — populates `retrospective_data["financial_impact"]` from the retrospective verdict's `metadata.custom["financial_impact"]`.

Rationale: the compute lives in retrospective generation where the inputs (blast_radius, breach_counts_by_service, duration_minutes, specs_dir) are already in scope. Duplicating the call in `analyze_incident` would require duplicating the inputs and risk drift between two compute paths for the same number.

### 2.4 Open design questions resolved by existing precedent

The bead body lists three open questions; each is already settled upstream:

- **volume_source default?** — retrospective.py:262–276 already chooses: `metric` when `breach_counts[svc] > 0`, else `spec_estimate` fallback via `estimate_decisions_in_window`. jmy.23 inherits that choice by propagation.
- **per-rec vs per-document?** — top-level metadata (§ 2.1).
- **failure_mode inference?** — retrospective.py:281 hardcodes `"false_negative"`. jmy.23 inherits that choice.

---

## 3. Wire shape

```yaml
apiVersion: nthlayer.io/learn/v1
kind: RecommendationPlan
metadata:
  incident: inc-2026-05-21-001
  generated_by: nthlayer-learn
  generated_at: 2026-05-28T10:00:00+00:00
  confidence: 0.65
  requires_human_review: true
  financial_impact:
    estimated: 5400.0
    currency: USD
    decisions_affected: 1200
    failure_mode: false_negative
    volume_source: metric
recommendations:
  - id: rec-a3f8b2e1c9d4
    service: fraud-detect
    type: tighten_slo
    field: spec.slos.judgment.target
    current_value: 95.0
    proposed_value: 98.5
    rationale: |
      Calibration drift detected: reversal rate climbed from 1.2% to 4.8%
      over the 30-day window.
    confidence: 0.7
```

`metadata.financial_impact` is omitted entirely when the upstream retrospective produced no figure (no outcomes block on any blast-radius manifest, mixed-currency aggregate, etc. — see retrospective.py:307–311). Absent ≠ zero; absent means "no financial signal available", matching the retrospective contract.

Field types follow `FinancialImpact`: `estimated` is float (rounded to 2dp by `_compute_financial_impact`), `currency` is ISO 4217 alpha-3, `decisions_affected` is int, `failure_mode` is one of `{false_positive, false_negative}`, `volume_source` is one of `{metric, spec_estimate}`.

---

## 4. Out of scope

| Concern | Why deferred |
|---|---|
| Per-recommendation attribution (split aggregate across recs) | Requires a model of how each recommendation type contributes to averting the incident-aggregate cost. File when a consumer needs it. |
| Per-recommendation `failure_mode` inference | Today's `_compute_financial_impact` hardcodes `false_negative`. Per-rec inference (e.g. `tighten_slo` → false_negative, `add_deploy_gate` → either) is a separate concern. |
| `financial_impact` on `add_dependency` recommendations | `add_dependency` (jmy.21) does not exist yet. File when the recommendation type lands and a financial attribution question follows. |
| Changing the upstream `_compute_financial_impact` contract | jmy.23 is propagation-only; any change to the compute path is its own bead. |

---

## 5. References

- Bead: `opensrm-jmy.23` (financial_impact field on SpecRecommendation, jmy.1 follow-up).
- Parent bead: `opensrm-jmy.6` (Learn → Spec operator workflow), which surfaced jmy.23 as a separate follow-up during reframing.
- Upstream compute: `nthlayer-workers/src/nthlayer_workers/learn/retrospective.py::_compute_financial_impact` (jmy.1).
- Canonical dataclass: `nthlayer-common/src/nthlayer_common/outcomes.py::FinancialImpact` (jmy.1).
- Document carrier: `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py::SpecRecommendation` (jmy.2).
- Predecessor design pattern: `nthlayer/docs/superpowers/specs/2026-05-26-jmy6-learn-spec-loop-design.md`.
