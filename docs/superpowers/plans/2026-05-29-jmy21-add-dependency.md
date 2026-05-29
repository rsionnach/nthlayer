# jmy.21 `add_dependency` Recommendation Type — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third recommendation type, `add_dependency`, to the Learn loop. For each incident, identify services in the blast radius that are not declared as dependencies of the trigger service, and emit one `Recommendation` per missing edge on the trigger service's manifest. Patch shape is minimum (`{"name": "<svc>", "type": "unknown"}`), confidence 0.5, append via a new `spec.dependencies[+]` sigil in the apply layer.

**Architecture:** Single-repo change in `nthlayer-workers`. Lowest layer first: extend `_yaml.py` with the `[+]` sigil (apply primitive + outcome taxonomy). Then enrich `retrospective.py` to populate `metadata.custom["declared_dependencies_by_service"]` alongside the existing `financial_impact` field. Then add the `_add_dependency_recommendations` heuristic in `recommendations.py` and wire it into `analyze_incident`. Tests land in TDD order at each layer.

**Tech Stack:** Python 3.11+. No new runtime deps.

**Spec:** `nthlayer/docs/superpowers/specs/2026-05-29-jmy21-add-dependency-design.md`.

**Bead:** `opensrm-jmy.21`. Parent `opensrm-jmy.6` (Learn → Spec loop) shipped.

---

## File structure

### Files modified

| Path | Responsibility |
|---|---|
| `nthlayer-workers/src/nthlayer_workers/learn/_yaml.py` | Extend `apply_at_path` (lines 59–88) to detect `[+]` sigil and append to a list at the parent path; extend `classify_outcome` (lines 145–183) with a list-append branch (name present → `ALREADY_APPLIED`; name absent → `APPLY_CLEAN`; parent not a list → `DRIFT_DETECTED`). Sigil-only — no other heuristic. |
| `nthlayer-workers/src/nthlayer_workers/learn/retrospective.py` | In the existing manifest-loading branch (around `_compute_financial_impact`, lines 197–319), also extract `declared_dependencies_by_service: dict[str, list[str]]` and store it on `metadata.custom["declared_dependencies_by_service"]`. |
| `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py` | Add module constant `_ADD_DEPENDENCY_CONFIDENCE = 0.5`; add private `_add_dependency_recommendations(incident, retrospective_data)` returning `list[Recommendation]`; wire into `analyze_incident()` alongside `_tighten_slo_recommendations` and `_add_deploy_gate_recommendations`. |

### Files added

None. All changes extend existing modules.

### Tests modified / added

| Path | Responsibility |
|---|---|
| `nthlayer-workers/tests/learn/test_yaml.py` | New sigil tests: append to existing list; append to absent path (creates list with one item); already-applied (name present); drift (parent is dict not list); drift (parent is scalar not list/dict). |
| `nthlayer-workers/tests/learn/test_retrospective_financial.py` (or sibling `test_retrospective.py`) | New test: `build_retrospective` populates `metadata.custom["declared_dependencies_by_service"]` with per-service declared dep names. |
| `nthlayer-workers/tests/learn/test_recommendations.py` | New test class `TestAddDependencyRecommendation`: empty blast_radius → no rec; trigger service only → no rec; declared deps excluded; trigger service self-excluded; multiple undeclared → multiple recs; rec shape (field, proposed_value, confidence, rationale). |

### Files NOT modified

- `nthlayer-workers/src/nthlayer_workers/learn/cli.py` — jmy.6 already emits whatever recs the engine produces; no flag, no subcommand change.
- `nthlayer-workers/src/nthlayer_workers/learn/apply.py` — `ApplyResult` / `SkippedRecommendation` / `RecOutcome` consumed unchanged via the existing `classify_outcome` contract.
- `nthlayer-workers/src/nthlayer_workers/learn/pr.py` — PR path unchanged.
- `nthlayer-common/src/nthlayer_common/outcomes.py` — no new shared dataclass.

---

## Phase A — `_yaml.py` sigil semantics (lowest layer)

### Task A1: `apply_at_path` `[+]` sigil — append semantics

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/_yaml.py`
- Test: `nthlayer-workers/tests/learn/test_yaml.py`

- [ ] **Step 1: Write failing tests**

```python
def test_apply_at_path_append_to_existing_list():
    doc = {"spec": {"dependencies": [{"name": "a", "type": "downstream"}]}}
    apply_at_path(doc, "spec.dependencies[+]", {"name": "b", "type": "unknown"})
    assert doc["spec"]["dependencies"] == [
        {"name": "a", "type": "downstream"},
        {"name": "b", "type": "unknown"},
    ]

