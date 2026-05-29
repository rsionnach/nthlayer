# `add_dependency` Recommendation Type Design (opensrm-jmy.21)

**Status:** Design-locked. Author: Rob Fox. Date: 2026-05-29. Bead: `opensrm-jmy.21`. Parent: `opensrm-jmy.6` (Learn → Spec loop) shipped; this adds a third recommendation type alongside `tighten_slo` (jmy.1/jmy.2) and `add_deploy_gate` (jmy.6).

**Foundation:**
- `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py::analyze_incident` (jmy.2): returns `SpecRecommendation` aggregating per-heuristic outputs (`_tighten_slo_recommendations`, `_add_deploy_gate_recommendations`). Adds a third heuristic in this bead.
- `nthlayer-workers/src/nthlayer_workers/learn/retrospective.py::build_retrospective` (lines 197–319, jmy.1): already loads per-service manifests for outcomes / `_compute_financial_impact`. Extends the same loop to also extract `declared_dependencies_by_service`.
- `nthlayer-workers/src/nthlayer_workers/learn/_yaml.py::apply_at_path` (lines 59–88) + `classify_outcome` (lines 145–183) (jmy.6): owns the apply primitive and three-state outcome taxonomy (APPLY_CLEAN / ALREADY_APPLIED / DRIFT_DETECTED). Extends both for list-append semantics.

---

## 1. Problem statement

`build_retrospective` already computes an incident's blast radius — the set of services causally implicated in the chain. Operators routinely discover, post-incident, that the trigger service's manifest declared none (or only some) of those downstream services as dependencies; the missing edges are exactly what the chain just demonstrated. Today the Learn loop has no way to suggest filling those gaps. jmy.21 adds a third recommendation type, `add_dependency`, that proposes one Recommendation per missing edge on the trigger service's manifest, sourced purely from the incident chain itself.

---

## 2. Existing surface

- `analyze_incident(incident, retrospective_data)` in `recommendations.py` reads `retrospective_data["calibration"]` / `["breach_counts_by_service"]` / `["financial_impact"]` and returns a `SpecRecommendation` document with `recommendations: list[Recommendation]`. Each heuristic is a private function returning a list of `Recommendation`s.
- `build_retrospective` in `retrospective.py` walks `incident.blast_radius`, loads each service's manifest, and populates `metadata.custom["financial_impact"]` (line 147) and the outcomes block. jmy.21 extends the same loop to populate `metadata.custom["declared_dependencies_by_service"]`.
- `apply_at_path(doc, "spec.slos.judgment.target", value)` in `_yaml.py` (lines 59–88) is the apply primitive: it walks a dotted path and overwrites a scalar / dict at the leaf. `classify_outcome(...)` (lines 145–183) classifies the result against the live spec into `APPLY_CLEAN` / `ALREADY_APPLIED` / `DRIFT_DETECTED`. jmy.21 extends both with a `[+]` sigil for list-append, keyed on dependency `name`.

---

## 3. Locked decisions

### 3.1 Signal: incident-chain only

For the trigger service `S` of an incident, `undeclared = blast_radius - declared_dependencies[S] - {S}`. No cross-referencing with `topology_drift.observed_not_declared` assessments. Rationale: blast radius already encodes the chain that the operator just lived through; corroboration with topology_drift is a noise-reduction lever, not a signal source — deferred until field experience shows the chain-only signal is too noisy.

### 3.2 Trigger service only (single subject)

Recommendations target ONLY the trigger service's manifest. Other chain services with their own undeclared deps are not addressed in this bead. Rationale: scoping to one subject keeps the rec document mono-service like today's `tighten_slo` / `add_deploy_gate`, and the trigger service is the only one whose dependency declaration directly explains the incident's propagation envelope.

### 3.3 Patch shape: minimum

`proposed_value = {"name": "<svc>", "type": "unknown"}`. Operator fills in real `type` / `criticality` / SLO guarantees on the PR. Rationale: `requires_human_review` on `SpecRecommendation` is already `True`; the `"unknown"` placeholder is explicit (not magic), matches existing minimum-viable-merge precedent set by `add_deploy_gate`, and avoids fabricating per-edge metadata the chain signal does not carry.

