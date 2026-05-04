# P3-B.2: Observe Module — Drift Detection and Portfolio

**Date:** 2026-04-24
**Epic:** P3-B (Observe Module)
**Dependencies:** P3-B.1
**Spec:** Existing nthlayer-observe capabilities (drift, portfolio, blast-radius, check-deploy)

## Summary

Port remaining observe capabilities as functions within the observe worker module and as CLI commands. Each capability uses the data-access pattern appropriate to its data-flow shape — not one pattern applied uniformly.

## Data-Access Patterns

| Capability | Pattern | Input Source | Rationale |
|---|---|---|---|
| **Portfolio** | C (in-memory pass) | `list[SLOResult]` from current cycle | Synthesises current-cycle data; no round-trip needed |
| **Drift** | Direct Prometheus | Prometheus range queries + manifests from core | Needs raw SLI values over time, not stored assessments |
| **Blast radius** | Direct Prometheus | Prometheus dependency metrics + manifests from core | Queries runtime topology, not assessment history |
| **Deploy gate** | A (read from core API) | `CoreAPIClient.get_assessments()` + manifests from core | Consults historical state at deploy time |

---

## Assessment Kinds

### New kinds (add to NTHLAYER-TELEMETRY-ENVELOPE §3.4)

| Kind | Producer | Description |
|---|---|---|
| `portfolio_status` | observe | Org-level portfolio health aggregated from current-cycle SLO results |
| `deploy_gate` | observe | Deployment gate decision (APPROVED/WARNING/BLOCKED) |
| `dependency_graph` | observe | Runtime dependency topology observation |

### Existing kinds (already in §3.4)

| Kind | Producer | Description |
|---|---|---|
| `slo_status` | observe | Per-service SLO metric collection (P3-B.1) |
| `drift_signal` | observe | SLO budget drift detection |

### Lineage

- `portfolio_status` → `parent_ids: [slo_status_id_1, slo_status_id_2, ...]` — references the SLO assessments synthesised in the current cycle
- `deploy_gate` → `parent_ids: [slo_status_id_1, ...]` — references the historical SLO assessments consulted
- `drift_signal` → no parents (independent Prometheus observation)
- `dependency_graph` → no parents (independent Prometheus observation)

---

## Capability Details

### 1. Portfolio (Pattern C — in-memory pass)

**Execution:** Runs as post-processing within `ObserveModule.process_cycle()`, after SLO collection completes. Receives `list[SLOResult]` and the SLO assessment IDs from the current cycle directly — no store query.

**Changes to `portfolio/aggregator.py`:**

Add a new entry point alongside the existing `build_portfolio(store)`:

```python
def build_portfolio_from_results(
    results_by_service: dict[str, list[SLOResult]],
) -> PortfolioSummary:
    """Build portfolio summary from current-cycle SLO results.

    Used by ObserveModule.process_cycle() — receives results in-memory
    from the collector, no store round-trip.
    """
```

The existing `build_portfolio(store)` stays with its `AssessmentStore` interface. Works with `MemoryAssessmentStore` (tests), `SQLiteAssessmentStore` (existing `nthlayer-observe portfolio --store X` CLI), and `CoreAPIAssessmentStore` (future CLI path). The demo currently uses the local SQLite path; it switches to the tiered architecture in P5.5 (demo polish), not in P3-B.2. No demo.sh changes in this task.

**Assessment output:**

```python
Assessment(
    kind="portfolio_status",
    # "__portfolio__" sentinel: portfolio is an org-level assessment, not
    # per-service. Uses a reserved name that cannot collide with real
    # service names (which come from manifest metadata.name and cannot
    # contain leading underscores per OpenSRM validation).
    service="__portfolio__",
    data={
        "total_services": 8,
        "healthy_count": 5,
        "warning_count": 2,
        "critical_count": 1,
        "exhausted_count": 0,
        "services": [
            {"service": "fraud-detect", "overall_status": "WARNING", "slo_count": 2},
            ...
        ],
    },
)
```

`parent_ids` on the assessment: list of all `slo_status` assessment IDs from the current cycle.

**Known coupling:** Portfolio cycle time is coupled to SLO collection cycle time (both in `process_cycle()`). If SLO collection moves to faster cadence (e.g., 15s), portfolio produces proportionally more assessments. Acceptable for v1.5; revisit if faster collection is needed.

