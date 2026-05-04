# NthLayer: Trace Abstraction Layer

**Status:** Proposal  
**Author:** Rob  
**Date:** 2026-04-02 (revised)  
**Depends on:** Existing correlate signal gathering pipeline, verdict schema, dependency graph builder  
**Unlocks:** Tempo trace adapter (first), Jaeger adapter (second)

---

## Context

NthLayer correlate currently gathers two signal types during its event collection phase: Prometheus alerts and metric breaches (via `prometheus.py`), and evaluation verdicts from the verdict store. The correlation engine groups these by temporal proximity and topology adjacency, then the reasoning layer interprets the groups.

Traces are the missing signal. The declared dependency graph says A calls B. Traces confirm it happened, show the actual latency, and reveal where in the call chain errors originated. For the dual-incident disambiguation scenario (fraud-detect model regression AND config-service OOM overlapping in time), traces provide direct evidence: "requests through fraud-detect show latency in model.predict(), requests through config-service show errors in ConnectionPool.acquire()." That's causal, not circumstantial.

The existing adapter pattern is well established: query the source for events affecting services in the blast radius during the incident time window, convert results to correlation events, insert into the event store. The correlation engine and reasoning layer don't change — they just see richer groups with trace evidence alongside alert and metric evidence.

This spec defines the trace abstraction and the first concrete adapter (Grafana Tempo). Tempo is the natural first target: it sits in the same Grafana ecosystem as Prometheus and Grafana (the stack NthLayer already targets), it's the trace backend most likely deployed by NthLayer's users, and it has server-side aggregation via TraceQL metrics that keeps the adapter thin. The abstraction must be thin enough that adding Jaeger is a day of work, not a week.

---

## Non-Goals

- NthLayer does not collect or store traces. It queries trace backends during the correlation window.
- NthLayer does not render trace visualisations. It extracts structured evidence (latency breakdown, error spans, service-to-service call patterns) for the reasoning layer.
- This spec does not cover trace-based topology discovery (inferring the dependency graph from traces rather than declared specs). That's a valuable future capability but it's a separate concern from using traces as correlation evidence.
- Commercial backend adapters (NewRelic, Datadog) are explicitly out of scope. NthLayer doubles down on open-source stacks where it fills genuine gaps rather than competing with incumbent platform features.

---

## Part 1: Trace Abstraction Interface

### 1.1 The Core Protocol

The trace adapter follows the same Protocol pattern as the profile backend adapter from the Profiles spec. Each backend implements this interface. NthLayer doesn't care whether the traces came from Tempo or Jaeger — it cares about structured evidence.

```python
# nthlayer-correlate/src/nthlayer_correlate/traces/protocol.py

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol


@dataclass
class TraceSpanSummary:
    """
    A single span from a trace, summarised for correlation evidence.
    Not the full span — just what the reasoning layer needs.
    """
    trace_id: str
    span_id: str
    service: str                    # service.name resource attribute
    operation: str                  # span name / operation name
    duration_ms: float
    status: str                     # "ok" | "error" | "unset"
    error_message: str | None       # if status == "error"
    parent_service: str | None      # calling service (from parent span)
    attributes: dict[str, str]      # selected span attributes


@dataclass
class ServiceTraceProfile:
    """
    Trace-derived evidence for a single service during the incident window.
    Aggregated from potentially thousands of individual spans.
    """
    service: str
    time_window_start: datetime
    time_window_end: datetime
    
    # Request flow: who calls this service, who does it call?
    # This is the observed topology, not declared
    callers: list["ServiceCallEdge"]    # upstream services that called this service
    callees: list["ServiceCallEdge"]    # downstream services this service called
    
    # Latency summary
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    baseline_p50_ms: float | None       # from before the incident window, if available
    latency_change_pct: float | None    # % change vs baseline
    
    # Error summary
    error_rate: float                   # 0.0 - 1.0
    error_count: int
    total_request_count: int
    top_errors: list["ErrorSummary"]    # top N distinct error messages
    
    # Slow operations: which operations within this service are slow?
    slow_operations: list["OperationLatency"]
    
    # Sample traces: a small number of representative traces for deep context
    sample_error_traces: list[TraceSpanSummary]     # up to 3 error traces
    sample_slow_traces: list[TraceSpanSummary]       # up to 3 p99+ traces


@dataclass
class ServiceCallEdge:
    """
    An observed call between two services, with latency and error stats.
    """
    source_service: str
    target_service: str
    request_count: int
    error_count: int
    p50_latency_ms: float
    p99_latency_ms: float


@dataclass
class ErrorSummary:
    """Top errors for a service during the incident window."""
    error_message: str
    count: int
    first_seen: datetime
    last_seen: datetime
    sample_trace_id: str | None


@dataclass
class OperationLatency:
    """
    Latency for a specific operation (span name) within a service.
    Used to identify which endpoint or function is slow.
    """
    operation: str                  # e.g. "POST /api/v1/predict", "grpc.FraudService/Evaluate"
    p50_ms: float
    p99_ms: float
    request_count: int
    error_rate: float
    baseline_p50_ms: float | None
    change_pct: float | None        # vs baseline


@dataclass
class TopologyDivergence:
    """
    Where observed trace topology differs from declared dependency graph.
    """
    declared_not_observed: list[tuple[str, str]]    # (A, B) declared A→B but no traces
    observed_not_declared: list[tuple[str, str]]    # (A, B) traces show A→B but not in spec
    

@dataclass
class TraceEvidence:
    """
    Complete trace evidence for all services in the blast radius.
    This is what the correlate adapter returns to the correlation engine.
    """
    services: list[ServiceTraceProfile]
    topology_divergence: TopologyDivergence | None
    query_time_ms: float            # how long the trace queries took
    backend: str                    # "tempo" | "jaeger"


class TraceBackend(Protocol):
    """
    Protocol that all trace backend adapters implement.
    
    The contract: given a set of services and a time window,
    return structured trace evidence. The backend handles all
    query specifics (TraceQL, Jaeger gRPC, etc.).
    """
    
    async def get_trace_evidence(
        self,
        services: list[str],
        start: datetime,
        end: datetime,
        baseline_window: timedelta = timedelta(hours=1),
    ) -> TraceEvidence:
        """
        Gather trace evidence for the given services during [start, end].
        
        baseline_window: how far before `start` to look for baseline
        latency/error comparisons. Default 1h before incident.
        """
        ...
    
    async def get_service_dependencies(
        self,
        service: str,
        start: datetime,
        end: datetime,
    ) -> list[ServiceCallEdge]:
        """
        Get observed dependencies for a single service from trace data.
        Used for topology validation against declared specs.
        """
        ...
    
    async def health_check(self) -> bool:
        """Can we reach the trace backend?"""
        ...
```