def test_apply_at_path_append_creates_list_when_absent():
    doc = {"spec": {}}
    apply_at_path(doc, "spec.dependencies[+]", {"name": "b", "type": "unknown"})
    assert doc["spec"]["dependencies"] == [{"name": "b", "type": "unknown"}]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-workers
uv run pytest tests/learn/test_yaml.py -v -k append
```

Expected: FAILED — `[+]` sigil not yet recognised.

- [ ] **Step 3: Implement sigil in `apply_at_path`**

In `_yaml.py` (lines 59–88), detect a trailing `[+]` on the last path segment. Strip it, resolve the parent path, and append `value` to the list at that key. If the key is absent on the parent dict, create an empty list, then append. Do not mutate any other branch of the function.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_yaml.py -v -k append
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/_yaml.py tests/learn/test_yaml.py
git commit -m "feat(yaml): add [+] sigil to apply_at_path for list-append · opensrm-jmy.21

Recognises a trailing [+] on the last path segment and appends value
to the list at the parent key (creating the list if absent). Sigil-only
— no type sniffing. Enables the add_dependency recommendation type to
patch spec.dependencies[+] without bespoke heuristics in the apply layer."
```

---

### Task A2: `classify_outcome` list-append branch

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/_yaml.py`
- Test: `nthlayer-workers/tests/learn/test_yaml.py`

- [ ] **Step 1: Write failing tests**

```python
def test_classify_outcome_append_name_present_is_already_applied():
    doc = {"spec": {"dependencies": [{"name": "b"}]}}
    result = classify_outcome(doc, "spec.dependencies[+]", {"name": "b", "type": "unknown"})
    assert result is RecOutcome.ALREADY_APPLIED

def test_classify_outcome_append_name_absent_is_apply_clean():
    doc = {"spec": {"dependencies": [{"name": "a"}]}}
    result = classify_outcome(doc, "spec.dependencies[+]", {"name": "b", "type": "unknown"})
    assert result is RecOutcome.APPLY_CLEAN

def test_classify_outcome_append_parent_is_dict_is_drift_detected():
    doc = {"spec": {"dependencies": {"a": {}}}}  # operator hand-edited to map shape
    result = classify_outcome(doc, "spec.dependencies[+]", {"name": "b", "type": "unknown"})
    assert result is RecOutcome.DRIFT_DETECTED

def test_classify_outcome_append_parent_is_scalar_is_drift_detected():
    doc = {"spec": {"dependencies": "see-readme"}}
    result = classify_outcome(doc, "spec.dependencies[+]", {"name": "b", "type": "unknown"})
    assert result is RecOutcome.DRIFT_DETECTED

def test_classify_outcome_append_absent_path_is_apply_clean():
    doc = {"spec": {}}
    result = classify_outcome(doc, "spec.dependencies[+]", {"name": "b", "type": "unknown"})
    assert result is RecOutcome.APPLY_CLEAN
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAILED — sigil branch not recognised by `classify_outcome`.

- [ ] **Step 3: Implement append branch in `classify_outcome`**

In `_yaml.py` (lines 145–183), detect `[+]` on the last path segment. Resolve the parent value:
- Parent is a list AND value (a dict) has a `name` key matching an existing element's `name` → `ALREADY_APPLIED`.
- Parent is a list AND no name match → `APPLY_CLEAN`.
- Parent path absent → `APPLY_CLEAN` (the append will create the list).
- Parent is anything else (dict, scalar) → `DRIFT_DETECTED`.

Three-state taxonomy preserved.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_yaml.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/_yaml.py tests/learn/test_yaml.py
git commit -m "feat(yaml): classify_outcome handles [+] list-append sigil · opensrm-jmy.21

Adds the list-append branch to the three-state outcome taxonomy:
name-match → ALREADY_APPLIED, no match (or absent path) → APPLY_CLEAN,
parent is dict/scalar → DRIFT_DETECTED. Matches the apply primitive
landed in the previous commit; preserves the existing taxonomy shape."
```

---

## Phase B — `retrospective.py` enrichment

### Task B1: Populate `declared_dependencies_by_service` in retrospective metadata

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/retrospective.py`
- Test: `nthlayer-workers/tests/learn/test_retrospective_financial.py` (or sibling `test_retrospective.py` — co-locate with the existing per-service-manifest tests)

