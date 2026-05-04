# P3-D.3: Correlate Module — Instructor-Backed NL Summary

**Date:** 2026-04-24
**Epic:** P3-D (Correlate Module)
**Dependencies:** P1-A.1 (Instructor integration), P3-D.1
**Spec:** NTHLAYER-CORRELATE-v1 §8 (NL summary)

## Summary

Add operator-legible natural language summaries to `correlation_snapshot` assessments. Uses `structured_call()` from nthlayer-common with Instructor for validated Pydantic output. LLM failure is non-blocking — snapshots submit with `nl_summary: None` on timeout or error.

The snapshot's category remains **assessment** (deterministic grouping is the primary content). The NL summary is an annotation for human-legibility, not semantic substance.

---

## Pydantic Model

```python
from pydantic import BaseModel, Field


class SnapshotSummary(BaseModel):
    """Operator-legible summary of a correlation window.

    2-4 sentences describing what happened. No root-cause speculation —
    summary describes observations, not conclusions.
    """

    summary: str = Field(max_length=500)
    notable_omissions: list[str] = Field(default_factory=list)
```

No `confidence` field. LLM self-reported confidence is unreliable and tempting to misuse downstream. Summary quality gets measured by measure module's self-calibration pipeline (v2 deferred), not in-band self-report. `notable_omissions` is retained — it's grounded (the LLM reports what it lacks context for, e.g. "no trace data available", "only 2 of 5 affected services had SLO assessments").

---

## Integration Point

`CorrelateSessionModule._emit_snapshot()` in `correlate/worker.py`. After building `snapshot_data`, before submitting the assessment.

```python
# In _emit_snapshot(), after building snapshot_data:
nl_summary = await _generate_summary(snapshot_data, window.events)
snapshot_data["nl_summary"] = nl_summary  # dict or None
```

---

## Summary Generation

```python
async def _generate_summary(
    snapshot_data: dict,
    events: list[SitRepEvent],
    model: str | None = None,
    timeout: float = 5.0,
) -> dict | None:
    """Generate NL summary for a correlation snapshot.

    Returns {"summary": "...", "notable_omissions": [...]} on success,
    or None on any failure (timeout, LLM unavailable, validation error).

    Uses asyncio.to_thread() because structured_call() is synchronous
    in v1.5. v2 LLM class refactor makes this native-async (V2-F deferred).
    """
```

### Prompt Design

**System prompt:**
> You are summarizing a correlation window for an on-call SRE operator. Describe what happened in 2-4 sentences. Be specific about services, metrics, and timeline. Do NOT speculate about root cause — describe observations only. If you lack context to be specific, say what's missing in notable_omissions.

**User prompt** contains:
- Affected services (from `snapshot_data["affected_services"]`)
- Event count by type (from `snapshot_data["event_types"]`)
- Peak severity (from `snapshot_data["peak_severity"]`)
- Window duration and close reason
- **Sample events** for concrete detail:
  - First event (chronologically)
  - Most severe event
  - Most recent event per affected service
  - Up to 10 events total, ~2-3k tokens

Sample events are serialised as compact dicts: `{service, type, severity, timestamp, source}`. No raw payloads — just the fields that matter for the summary.

### Timeout and Error Handling

**Explicit 5-second timeout** on the LLM call. Snapshot latency stays bounded.

```python
try:
    result = await asyncio.wait_for(
        asyncio.to_thread(
            structured_call,
            system=SYSTEM_PROMPT,
            user=user_prompt,
            response_model=SnapshotSummary,
            model=model,
            timeout=5,
        ),
        timeout=5.0,
    )
    return {"summary": result.summary, "notable_omissions": result.notable_omissions}
except Exception as e:
    _record_summary_failure(e, snapshot_id)
    return None
```

On timeout or any exception: `nl_summary: None`, submit snapshot immediately, log warning, emit metrics.

### Observability

Emit on every failure:

