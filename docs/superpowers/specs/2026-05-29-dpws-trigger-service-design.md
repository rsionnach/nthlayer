# Populate `trigger_service` on Retrospectives Design (opensrm-dpws)

**Status:** Design-locked. Author: Rob Fox. Date: 2026-05-29. Bead: `opensrm-dpws`. Parent: `opensrm-jmy.21` (`add_dependency` recommendation type) — this bead populates the upstream key that jmy.21's heuristic reads, turning the recommendation type from "lands but never fires" into a working end-to-end signal.

**Foundation:**
- `nthlayer-workers/src/nthlayer_workers/learn/retrospective.py::build_retrospective` (CLI path) — already loads manifests for `_compute_financial_impact` and populates `metadata.custom["declared_dependencies_by_service"]` (jmy.21). Missing: `metadata.custom["trigger_service"]`.
- `nthlayer-workers/src/nthlayer_workers/learn/worker.py::LearnRetrospectiveModule._generate_retrospective` (worker path) — emits retrospective **assessment** (`data.{...}` shape, not `metadata.custom`). Missing: `data["trigger_service"]` AND `data["declared_dependencies_by_service"]`. Currently fetches no manifests.
- `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py::_add_dependency_recommendations` (jmy.21) — reads `incident_custom["trigger_service"]`. Absent → `log.debug("add_dependency_skipped")` + `[]`. This is the back-compat path the bead is closing.

---

## 1. Problem statement

`_add_dependency_recommendations` was landed by jmy.21 with deliberate back-compat tolerance: absent `trigger_service` is logged at debug and produces zero recommendations rather than crashing. No code path currently populates that key. Until it does, jmy.21's third recommendation type ships but never fires — silent no-op in both production and the demo orchestrator. This bead wires `trigger_service` and the parity-required `declared_dependencies_by_service` into both retrospective code paths.

---

## 2. Existing surface

- **CLI path** (`build_retrospective`) writes a retrospective **Verdict** with `metadata.custom = {blast_radius, declared_dependencies_by_service, financial_impact, recommendations, ...}`. Has `incident` (the incident verdict) and `correlation_verdicts` (walked from lineage). Already loads on-disk manifests via `_load_manifests_from_specs(specs_dir)` and produces `declared_dependencies_by_service` via `_extract_declared_dependencies(loaded_manifests: dict[str, Manifest])`. Returns canonical `dict[str, list[str]]`.
- **Worker path** (`LearnRetrospectiveModule._generate_retrospective`) emits a retrospective **Assessment** with `data = {correlation_snapshot_id, blast_radius (from snapshot.data.affected_services), recommendations, ...}`. Has the `correlation_snapshot` dict — already extracts `service = snapshot.get("service", domain.get("service", "unknown"))`. Has `CoreAPIClient` (`self.client`) but does not currently call `get_manifests()`.
- **Downstream consumer** (`_add_dependency_recommendations`) only reads `declared_map.get(trigger, [])`. It does NOT iterate other entries. This shapes the coverage policy (§ 3.4): only the trigger's own manifest matters for correctness; gaps in other services' manifests are harmless to this heuristic.
- **Adapter shape:** `analyze_incident(retrospective_data, incident_id)` expects `retrospective_data["incident_custom"]["trigger_service"]` — wrapped under `incident_custom`. The CLI path writes flat `metadata.custom["trigger_service"]`; the future jmy.6 adapter (`_build_plan_from_incident`, currently `NotImplementedError`) is responsible for reshaping. This bead writes flat in both paths; the wrapping shape is the adapter's concern, not ours.

---

## 3. Locked decisions

### 3.1 Source-of-truth precedence: correlation-first, subject-fallback

A shared helper `_resolve_trigger_service(correlation_candidates: list[str | None], fallback: str | None) → str | None`:
- First non-empty string in `correlation_candidates` → return it
- Else `fallback` if non-empty → return it
- Else `None` — caller OMITS the key entirely