### 1.2 Why This Shape

The abstraction returns **aggregated evidence**, not raw spans. This is deliberate:

- The reasoning layer needs "fraud-detect p99 latency is 340ms, up 180% from baseline, with the slowest operation being POST /predict" — not 50,000 individual span records.
- Different backends have vastly different query capabilities. Tempo can do server-side aggregation via TraceQL metrics. Jaeger has limited aggregation and requires client-side processing. The adapter hides these differences.
- Token cost matters. Raw spans would blow the context window. Structured summaries are compact and directly useful for the reasoning prompt.

The `TopologyDivergence` field is a bonus signal unique to traces: if the declared dependency graph says A→B but traces show A→C→B, that's relevant context for the reasoning layer. It may indicate an undeclared proxy, a misconfigured service mesh, or a stale spec.

---

## Part 2: Integration into Correlate

### 2.1 Signal Gathering Phase

The correlate command's signal gathering phase (`_gather()` in cli.py) currently queries Prometheus and the verdict store. Trace evidence is a third source, queried in parallel.

```python
# Conceptual change to cli.py's _gather() function
# Audit actual code structure before implementing

async def _gather(
    prometheus_url: str,
    specs_dir: Path,
    verdict_store: VerdictStore,
    trace_backend: TraceBackend | None,  # NEW — None if no trace backend configured
    trigger_verdict: Verdict,
    time_window: TimeWindow,
) -> GatheredSignals:
    
    # Existing: gather alerts and metrics from Prometheus
    alerts_task = asyncio.create_task(
        fetch_prometheus_alerts(prometheus_url, time_window)
    )
    
    # Existing: gather related verdicts from the verdict store
    verdicts_task = asyncio.create_task(
        fetch_related_verdicts(verdict_store, trigger_verdict)
    )
    
    # NEW: gather trace evidence if backend is configured
    trace_task = None
    if trace_backend:
        blast_services = compute_blast_radius(trigger_verdict, specs_dir)
        trace_task = asyncio.create_task(
            trace_backend.get_trace_evidence(
                services=blast_services,
                start=time_window.start,
                end=time_window.end,
            )
        )
    
    alerts = await alerts_task
    verdicts = await verdicts_task
    trace_evidence = await trace_task if trace_task else None
    
    return GatheredSignals(
        alerts=alerts,
        verdicts=verdicts,
        trace_evidence=trace_evidence,  # NEW
    )
```

### 2.2 Correlation Engine — No Changes Required

The correlation engine (`CorrelationEngine.correlate()`) groups signals by temporal proximity and topology adjacency. It operates on `TemporalGroup` and `CorrelationGroup` dataclasses. Trace evidence does **not** change the grouping logic — it enriches groups that already exist.

The integration point is between `engine.correlate()` producing groups (around line 463 in cli.py per the audit) and the reasoning layer / root cause construction (around line 480). This is the same integration point identified for the reasoning layer itself.

### 2.3 Reasoning Layer Enrichment

The reasoning layer's prompt already includes alert signals, change candidates, and dependency graph context. Trace evidence adds a new section to the prompt.

```python
# Addition to reasoning.py _build_user_prompt()

def _build_trace_evidence_section(trace_evidence: TraceEvidence | None) -> str:
    """
    Format trace evidence for the reasoning prompt.
    Only included if trace evidence was gathered.
    """
    if not trace_evidence or not trace_evidence.services:
        return ""
    
    sections = ["## Trace Evidence\n"]
    
    for svc in trace_evidence.services:
        lines = [f"### {svc.service}"]
        
        # Latency summary
        if svc.latency_change_pct is not None and abs(svc.latency_change_pct) > 10:
            lines.append(
                f"Latency: p50={svc.p50_latency_ms:.0f}ms, "
                f"p99={svc.p99_latency_ms:.0f}ms "
                f"({svc.latency_change_pct:+.0f}% vs baseline)"
            )
        else:
            lines.append(
                f"Latency: p50={svc.p50_latency_ms:.0f}ms, "
                f"p99={svc.p99_latency_ms:.0f}ms (within baseline)"
            )
        
        # Error summary
        if svc.error_rate > 0.01:
            lines.append(
                f"Errors: {svc.error_rate:.1%} error rate "
                f"({svc.error_count}/{svc.total_request_count} requests)"
            )
            for err in svc.top_errors[:3]:
                lines.append(f"  - \"{err.error_message}\" (x{err.count})")
        
        # Slow operations
        for op in svc.slow_operations[:3]:
            if op.change_pct is not None and op.change_pct > 20:
                lines.append(
                    f"Slow operation: {op.operation} "
                    f"p99={op.p99_ms:.0f}ms ({op.change_pct:+.0f}% vs baseline)"
                )
        
        # Observed call edges (who calls this, who does it call)
        if svc.callers:
            caller_str = ", ".join(
                f"{c.source_service} ({c.request_count} reqs, "
                f"p99={c.p99_latency_ms:.0f}ms)"
                for c in svc.callers[:3]
            )
            lines.append(f"Called by: {caller_str}")
        
        if svc.callees:
            callee_str = ", ".join(
                f"{c.target_service} ({c.request_count} reqs, "
                f"p99={c.p99_latency_ms:.0f}ms, "
                f"err={c.error_count}/{c.request_count})"
                for c in svc.callees[:3]
            )
            lines.append(f"Calls: {callee_str}")
        
        sections.append("\n".join(lines))
    
    # Topology divergence — if observed call graph differs from declared
    if trace_evidence.topology_divergence:
        div = trace_evidence.topology_divergence
        if div.observed_not_declared:
            sections.append(
                "### Undeclared Dependencies (observed in traces, not in specs)\n"
                + "\n".join(
                    f"  - {a} → {b}" for a, b in div.observed_not_declared
                )
            )
        if div.declared_not_observed:
            sections.append(
                "### Declared but Unobserved Dependencies (in specs, no traces)\n"
                + "\n".join(
                    f"  - {a} → {b}" for a, b in div.declared_not_observed
                )
            )
    
    return "\n\n".join(sections)
```