- [ ] **Step 1: Write failing test**

```python
def test_build_retrospective_populates_declared_dependencies_by_service(tmp_path):
    """jmy.21: retrospective metadata carries declared deps per blast-radius service."""
    # Arrange: write two manifests under tmp_path/specs/.
    #   fraud-detect declares [{name: payments-api}, {name: catalog-api}].
    #   payments-api declares [{name: ledger}].
    # Build a fake incident with blast_radius = [fraud-detect, payments-api].
    # Act: retro = build_retrospective(incident, specs_dir=tmp_path / "specs", ...)
    # Assert:
    custom = retro.metadata.custom
    assert custom["declared_dependencies_by_service"] == {
        "fraud-detect": ["payments-api", "catalog-api"],
        "payments-api": ["ledger"],
    }
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/learn/test_retrospective_financial.py -v -k declared_dependencies_by_service
```

Expected: FAIL — field not yet populated.

- [ ] **Step 3: Extend the manifest-loading branch**

In `retrospective.py`, locate the per-service manifest loop used by `_compute_financial_impact` (around lines 197–319). The loop already opens each blast-radius service's manifest. While the manifest is in hand, also extract `spec.dependencies` (default `[]`), map each entry to its `name`, and accumulate into a `dict[str, list[str]]` keyed by service name. Store it on the retrospective verdict's `metadata.custom["declared_dependencies_by_service"]` next to `metadata.custom["financial_impact"]` (line 147).

Edge cases: service missing from `specs_dir` → omit from the map (matches existing `_compute_financial_impact` tolerance); `spec.dependencies` absent → empty list for that service; entry without a `name` key → skip silently (defensive; manifest validation is upstream).

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/learn/test_retrospective_financial.py -v
```

Expected: PASS. Also run existing retrospective tests to confirm no regression.

```bash
uv run pytest tests/learn/test_retrospective.py tests/learn/test_retrospective_financial.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/retrospective.py tests/learn/test_retrospective_financial.py
git commit -m "feat(retrospective): populate declared_dependencies_by_service · opensrm-jmy.21

Extends the existing manifest-loading branch (alongside financial_impact)
to record a per-service map of declared dependency names on the
retrospective verdict's metadata.custom. Propagation-only — no new
inputs into build_retrospective, no new compute path. Consumed by
analyze_incident in the add_dependency heuristic landing next."
```

---

## Phase C — `recommendations.py` new heuristic

### Task C1: `_add_dependency_recommendations` heuristic + wire into `analyze_incident`

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py`
- Test: `nthlayer-workers/tests/learn/test_recommendations.py`

- [ ] **Step 1: Write failing tests**

Add a new test class to `test_recommendations.py`:

```python
class TestAddDependencyRecommendation:
    def test_empty_blast_radius_produces_no_rec(self):
        # incident.blast_radius == [] → no add_dependency recs.

    def test_trigger_service_only_produces_no_rec(self):
        # blast_radius == [trigger]; nothing undeclared after self-exclude.

    def test_declared_deps_excluded(self):
        # blast_radius = [trigger, payments]; trigger declares [payments] → no rec.

    def test_trigger_service_self_excluded(self):
        # blast_radius = [trigger, payments]; trigger declares [] →
        # exactly one rec for payments, none for trigger itself.

    def test_multiple_undeclared_produces_multiple_recs(self):
        # blast_radius = [trigger, a, b, c]; trigger declares [] →
        # three recs, one per missing service.

    def test_rec_shape(self):
        rec = ...  # single undeclared dep "payments-api"
        assert rec.type == "add_dependency"
        assert rec.field == "spec.dependencies[+]"
        assert rec.current_value is None
        assert rec.proposed_value == {"name": "payments-api", "type": "unknown"}
        assert rec.confidence == 0.5
        assert "blast radius" in rec.rationale.lower()
        assert rec.service == "<trigger-service>"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_recommendations.py::TestAddDependencyRecommendation -v
```

Expected: FAIL — heuristic not yet wired.

- [ ] **Step 3: Implement the heuristic**

In `recommendations.py`:

1. Add module constant near other confidence constants:

```python
_ADD_DEPENDENCY_CONFIDENCE = 0.5
```