Per-path inputs:
- **CLI:** `correlation_candidates = [v.subject.service for v in correlation_verdicts]`, `fallback = incident.subject.service`
- **Worker:** `correlation_candidates = [snapshot["data"]["domain"]["service"]]`, `fallback = snapshot["service"]`

Rationale: The correlator's grouping IS the trigger context — a correlation verdict's `subject.service` is literally "the service the correlator anchored a session window on." Falling back to `incident.subject.service` (CLI) / top-level `snapshot["service"]` (worker) keeps the feature working for breach-fallback incidents, pre-correlate scenarios, and any future degraded path where the correlator's domain isn't populated.

### 3.2 Absence semantics: omit, don't write `None`

When `_resolve_trigger_service` returns `None`, the caller does NOT add `trigger_service` to the metadata/data dict. Existing pre-jmy.21 retrospectives (and any retrospective where no service can be resolved) continue to look exactly like they did. The downstream `_add_dependency_recommendations` already handles the absent key via `incident_custom.get("trigger_service")` → `None` → no-rec. Writing `None` would be a wire-shape regression with no behavioural gain.

### 3.3 Shared `declared_dependencies_by_service` builder in `nthlayer_common.manifest`

Divergence analysis: CLI input is `dict[str, Manifest]` (attribute access on `Dependency` dataclasses); worker input is `list[dict]` (key access on raw JSON dicts from `GET /manifests`). The output construction is identical: `dict[str, list[str]]`. This is deserialisation-only divergence, not semantic divergence.

Extract a single helper in `nthlayer_common.manifest`:

```python
def extract_declared_dependencies(
    *,
    from_manifests: dict[str, "ReliabilityManifest"] | None = None,
    from_dicts: list[dict] | None = None,
) -> dict[str, list[str]]:
    """Single source of truth for declared-dep extraction.

    Exactly one of from_manifests / from_dicts must be supplied.
    Output shape is identical regardless of input format.
    """
```

CLI's existing `_extract_declared_dependencies` in `retrospective.py` becomes a one-line wrapper that calls `extract_declared_dependencies(from_manifests=loaded_manifests)`. Worker calls `extract_declared_dependencies(from_dicts=manifest_dicts)`.

Rationale: matches the established "align internal types with canonical shapes" pattern (per CLAUDE.md). The dispatch is explicit and keyword-only — `from_manifests=X` vs `from_dicts=Y` makes the call site self-documenting. R5 won't flag this as polymorphic complexity because the two branches are narrow (~3 lines each) and the input formats are publicly named in the signature.

### 3.4 Worker-path coverage policy: trigger-manifest-narrow

`declared_dependencies_by_service` is populated when the trigger's own manifest is in the API result. Other blast-radius services missing from the catalogue → harmless (downstream consumer doesn't iterate them).

Decision matrix for worker-path `declared_dependencies_by_service`:

| Condition | Action | Log |
|---|---|---|
| `client.get_manifests()` fails (`result.ok=False`) | Omit field | `WARN learn_manifest_fetch_failed` |
| Returns empty list | Omit field | `INFO learn_manifest_catalogue_empty` |
| Returns data, trigger's manifest absent | Omit field | `WARN learn_trigger_manifest_absent service=<trigger>` |
| Returns data including trigger's manifest | Populate from `extract_declared_dependencies(from_dicts=...)` | (no log) |

Note: the third row is the narrower interpretation of the original "partial coverage" refinement. The downstream `_add_dependency_recommendations` only consults `declared_map.get(trigger, [])` — it never iterates other entries. Therefore non-trigger manifest gaps cannot produce wrong recs. Tighter "any blast-radius gap → omit" would cause more false-omits without preventing any false-positive recs.

Rationale: matches actual downstream behaviour; minimises noise; documents the analysis explicitly so a future contributor (or a future downstream consumer that DOES iterate) has the trail.

### 3.5 CLI-path coverage policy: unchanged

