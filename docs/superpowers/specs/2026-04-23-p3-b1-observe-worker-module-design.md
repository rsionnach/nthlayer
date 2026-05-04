# P3-B.1: Observe Worker Module — SLO Collection via Core API

**Date:** 2026-04-23
**Epic:** P3-B (Observe Module)
**Dependencies:** P3-A.1 (module runner), P2-A.3 (manifest catalogue)
**Spec:** NTHLAYER-SERVE-MODE-v2.1 §5.2

## Summary

Adapt the existing observe SLO collection to work as a worker module. The work is sequenced in two phases: first align observe's internal types with the canonical v1.5 shapes (eliminating adapter friction), then build the `ObserveModule` on the aligned internals.

## Design Principle

When the existing component's internal shape differs from the canonical v1.5 shape, update the component — don't write adapters. Adapters are appropriate when modifying code you don't own. Inside our codebase, alignment is cheaper long-term.

---

## Phase A: Internal Alignment (cleanup, no new functionality)

Three independent changes. Each is verifiable in isolation: run existing observe tests after each change, confirm zero regressions (with updated string assertions).

### A1. Rename `slo_state` → `slo_status` across observe

**Rationale:** The CloudEvents taxonomy (NTHLAYER-TELEMETRY-ENVELOPE-v1 §3) defines `slo_status` as the canonical assessment kind. Observe currently uses `slo_state`. Aligning now means CloudEvents wrapping works with zero translation.

**Scope:**
- `nthlayer-workers/src/nthlayer_workers/observe/assessment.py`: update `VALID_ASSESSMENT_TYPES` — `"slo_state"` → `"slo_status"`
- `nthlayer-workers/src/nthlayer_workers/observe/slo/collector.py`: `results_to_assessments()` — `create("slo_state", ...)` → `create("slo_status", ...)`
- `nthlayer-workers/src/nthlayer_workers/observe/cli.py`: any string references to `"slo_state"` in `_cmd_collect`, `_cmd_explain`, `_cmd_portfolio`
- `nthlayer-workers/src/nthlayer_workers/observe/portfolio/aggregator.py`: filter queries using `"slo_state"` → `"slo_status"`
- `nthlayer-workers/src/nthlayer_workers/observe/gate/evaluator.py`: `AssessmentFilter(assessment_type="slo_state")` → filter by kind=`"slo_status"`
- `nthlayer-workers/src/nthlayer_workers/observe/explanation.py`: if it filters by assessment type
- `nthlayer-workers/src/nthlayer_workers/observe/decision_records.py`: `_TYPE_MAP` keys, `map_severity()` branches, `build_stream()` branches, `generate_summaries()` branches
- All test files referencing `"slo_state"` — string replacement

**Also rename `drift` → `drift_signal`** to match CloudEvents `_ASSESSMENT_KINDS`. Same mechanical process.

**Do NOT rename** `verification`, `gate`, or `dependency`. These are observe-internal types consumed by observe's own functions (check-deploy, portfolio, discover). They're not submitted to core in P3-B.1 — that's P3-B.2 scope. Renaming them now would be premature; P3-B.2 will decide whether they become CloudEvents kinds or remain internal.

**Verification:** `uv run pytest nthlayer-workers/tests/observe/ -x` — all tests pass with updated strings.

### A2. Align observe `Assessment` class fields with core API

**Rationale:** Core's `POST /assessments` requires `{id, service, kind, created_at}`. Observe's `Assessment` uses `{id, service, assessment_type, timestamp, producer, data}`. Aligning field names means `to_dict()` output is directly submittable to core — no translation layer.

**Changes to `assessment.py`:**

```python
# Before
@dataclass
class Assessment:
    id: str
    timestamp: datetime
    assessment_type: str
    service: str
    producer: str
    data: dict

# After
@dataclass
class Assessment:
    id: str
    created_at: datetime
    kind: str
    service: str
    producer: str
    data: dict
```

**Changes to `create()`:** parameter `assessment_type` → `kind`. Validation set name updated.

**Changes to `to_dict()` / `from_dict()`:** field names updated (`"timestamp"` → `"created_at"`, `"assessment_type"` → `"kind"`).

**Downstream updates:**
- Every file that accesses `assessment.timestamp` → `assessment.created_at`
- Every file that accesses `assessment.assessment_type` → `assessment.kind`
- Every call to `create("slo_status", ...)` already has positional `assessment_type` → rename parameter
- `AssessmentFilter` in `store.py`: field `assessment_type` → `kind`
- `SQLiteAssessmentStore`: column names in SQL statements — `assessment_type` → `kind`, `timestamp` → `created_at`
- All test files