### 2.4 What This Gives the Reasoning Layer

With trace evidence, the reasoning prompt for the dual-incident scenario changes from:

**Before (alerts + change events only):**
```
Correlation Group 1: fraud-detect (P1)
  Signals: reversal_rate breach, latency_p99 breach
  Change candidates: model deploy v2.2→v2.3 (240s before breach)

Correlation Group 2: config-service (P2)
  Signals: availability breach, error_rate breach
  Change candidates: none
```

**After (with trace evidence):**
```
Correlation Group 1: fraud-detect (P1)
  Signals: reversal_rate breach, latency_p99 breach
  Change candidates: model deploy v2.2→v2.3 (240s before breach)
  Trace evidence:
    fraud-detect: p99=340ms (+180% vs baseline)
    Slow operation: POST /api/v1/predict p99=312ms (+195% vs baseline)
    Called by: payment-api (1,204 reqs, p99=380ms)
    Calls: model-store (1,204 reqs, p99=45ms, err=0/1204)

Correlation Group 2: config-service (P2)
  Signals: availability breach, error_rate breach
  Change candidates: none
  Trace evidence:
    config-service: p99=2,100ms (+850% vs baseline), 34.2% error rate
    Errors: "ConnectionPool exhausted: no available connections" (x4,821)
    Slow operation: GET /api/v1/config p99=2,050ms (+900% vs baseline)
    Called by: notification-service (2,106 reqs, p99=2,200ms)
    Calls: postgres-primary (8,412 reqs, p99=1,800ms, err=3241/8412)
```

The reasoning layer now has evidence to conclude:
- **Incident A** is CPU-bound in the model predict path — consistent with a model change, not a downstream dependency issue.
- **Incident B** is a connection pool exhaustion causing cascading timeouts to postgres — independent of the model deploy, likely a resource leak.

Without traces, both incidents look like "multiple services degraded at the same time." With traces, they're clearly independent failure modes with different root causes.

### 2.5 Correlation Verdict Extension

The `correlation` verdict's evidence array gains trace-derived entries:

```yaml
correlation_verdict:
  root_causes:
    - service: fraud-detect
      type: model_deployment
      confidence: 0.93       # higher than without traces — more evidence
      evidence:
        - type: alert
          detail: "reversal_rate breach"
        - type: change_event
          detail: "model deploy v2.2→v2.3, 240s before breach"
        - type: trace
          detail: "POST /predict p99=312ms (+195%), no downstream errors"
          
    - service: config-service
      type: resource_exhaustion
      confidence: 0.87
      evidence:
        - type: alert
          detail: "availability breach, error_rate breach"
        - type: trace
          detail: "ConnectionPool exhausted (x4821), postgres p99=1800ms with 38.5% errors"
```

---

## Part 3: Tempo Trace Adapter

### 3.1 Why Tempo First

Tempo sits in the Grafana ecosystem alongside Prometheus and Grafana — the exact stack NthLayer already targets. Teams running Prometheus + Grafana are the most likely to also run Tempo for traces. It's the natural complement.

Tempo also has two server-side aggregation paths that keep the adapter thin:

- **TraceQL metrics API** (`/api/metrics/query_range`): computes `rate()`, `quantile_over_time()`, and `count_over_time()` on trace data on-the-fly, returning Prometheus-like time series. No pre-computation required — queries run against raw trace storage. This is the primary path for latency percentiles, error rates, and request counts.
- **metrics-generator service graphs**: pre-computes service-to-service call edges (caller/callee relationships with RED metrics) and writes them to Prometheus. NthLayer can query these via the existing Prometheus adapter if available, or fall back to TraceQL.

This means the Tempo adapter is mostly TraceQL query construction, with the metrics-generator service graph as an optimisation path for call edges.

### 3.2 Configuration

```bash
# Environment variables
export NTHLAYER_TRACE_BACKEND="tempo"
export TEMPO_ENDPOINT="http://tempo:3200"
export TEMPO_ORG_ID=""              # optional, for multi-tenant Tempo

# Or in nthlayer config
# ~/.nthlayer/config.yaml
traces:
  backend: tempo
  tempo:
    endpoint: "http://tempo:3200"   # Tempo query-frontend or monolithic endpoint
    org_id: ""                      # X-Scope-OrgID header for multi-tenant
    timeout_seconds: 30
    use_service_graphs: true        # query Prometheus for service graph metrics if available
    service_graph_source: prometheus # where metrics-generator writes service graphs
```

CLI flag for correlate:

```bash
nthlayer correlate \
  --trigger-verdict <id> \
  --prometheus-url http://localhost:9090 \
  --trace-backend tempo \
  --tempo-endpoint http://tempo:3200 \
  --specs-dir ./specs/ \
  --verdict-store ./verdicts.db
```

### 3.3 Tempo Adapter Implementation