The CLI path already populates `declared_dependencies_by_service` from `specs_dir` manifests (jmy.21). This bead adds NO new coverage logic to the CLI path — the existing helper handles empty `specs_dir` by producing `{}`, which downstream `_add_dependency_recommendations` reads as "trigger has no declared deps." That's the back-compat behaviour and we keep it; the new `trigger_service` key is the only change to `build_retrospective`'s output.

The asymmetry (worker omits on coverage gap, CLI populates `{}`) is intentional: the worker's coverage gap is "API unavailability" (a transient external failure), while the CLI's empty `specs_dir` is "operator chose to run without specs" (an explicit user state). Different semantics → different policies.

### 3.6 `trigger_service` is always written when resolvable, independent of declared_deps coverage

A retrospective with `trigger_service` populated but `declared_dependencies_by_service` omitted is a legitimate state: it tells consumers "we know the trigger, but we couldn't verify its declared deps right now." Downstream `_add_dependency_recommendations` handles this combination cleanly via `declared_map.get(trigger, [])` → `[]` → empty `declared_for_trigger` set → over-broad recs (but only the operator-review-required path, not a silent miss). The alternative — omit `trigger_service` when we can't verify deps — would couple two orthogonal concerns and lose the trigger identity for other consumers (the demo orchestrator, future analyses).

### 3.7 Integration test deferred to jmy.6

