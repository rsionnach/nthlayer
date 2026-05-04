# P3-D.1: Correlate Module — Session Window Semantics

**Date:** 2026-04-24 (revised)
**Epic:** P3-D (Correlate Module)
**Dependencies:** P3-A.1 (module runner)
**Spec:** NTHLAYER-CORRELATE-v1 §4 (renamed to "Session Window Semantics")

## Summary

Implement asyncio-based session window logic as a worker module. Events polled from core API are grouped by correlation domain into session windows that close on temporal gap, max duration, or trigger verdict. Closed windows produce `correlation_snapshot` assessments submitted to core.

This is the architectural core of the correlate module — session windows are what make correlation novel vs. simple alert aggregation.

## What's New vs. What Exists

| Concept | Existing code | P3-D.1 |
|---------|--------------|--------|
| **Correlation domain** | Groups by `service` only | Groups by `(service, environment)` |
| **Window type** | Fixed-window (N minutes from first event) | Session window (gap-based + max duration) |
| **Window close** | Implicit (all events in range) | Explicit: 60s gap, 15m max, or trigger verdict |
| **State persistence** | None across invocations | Cursor + open windows persisted to core `component_state` |
| **Event source** | Prometheus alerts + trigger verdict (one-shot) | Core API poll (continuous) |
| **FTS5 store** | Exists, used as temp store per invocation | Reused as per-worker event cache across cycles |

---

## CloudEvents Taxonomy Fix

**`correlation_snapshot` is an assessment, not a verdict.**

The existing CloudEvents taxonomy in `cloudevents.py` incorrectly places `correlation_snapshot` in `_VERDICT_TYPES`. A correlation snapshot is deterministic grouping of events by temporal proximity and topological relationships, with heuristic (not LLM-driven) priority scoring. Same events in, same groups out. No confidence score, no reasoning chain. This is an assessment (deterministic observation), not a verdict (judgment-bearing decision).

**When P3-D.3 adds NL summary**, the snapshot remains an assessment. The LLM-generated summary is an annotation for human-legibility, not the semantic substance. Deterministic grouping and heuristic priority remain the primary content. The category does not change.

**Fix (step 1 of work sequence):**
1. Move `correlation_snapshot` from `_VERDICT_TYPES` to `_ASSESSMENT_KINDS`
2. Move `topology_drift` from `_VERDICT_TYPES` to `_ASSESSMENT_KINDS`
3. Move `contract_divergence` from `_VERDICT_TYPES` to `_ASSESSMENT_KINDS`
4. Submit via `client.submit_assessment()` throughout P3-D.1

All three share the same architectural property: they are observations-that-inform-decisions, not decisions themselves. Topology drift ("declared dependency A→B, observed traffic A→C") and contract divergence ("promised 99.9%, measured 99.5%") are factual comparisons between declared and observed state. Neither authorises action or changes system state. Moving all three at once means one taxonomy-fix commit rather than three.

**Update NTHLAYER-TELEMETRY-ENVELOPE §3.4** to reflect the change.

### Centralise Assessment Kind Validation

Observe currently maintains a local `VALID_ASSESSMENT_TYPES` frozenset in `assessment.py` that duplicates the canonical `_ASSESSMENT_KINDS` in `cloudevents.py`. Two sources of truth for valid assessment kinds is the drift-magnet we've been avoiding.

**Fix:** Export `ASSESSMENT_KINDS` from `nthlayer_common.cloudevents` as a public constant. Observe's local `VALID_ASSESSMENT_TYPES` imports from common rather than maintaining a copy. Correlate uses common's validation directly — no new local validator.

```python
# nthlayer_common/cloudevents.py
ASSESSMENT_KINDS = frozenset({
    "slo_status",
    "judgment_slo_evaluation",
    "burn_rate",
    "drift_signal",
    "portfolio_status",
    "deploy_gate",
    "dependency_graph",
    "correlation_snapshot",   # moved from _VERDICT_TYPES
    "topology_drift",         # moved from _VERDICT_TYPES
    "contract_divergence",    # moved from _VERDICT_TYPES
})

# Internal alias for backward compat within this file
_ASSESSMENT_KINDS = ASSESSMENT_KINDS
```