```python
# nthlayer-correlate/src/nthlayer_correlate/traces/tempo.py

import os
import time
from datetime import datetime, timedelta
from dataclasses import dataclass

import httpx

from .protocol import (
    TraceBackend,
    TraceEvidence,
    ServiceTraceProfile,
    ServiceCallEdge,
    ErrorSummary,
    OperationLatency,
    TopologyDivergence,
    TraceSpanSummary,
)


class TempoTraceBackend:
    """
    TraceBackend implementation for Grafana Tempo.
    
    Uses two Tempo APIs:
    - TraceQL metrics API for server-side aggregation (latency, error rate, request count)
    - TraceQL search API for sample traces and error details
    
    Optionally uses metrics-generator service graph metrics via Prometheus
    for call edge data (faster than computing from raw traces).
    """
    
    def __init__(
        self,
        endpoint: str | None = None,
        org_id: str | None = None,
        timeout: int = 30,
        use_service_graphs: bool = True,
        prometheus_url: str | None = None,
    ):
        self.endpoint = (
            endpoint 
            or os.environ.get("TEMPO_ENDPOINT", "http://localhost:3200")
        )
        self.org_id = org_id or os.environ.get("TEMPO_ORG_ID", "")
        self.timeout = timeout
        self.use_service_graphs = use_service_graphs
        self.prometheus_url = prometheus_url
        
        headers = {"Content-Type": "application/json"}
        if self.org_id:
            headers["X-Scope-OrgID"] = self.org_id
        
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers=headers,
        )

    async def get_trace_evidence(
        self,
        services: list[str],
        start: datetime,
        end: datetime,
        baseline_window: timedelta = timedelta(hours=1),
    ) -> TraceEvidence:
        query_start = time.monotonic()
        
        baseline_start = start - baseline_window
        service_profiles: list[ServiceTraceProfile] = []
        
        # --- Phase 1: Per-service latency + error aggregation ---
        # Uses TraceQL metrics API for server-side computation
        incident_stats = await self._query_service_stats(services, start, end)
        baseline_stats = await self._query_service_stats(
            services, baseline_start, start
        )
        
        # --- Phase 2: Service-to-service call edges ---
        if self.use_service_graphs and self.prometheus_url:
            # Fast path: query pre-computed service graph metrics from Prometheus
            edges = await self._query_service_graphs_from_prometheus(
                services, start, end
            )
        else:
            # Slow path: derive edges from trace search
            edges = await self._query_edges_from_traces(services, start, end)
        
        # --- Phase 3: Per-operation breakdown ---
        operations = await self._query_operation_breakdown(
            services, start, end, baseline_start
        )
        
        # --- Phase 4: Top errors ---
        errors = await self._query_top_errors(services, start, end)
        
        # --- Phase 5: Sample traces ---
        samples = await self._query_sample_traces(services, start, end)
        
        # Assemble per-service profiles
        for service in services:
            incident = incident_stats.get(service)
            baseline = baseline_stats.get(service)
            
            if not incident:
                continue  # no trace data for this service
            
            latency_change = None
            if baseline and baseline.p50_ms > 0:
                latency_change = (
                    (incident.p50_ms - baseline.p50_ms) / baseline.p50_ms * 100
                )
            
            profile = ServiceTraceProfile(
                service=service,
                time_window_start=start,
                time_window_end=end,
                callers=[e for e in edges if e.target_service == service],
                callees=[e for e in edges if e.source_service == service],
                p50_latency_ms=incident.p50_ms,
                p95_latency_ms=incident.p95_ms,
                p99_latency_ms=incident.p99_ms,
                baseline_p50_ms=baseline.p50_ms if baseline else None,
                latency_change_pct=latency_change,
                error_rate=incident.error_rate,
                error_count=incident.error_count,
                total_request_count=incident.total_count,
                top_errors=errors.get(service, []),
                slow_operations=operations.get(service, []),
                sample_error_traces=samples.get(service, {}).get("errors", []),
                sample_slow_traces=samples.get(service, {}).get("slow", []),
            )
            service_profiles.append(profile)
        
        query_time = (time.monotonic() - query_start) * 1000
        
        return TraceEvidence(
            services=service_profiles,
            topology_divergence=None,  # computed by caller with specs
            query_time_ms=query_time,
            backend="tempo",
        )

    # ---------------------------------------------------------------
    # TraceQL Metrics API queries
    # ---------------------------------------------------------------
    
    async def _query_service_stats(
        self, services: list[str], start: datetime, end: datetime
    ) -> dict[str, "_ServiceStats"]:
        """
        Per-service latency percentiles, error count, and request count.
        
        Uses TraceQL metrics API: five parallel queries
        (p50, p95, p99, total count, error count) faceted by service.name.
        Results are Prometheus-like time series.
        """
        results: dict[str, _ServiceStats] = {}
        
        service_filter = self._traceql_service_filter(services)
        duration_secs = max(int((end - start).total_seconds()), 60)
        # Step size: aim for ~20 data points across the window
        step = f"{max(duration_secs // 20, 15)}s"
        
        # Latency percentiles
        p50_query = (
            f'{{ {service_filter} && span.kind = server }} '
            f'| quantile_over_time(duration, .50) by (resource.service.name)'
        )
        p95_query = (
            f'{{ {service_filter} && span.kind = server }} '
            f'| quantile_over_time(duration, .95) by (resource.service.name)'
        )
        p99_query = (
            f'{{ {service_filter} && span.kind = server }} '
            f'| quantile_over_time(duration, .99) by (resource.service.name)'
        )
        
        # Request and error counts
        count_query = (
            f'{{ {service_filter} && span.kind = server }} '
            f'| count_over_time() by (resource.service.name)'
        )
        error_query = (
            f'{{ {service_filter} && span.kind = server && status = error }} '
            f'| count_over_time() by (resource.service.name)'
        )
        
        # Run all five in parallel
        import asyncio
        p50_data, p95_data, p99_data, count_data, error_data = await asyncio.gather(
            self._traceql_metrics_query(p50_query, start, end, step),
            self._traceql_metrics_query(p95_query, start, end, step),
            self._traceql_metrics_query(p99_query, start, end, step),
            self._traceql_metrics_query(count_query, start, end, step),
            self._traceql_metrics_query(error_query, start, end, step),
        )
        
        # Parse results — each returns {service_name: average_value_across_window}
        p50_by_svc = self._extract_metric_by_service(p50_data)
        p95_by_svc = self._extract_metric_by_service(p95_data)
        p99_by_svc = self._extract_metric_by_service(p99_data)
        count_by_svc = self._extract_metric_by_service(count_data)
        error_by_svc = self._extract_metric_by_service(error_data)
        
        for service in services:
            total = count_by_svc.get(service, 0)
            errors = error_by_svc.get(service, 0)
            if total == 0:
                continue
            
            results[service] = _ServiceStats(
                # Tempo returns duration in nanoseconds; convert to ms
                p50_ms=p50_by_svc.get(service, 0) / 1_000_000,
                p95_ms=p95_by_svc.get(service, 0) / 1_000_000,
                p99_ms=p99_by_svc.get(service, 0) / 1_000_000,
                total_count=int(total),
                error_count=int(errors),
                error_rate=errors / total if total > 0 else 0.0,
            )
        
        return results

    async def _query_operation_breakdown(
        self,
        services: list[str],
        start: datetime,
        end: datetime,
        baseline_start: datetime,
    ) -> dict[str, list[OperationLatency]]:
        """
        Per-operation latency breakdown within each service.
        Uses TraceQL metrics faceted by span name.
        """
        service_filter = self._traceql_service_filter(services)
        duration_secs = max(int((end - start).total_seconds()), 60)
        step = f"{max(duration_secs // 20, 15)}s"
        
        # Incident window: p50, p99, count, errors by service + operation
        p50_query = (
            f'{{ {service_filter} && span.kind = server }} '
            f'| quantile_over_time(duration, .50) by (resource.service.name, name)'
        )
        p99_query = (
            f'{{ {service_filter} && span.kind = server }} '
            f'| quantile_over_time(duration, .99) by (resource.service.name, name)'
        )
        count_query = (
            f'{{ {service_filter} && span.kind = server }} '
            f'| count_over_time() by (resource.service.name, name)'
        )
        error_query = (
            f'{{ {service_filter} && span.kind = server && status = error }} '
            f'| count_over_time() by (resource.service.name, name)'
        )
        
        # Baseline window: p50 only (for comparison)
        baseline_p50_query = p50_query  # same query, different time range
        
        import asyncio
        (
            inc_p50, inc_p99, inc_count, inc_error, base_p50
        ) = await asyncio.gather(
            self._traceql_metrics_query(p50_query, start, end, step),
            self._traceql_metrics_query(p99_query, start, end, step),
            self._traceql_metrics_query(count_query, start, end, step),
            self._traceql_metrics_query(error_query, start, end, step),
            self._traceql_metrics_query(
                baseline_p50_query, baseline_start, start, step
            ),
        )
        
        # Parse into {(service, operation): value} dicts
        inc_p50_map = self._extract_metric_by_service_and_op(inc_p50)
        inc_p99_map = self._extract_metric_by_service_and_op(inc_p99)
        inc_count_map = self._extract_metric_by_service_and_op(inc_count)
        inc_error_map = self._extract_metric_by_service_and_op(inc_error)
        base_p50_map = self._extract_metric_by_service_and_op(base_p50)
        
        result: dict[str, list[OperationLatency]] = {}
        
        for (service, operation), p50_ns in inc_p50_map.items():
            if service not in result:
                result[service] = []
            
            total = inc_count_map.get((service, operation), 0)
            errors = inc_error_map.get((service, operation), 0)
            p50_ms = p50_ns / 1_000_000
            p99_ms = inc_p99_map.get((service, operation), 0) / 1_000_000
            baseline_p50_ns = base_p50_map.get((service, operation))
            baseline_p50_ms = baseline_p50_ns / 1_000_000 if baseline_p50_ns else None
            
            change_pct = None
            if baseline_p50_ms and baseline_p50_ms > 0:
                change_pct = (p50_ms - baseline_p50_ms) / baseline_p50_ms * 100
            
            result[service].append(OperationLatency(
                operation=operation,
                p50_ms=p50_ms,
                p99_ms=p99_ms,
                request_count=int(total),
                error_rate=errors / total if total > 0 else 0.0,
                baseline_p50_ms=baseline_p50_ms,
                change_pct=change_pct,
            ))
        
        # Sort by p99 descending within each service (slowest first)
        for service in result:
            result[service].sort(key=lambda o: o.p99_ms, reverse=True)
            result[service] = result[service][:10]  # top 10 operations
        
        return result

    # ---------------------------------------------------------------
    # Service graph edges (two paths)
    # ---------------------------------------------------------------

    async def _query_service_graphs_from_prometheus(
        self, services: list[str], start: datetime, end: datetime
    ) -> list[ServiceCallEdge]:
        """
        Fast path: query pre-computed service graph metrics from Prometheus.
        
        The metrics-generator writes:
        - traces_service_graph_request_total{client="svc-a", server="svc-b"}
        - traces_service_graph_request_failed_total{client="svc-a", server="svc-b"}
        - traces_service_graph_request_server_seconds_bucket{...}
        
        These are standard Prometheus metrics that NthLayer can query
        via the existing Prometheus adapter.
        """
        if not self.prometheus_url:
            return []
        
        service_regex = "|".join(services)
        window = f"{int((end - start).total_seconds())}s"
        
        # Request count per edge
        count_query = (
            f'sum by (client, server) ('
            f'increase(traces_service_graph_request_total'
            f'{{client=~"{service_regex}|", server=~"|{service_regex}"}}'
            f'[{window}]))'
        )
        
        # Error count per edge
        error_query = (
            f'sum by (client, server) ('
            f'increase(traces_service_graph_request_failed_total'
            f'{{client=~"{service_regex}|", server=~"|{service_regex}"}}'
            f'[{window}]))'
        )
        
        # Latency per edge
        p99_query = (
            f'histogram_quantile(0.99, sum by (client, server, le) ('
            f'increase(traces_service_graph_request_server_seconds_bucket'
            f'{{client=~"{service_regex}|", server=~"|{service_regex}"}}'
            f'[{window}])))'
        )
        p50_query = p99_query.replace("0.99", "0.50")
        
        import asyncio
        count_data, error_data, p99_data, p50_data = await asyncio.gather(
            self._prometheus_query(count_query, end),
            self._prometheus_query(error_query, end),
            self._prometheus_query(p99_query, end),
            self._prometheus_query(p50_query, end),
        )
        
        return self._parse_service_graph_results(
            count_data, error_data, p99_data, p50_data
        )

    async def _query_edges_from_traces(
        self, services: list[str], start: datetime, end: datetime
    ) -> list[ServiceCallEdge]:
        """
        Slow path: derive service-to-service edges from trace search.
        
        Uses TraceQL search to find client spans that call into our services,
        then aggregates counts client-side.
        
        This is less efficient than service graph metrics but works
        without the metrics-generator being enabled.
        """
        service_filter = self._traceql_service_filter(services)
        search_query = f'{{ {service_filter} && span.kind = client }}'
        
        results = await self._traceql_search(search_query, start, end, limit=1000)
        
        # Client-side aggregation of edges
        edge_counts: dict[tuple[str, str], _EdgeAccumulator] = {}
        
        for span in results:
            source = span.get("rootServiceName", "")
            target = span.get("resource.service.name", "")
            if not source or not target or source == target:
                continue
            
            key = (source, target)
            if key not in edge_counts:
                edge_counts[key] = _EdgeAccumulator()
            
            acc = edge_counts[key]
            acc.count += 1
            duration_ms = span.get("durationMs", 0)
            acc.durations.append(duration_ms)
            if span.get("status") == "error":
                acc.errors += 1
        
        edges = []
        for (source, target), acc in edge_counts.items():
            sorted_d = sorted(acc.durations)
            edges.append(ServiceCallEdge(
                source_service=source,
                target_service=target,
                request_count=acc.count,
                error_count=acc.errors,
                p50_latency_ms=sorted_d[len(sorted_d) // 2] if sorted_d else 0,
                p99_latency_ms=sorted_d[int(len(sorted_d) * 0.99)] if sorted_d else 0,
            ))
        
        return edges

    # ---------------------------------------------------------------
    # Error and sample trace queries
    # ---------------------------------------------------------------

    async def _query_top_errors(
        self, services: list[str], start: datetime, end: datetime
    ) -> dict[str, list[ErrorSummary]]:
        """
        Top error messages per service.
        Uses TraceQL search filtered to error spans, grouped client-side.
        """
        result: dict[str, list[ErrorSummary]] = {}
        
        for service in services:
            search_query = (
                f'{{ resource.service.name = "{service}" '
                f'&& status = error && span.kind = server }}'
            )
            spans = await self._traceql_search(
                search_query, start, end, limit=100
            )
            
            if not spans:
                continue
            
            # Group by error message
            error_groups: dict[str, list[dict]] = {}
            for span in spans:
                msg = (
                    span.get("span.status_message", "")
                    or span.get("status.message", "")
                    or "unknown error"
                )
                error_groups.setdefault(msg, []).append(span)
            
            # Sort by count, take top 5
            sorted_errors = sorted(
                error_groups.items(), key=lambda x: len(x[1]), reverse=True
            )[:5]
            
            result[service] = [
                ErrorSummary(
                    error_message=msg,
                    count=len(group_spans),
                    first_seen=self._parse_tempo_timestamp(
                        min(s.get("startTimeUnixNano", 0) for s in group_spans)
                    ),
                    last_seen=self._parse_tempo_timestamp(
                        max(s.get("startTimeUnixNano", 0) for s in group_spans)
                    ),
                    sample_trace_id=group_spans[0].get("traceID"),
                )
                for msg, group_spans in sorted_errors
            ]
        
        return result

    async def _query_sample_traces(
        self, services: list[str], start: datetime, end: datetime
    ) -> dict[str, dict[str, list[TraceSpanSummary]]]:
        """
        Sample error and slow traces per service. Up to 3 of each.
        """
        result: dict[str, dict[str, list[TraceSpanSummary]]] = {}
        
        for service in services:
            # Error traces
            error_query = (
                f'{{ resource.service.name = "{service}" '
                f'&& status = error && span.kind = server }}'
            )
            error_spans = await self._traceql_search(
                error_query, start, end, limit=3
            )
            
            # Slow traces — fetch more and sort client-side
            # (TraceQL search doesn't support ORDER BY duration)
            slow_query = (
                f'{{ resource.service.name = "{service}" '
                f'&& span.kind = server }}'
            )
            slow_spans_raw = await self._traceql_search(
                slow_query, start, end, limit=50
            )
            slow_spans_raw.sort(
                key=lambda s: s.get("durationNanos", 0), reverse=True
            )
            slow_spans = slow_spans_raw[:3]
            
            result[service] = {
                "errors": [self._span_to_summary(s) for s in error_spans],
                "slow": [self._span_to_summary(s) for s in slow_spans],
            }
        
        return result

    # ---------------------------------------------------------------
    # Tempo HTTP API transport
    # ---------------------------------------------------------------

    async def _traceql_metrics_query(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str,
    ) -> dict:
        """
        Execute a TraceQL metrics query via /api/metrics/query_range.
        Returns Prometheus-like time series response.
        """
        params = {
            "q": query,
            "start": str(int(start.timestamp())),
            "end": str(int(end.timestamp())),
            "step": step,
        }
        response = await self._client.get(
            f"{self.endpoint}/api/metrics/query_range",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def _traceql_search(
        self,
        query: str,
        start: datetime,
        end: datetime,
        limit: int = 20,
    ) -> list[dict]:
        """
        Execute a TraceQL search via /api/search.
        Returns matching trace/span results.
        """
        params = {
            "q": query,
            "start": str(int(start.timestamp())),
            "end": str(int(end.timestamp())),
            "limit": str(limit),
        }
        response = await self._client.get(
            f"{self.endpoint}/api/search",
            params=params,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("traces", [])

    async def _prometheus_query(self, query: str, at: datetime) -> dict:
        """
        Instant query against Prometheus for service graph metrics.
        Reuses the Prometheus URL already configured for NthLayer.
        """
        if not self.prometheus_url:
            return {}
        
        params = {
            "query": query,
            "time": str(int(at.timestamp())),
        }
        response = await self._client.get(
            f"{self.prometheus_url}/api/v1/query",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def health_check(self) -> bool:
        """Verify Tempo is reachable via the ready endpoint."""
        try:
            response = await self._client.get(f"{self.endpoint}/ready")
            return response.status_code == 200
        except Exception:
            return False

    async def get_service_dependencies(
        self,
        service: str,
        start: datetime,
        end: datetime,
    ) -> list[ServiceCallEdge]:
        if self.use_service_graphs and self.prometheus_url:
            return await self._query_service_graphs_from_prometheus(
                [service], start, end
            )
        return await self._query_edges_from_traces([service], start, end)

    # ---------------------------------------------------------------
    # Result parsing helpers
    # ---------------------------------------------------------------

    def _extract_metric_by_service(self, response: dict) -> dict[str, float]:
        """
        Extract {service_name: average_value} from TraceQL metrics response.
        
        TraceQL metrics API returns Prometheus-like format:
        {
            "series": [
                {
                    "labels": {"resource.service.name": "fraud-detect"},
                    "samples": [[timestamp, value], ...]
                }
            ]
        }
        """
        result: dict[str, float] = {}
        for series in response.get("series", []):
            service = (
                series.get("labels", {}).get("resource.service.name", "")
                or series.get("promLabels", {}).get("resource_service_name", "")
            )
            if not service:
                continue
            
            samples = series.get("samples", [])
            if samples:
                values = [s[1] for s in samples if s[1] is not None]
                result[service] = sum(values) / len(values) if values else 0
        
        return result

    def _extract_metric_by_service_and_op(
        self, response: dict
    ) -> dict[tuple[str, str], float]:
        """
        Extract {(service, operation): average_value} from TraceQL metrics response
        faceted by service.name and span name.
        """
        result: dict[tuple[str, str], float] = {}
        for series in response.get("series", []):
            labels = series.get("labels", {})
            service = labels.get("resource.service.name", "")
            operation = labels.get("name", "")
            if not service or not operation:
                continue
            
            samples = series.get("samples", [])
            if samples:
                values = [s[1] for s in samples if s[1] is not None]
                result[(service, operation)] = (
                    sum(values) / len(values) if values else 0
                )
        
        return result

    def _parse_service_graph_results(
        self,
        count_data: dict,
        error_data: dict,
        p99_data: dict,
        p50_data: dict,
    ) -> list[ServiceCallEdge]:
        """
        Parse Prometheus query results for service graph metrics
        into ServiceCallEdge objects.
        """
        edges: dict[tuple[str, str], dict] = {}
        
        for result in count_data.get("data", {}).get("result", []):
            client = result["metric"].get("client", "")
            server = result["metric"].get("server", "")
            if client and server:
                edges[(client, server)] = {
                    "count": float(result["value"][1]),
                    "errors": 0, "p50": 0, "p99": 0,
                }
        
        for result in error_data.get("data", {}).get("result", []):
            key = (
                result["metric"].get("client", ""),
                result["metric"].get("server", ""),
            )
            if key in edges:
                edges[key]["errors"] = float(result["value"][1])
        
        for result in p99_data.get("data", {}).get("result", []):
            key = (
                result["metric"].get("client", ""),
                result["metric"].get("server", ""),
            )
            if key in edges:
                # Service graph latency is in seconds; convert to ms
                edges[key]["p99"] = float(result["value"][1]) * 1000
        
        for result in p50_data.get("data", {}).get("result", []):
            key = (
                result["metric"].get("client", ""),
                result["metric"].get("server", ""),
            )
            if key in edges:
                edges[key]["p50"] = float(result["value"][1]) * 1000
        
        return [
            ServiceCallEdge(
                source_service=client,
                target_service=server,
                request_count=int(vals["count"]),
                error_count=int(vals["errors"]),
                p50_latency_ms=vals["p50"],
                p99_latency_ms=vals["p99"],
            )
            for (client, server), vals in edges.items()
        ]

    def _span_to_summary(self, span: dict) -> TraceSpanSummary:
        """Convert a Tempo search result span to TraceSpanSummary."""
        return TraceSpanSummary(
            trace_id=span.get("traceID", ""),
            span_id=span.get("spanID", ""),
            service=span.get("rootServiceName", ""),
            operation=span.get("rootTraceName", ""),
            duration_ms=span.get("durationMs", 0),
            status="error" if span.get("status") == "error" else "ok",
            error_message=span.get("span.status_message"),
            parent_service=None,  # not available in search results
            attributes={},
        )

    @staticmethod
    def _parse_tempo_timestamp(nanos: int) -> datetime:
        """Convert nanosecond unix timestamp to datetime."""
        from datetime import timezone
        return datetime.fromtimestamp(nanos / 1_000_000_000, tz=timezone.utc)

    @staticmethod
    def _traceql_service_filter(services: list[str]) -> str:
        """
        Build a TraceQL filter for multiple services.
        TraceQL uses || for OR within a spanset filter.
        """
        if len(services) == 1:
            return f'resource.service.name = "{services[0]}"'
        
        conditions = " || ".join(
            f'resource.service.name = "{s}"' for s in services
        )
        return f'({conditions})'


@dataclass
class _ServiceStats:
    """Internal: aggregated stats for a single service."""
    p50_ms: float
    p95_ms: float
    p99_ms: float
    total_count: int
    error_count: int
    error_rate: float


@dataclass
class _EdgeAccumulator:
    """Internal: accumulator for client-side edge aggregation."""
    count: int = 0
    errors: int = 0
    durations: list[float] = None
    
    def __post_init__(self):
        if self.durations is None:
            self.durations = []
```