End-to-end verification ("seed an incident, run learn retrospective, run `learn recommendations`, assert `add_dependency` recs in output plan") chains on jmy.6's `_build_plan_from_incident` adapter, currently a `NotImplementedError` stub. The disposition: this integration test belongs in jmy.6's scope (it verifies the recommendation→apply workflow end-to-end; dpws's output is one input to that workflow). Filed as a note on the jmy.6 design doc rather than a separate followup bead.

---

## 4. Out of scope

- **Reshaping the `incident_custom`-wrapped dict that `analyze_incident` expects.** The bead writes flat `trigger_service` at the top level of `metadata.custom` / `data`. The `analyze_incident` adapter that wraps it under `incident_custom` is jmy.6's `_build_plan_from_incident`, still a stub.
- **`declared_dependencies_by_service` for non-trigger services on the worker path beyond what `client.get_manifests()` naturally returns.** Per § 3.4, we populate every service whose manifest the API returns, but we don't make extra calls to fill gaps.
- **Auditing CLI-path coverage.** The existing helper handles `specs_dir` absence by producing `{}`; this bead does not extend it.
- **Replacing the `_extract_declared_dependencies` helper in `retrospective.py` with the shared helper.** Replace it, yes (per § 3.3) — but this is the only adapter-style change to the existing file; no broader refactor.
- **Integration test for end-to-end add_dependency emission.** Deferred to jmy.6's scope per § 3.7.

---

## 5. Test surface

~9 tests total across three files.

### 5.1 New file: `tests/learn/test_retrospective_trigger.py`

CLI-path coverage. Builds a synthetic incident + correlation verdict pair, calls `build_retrospective`, inspects `retro.metadata.custom`.

- `test_trigger_service_from_correlation_verdict` — correlation verdict's `subject.service="fraud-detect"` → `metadata.custom["trigger_service"] == "fraud-detect"`
- `test_trigger_service_fallback_to_incident_subject` — no correlation verdicts in lineage → uses `incident.subject.service`
- `test_trigger_service_omitted_when_neither` — both correlation absent and `incident.subject.service` empty → key absent from `metadata.custom`
- `test_trigger_service_skips_empty_correlation_subject_to_fallback` — correlation verdict present but `subject.service` is `""` / `None` → skipped, falls through to `incident.subject.service`

### 5.2 Extend `tests/learn/test_learn_worker.py::TestRetrospectiveCycle`

Worker-path coverage. Mocks `client.get_assessments` to seed snapshot, `client.get_verdicts` to seed chain, `client.get_manifests` to seed catalogue.

- `test_retrospective_includes_trigger_service` — snapshot has `data.domain.service="fraud-detect"` → emitted assessment's `data["trigger_service"] == "fraud-detect"`
- `test_retrospective_trigger_service_fallback_to_top_level_service` — `data.domain.service` absent → uses `snapshot["service"]`
- `test_retrospective_includes_declared_dependencies` — `get_manifests` returns trigger's manifest → `data["declared_dependencies_by_service"]` populated with at least the trigger's entry
- `test_retrospective_omits_declared_deps_when_manifest_fetch_fails` — `get_manifests` returns `APIResult(ok=False)` → `data["declared_dependencies_by_service"]` absent, retrospective still emitted, no crash
- `test_retrospective_omits_declared_deps_when_trigger_manifest_absent` — `get_manifests` returns list NOT containing the trigger's manifest → `data["declared_dependencies_by_service"]` absent (§ 3.4 row 3)

### 5.3 New tests in `nthlayer-common/tests/test_manifest_parser.py`

Shared helper coverage. Both branches of `extract_declared_dependencies`.

- `test_extract_declared_dependencies_from_manifests` — input `dict[str, ReliabilityManifest]` with mixed empty/non-empty `dependencies` → correct `dict[str, list[str]]`
- `test_extract_declared_dependencies_from_dicts` — input `list[dict]` matching `GET /manifests` wire shape → correct `dict[str, list[str]]`
- `test_extract_declared_dependencies_requires_exactly_one_input` — neither / both supplied → `ValueError`
- `test_extract_declared_dependencies_skips_dict_with_no_name` — input `list[dict]` containing `{"dependencies": [...]}` without `name` → entry silently skipped (matches `_extract_service_slos` precedent)

---

## 6. Implementation plan

Five edit sites, ordered to minimise rebases:

1. **`nthlayer-common/src/nthlayer_common/manifest/parser/_shared.py`** (existing): add `extract_declared_dependencies` with keyword-only `from_manifests` / `from_dicts` args. Export via `nthlayer_common/manifest/__init__.py`.
2. **`nthlayer-common/tests/test_manifest_parser.py`**: add the 4 new tests for the helper.
3. **`nthlayer-workers/src/nthlayer_workers/learn/retrospective.py`**:
   - Add `_resolve_trigger_service` helper (module-level).
   - Replace `_extract_declared_dependencies` body with a call to `extract_declared_dependencies(from_manifests=loaded_manifests)`.
   - In `build_retrospective`, after computing `correlation_verdicts`, compute `trigger = _resolve_trigger_service([v.subject.service for v in correlation_verdicts], incident.subject.service)`. If non-None, add to `metadata.custom["trigger_service"]`.
4. **`nthlayer-workers/src/nthlayer_workers/learn/worker.py`**:
   - In `_generate_retrospective`, after computing `service`, compute trigger via shared `_resolve_trigger_service` (move to `_helpers.py` or duplicate inline — see § 6.1).
   - Add `manifests_result = await self.client.get_manifests()` call.
   - Build `declared_dependencies_by_service` via `extract_declared_dependencies(from_dicts=...)` only when trigger's manifest is present in the result.
   - Add both to `data` dict in the constructed assessment.
5. **`nthlayer-workers/tests/learn/test_retrospective_trigger.py`** (new) + extensions to `test_learn_worker.py`.

### 6.1 Helper placement

`_resolve_trigger_service` is used by both `retrospective.py` (CLI path) and `worker.py` (worker path). Two reasonable homes:

- (a) Inline in each module (4 lines, trivial; duplicates the docstring)
- (b) Module-level in `nthlayer_workers/learn/__init__.py` or a new `_trigger.py`

Recommend (b) — single source for the precedence rule, easier to audit. New file `nthlayer_workers/learn/_trigger.py` exports `resolve_trigger_service`. Both callers import.

---

## 7. Effort

- 1 shared helper in `nthlayer_common.manifest` (~15 LOC + 4 tests)
- 1 module-level helper in `nthlayer_workers/learn/_trigger.py` (~10 LOC + tested via callers)
- 2 file modifications in `nthlayer-workers/learn/` (~20 LOC additive total)
- 9 tests (~150 LOC)
- R5 supervise (4 passes, sequential)

Estimate: 0.5–1 session including R5. Matches the bead's original estimate.