```python
def _record_summary_failure(error: Exception, snapshot_id: str) -> None:
    reason = _classify_failure(error)  # "timeout" | "validation_error" | "llm_unavailable"
    logger.warning("correlate_summary_failed", reason=reason, snapshot_id=snapshot_id)
    # Prometheus counter
    from nthlayer_common.metrics import errors_total
    errors_total.labels(component="correlate", error_type=f"summary_{reason}").inc()
    # OTel event
    from nthlayer_common.telemetry import emit_llm_event
    emit_llm_event(
        model=model or "unknown",
        provider="unknown",
        caller="correlate._generate_summary",
        success=False,
        error=str(error),
    )
```

Failure reasons:
- `timeout` — `asyncio.TimeoutError`
- `validation_error` — Instructor validation failures after exhausting retries
- `llm_unavailable` — `LLMError` from provider (API key missing, connection refused, etc.)

---

## Sample Event Selection

```python
def _select_sample_events(events: list[SitRepEvent], max_samples: int = 10) -> list[dict]:
    """Select representative events for the LLM prompt.

    Includes: first event, most severe event, most recent per service.
    Deduplicates by ID. Caps at max_samples.
    """
    samples: dict[str, SitRepEvent] = {}

    # First event (chronologically)
    sorted_events = sorted(events, key=lambda e: e.timestamp)
    if sorted_events:
        samples[sorted_events[0].id] = sorted_events[0]

    # Most severe event
    most_severe = max(events, key=lambda e: e.severity)
    samples[most_severe.id] = most_severe

    # Most recent per service
    by_service: dict[str, SitRepEvent] = {}
    for e in sorted_events:
        by_service[e.service] = e  # last wins = most recent
    for e in by_service.values():
        samples[e.id] = e

    # Cap at max_samples
    result = list(samples.values())[:max_samples]
    return [
        {
            "service": e.service,
            "type": e.type.value,
            "severity": e.severity,
            "timestamp": e.timestamp,
            "source": e.source,
        }
        for e in result
    ]
```

---

## Test Strategy

### Summary generation
- `test_summary_success` — mock `structured_call` returns valid SnapshotSummary → dict with summary + notable_omissions
- `test_summary_timeout` — mock `structured_call` hangs → returns None within 5s, no crash
- `test_summary_llm_unavailable` — mock raises `LLMError` → returns None
- `test_summary_validation_error` — mock returns malformed data → returns None after retries

### Integration
- `test_snapshot_includes_summary` — full `_emit_snapshot` with mock LLM → submitted assessment has `nl_summary` dict
- `test_snapshot_submits_without_summary_on_failure` — mock LLM fails → snapshot still submitted with `nl_summary: None`

### Sample event selection
- `test_select_sample_events_basic` — returns first, most severe, most recent per service
- `test_select_sample_events_caps_at_max` — more than max_samples events → capped
- `test_select_sample_events_deduplicates` — same event is first and most severe → appears once

### Pydantic model
- `test_snapshot_summary_max_length` — summary > 500 chars fails validation
- `test_snapshot_summary_default_omissions` — default empty list

---

## Acceptance Criteria

From the epic tree:
1. Summary generated for each closed window
2. Structured output via Instructor with validation
3. Summary max 500 chars, 2-4 sentences
4. LLM unavailability → summary dropped (not blocking), snapshot still produced

Added:
5. Explicit 5-second timeout on LLM call
6. Sample events (up to 10) included in prompt for concrete detail
7. No confidence field — grounded notable_omissions only
8. Observability: Prometheus counter + OTel event on every failure
9. `asyncio.to_thread()` wrapper flagged for v2 cleanup (V2-F)

---

## Work Sequence

| Step | What | Verify |
|------|------|--------|
| 1 | Define `SnapshotSummary` Pydantic model + `_select_sample_events()` | Unit tests pass |
| 2 | Implement `_generate_summary()` with structured_call + timeout + observability | Summary tests pass |
| 3 | Wire into `_emit_snapshot()` — replace `nl_summary: None` placeholder | Integration tests pass |
| 4 | Full suite verification | All correlate + observe + runner tests pass |