### 3.4 Query Strategy

The adapter uses two Tempo APIs depending on what it needs:

| Data | API | Server-side? | Notes |
|---|---|---|---|
| Latency percentiles | TraceQL metrics (`quantile_over_time`) | Yes | 3 queries (p50, p95, p99) faceted by service |
| Request/error count | TraceQL metrics (`count_over_time`) | Yes | 2 queries faceted by service |
| Per-operation breakdown | TraceQL metrics (faceted by service + name) | Yes | 5 queries (incident + baseline) |
| Service call edges | Prometheus service graph metrics | Yes | 4 PromQL queries (fast path) |
| Service call edges | TraceQL search (fallback) | No — client-side aggregation | Used when metrics-generator not available |
| Top errors | TraceQL search | Partially — search server-side, grouping client-side | Per-service, capped at 100 spans |
| Sample traces | TraceQL search | No — fetch + client-side sort | 3 error + 3 slow per service |

For a blast radius of 5-10 services, the fast path (with service graph metrics) runs ~10 TraceQL metrics queries + 4 PromQL queries, all parallelised. Typical wall time: 5-10 seconds. The slow path (without metrics-generator) replaces the 4 PromQL queries with per-service trace searches, adding ~3-5 seconds.

### 3.5 Tempo Requirements

The adapter has a minimal requirement: **Tempo with TraceQL metrics enabled** (requires the `local_blocks` processor in the metrics-generator config). This is enabled by default in Grafana Cloud and straightforward to enable in self-hosted Tempo.