2. Add private function:

```python
def _add_dependency_recommendations(
    incident,
    retrospective_data: dict,
) -> list[Recommendation]:
    trigger = incident.trigger_service
    blast_radius = set(incident.blast_radius or [])
    declared_by_service = retrospective_data.get("declared_dependencies_by_service", {})
    declared = set(declared_by_service.get(trigger, []))
    undeclared = sorted(blast_radius - declared - {trigger})
    return [
        Recommendation(
            id=_make_rec_id(...),
            service=trigger,
            type="add_dependency",
            field="spec.dependencies[+]",
            current_value=None,
            proposed_value={"name": svc, "type": "unknown"},
            rationale=(
                f"{svc} appeared in this incident's blast radius but was "
                f"not declared as a dependency on {trigger}. Add the edge "
                f"so future incidents propagate through the declared topology."
            ),
            confidence=_ADD_DEPENDENCY_CONFIDENCE,
        )
        for svc in undeclared
    ]
```

3. Wire into `analyze_incident` alongside the existing heuristic calls, extending the returned `recommendations` list. Order: existing recs first, then `add_dependency` recs (deterministic; sorted blast radius gives deterministic per-rec order).

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_recommendations.py -v
```

Expected: all PASS, including the existing `tighten_slo` / `add_deploy_gate` tests (no regression).

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/recommendations.py tests/learn/test_recommendations.py
git commit -m "feat(recommendations): add add_dependency heuristic · opensrm-jmy.21

For the trigger service S of an incident, emits one Recommendation per
service in (blast_radius - declared_deps[S] - {S}), patching
spec.dependencies[+] with {name, type: unknown}. Confidence 0.5
(constant _ADD_DEPENDENCY_CONFIDENCE). Operator fills type / criticality
/ SLO guarantees on the PR — requires_human_review is already True."
```

---

## Phase D — Gates + R5

### Task D1: Local gates

- [ ] **pytest**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-workers
uv run pytest -q
```

Expected: all green; new tests pass (sigil tests + retrospective field test + `TestAddDependencyRecommendation`); no regressions in the existing `_yaml.py` / `retrospective.py` / `recommendations.py` suites.

- [ ] **ruff**

```bash
uv run ruff check src/ tests/
```

- [ ] **mypy** (if configured in the repo's CI)

```bash
uv run mypy src/
```

### Task D2: R5 supervise

- [ ] Run `/r5-supervise jmy.21` to drive the 4-pass Rule-of-Five review (Correctness / Clarity / Edge Cases / Excellence) sequentially per the ecosystem-root protocol. Each pass: review → fix findings → commit → next pass. The supervisor coordinates via `.claude/r5-state.json` and the parallel-block hook prevents cross-session reviewer dispatches while state is in flight.

Special attention areas for reviewers:
- **Correctness:** trigger-service self-exclusion in `_add_dependency_recommendations`; `[+]` sigil parsing in `apply_at_path` against deeply-nested paths; `classify_outcome` taxonomy completeness on the absent-parent edge.
- **Clarity:** rationale string template; constant naming (`_ADD_DEPENDENCY_CONFIDENCE`); field-string round-trip between rec and YAML doc.
- **Edge cases:** missing manifest for a blast-radius service; manifest with `spec.dependencies` as a non-list; duplicate entries in blast radius; trigger service absent from `declared_dependencies_by_service`.
- **Excellence:** rec id determinism; sort order; rationale wording matches `tighten_slo` / `add_deploy_gate` tone.

---

## References

- Spec: `nthlayer/docs/superpowers/specs/2026-05-29-jmy21-add-dependency-design.md`
- Bead: `opensrm-jmy.21`
- Foundation: `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py::analyze_incident` (jmy.2), `retrospective.py::build_retrospective` (jmy.1, lines 197–319), `_yaml.py::apply_at_path` + `classify_outcome` (jmy.6, lines 59–88 + 145–183).
- Sibling precedent: `nthlayer/docs/superpowers/plans/2026-05-28-jmy23-financial-impact.md` (propagation-not-recomputation through `retrospective_data`).
- Sibling precedent: `nthlayer/docs/superpowers/plans/2026-05-29-jmy25-json-output.md` (additive CLI-surface sibling; same Phase A/B/C/D shape).
- Follow-up beads (to file post-merge): per-chain-service emission; topology_drift corroboration gate; inferred dependency `type` from trace metadata.