```python
# nthlayer_workers/observe/assessment.py
from nthlayer_common.cloudevents import ASSESSMENT_KINDS

# Local additions for observe-only types not in CloudEvents taxonomy
VALID_ASSESSMENT_TYPES = ASSESSMENT_KINDS | frozenset({"verification"})
```

`verification` is an observe-internal type not in the CloudEvents taxonomy (CLI-only, never submitted to core). It stays as a local addition.

### P3-D.2 Flag

P3-D.2 currently categorises `topology_drift` and `contract_divergence` as verdicts. Per the same reasoning as `correlation_snapshot`, these are factual observations about declared-vs-observed state, not judgment-bearing decisions. **Re-examine during P3-D.2 design** — the taxonomy fix in this step moves them pre-emptively based on the architectural analysis, but P3-D.2 should confirm the categorisation when implementing those specific outputs.

---

## Architecture

### CorrelateModule (WorkerModule)

```
CorrelateModule.process_cycle()
  │
  ├─ 1. Poll core API for new verdicts + assessments since cursor
  │     (quality_breach, slo_status, drift_signal, autonomy_change)
  │
  ├─ 2. Convert to SitRepEvents, ingest into local FTS5 store
  │
  ├─ 3. Assign events to session windows by correlation domain
  │     key = (service, environment)
  │
  ├─ 4. Check close conditions for each open window:
  │     - Temporal gap: no new events for 60s
  │     - Max duration: window open > 15 minutes
  │     - Trigger: quality_breach verdict in this domain
  │
  ├─ 5. For each closed window:
  │     - Run CorrelationEngine.correlate() on window events
  │     - Build correlation_snapshot assessment
  │     - Fetch topology from core manifests for blast radius
  │     - Submit to core via POST /assessments
  │
  └─ 6. Persist cursor + open window state to core component_state
```

### Correlation Domain

**New concept.** Not present in existing code. Current temporal grouping keys by `service` only; `environment` field exists on `SitRepEvent` but is unused for grouping.

```python
@dataclass(frozen=True)
class CorrelationDomain:
    """Key for session window grouping."""
    service: str
    environment: str

    @classmethod
    def from_event(cls, event: SitRepEvent) -> CorrelationDomain:
        return cls(service=event.service, environment=event.environment)
```

A `fraud-detect` incident in `production` and `staging` are separate correlation domains with separate windows.

### Session Window

```python
@dataclass
class SessionWindow:
    """An open session window accumulating events for a correlation domain."""
    domain: CorrelationDomain
    events: list[SitRepEvent]
    opened_at: datetime       # when first event arrived
    last_event_at: datetime   # when most recent event arrived
    has_trigger: bool = False # quality_breach verdict seen in this domain

    def should_close(self, now: datetime, gap_seconds: float = 60.0, max_duration_seconds: float = 900.0) -> bool:
        gap_exceeded = (now - self.last_event_at).total_seconds() >= gap_seconds
        duration_exceeded = (now - self.opened_at).total_seconds() >= max_duration_seconds
        return gap_exceeded or duration_exceeded or self.has_trigger
```

**Close conditions:**
- **Temporal gap (60s):** No new events in the window's domain for 60 seconds.
- **Max duration (15m):** Prevents never-closing windows under continuous load (flapping service).
- **Trigger verdict:** A `quality_breach` verdict arrives for a domain with an open window — force-close immediately and synthesise.

**All defaults configurable** via `nthlayer.yaml`:
```yaml
workers:
  correlate:
    cycle_interval_seconds: 10
    gap_seconds: 60
    max_window_seconds: 900  # 15 minutes
```

### Cycle Interval Trade-off

Default: **10 seconds**. Session windows need sub-minute granularity to detect the 60-second gap condition accurately.

| Interval | Gap detection latency | Core API load | Trade-off |
|----------|----------------------|---------------|-----------|
| 10s | Up to 10s | ~6 polls/min | Best gap accuracy, higher API load |
| 15s | Up to 15s | ~4 polls/min | Acceptable accuracy, moderate load |
| 30s | Up to 30s | ~2 polls/min | Poor gap accuracy (gap appears 30-90s, not 60s) |