Without TraceQL metrics enabled, the adapter cannot compute latency percentiles or request counts server-side. The adapter should detect this on the first query failure and emit a clear error:

```
✗ Tempo TraceQL metrics not available at http://tempo:3200
  → Enable the local_blocks processor in your metrics-generator config.
  → See: https://grafana.com/docs/tempo/latest/metrics-from-traces/metrics-queries/configure-traceql-metrics/
```

The **service graph metrics** (fast path for call edges) require the `service_graphs` processor in the metrics-generator, writing to Prometheus. This is optional — the adapter falls back to trace search if not available.

---

## Part 4: Topology Divergence Detection

### 4.1 Comparing Declared vs Observed

This is computed by the correlation engine (not the adapter) because it requires the declared dependency graph from the OpenSRM specs.

```python
# nthlayer-correlate/src/nthlayer_correlate/traces/topology.py

from .protocol import TraceEvidence, TopologyDivergence


def detect_topology_divergence(
    trace_evidence: TraceEvidence,
    declared_deps: dict[str, dict],  # from load_dependency_graph()
) -> TopologyDivergence:
    """
    Compare observed trace edges against declared dependency graph.
    
    declared_deps format (from prometheus.py:load_dependency_graph):
    {
        "service-a": {
            "tier": "critical",
            "dependencies": ["service-b", "service-c"],
            "dependents": ["service-d"],
        }
    }
    """
    # Build sets of observed edges
    observed_edges: set[tuple[str, str]] = set()
    for svc_profile in trace_evidence.services:
        for callee in svc_profile.callees:
            observed_edges.add((callee.source_service, callee.target_service))
        for caller in svc_profile.callers:
            observed_edges.add((caller.source_service, caller.target_service))
    
    # Build set of declared edges (only for services in blast radius)
    blast_services = {svc.service for svc in trace_evidence.services}
    declared_edges: set[tuple[str, str]] = set()
    for service, info in declared_deps.items():
        if service not in blast_services:
            continue
        for dep in info.get("dependencies", []):
            if dep in blast_services:
                declared_edges.add((service, dep))
    
    return TopologyDivergence(
        declared_not_observed=sorted(declared_edges - observed_edges),
        observed_not_declared=sorted(observed_edges - declared_edges),
    )
```

