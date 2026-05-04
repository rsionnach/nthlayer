# P3-D.2: Correlate Module — Three-Type Output

**Date:** 2026-04-24
**Epic:** P3-D (Correlate Module)
**Dependencies:** P3-D.1
**Spec:** NTHLAYER-CORRELATE-v1 §9 (output types)

## Summary

Add two periodic assessment modules alongside P3-D.1's session window module. Each is a separate `WorkerModule` with its own cycle interval and data-access pattern.

| Module | Kind | Cycle | Data Source |
|--------|------|-------|-------------|
| `CorrelateSessionModule` | `correlation_snapshot` | 10s | Core API (verdicts + assessments) |
| `CorrelateTopologyModule` | `topology_drift` | 1h | Manifests (core) + traces (Tempo) |
| `CorrelateContractModule` | `contract_divergence` | 1h | Manifests (core) + Prometheus |

All three produce **assessments** (not verdicts) — per P3-D.1 taxonomy fix, all three kinds are in `ASSESSMENT_KINDS`.

This parallels observe's three-module split (collect/drift/topology) and keeps the module-responsibility model consistent across workers.

---

## Module 1: CorrelateSessionModule (existing — rename from CorrelateModule)

P3-D.1's `CorrelateModule` is renamed to `CorrelateSessionModule` for consistency with the three-module naming pattern.

No functional changes — session window logic, event polling, snapshot emission all stay as-is.

---

## Module 2: CorrelateTopologyModule

**Purpose:** Detect mismatches between declared dependencies (manifests) and observed dependencies (trace data from Tempo).

**Cycle interval:** 1 hour (configurable: `workers.correlate.topology_interval_seconds`, default 3600).

**Data-access pattern:**
1. Fetch manifests from core API (`GET /manifests`)
2. For each service, extract declared dependencies
3. Query Tempo for observed service-to-service edges (using existing `TempoTraceBackend`)
4. Run `detect_topology_divergence()` (existing function in `traces/topology.py`)
5. If divergence found, emit `topology_drift` assessment to core

**Three categories of drift:**
- `declared_not_observed` — dependency declared in manifest but no traffic seen in traces
- `observed_not_declared` — traffic observed between services not declared as dependencies
- `guarantee_mismatch` — dependency declared but observed latency/error rate violates expected guarantees (from `DependencySLO` on the dependency definition)

The first two categories are already computed by `detect_topology_divergence()`. `guarantee_mismatch` is new — requires comparing `dependency.slo.availability` / `dependency.slo.latency_p99` from the manifest against observed values from Tempo's `ServiceCallEdge` data.

**Assessment output:**

```python
assessment = {
    "id": f"tdr-{service}-{uuid4().hex[:8]}",
    "created_at": now.isoformat(),
    "kind": "topology_drift",
    "service": service,
    "data": {
        "declared_not_observed": [
            {"source": "payment-api", "target": "fraud-detect"},
        ],
        "observed_not_declared": [
            {"source": "payment-api", "target": "analytics-api"},
        ],
        "guarantee_mismatches": [
            {
                "source": "payment-api",
                "target": "fraud-detect",
                "metric": "availability",
                "promised": 0.999,       # ratio (0.0-1.0), matches ContractPromise convention
                "observed": 0.982,       # ratio, from Tempo ServiceCallEdge
                "tempo_window": "1h",    # Tempo query time range for this observation
            },
        ],
        "total_declared": 5,
        "total_observed": 6,
        "drift_detected": True,
    },
}
```

**Only emitted when drift is detected.** No assessment produced when declared == observed (no drift). This avoids flooding the assessments table with "everything is fine" records every hour.

### Trace Backend Unavailability

**Not configured:** Log once at startup (`topology_module_no_trace_backend`), become a permanent no-op. No assessments emitted. The module still registers with the runner and receives heartbeats — it just does no work. This is a valid deployment state (not all environments have Tempo).

**Unreachable:** TransientError handling per P1-A.7. Log warning, skip this cycle, retry next. Never produce a misleading "no drift detected" assessment when we have no data.

### Existing Code Reuse

`detect_topology_divergence()` in `traces/topology.py` already computes `declared_not_observed` and `observed_not_declared`. P3-D.2 adds `guarantee_mismatch` as a third comparison using `ServiceCallEdge.error_rate` and `ServiceCallEdge.latency_p99` from Tempo against `Dependency.slo` from manifests.

**Why guarantee_mismatch lives in CorrelateTopologyModule:** Guarantee mismatches are topology-shaped — they describe the relationship between two services (caller→callee), not a service's own SLOs. The data source is Tempo (observed call edges), not Prometheus (SLO indicators). Placing guarantee_mismatch in the topology module keeps data source affinity: topology module = Tempo data, contract module = Prometheus data. The alternative (placing it in CorrelateContractModule) would split the Tempo dependency across two modules.

`TempoTraceBackend` in `traces/tempo.py` already queries Tempo for service graphs and call edges. Reuse as-is.

---

## Module 3: CorrelateContractModule

**Purpose:** Detect mismatches between promised service guarantees (reliability contracts in manifests) and observed performance (Prometheus metrics).

**Cycle interval:** 1 hour (configurable: `workers.correlate.contract_interval_seconds`, default 3600).

**Data-access pattern:**
1. Fetch manifests from core API (`GET /manifests`)
2. For each service with contracts, extract promised values (`ContractPromise.availability`, `ContractPromise.latency_p99`)
3. Query Prometheus directly using the SLO's indicator expression to compute observed values over the contract window
4. Compare promised vs observed
5. If divergence found, emit `contract_divergence` assessment to core