10s is the default because gap accuracy matters more than API load at v1.5 scale. Operators can increase to 15-30s via config if API load is a concern.

### Event Source: Core API Polling

Each `process_cycle()` polls core for new verdicts and assessments since the last cursor.

**Verdict types polled:** `quality_breach`, `autonomy_change` (from measure)
**Assessment kinds polled:** `slo_status`, `drift_signal` (from observe)

**Cursor:** ISO 8601 timestamp of the most recent event processed.

**Event conversion:** Core verdicts/assessments are converted to `SitRepEvent` objects:

```python
def verdict_to_event(verdict: dict) -> SitRepEvent:
    return SitRepEvent(
        id=verdict["id"],
        timestamp=verdict["created_at"],
        source=f"verdict:{verdict.get('type', 'unknown')}",
        type=EventType.VERDICT if verdict.get("type") != "quality_breach" else EventType.QUALITY_SCORE,
        service=verdict.get("service", "unknown"),
        environment=verdict.get("environment", "production"),
        severity=_severity_from_verdict(verdict),
        payload=verdict,
    )

def assessment_to_event(assessment: dict) -> SitRepEvent:
    return SitRepEvent(
        id=assessment["id"],
        timestamp=assessment["created_at"],
        source=f"assessment:{assessment.get('kind', 'unknown')}",
        type=EventType.METRIC_BREACH if _is_breach(assessment) else EventType.ALERT,
        service=assessment.get("service", "unknown"),
        environment="production",
        severity=_severity_from_assessment(assessment),
        payload=assessment,
    )
```

**Environment defaulting:** Assessments don't carry an `environment` field — default `"production"`. This is a known limitation. v2 plan: add `environment` to the assessment data model (requires core schema change) or resolve from manifest's deployment config. For v1.5, single-environment deployments are the expected case.

### Local FTS5 Event Store

The existing `SQLiteEventStore` is reused as a **per-worker event cache**. NOT authoritative — if the worker crashes and loses the store, events can be re-ingested from core API by resetting the cursor. The store is a working cache, not durable state.

**Lifecycle:**
- Created on module init
- Events inserted each cycle
- Expired events cleaned up periodically (default TTL: 24h)
- On crash recovery: cursor reset, events re-ingested from core

**FTS5 retained** for the correlation engine's `search()` capability and the reasoning layer in P3-D.3.

### Snapshot Output

Each closed window produces a `correlation_snapshot` **assessment** (not verdict):

```python
assessment = create("correlation_snapshot", domain.service, {
    "domain": {"service": domain.service, "environment": domain.environment},
    "window": {
        "opened_at": window.opened_at.isoformat(),
        "closed_at": now.isoformat(),
        "duration_seconds": (now - window.opened_at).total_seconds(),
        "close_reason": close_reason,  # "gap" | "max_duration" | "trigger"
    },
    "event_count": len(window.events),
    "event_types": _count_by_type(window.events),
    "peak_severity": max(e.severity for e in window.events),
    "affected_services": _unique_services(window.events),
    "correlation_groups": [_group_to_dict(g) for g in groups],
    "blast_radius": blast_radius_dict,
    "environment_source": "default",  # "default" | "manifest" | "event" — for downstream consumers
    "nl_summary": None,  # Placeholder for P3-D.3
})
```

Submitted via `client.submit_assessment()`.

---

## Alignment Work

### Existing code updates

1. **`group_temporal()` groups by `service` only** — add a new `group_by_domain()` that session windows use. Existing `group_temporal()` stays for CLI backward compat.

2. **`SitRepEvent.environment` field exists** but unused for grouping. Session windows use it via `CorrelationDomain`. No change to the field itself.

### No type renames needed

Unlike observe, correlate's internal types are already aligned with v1.5 shapes.

---

## CLI: On-demand Correlation

The existing `nthlayer-correlate correlate --trigger-verdict X` command stays as an on-demand CLI tool, analogous to `nthlayer-workers gate`.

**Concurrent invocation:** The worker module and CLI command should NOT run concurrently against the same FTS5 store. The worker uses an in-memory or temp-file store; the CLI uses its own store path. No shared state, no conflict. If both are pointed at the same store path (misconfiguration), SQLite WAL mode prevents corruption but results will be unpredictable. Document this as a usage constraint.