### 4.2 Why This Matters

Topology divergence is a correlation signal in its own right. If the declared graph says `payment-api → fraud-detect` but traces show `payment-api → api-gateway → fraud-detect`, the blast radius calculation may be wrong (api-gateway is an undeclared intermediate that could also be a failure point). The reasoning layer should know this.

More importantly for NthLayer's positioning: topology divergence is a **spec drift** detection. The declared state doesn't match reality. That's exactly NthLayer's value prop — schemas + enforcement, with drift detection as the feedback loop.

---

## Part 5: CLI and Configuration

### 5.1 New CLI Flags

```bash
nthlayer correlate \
  --trigger-verdict <id> \
  --prometheus-url http://localhost:9090 \
  --trace-backend tempo \
  --tempo-endpoint http://tempo:3200 \
  --specs-dir ./specs/ \
  --verdict-store ./verdicts.db

# Trace detail level (optional, default: full)
nthlayer correlate \
  --trigger-verdict <id> \
  --trace-backend tempo \
  --trace-detail summary              # summary = stats only, full = stats + ops + samples
```

### 5.2 Configuration File

```yaml
# ~/.nthlayer/config.yaml

traces:
  backend: tempo                       # tempo | jaeger | none
  detail: full                         # summary | full
  baseline_window: 1h                  # comparison window before incident
  
  tempo:
    endpoint: "http://tempo:3200"
    org_id: ""                         # X-Scope-OrgID for multi-tenant
    timeout_seconds: 30
    use_service_graphs: true           # query Prometheus for service graph metrics
  
  # Future
  jaeger:
    endpoint: "http://jaeger-query:16685"
```