**Direct Prometheus query** (design decision #3): Uses the same indicator expression as observe's SLO collection. This gives one consistent source for "observed availability." The module is analogous to observe but computing contract divergence rather than SLO status.

**Assessment output:**

```python
assessment = {
    "id": f"cdv-{service}-{uuid4().hex[:8]}",
    "created_at": now.isoformat(),
    "kind": "contract_divergence",
    "service": service,
    "data": {
        "contract_name": "payment-api-contract",
        # Each entry in divergences is a breach — if it's in the list,
        # the promise is violated. No redundant "breach: True" field.
        "divergences": [
            {
                "metric": "availability",
                "promised": 0.9999,      # ratio (0.0-1.0), from ContractPromise.availability
                "observed": 0.9985,      # ratio, from Prometheus query
                "window": "30d",         # measurement window (see Contract Window below)
            },
            {
                "metric": "latency_p99",
                "promised": "200ms",     # string, from ContractPromise.latency_p99
                "observed": "350ms",     # string, from Prometheus histogram_quantile
                "window": "30d",
            },
        ],
        "total_promises": 2,
        "divergence_count": 2,
    },
}
```

**Only emitted when divergence is detected.** No assessment when all promises are met.

### Insufficient Data Handling

If Prometheus returns no data for a service's indicator expression (empty result or 0.0 ambiguity per opensrm-e1gk), skip that service. Don't emit an assessment. Log at debug level.

If a service has contracts but no SLOs with matching indicator expressions (contract references metrics not defined in the service's SLO spec), skip. Log warning once per service.

### Prometheus Interaction

Uses `PrometheusProvider` from nthlayer-common (same as observe's collector). Queries over the contract's window (typically 30d). For latency metrics, queries `histogram_quantile(0.99, ...)` using the SLO's indicator expression.

**Contract window:** `ReliabilityContract` has no `window` field in the v1.5 manifest model. Default to **30 days** for contract divergence measurement. This is the standard reliability contract measurement window and matches the most common SLO window in the demo specs. If a future manifest version adds a `window` field to `ReliabilityContract`, use it instead.

**Unit conventions:**
- Availability: ratio (0.0-1.0) matching `ContractPromise.availability`. `SLODefinition.target` is a percentage (99.9) — convert `target / 100` when comparing against contract promises.
- Latency: string format matching `ContractPromise.latency_p99` (e.g., "200ms"). Parse to milliseconds for numeric comparison.

---

## Module Registration

```python
# In nthlayer-workers CLI serve command:
session = CorrelateSessionModule(client=client)
topology = CorrelateTopologyModule(client=client, trace_backend=trace_backend)
contract = CorrelateContractModule(client=client, prometheus_url=url)

runner.register(session, interval_seconds=args.correlate_interval)
runner.register(topology, interval_seconds=args.topology_drift_interval)
runner.register(contract, interval_seconds=args.contract_interval)
```

CLI flags:
- `--correlate-interval` (existing, default 10s)
- `--topology-drift-interval` (new, default 3600s)
- `--contract-interval` (new, default 3600s)
- `--tempo-endpoint` (new, optional — if not set, topology module is no-op)

---

## Alignment Work

### Rename CorrelateModule → CorrelateSessionModule

Same pattern as P3-B.2's `ObserveModule` → `ObserveCollectModule`. Update `worker.py`, `cli.py`, test imports.

### No new assessment kinds needed

`topology_drift` and `contract_divergence` were already added to `ASSESSMENT_KINDS` in P3-D.1 step 1.

---

## Test Strategy

### CorrelateTopologyModule
- `test_topology_module_protocol` — satisfies WorkerModule
- `test_topology_drift_detected` — mock manifests + Tempo, declared != observed → assessment emitted
- `test_topology_no_drift` — declared == observed → no assessment
- `test_topology_no_trace_backend_noop` — no Tempo configured → no crash, no assessment
- `test_topology_tempo_unreachable` — Tempo down → warning, no assessment, no crash
- `test_guarantee_mismatch_detected` — observed latency/error exceeds declared SLO → included in assessment

### CorrelateContractModule
- `test_contract_module_protocol` — satisfies WorkerModule
- `test_contract_divergence_detected` — mock manifests + Prometheus, observed < promised → assessment
- `test_contract_no_divergence` — all promises met → no assessment
- `test_contract_no_data_skips_service` — Prometheus returns empty → skip, no assessment
- `test_contract_no_contracts_noop` — manifests have no contracts → no work
- `test_contract_prometheus_query` — verify correct indicator expression used

### Existing tests
All existing correlate tests pass unchanged. Session module tests pass unchanged (rename only).

---

## Acceptance Criteria

From the epic tree:
1. Each closed window produces correlation_snapshot assessment (P3-D.1 — done)
2. Topology drift detected and produces topology_drift assessment
3. Contract divergence detected and produces contract_divergence assessment
4. All have distinct CloudEvents type attributes (already in ASSESSMENT_KINDS)

Added:
5. `CorrelateModule` renamed to `CorrelateSessionModule`
6. Topology module is no-op when Tempo not configured
7. Contract module queries Prometheus directly (not SLO assessment history)
8. No assessment emitted when no drift/divergence detected
9. Insufficient data → skip, not false-negative

---

## Work Sequence

| Step | What | Verify |
|------|------|--------|
| 1 | Rename `CorrelateModule` → `CorrelateSessionModule` | Existing tests pass |
| 2 | Implement `CorrelateTopologyModule` with `detect_topology_divergence()` + guarantee_mismatch | New topology tests pass |
| 3 | Implement `CorrelateContractModule` with Prometheus queries | New contract tests pass |
| 4 | Register all three modules in workers CLI | Full suite passes |