### 2. Drift Detection (Pattern: Direct Prometheus)

**Execution:** Runs on a configurable interval within the runner, separate from SLO collection. Default interval: 30 minutes.

**v1.5 interval:** Global only — `workers.observe.drift_interval_seconds` in `nthlayer.yaml` (default 1800 = 30m). Configurable via `--drift-interval` CLI flag.

**v2 interval (deferred):** Per-SLO drift interval via manifest. The `measurement.frequency` field exists on `JudgmentMeasurement` but not on classical SLOs. v2 adds a resolution order: SLO-level frequency → SLO-type default (classical availability: 15m, stability: daily) → global fallback. Requires extending `SLODefinition` with a `drift_frequency` field for classical SLOs.

**Changes to `drift/analyzer.py`:** None to the analysis logic. The `DriftAnalyzer` class already takes a Prometheus URL and queries range data directly.

**Changes to `ObserveModule`:**

Add a `drift_cycle()` method registered with the runner at the drift interval:

```python
async def drift_cycle(self) -> None:
    """Run drift analysis for all services and SLOs from manifests."""
    manifests = await self._fetch_manifests()
    if not manifests:
        return

    analyzer = DriftAnalyzer(self.prometheus_url)
    for service, tier, slo_name, window in _drift_targets(manifests):
        try:
            result = await analyzer.analyze(service, tier, slo_name, window)
        except DriftAnalysisError:
            logger.warning("drift_analysis_failed", service=service, slo=slo_name)
            continue

        assessment = create("drift_signal", service, {
            "slo_name": result.slo_name,
            "severity": result.severity.value,
            "pattern": result.pattern.value,
            "slope_per_week": result.metrics.slope_per_week,
            "days_until_exhaustion": result.projection.days_until_exhaustion,
            "current_budget": result.metrics.current_budget,
            "summary": result.summary,
            "recommendation": result.recommendation,
        })
        await self.client.submit_assessment(to_dict(assessment))
```

**Registration:** The runner supports multiple registrations per module. But `WorkerModule` protocol has a single `process_cycle()`. Two options:

- **(i)** Register two separate module instances (`ObserveCollectModule` + `ObserveDriftModule`) at different intervals
- **(ii)** Single `ObserveModule` with internal sub-cycle logic — `process_cycle()` runs SLO collection + portfolio; drift runs on a separate internal timer

Recommend **(i)** — cleaner separation, each module has one responsibility, no internal timer complexity. The runner already handles multiple modules at different intervals.

**Revised module structure:**

```
ObserveCollectModule   — interval: 60s  — SLO collection + portfolio
ObserveDriftModule     — interval: 1800s — drift analysis per service+SLO
ObserveTopologyModule  — interval: 86400s — blast radius/dependency graph
```

Each implements `WorkerModule` protocol independently. All share the same `CoreAPIClient` and `prometheus_url`.

**Heartbeat on empty cycles:** Heartbeats are runner-emitted (one per tick when any module ran), not module-emitted. The runner calls `process_cycle()` and marks the module as "ran" regardless of whether the module did any work (e.g., empty manifest list). No special "ran, no work" signal needed from modules.

### 3. Blast Radius (Pattern: Direct Prometheus)

**Execution:** Runs on a daily interval (configurable, default 86400s). Queries Prometheus for dependency metrics, builds graph, computes blast radius per service.

**Changes to `dependencies/discovery.py`:** None to the discovery/blast-radius logic.

**New module: `ObserveTopologyModule`**

```python
async def process_cycle(self) -> None:
    """Discover dependencies and compute blast radius for all services."""
    manifests = await self._fetch_manifests()
    if not manifests:
        return

    discovery = DependencyDiscovery()
    discovery.add_provider(PrometheusDepProvider(url=self.prometheus_url))
    graph = await discovery.build_graph([m["name"] for m in manifests])

    for m in manifests:
        service = m["name"]
        tier = m.get("tier", "standard")
        result = discovery.calculate_blast_radius(service, graph)
        assessment = create("dependency_graph", service, {
            "total_services_affected": result.total_services_affected,
            "critical_services_affected": result.critical_services_affected,
            "risk_level": result.risk_level,
            "direct_downstream_count": len(result.direct_downstream),
            "recommendation": result.recommendation,
        })
        await self.client.submit_assessment(to_dict(assessment))
```