### 5.3 Graceful Degradation

If the trace backend is configured but unreachable, correlate proceeds without trace evidence. This is the same pattern as the reasoning layer fallback.

```python
trace_evidence = None
if trace_backend:
    try:
        trace_evidence = await asyncio.wait_for(
            trace_backend.get_trace_evidence(services, start, end),
            timeout=trace_timeout,
        )
    except (httpx.HTTPError, asyncio.TimeoutError) as e:
        logger.warning(
            "trace_evidence_unavailable",
            backend=trace_backend_name,
            error=str(e),
        )
```

The correlation verdict indicates whether trace evidence was available:

```yaml
metadata:
  custom:
    evidence_sources:
      prometheus: true
      verdict_store: true
      trace_backend: "tempo"        # or null if unavailable
    trace_query_time_ms: 6240       # or null
```

---

## Part 6: Jaeger Adapter (Sketch)

Jaeger is the second adapter target. It validates the abstraction holds for a backend with very different query capabilities.

**Key difference from Tempo:** Jaeger has no server-side aggregation. No equivalent of TraceQL metrics. The Jaeger adapter must fetch spans via the gRPC query service (`FindTraces` RPC) and compute all percentiles, error rates, and edge counts client-side.

This means the Jaeger adapter is heavier — potentially fetching thousands of spans for a blast radius of 5-10 services over a 30-minute window. Mitigations:

- Cap span fetch at 1,000 per service (configurable)
- Use Jaeger's service/operation filtering to narrow the fetch
- Compute aggregations incrementally rather than loading all spans into memory

The abstraction handles this cleanly because `TraceBackend.get_trace_evidence()` returns the same `TraceEvidence` structure regardless of how the adapter computed it. The correlation engine and reasoning layer never know whether the percentiles came from server-side TraceQL or client-side computation.

**Estimated effort:** 2-3 days. The protocol and all integration code from the Tempo work carries over. Only the query transport and client-side aggregation logic is new.

---

## Implementation Priority

| Phase | Work | Effort | Outcome |
|---|---|---|---|
| **1** | Protocol + dataclasses (`traces/protocol.py`) | 1 day | Abstraction defined, importable |
| **2** | Tempo adapter (`traces/tempo.py`) | 3-4 days | First working trace backend |
| **3** | Integrate into `_gather()` + reasoning prompt | 2-3 days | Traces appear in correlation verdicts |
| **4** | Topology divergence detection | 1 day | Spec drift from traces |
| **5** | CLI flags + config | 1 day | User-configurable |
| **6** | Jaeger adapter | 2-3 days | Validates abstraction, broadens reach |

**Phases 1-5:** ~8-10 days for a working trace integration with Tempo.

**Phase 6** is follow-on. The Jaeger adapter should be a single file implementing `TraceBackend`, with no changes to the correlation engine, reasoning layer, or verdict schema. If it requires changes, the abstraction is wrong.

---

## Audit First

Before implementing, Claude Code must:

1. Read `nthlayer-correlate/src/nthlayer_correlate/cli.py` — specifically `correlate_command()` and `_gather()`. Document the exact signal gathering flow, what data structures are passed between stages, and where trace evidence should be injected.
2. Read `nthlayer-correlate/src/nthlayer_correlate/prometheus.py` — this is the reference adapter. Understand the query patterns, error handling, and how results are converted to correlation events.
3. Read `nthlayer-correlate/src/nthlayer_correlate/reasoning.py` — specifically `_build_user_prompt()`. Understand the existing prompt structure and where the trace evidence section should be added.
4. Read `nthlayer-correlate/src/nthlayer_correlate/types.py` — understand `CorrelationGroup`, `TemporalGroup`, `ChangeCandidate` and how evidence is represented.
5. Check whether a `traces/` directory or any trace-related code already exists.
6. Check the existing config loading pattern (`config.py` or CLI argument parsing) to understand how to add trace backend configuration consistently.
7. Document findings before implementing. Where the existing code already partially covers a capability, extend it rather than creating parallel structures.