### 3.4 Plumbing: enrich `retrospective_data`

`build_retrospective` already loads manifests for outcomes / `_compute_financial_impact`. Extend that loop to populate `metadata.custom["declared_dependencies_by_service"]: dict[str, list[str]]` (service name → list of declared dep names). `analyze_incident` reads it via `retrospective_data["declared_dependencies_by_service"]` like every other retrospective field. Rationale: no new manifest-loading path, no new inputs threaded into `analyze_incident`; matches the jmy.23 propagation-not-recomputation precedent.

### 3.5 Apply primitive: `[+]` sigil for list-append

`field: "spec.dependencies[+]"` triggers append semantics in `apply_at_path` and list-contains check (matched on `name` key) in `classify_outcome`. Sigil-only — no other heuristic in the apply layer (no "is the value a dict with a name key, maybe append?" inference). Rationale: keeping the apply layer dumb and string-driven preserves the property that `field` strings round-trip between the YAML doc and the recommendation; the sigil is visible to operators reading the rec, not hidden behind type sniffing.

### 3.6 Confidence: 0.5

Hardcoded constant `_ADD_DEPENDENCY_CONFIDENCE = 0.5`. Between `tighten_slo` placeholder (0.4) and `add_deploy_gate` with breach evidence (0.65). Rationale: the chain is a strong structural signal — the propagation actually happened — but the operator still has to validate the edge wasn't intentionally implicit (e.g. transitively-known shared infra) and fill in the type/criticality.

### 3.7 Multi-rec emission

One Recommendation per missing dependency, NOT one rec per incident. If three services are missing from `S`'s deps, three `add_dependency` recs land in the document — all on `S`'s manifest, different `proposed_value.name`. Rationale: aligns with the existing per-edge granularity of `tighten_slo` (one rec per SLO field) and lets the operator partially-apply / partially-reject without rewriting a composite patch.

---

## 4. Recommendation shape (canonical YAML)

```yaml
- id: rec-d8c2f9a1b7e0
  service: fraud-detect
  type: add_dependency
  field: spec.dependencies[+]
  current_value: null
  proposed_value:
    name: payments-api
    type: unknown
  rationale: |
    payments-api appeared in this incident's blast radius but was not
    declared as a dependency on fraud-detect. Add the edge so future
    incidents propagate through the declared topology.
  confidence: 0.5
```

`current_value` is `null` (list-append has no scalar predecessor). `field` carries the `[+]` sigil — operators reading the plan see the append shape directly. One such block per undeclared service.

---

## 5. Out of scope

- Cross-referencing with `topology_drift.observed_not_declared` assessments (separate noise-reduction signal; defer).
- Per-chain-service emission (only the trigger service's manifest is addressed; the other chain services' missing deps are a separate bead).
- Inferring `type` (`upstream` / `downstream` / `peer`) from trace direction or call shape — operator fills.
- SLO guarantees on the proposed dependency — operator fills.
- CLI changes: jmy.6's `learn recommendations` CLI emits whatever recs the engine produces; no flag, no subcommand, no output format change.

---

## 6. Follow-ups

- Per-chain-service emission — extend to non-trigger services in the chain that also have undeclared deps (later).
- topology_drift corroboration — gate `add_dependency` recs on `observed_not_declared` presence to cut noise (later).
- Inferred dependency `type` from trace metadata — replace the `"unknown"` placeholder when call direction is unambiguous (later).

---

## 7. References

- Bead: `opensrm-jmy.21` (`add_dependency` recommendation type).
- Parent bead: `opensrm-jmy.6` (Learn → Spec operator workflow).
- Sibling design: `nthlayer/docs/superpowers/specs/2026-05-28-jmy23-financial-impact-design.md` (propagation-not-recomputation precedent).
- Sibling design: `nthlayer/docs/superpowers/specs/2026-05-29-jmy25-json-output-design.md` (additive CLI-surface sibling).
- Foundation code: `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py::analyze_incident` (jmy.2), `retrospective.py::build_retrospective` (jmy.1), `_yaml.py::apply_at_path` + `classify_outcome` (jmy.6).