**SQLite schema migration:** The observe CLI's local SQLite store has columns named `assessment_type` and `timestamp`. The column rename applies to the observe-internal store schema. This is a v1.5 migration — the store is local, not shared. Either:
- (a) Drop and recreate (acceptable for local assessment stores — they're ephemeral, rebuilt by `collect`)
- (b) `ALTER TABLE assessments RENAME COLUMN assessment_type TO kind` (SQLite 3.25+)

Recommend (a) — the assessment store is rebuilt every `collect` run. No migration complexity.

**Verification:** `uv run pytest nthlayer-workers/tests/observe/ -x` — all tests pass with updated field names.

### A3. Delete observe's local `SLODefinition`, use common model

**Rationale:** Observe has its own `SLODefinition(service, name, spec: dict)` in `slo/spec_loader.py`. The canonical model is `nthlayer_common.manifest.models.SLODefinition` with typed fields (`target`, `window`, `indicator_query`, etc.). Using the canonical model means the collector can accept SLOs from any source (local YAML via parser, or core API) without translation.

**Changes to `slo/collector.py`:**

Replace all `slo_def.spec[...]` dict access with typed field access:

| Before (raw dict) | After (typed field) |
|---|---|
| `spec.get("target", spec.get("objective", 99.9))` | `slo_def.target` |
| `spec.get("window", "30d")` | `slo_def.window` |
| `spec.get("indicator", {}).get("query")` | `slo_def.indicator_query` |
| `indicators[0]["success_ratio"]["total_query"]` | `slo_def.total_query` |
| `indicators[0]["success_ratio"]["good_query"]` | `slo_def.good_query` |

The collector also needs `service` context. The common `SLODefinition` does NOT carry a `service` field — it's a property of `ReliabilityManifest`, not individual SLOs. Two options:

- **(i)** Change `collect()` signature to accept `list[tuple[str, SLODefinition]]` (service + SLO pairs)
- **(ii)** Change `collect()` to accept `list[ReliabilityManifest]` and iterate internally

Recommend **(i)**. The collector's job is "given SLOs, query Prometheus." It shouldn't know about manifests. The caller (CLI or ObserveModule) pairs SLOs with their service name. This keeps the collector's interface minimal and testable.

Updated signature:

```python
async def collect(self, slo_definitions: list[tuple[str, SLODefinition]]) -> list[tuple[str, SLOResult]]:
    """Collect SLO metrics. Each item is (service_name, slo_definition).
    Returns (service_name, result) pairs."""
```

Alternative: keep the flat `list[SLODefinition]` signature but add a `service` field as a property of `results_to_assessments` only. This is what happens now — `results_to_assessments(results, service)` takes service separately. The issue is the collector also needs service for `_build_slo_query()` template substitution (`${service}`).

**Revised recommendation:** Keep the existing pattern — `collect()` takes a flat list, and we pass service via a simple wrapper.

**File:** `nthlayer-workers/src/nthlayer_workers/observe/slo/collector.py` (co-located with the collector that uses it)

```python
@dataclass
class ServiceSLO:
    """SLO with its owning service name — bridges manifest-level context to collector."""
    service: str
    slo: SLODefinition
```

The collector accesses `item.service` and `item.slo.target`, etc. This is a data carrier, not an adapter — it adds the one piece of context (service name) that the common SLODefinition legitimately doesn't carry.

**Changes to `slo/spec_loader.py`:**
- Delete `SLODefinition` class
- `load_specs()` returns `list[ServiceSLO]` — constructs `ServiceSLO(service=name, slo=common_slo)` for each SLO
- Parsing: `load_specs()` currently reads raw YAML and builds its own `SLODefinition(service, name, spec=raw_dict)`. After this change, it needs to build `nthlayer_common.manifest.models.SLODefinition` from the raw YAML. **But** `load_manifest()` in nthlayer-common already does this. So `load_specs()` can call `load_manifest()` for each file and extract SLOs:

```python
def load_specs(specs_dir: str | Path) -> list[ServiceSLO]:
    specs_path = Path(specs_dir)
    if not specs_path.is_dir():
        raise ValueError(f"Specs directory does not exist: {specs_dir}")

    results: list[ServiceSLO] = []
    for path in sorted(specs_path.iterdir()):
        if path.suffix not in (".yaml", ".yml"):
            continue
        try:
            manifest = load_manifest(path, suppress_deprecation_warning=True)
        except (ManifestLoadError, FileNotFoundError, ValueError, OSError):
            continue
        for slo in manifest.slos:
            results.append(ServiceSLO(service=manifest.name, slo=slo))
    return results
```

This replaces ~40 lines of hand-rolled YAML parsing with a call to the canonical parser, which already handles v1/v2/legacy format detection.

**Changes to `_build_slo_query()`:**

```python
# Before
def _build_slo_query(spec: dict, indicator: dict, service_name: str) -> str | None:

# After
def _build_slo_query(slo: SLODefinition, service_name: str) -> str | None:
    query = slo.indicator_query
    if not query and slo.total_query and slo.good_query:
        query = f"({slo.good_query}) / ({slo.total_query})"
    if query:
        query = query.replace("${service}", service_name)
        query = query.replace("$service", service_name)
    return query
```

**Verification:** `uv run pytest nthlayer-workers/tests/observe/ -x` — all tests pass. Some test fixtures will need updating: tests that construct observe `SLODefinition(service, name, spec={...})` need to construct `ServiceSLO(service, SLODefinition(name, target, slo_type, ...))` instead.

---

## Phase B: ObserveModule Implementation

Built on the aligned internals from Phase A. No translation layers.

### B1. `ObserveModule` class

**File:** `nthlayer-workers/src/nthlayer_workers/observe/worker.py`

Implements the `WorkerModule` protocol from `runner.py`:

```python
@dataclass
class ObserveModule:
    """Observe worker module — SLO collection via core API.

    Reads manifests from core, queries Prometheus for SLI values,
    produces slo_status assessments, submits to core with CloudEvents envelope.
    """
    client: CoreAPIClient
    prometheus_url: str
    deployment_id: str | None = None

    @property
    def name(self) -> str:
        return "observe"

    async def restore_state(self, state: dict | None) -> None:
        """Observe SLO collection is stateless — no cursor or hysteresis needed.

        P3-B.2 (drift detection) will add hysteresis state here.
        """
        pass

    async def process_cycle(self) -> None:
        """One collection cycle: fetch manifests → query Prometheus → submit assessments."""
        # 1. Fetch manifests from core
        result = await self.client.get_manifests()
        if not result.ok:
            logger.warning("observe_manifest_fetch_failed", error=result.error)
            return
        manifests = result.data  # list[dict] from GET /manifests

        # 2. Extract ServiceSLO pairs from manifest dicts
        service_slos = _extract_service_slos(manifests)
        if not service_slos:
            return

        # 3. Collect SLO metrics from Prometheus
        collector = SLOMetricCollector(self.prometheus_url)
        results = await collector.collect(service_slos)

        # 4. Convert to assessments, wrap in CloudEvents, submit to core
        for service_name, slo_results in _group_by_service(results):
            assessments = results_to_assessments(slo_results, service_name)
            for assessment in assessments:
                envelope = wrap_assessment(
                    to_dict(assessment),
                    component="observe",
                    deployment_id=self.deployment_id,
                )
                await self.client.submit_assessment(envelope["data"])

    async def get_state(self) -> dict:
        """No persistent state for SLO collection."""
        return {}
```

### B2. Manifest dict → ServiceSLO extraction

The core API returns manifests as dicts (serialised by `catalogue.manifest_to_dict()`). The `ObserveModule` needs to convert these back to `ServiceSLO` pairs for the collector.

```python
def _extract_service_slos(manifest_dicts: list[dict]) -> list[ServiceSLO]:
    """Extract ServiceSLO pairs from core API manifest response."""
    results = []
    for m in manifest_dicts:
        service = m["name"]
        for slo_dict in m.get("slos", []):
            slo = SLODefinition(
                name=slo_dict["name"],
                target=slo_dict["target"],
                slo_type=slo_dict["slo_type"],
                window=slo_dict.get("window", "30d"),
                indicator_query=slo_dict.get("indicator_query"),
                judgment_type=slo_dict.get("judgment_type"),
            )
            results.append(ServiceSLO(service=service, slo=slo))
    return results
```

This reconstructs typed `SLODefinition` objects from the API response dicts. Only the fields the collector uses need to be populated (`name`, `target`, `slo_type`, `window`, `indicator_query`, `total_query`, `good_query`).

### B3. Add `get_manifests()` to CoreAPIClient

`CoreAPIClient` does NOT have manifest methods — confirmed gap. Add to `nthlayer-common/src/nthlayer_common/api_client.py`:

```python
async def get_manifests(self) -> APIResult:
    return await self._request("GET", "/manifests")

async def get_manifest(self, service: str) -> APIResult:
    return await self._request("GET", f"/manifests/{service}")
```

Add corresponding tests in `nthlayer-common/tests/test_api_client.py`.

### B4. Registration in workers CLI

In `nthlayer-workers/src/nthlayer_workers/cli.py`, register the observe module with the runner:

```python
from nthlayer_workers.observe.worker import ObserveModule

# In serve command handler:
observe = ObserveModule(
    client=runner.client,
    prometheus_url=config.prometheus_url,
    deployment_id=config.deployment_id,
)
runner.register(observe, interval_seconds=config.get("workers.observe.cycle_interval_seconds", 60))
```

Default cycle interval: 60 seconds.

---

## Test Strategy

### Phase A tests (existing suite, updated assertions)

All existing observe tests continue to pass — the changes are mechanical renames:
- String `"slo_state"` → `"slo_status"`, `"drift"` → `"drift_signal"` in assertions
- Field `assessment.timestamp` → `assessment.created_at` in assertions
- Field `assessment.assessment_type` → `assessment.kind` in assertions
- `SLODefinition(service, name, spec={...})` → `ServiceSLO(service, SLODefinition(name, target, slo_type, ...))` in fixtures

No test logic changes. No new test files for Phase A.

### Phase B tests (new file: `tests/observe/test_observe_worker.py`)

1. **`test_observe_module_protocol`** — verify `ObserveModule` satisfies `WorkerModule` protocol (name, restore_state, process_cycle, get_state)
2. **`test_process_cycle_happy_path`** — mock core API returns manifests, mock Prometheus returns SLI values → verify assessments submitted to core with correct kind=`slo_status`, correct service name, CloudEvents envelope
3. **`test_process_cycle_manifest_fetch_fails`** — mock core API returns error → verify no Prometheus queries, no assessments submitted, no crash
4. **`test_process_cycle_prometheus_fails`** — mock core API returns manifests, Prometheus unreachable → verify assessments with status=ERROR submitted (existing collector behavior)
5. **`test_process_cycle_assessment_submit_fails`** — mock core API returns 503 on submit → verify cycle completes (doesn't crash runner)
6. **`test_process_cycle_no_manifests`** — core returns empty manifest list → verify no-op
7. **`test_extract_service_slos`** — unit test for manifest dict → ServiceSLO extraction
8. **`test_restore_state_noop`** — verify restore_state accepts None and dict without error
9. **`test_get_state_empty`** — verify get_state returns empty dict

---

## Acceptance Criteria

From the epic tree, refined:

1. Reads manifests from core's `GET /manifests` endpoint
2. Queries Prometheus for each SLO's indicator (via existing `SLOMetricCollector`)
3. Produces `slo_status` assessments with correct status (HEALTHY/WARNING/CRITICAL/EXHAUSTED)
4. Submits assessments to core via `POST /assessments`
5. CloudEvents envelope on each assessment
6. **Existing observe tests pass after alignment renames (zero loss of coverage)**
7. New `ObserveModule` tests cover manifest fetching, API submission, CloudEvents wrapping
8. `ObserveModule` registered with `ModuleRunner` in workers CLI

## Work Sequence

| Step | What | Verify |
|------|------|--------|
| A1 | Rename `slo_state` → `slo_status`, `drift` → `drift_signal` | `pytest nthlayer-workers/tests/observe/ -x` |
| A2 | Rename Assessment fields: `assessment_type` → `kind`, `timestamp` → `created_at` | `pytest nthlayer-workers/tests/observe/ -x` |
| A3 | Delete observe `SLODefinition`, use common model + `ServiceSLO` carrier | `pytest nthlayer-workers/tests/observe/ -x` |
| B1 | Implement `ObserveModule` in `observe/worker.py` | New worker tests pass |
| B2 | Add `get_manifests()` to `CoreAPIClient` if missing | `pytest nthlayer-common/ -x` |
| B3 | Register in workers CLI | `pytest nthlayer-workers/ -x` (full suite) |

Steps A1–A3 are independent of each other and can be done in any order. Each is independently verifiable. Phase B depends on all of Phase A being complete.