**Use case for v1.5:** Topology observation for planning purposes. The "incident blast radius" use case (who's affected right now?) lives in respond's correlation output, not in observe's periodic computation. Daily cadence is appropriate.

**Scale note:** The per-service loop over `calculate_blast_radius()` builds a single graph then evaluates each service against it. Graph construction is O(services × providers); blast radius per service is O(edges) from the pre-built graph. Fine for v1.5 (demo has 8 services). If service count grows meaningfully (100+), consider a bulk API that builds the graph once and emits all assessments, or caching the graph across cycles.

### 4. Deploy Gate (Pattern A — read from core API, CLI-only)

**Execution:** On-demand CLI command. Not periodic, not part of `process_cycle()`.

**CLI command:** `nthlayer-workers gate --service X [--tier critical] [--commit-sha Y] [--core-url URL]`

`--tier` is optional: if omitted, resolved from the service's manifest via core API.

**Exit codes:**
- `0` = APPROVED or WARNING (deploy allowed; WARNING text printed to stderr)
- `1` = evaluation error (couldn't evaluate — core unreachable, no assessments found, malformed data; deploy scripts decide)
- `2` = BLOCKED (do not deploy)

Deploy scripts use `set -e` or `if nthlayer-workers gate ...; then deploy; fi`. Bash convention: non-zero = failure, so WARNING must return 0 to avoid blocking deploys on non-critical signals.

**Flow:**
1. Read manifests from core API (for tier if `--tier` not specified)
2. Read historical `slo_status` assessments from core API via `client.get_assessments(service=X, kind="slo_status")`
3. Run `check_deploy(service, tier, store)` — requires an `AssessmentStore` interface

**Store adapter for core API:** The gate evaluator takes `AssessmentStore`. For CLI-from-core, create a thin `CoreAPIAssessmentStore` that wraps `CoreAPIClient.get_assessments()` behind the `AssessmentStore` interface. This lets the evaluator work identically whether reading from local SQLite (CLI `nthlayer-observe check-deploy`) or from core API (CLI `nthlayer-workers gate`).

```python
class CoreAPIAssessmentStore(AssessmentStore):
    """Read-only assessment store backed by core API.

    Used by deploy gate CLI to read historical assessments from core.
    Write operations raise NotImplementedError.
    """

    def __init__(self, client: CoreAPIClient):
        self._client = client

    def put(self, assessment):
        raise NotImplementedError("CoreAPIAssessmentStore is read-only")

    def get(self, assessment_id):
        raise NotImplementedError("Use core API directly for single assessment lookup")

    def query(self, criteria):
        # Synchronous wrapper — safe for CLI use only (no running event loop).
        # Gate is CLI-only in v1.5; if gate moves to async (v2), use the
        # client directly instead of this adapter.
        result = asyncio.run(self._client.get_assessments(
            service=criteria.service,
            kind=criteria.kind,
            limit=criteria.limit if criteria.limit > 0 else 100,
        ))
        if not result.ok:
            return []
        return [from_dict(d) for d in result.data]
```

**Assessment output:** After gate evaluation, submit a `deploy_gate` assessment to core with `parent_ids` referencing the consulted `slo_status` assessments.

**No HTTP API for gate in v1.5.** If HTTP-API-accessible gate is needed in v2, design a core-to-worker dispatch pattern (verdict-request-based: core writes a `gate_request` verdict, workers pick it up on next cycle, workers submit `deploy_gate` assessment as result). This introduces cycle-latency and is not in scope for v1.5.

---

## Type Alignment (Deferred from P3-B.1)

| Old name | New name | Scope |
|---|---|---|
| `"gate"` | `"deploy_gate"` | Rename in `VALID_ASSESSMENT_TYPES`, `decision_records.py`, `cli.py`, all tests |
| `"dependency"` | `"dependency_graph"` | Same scope |
| `"verification"` | No change | CLI-only, not ported |

Same mechanical rename process as P3-B.1's A1. Update `VALID_ASSESSMENT_TYPES`, `decision_records.py` type map/severity/stream/summary branches, `cli.py` create() calls, all test assertions.

---

## CloudEvents Taxonomy Update

**Task:** Add three new assessment kinds to `nthlayer_common/cloudevents.py` `_ASSESSMENT_KINDS`:

```python
_ASSESSMENT_KINDS = frozenset({
    "slo_status",
    "judgment_slo_evaluation",
    "burn_rate",
    "drift_signal",
    "portfolio_status",     # NEW — P3-B.2
    "deploy_gate",          # NEW — P3-B.2
    "dependency_graph",     # NEW — P3-B.2
})
```

Document in NTHLAYER-TELEMETRY-ENVELOPE §3.4.

---

## Module Registration

```python
# In nthlayer-workers CLI serve command:
collect_module = ObserveCollectModule(client=client, prometheus_url=url)
drift_module = ObserveDriftModule(client=client, prometheus_url=url)
topology_module = ObserveTopologyModule(client=client, prometheus_url=url)

runner.register(collect_module, interval_seconds=60)
runner.register(drift_module, interval_seconds=1800)
runner.register(topology_module, interval_seconds=86400)

# Gate is CLI-only, not registered with runner
```

The existing `ObserveModule` from P3-B.1 becomes `ObserveCollectModule`. This is a rename — the module code stays the same, just the class name changes to distinguish it from the new modules.

---

## Test Strategy

### Type renames (gate→deploy_gate, dependency→dependency_graph)
Same mechanical process as P3-B.1's A1. String replacements in source + test files, run test gate after.

### Portfolio integration
- `test_build_portfolio_from_results` — pass SLOResults directly, verify PortfolioSummary
- `test_process_cycle_produces_portfolio_assessment` — mock collector, verify portfolio_status assessment submitted after SLO assessments
- `test_portfolio_parent_ids` — verify portfolio assessment references SLO assessment IDs

### Drift module
- `test_drift_module_protocol` — satisfies WorkerModule
- `test_drift_cycle_happy_path` — mock manifests + Prometheus, verify drift_signal assessments submitted
- `test_drift_cycle_analysis_failure_continues` — one service fails, others still processed
- `test_drift_targets_from_manifests` — verify SLO extraction from manifest dicts

### Topology module
- `test_topology_module_protocol` — satisfies WorkerModule
- `test_topology_cycle_happy_path` — mock manifests + Prometheus, verify dependency_graph assessments
- `test_topology_cycle_empty_graph` — no dependencies discovered, no assessments

### Deploy gate CLI
- `test_gate_cli_approved` — mock core returns healthy assessments, exit code 0
- `test_gate_cli_warning` — mock core returns warning-level assessments, exit code 0 (WARNING on stderr)
- `test_gate_cli_blocked` — mock core returns exhausted assessments, exit code 2
- `test_gate_cli_evaluation_error` — mock core unreachable, exit code 1
- `test_gate_cli_tier_from_manifest` — `--tier` omitted, resolved from manifest
- `test_core_api_assessment_store_query` — verify CoreAPIAssessmentStore wraps client correctly

---

## Acceptance Criteria

From the epic tree:
1. Drift detection produces assessments via core API
2. Portfolio scoring produces assessments via core API
3. Deploy gate evaluation produces assessments via core API
4. Existing observe test assertions pass (adapted to new import paths)

Added:
5. Three new assessment kinds added to CloudEvents taxonomy
6. Type renames (gate→deploy_gate, dependency→dependency_graph) complete across all files
7. ObserveModule renamed to ObserveCollectModule; two new modules (drift, topology) registered
8. Deploy gate works as CLI command reading from core API
9. Portfolio assessment includes parent_ids referencing source SLO assessments

## Work Sequence

| Step | What | Verify |
|------|------|--------|
| 1 | Rename `gate` → `deploy_gate`, `dependency` → `dependency_graph` | `pytest tests/observe/ -x` |
| 2 | Add three new kinds to CloudEvents `_ASSESSMENT_KINDS` | `pytest nthlayer-common/ -x` |
| 3 | Add `build_portfolio_from_results()` entry point | `pytest tests/observe/test_portfolio.py -x` |
| 4 | Wire portfolio into ObserveCollectModule.process_cycle() | New portfolio tests pass |
| 5 | Implement ObserveDriftModule | New drift tests pass |
| 6 | Implement ObserveTopologyModule | New topology tests pass |
| 7 | Implement `nthlayer-workers gate` CLI + CoreAPIAssessmentStore | New gate tests pass |
| 8 | Register all modules in workers CLI | Full suite passes |