---

## Module Registration

```python
correlate = CorrelateModule(client=client, prometheus_url=url)
runner.register(correlate, interval_seconds=10)
```

---

## State Persistence

Persisted to core via `put_component_state("correlate", state)` after each cycle:

```python
{
    "cursor": "2026-04-24T12:00:00Z",
    "windows": {
        "fraud-detect:production": {
            "opened_at": "2026-04-24T11:55:00Z",
            "last_event_at": "2026-04-24T11:59:30Z",
            "event_count": 7,
            "has_trigger": false,
        },
    }
}
```

**On restore:** `restore_state()` rebuilds open windows by re-fetching events from core API between `window.opened_at` and now. Window metadata restored from component_state; actual events re-fetched. This avoids serialising full event payloads into component_state.

**Retention corner case:** Events in an open window may have been pruned from core's store by the time worker restoration happens (core's retention runs daily, default 365d for verdicts, 90d for assessments). For v1.5 this is a non-issue — windows live for at most 15 minutes, and the shortest retention is 90 days. Document the assumption: window lifetime << assessment retention.

---

## Test Strategy

### Session window logic (new)
- `test_window_closes_on_gap` — events arrive, 60s gap, window closes
- `test_window_closes_on_max_duration` — continuous events for 15m, window force-closes
- `test_window_closes_on_trigger` — quality_breach verdict force-closes window
- `test_multiple_domains_independent` — two services, events interleaved, separate windows
- `test_window_produces_snapshot` — closed window generates correlation_snapshot assessment

### CorrelateModule protocol
- `test_correlate_module_protocol` — satisfies WorkerModule
- `test_process_cycle_polls_core` — verifies cursor-based polling
- `test_process_cycle_no_events_noop` — empty poll, no windows opened
- `test_state_persistence` — cursor and window metadata persisted after cycle
- `test_state_restoration` — module restores cursor and rebuilds windows from core

### Event conversion
- `test_verdict_to_event` — quality_breach verdict → SitRepEvent
- `test_assessment_to_event` — slo_status assessment → SitRepEvent
- `test_environment_defaults_to_production` — assessments without environment field

### Existing tests
All existing correlate tests (19 files, ~4000 lines) continue to pass unchanged. Session window logic is additive.

---

## Acceptance Criteria

From the epic tree:
1. Events grouped by correlation domain
2. Windows close after 60s gap with no new events
3. Session state survives worker restart (persisted to core component_state)
4. Closed windows produce correlation_snapshot assessments
5. Test: send burst of events, wait 60s gap, verify window closes and snapshot produced

Added:
6. Max duration (15m) prevents never-closing windows
7. quality_breach verdict force-closes window immediately
8. Cursor-based polling from core API
9. Module registered at 10s interval
10. Existing correlate tests pass unchanged
11. `correlation_snapshot`, `topology_drift`, `contract_divergence` moved from verdict types to assessment kinds in CloudEvents taxonomy
12. Assessment kind validation centralised in `nthlayer_common.cloudevents`

---

## Work Sequence

| Step | What | Verify |
|------|------|--------|
| 1 | CloudEvents taxonomy fix: move 3 types from `_VERDICT_TYPES` to `_ASSESSMENT_KINDS`; export `ASSESSMENT_KINDS`; update observe to import from common | `pytest nthlayer-common/ -x` then `pytest nthlayer-workers/tests/observe/ -x` |
| 2 | Implement `CorrelationDomain` and `SessionWindow` dataclasses | Unit tests pass |
| 3 | Implement session window manager (open/close/assign logic) | Window tests pass |
| 4 | Implement event conversion (verdict/assessment → SitRepEvent) | Conversion tests pass |
| 5 | Implement `CorrelateModule` (WorkerModule protocol) | Protocol + cycle tests pass |
| 6 | Wire snapshot output (closed window → correlation_snapshot assessment → core API) | End-to-end test pass |
| 7 | Implement state persistence + restoration | State roundtrip tests pass |
| 8 | Register in workers CLI | Full suite passes |
