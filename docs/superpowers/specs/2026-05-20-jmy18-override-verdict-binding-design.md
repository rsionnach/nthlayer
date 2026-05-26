# Override Verdict-Binding Path Design (opensrm-jmy.18)

**Status:** Approved for implementation. Reframed from the original "OTel consumer in nthlayer-workers/measure" framing via `/challenge-the-premise` on 2026-05-19. The bead in opensrm Dolt carries the reframed scope; this document is the design.

**Spec source:** `nthlayer/docs/roadmap/NTHLAYER_MISSING_CAPABILITIES_SPEC.md` § 4 steps 1-2 ("look up the verdict by decision_id; update outcome.status='overridden' and populate outcome.override").

**Foundation:**
- `nthlayer-common/src/nthlayer_common/overrides/ingestion.py` — `apply_override_to_verdict` (jmy.4 + jmy.11): CAS-safe verdict mutation, first-writer-wins, idempotent on same-content re-apply, structured logging on every None-return path.
- `nthlayer-common/src/nthlayer_common/api_client.py` — `CoreAPIClient` async HTTP client (fail-soft `APIResult`, transient-code retries, connection-error client reset).
- `nthlayer-override-adapter/` v0.1.0 (jmy.7) — running sidecar with canonical single + batch endpoints, generic webhook field-mapper, privacy applied at emission, unparented `gen_ai.override` OTel spans.

---

## 1. Reframing context

Original framing: OTel `gen_ai.override` consumer in `nthlayer-workers/measure` subscribes to the sidecar's emitted events and calls `apply_override_to_verdict`. Three candidate subscription mechanisms were left TBD (custom OTLP receiver, collector tap, span-exporter fork).

Reframed via `/challenge-the-premise`: route operational state mutation through HTTP, not through the observability pipeline. The sidecar already holds the `OverrideEvent` in memory; it can POST it to core directly, parallel to its OTel emission. Two thin transports with distinct semantics replace one transport doing two jobs.

| Concern | Transport | Rationale |
|---|---|---|
| Observability fan-out (reversal-rate metric, broadcast, lossy-tolerant) | OTel span emission (existing, unchanged) | OTel's strength: multi-consumer, decoupled, eventually consistent |
| Canonical state mutation (verdict outcome binding, idempotent, single-writer) | HTTP POST to core (new) | HTTP's strength: synchronous, retried, lossless, single authority |

Counter-considerations resolved on the bead:
- **Worker placement / decoupling**: not a v1.5 blocker. Override acceptance is already coupled to OTel collector availability; adding core as a second target doesn't fundamentally change the coupling profile. If reliability requirements emerge later, the sidecar gets a local buffer with retry — small additive change.
- **Privacy locus**: privacy applies uniformly at sidecar entry. Both OTel emission and core POST receive the same redacted payload. Per-target privacy configuration deferred to v2.
- **Spec § 4 wording**: "update outcome.status='overridden'" is a state-mutation contract, which the reframe matches more literally than the OTel-consumer interpretation.

---

## 2. Outcome representation patterns

NthLayer's verdict store supports two patterns for representing outcomes. They coexist by design; this design doc adds the first writer to the mutation-style pattern (which previously had no in-process writer despite having consumers).

**Mutation-style (overrides).** The verdict's `outcome.status` is updated in place to `"overridden"`, with `outcome.override` populated. Used for operator overrides where the canonical record lives on the original decision.

- Endpoint: `POST /verdicts/{id}/override` (new — this design)
- Function: `apply_override_to_verdict` in `nthlayer-common.overrides.ingestion`
- Concurrency: CAS via `expected_status`; first-writer-wins; idempotent on same-content re-apply.

**Lineage-style (resolutions).** A new `outcome_resolution` verdict is created as a child of the original via `parent_ids=[original_id]`. Used when the resolution is itself an event worth recording as a discrete artefact.

- Endpoint: `POST /verdicts/{id}/outcome` (existing, unchanged)
- Operation: creates new verdict; original unchanged.

Choose based on whether the outcome is *operator-imposed amendment* (mutation) or *new evidence about the decision* (lineage). The two patterns coexist because they serve different concerns; do not conflate.

---

## 3. Scope

### In scope

1. New endpoint `POST /verdicts/{verdict_id}/override` in `nthlayer-core/src/nthlayer_core/server.py`, parallel to `post_verdict_outcome`.
2. New method `CoreAPIClient.apply_override(verdict_id, payload) -> APIResult` in `nthlayer-common/src/nthlayer_common/api_client.py`.
3. New flag `OverridePrivacyConfig.pre_redacted: bool = False` in `nthlayer-common/src/nthlayer_common/overrides/models.py`, with `plaintext_reviewer` retained as a deprecated alias for backward compatibility.
4. Core-binding path in `nthlayer-override-adapter`:
   - New sidecar config block `core.{url, timeout_seconds}` (required).
   - Helper `_bind_to_core(event, decision_id) -> BindingResult` invoked per accepted decision in the canonical single, canonical batch, and dynamic webhook handlers.
   - Response envelope gains `bindings` field keyed by `decision_id`.
   - New Prometheus metric `nthlayer_override_binding_total{result, reason}`.
5. Tests across the three repos (see § 9).

### Out of scope (filed)

- `opensrm-jmy.19` — bench post_incident: surface mutation-style override attribution alongside lineage-style outcome_resolution rendering. The workers-side `respond/sre/post_incident.py` already reads `outcome.override` and lights up automatically once jmy.18 ships; the bench-side renderer walks lineage and needs an additive code change to also read mutation-style data. P3, parent jmy, discovered-from jmy.18.
- Retry / DLQ semantics for the core POST. v1.5 fails fast at 5s; failures surface in the response body's `bindings` map and in the Prometheus metric. v2 may add a local buffer + replay; defer until a real deployment needs it.
- Auth on `POST /verdicts/{id}/override`. Matches existing nthlayer-core posture (no auth in v1.5). File a separate follow-up if a deployment requires it.

### Capability boundary

After jmy.18 ships, retrospectives can claim "verdict X was overridden by operator Y at time Z for reason R" against the original verdict's `outcome.override`. The reversal-rate metric path (jmy.4 + jmy.7) continues working independently — the metric does not depend on jmy.18 and the demo's reversal-rate narrative remains delivered without it.

---

## 4. Architecture

```
┌──────────────────────┐
│ operator / webhook   │
└──────────┬───────────┘
           │ HTTP
           ▼
┌──────────────────────────────────────────────────────────┐
│ nthlayer-override-adapter (sidecar)                       │
│                                                           │
│ canonical / webhook routes ──► validate + apply privacy   │
│                                  │                        │
│                                  ▼                        │
│                          emit_override(event)             │
│                                  │  fail-open             │
│                                  ▼                        │
│                          OTel SDK ───► OTLP collector ──► observability
│                                  │                        │
│                                  ▼                        │
│                  CoreAPIClient.apply_override(id, body)   │
│                       (5s timeout, fail-soft APIResult)   │
│                                  │                        │
│                                  ▼                        │
│                  build BindingResult, increment counter   │
│                                  │                        │
│                                  ▼                        │
│            response body with bindings map                │
└──────────────────────────────────────────────────────────┘
                                  │ HTTP
                                  ▼
┌──────────────────────────────────────────────────────────┐
│ nthlayer-core                                             │
│                                                           │
│ POST /verdicts/{id}/override ──► deserialize OverrideEvent │
│                                  │                        │
│                                  ▼                        │
│                  apply_override_to_verdict(                │
│                      store, event,                         │
│                      privacy=OverridePrivacyConfig(        │
│                          pre_redacted=True))               │
│                                  │                        │
│                                  ▼                        │
│                  HTTP status from return-value mapping     │
└──────────────────────────────────────────────────────────┘
```

Two transports run sequentially per accepted decision (OTel emission first, then core POST) but **independently** — OTel emission failure does not skip the core POST, and core POST failure does not roll back OTel emission. The sidecar's existing fail-open posture on OTel is preserved; the new core POST inherits the same posture.

---

## 5. Wire shapes

### 5.1 Request body for `POST /verdicts/{verdict_id}/override`

JSON of the existing `OverrideEvent` dataclass shape. The sidecar already JSON-encodes this shape for OTel via `to_otel_attributes()`; the HTTP body is the same fields without the `gen_ai.override.` attribute prefix.

```json
{
  "decision_id": "dec_001",
  "service": "fraud-detect",
  "corrected_action": "approve",
  "original_action": "reject",
  "reviewer": "<sha256-hex when redacted, plaintext when policy allows>",
  "reason": "false positive on synthetic txn",
  "confidence_at_decision": 0.92,
  "source_system": "slack-adapter",
  "timestamp": "2026-05-20T10:33:00+00:00"
}
```

- `decision_id` is redundant with the path; the handler asserts they match and returns 400 with `decision_id_mismatch` if they don't.
- `reviewer` is **already in its final form** when the request arrives — hashed when sidecar policy requires it, plaintext only when policy explicitly allows. Core does no further redaction (see § 7).
- `timestamp` is the operator's override time, recorded on `outcome.override.at` per `apply_override_to_verdict` semantics.

### 5.2 Status-code mapping from `apply_override_to_verdict` to HTTP

| Function return / log code | HTTP | Sidecar `reason` |
|---|---|---|
| `Verdict` (applied or idempotent re-apply) | 200 | `ok` |
| None + `override_unmatched_decision_id` | 404 | `verdict_not_found` |
| None + `override_lost_race_to_concurrent_delete` | 404 | `verdict_not_found` |
| None + `override_conflicts_with_existing` | 409 | `validation_error` |
| None + `override_blocked_by_status` (terminal: confirmed / superseded / expired / partial / unknown future) | 422 | `validation_error` |
| None + `override_lost_race_to_concurrent_writer` (CAS miss) | 409 | `validation_error` |
| body parse / schema failure (missing required field, naive timestamp, etc.) | 422 | `validation_error` |
| uncaught internal exception in handler | 500 | `other` |
| any other HTTP status not in the table (e.g. 501, 502 returned to client) | — | `other` |
| `CoreAPIClient` transient retries exhausted, or true connection failure (`APIResult.status_code == 0`) | — | `core_unreachable` |
| `asyncio.TimeoutError` from sidecar's `wait_for` (>5s wall-clock at sidecar layer) | — | `core_timeout` |

"Transport-layer" rows describe what the sidecar observes — `core_unreachable` means the sidecar's `CoreAPIClient` could not complete a request to core (returned `status_code=0`), and `core_timeout` means the sidecar's own `asyncio.wait_for` fired before any response came back. A 5xx that core actually returned (e.g. 500 from an unhandled handler exception) is **not** `core_unreachable` — the sidecar reached core; core's handler errored. That maps to `other` so operators investigating the metric drill into logs rather than wrongly chasing a network problem.

The five None-paths collapse to two operator-facing reasons (`verdict_not_found` for "no record to bind to", `validation_error` for "record exists but binding can't be made"). Internal forensics remain available via the existing structured-log emissions in `nthlayer-common.overrides.ingestion` — no detail lost, just bounded for the metric and the operator's eyes.

#### Operator guidance for `validation_error` at HTTP 409

HTTP 409 with `reason="validation_error"` covers two distinct underlying causes that share the operator-facing reason code:

- `override_conflicts_with_existing` — the verdict is already overridden, and the proposed override conflicts with the existing one. Operator action: investigate the existing override; decide whether the conflict represents two correct independent operator decisions or one operator error.
- `override_lost_race_to_concurrent_writer` (CAS miss) — another writer landed an override on this verdict between the sidecar's read and write. Operator action: **fetch the verdict's current state via `GET /verdicts/{id}` before retrying**. If the existing override matches your intent, the work is already done; if not, decide whether to apply a fresh override.

Structured logs distinguish the two — the metric does not. This is deliberate: alarm fatigue from a blind-retry pattern on CAS misses is worse than the cost of looking at logs on the rare 409. Document this in the spec so operators don't reflex-retry.

### 5.3 Response envelope (sidecar)

The sidecar's existing response shapes (single, batch, webhook) gain a `bindings` field keyed by `decision_id`. Existing `accepted` / `rejected` / `duplicates` / `errors` fields are unchanged.

```json
{
  "accepted": ["dec_001", "dec_004"],
  "rejected": [],
  "duplicates": [],
  "errors": [],
  "bindings": {
    "dec_001": {"otel": "ok", "core": "ok"},
    "dec_004": {"otel": "ok", "core": "failed", "reason": "core_unreachable"}
  }
}
```

- `bindings` includes an entry only for accepted decision_ids (rejected / duplicate / error ids never bind).
- `otel` ∈ `{"ok", "failed"}`. `core` ∈ `{"ok", "failed"}`.
- `reason` is **core-specific**: present iff `core == "failed"`, omitted when `core == "ok"`. Values: `core_unreachable | verdict_not_found | validation_error | core_timeout | other`. OTel-emission failures do **not** populate `reason` — operators investigating OTel use the existing `override_collector_errors_total` counter and structured logs from the OTel SDK. Decoupling `reason` from OTel keeps the reason set well-typed and avoids a per-transport reason field on every binding.
- When the sidecar's `app.state.core_client` is absent (deployment misconfiguration), the `bindings` field is **omitted entirely** for that route's response — no per-decision entry is produced. Operators detect this state via the `nthlayer_override_binding_total{result="skipped", reason="no_client"}` counter and the `core_client_absent` WARNING log line, not via the response body. C7's absent-guard intentionally fails soft on the HTTP path so a misconfigured sidecar still accepts overrides for OTel emission; the missing `bindings` field is the visible signal.
- HTTP status of the sidecar's response is unchanged from today (201 on accepted single, 201 on batch with mixed outcomes). Partial binding failure does **not** alter the HTTP status — the body is the truth source. This preserves the existing client contract and aligns with the Option C selection during brainstorming.

---

## 6. Data flow

For each accepted override in a single, batch, or webhook payload:

```
sidecar
  ├─ validate + apply privacy (existing behaviour)
  │
  ├─ emit_override(event, privacy)  ─────►  OTel SDK ─► OTLP collector
  │      [if fail: log + increment override_collector_errors_total, continue regardless]
  │
  ├─ CoreAPIClient.apply_override(decision_id, payload)   # always attempted
  │      bind_result = await asyncio.wait_for(call, timeout=cfg.core.timeout_seconds)
  │
  ├─ build BindingResult(otel_status, core_status, reason)
  │
  ├─ increment nthlayer_override_binding_total{result, reason}
  │
  └─ append to response body's bindings map
```

OTel emission and core POST are **sequential but independent**: each runs to completion before the next; neither blocks the other in the success-or-fail sense. The sequencing (OTel first) is chosen because (a) OTel is the older, already-deployed path with an established fail-open contract, and (b) at expected scale the per-decision latency difference between sequential and concurrent is negligible while error-handling complexity drops materially.

### Batch behaviour

The existing canonical batch handler runs in two passes: dedup-pass identifies winners (last-in-array-wins on duplicate `decision_id`), emit-pass performs side effects per winner. The new core-binding step extends the emit-pass: per winner, run OTel emission then core POST, collect the per-id BindingResult into the response's `bindings` map. The existing cardinality invariant (response `accepted` set equals the set of emitted-span `gen_ai.override.decision_id` values) is preserved; a new invariant is added: `bindings.keys() == set(accepted)`.

---

## 7. Privacy locus

Privacy is applied **once, at the sidecar's entry**. Both downstream side effects (OTel emission, core POST) receive the same already-redacted payload.

| Stage | Reviewer field |
|---|---|
| Inbound HTTP body / webhook (before sidecar privacy) | plaintext |
| Sidecar applies privacy (existing) | SHA-256 hex when `hash_reviewer` policy applies; plaintext when policy explicitly opts in |
| OTel span attribute `gen_ai.override.reviewer` | as above |
| Core POST body `reviewer` field | as above (same payload) |
| `apply_override_to_verdict` invocation in core | `privacy=OverridePrivacyConfig(pre_redacted=True, exclude_reason=False)` — function does no further redaction |
| Stored `outcome.override.by` | as above |

The wire (sidecar → core) carries the same string the OTel collector receives. Core never holds the plaintext reviewer when policy prohibits it; the sidecar is the single privacy boundary.

### `OverridePrivacyConfig.pre_redacted` (new)

Add a new flag to the existing dataclass in `nthlayer-common/src/nthlayer_common/overrides/models.py`:

```python
@dataclass
class OverridePrivacyConfig:
    """Privacy policy for override processing.

    Attributes:
        pre_redacted: trust the wire; no further redaction. Set this when
            the caller (e.g. nthlayer-override-adapter) has already applied
            privacy policy at its boundary and the values arriving here are
            already in their final form.
        plaintext_reviewer: alias for pre_redacted. DEPRECATED — use
            pre_redacted instead. Will be removed in v2. Both flags trigger
            the same code path in _build_override.
        exclude_reason: drop the reason field from the resulting Override.
            Independent of pre_redacted (a pre-redacted payload may still
            have a reason that the caller decided to keep).
    """
    pre_redacted: bool = False
    plaintext_reviewer: bool = False  # deprecated alias for pre_redacted
    exclude_reason: bool = False
```

`_build_override` treats `pre_redacted or plaintext_reviewer` as the trust-the-wire predicate. No behavioural change for existing callers. New callers use `pre_redacted=True`.

---

## 8. Component-level changes

### 8.1 nthlayer-core

`server.py` gains a new handler parallel to `post_verdict_outcome`:

```python
async def post_verdict_override(request: Request) -> JSONResponse:
    """Apply an operator override to a verdict (mutation-style).

    Calls apply_override_to_verdict on the verdict store, mutating the
    original verdict's outcome in place. Distinct from POST /outcome which
    creates an outcome_resolution child verdict (lineage-style).
    """
    verdict_id = request.path_params["verdict_id"]
    body, err = await _parse_json_body(request)
    if err:
        return err

    # Construct OverrideEvent; 422 on schema failure
    try:
        event = OverrideEvent(**body)
    except (TypeError, ValueError) as exc:
        return JSONResponse(
            {"error": "validation_error", "detail": str(exc)},
            status_code=422,
        )

    if event.decision_id != verdict_id:
        return JSONResponse(
            {"error": "decision_id_mismatch",
             "detail": {"path": verdict_id, "body": event.decision_id}},
            status_code=400,
        )

    store = _get_store()
    privacy = OverridePrivacyConfig(pre_redacted=True, exclude_reason=False)
    result = apply_override_to_verdict(store, event, privacy=privacy)

    if result is not None:
        return JSONResponse({"id": verdict_id, "status": "overridden"}, status_code=200)

    # None path: map structured log code → HTTP status.
    # The function logged a single structured warning identifying the cause;
    # the handler returns a generic mapping. Per § 5.2.
    verdict = store.get_verdict(verdict_id)
    if verdict is None:
        return JSONResponse({"error": "verdict_not_found"}, status_code=404)

    status = (verdict.get("outcome_status") or "").lower()
    if status == "overridden":
        # Either conflict_with_existing or CAS race won by another writer.
        return JSONResponse({"error": "conflict"}, status_code=409)
    # Terminal non-pending status (confirmed/superseded/expired/partial/unknown).
    return JSONResponse({"error": "validation_error"}, status_code=422)
```

Route registration in the existing `Mount`/`Route` list:

```python
Route("/verdicts/{verdict_id}/override", post_verdict_override, methods=["POST"]),
```

Note: the handler's status-derivation pattern (read verdict again to map None to HTTP status) is intentionally simple. The alternative — extending `apply_override_to_verdict` to return a structured result instead of `Verdict | None` — is a bigger change to a stable, already-tested function. Filed as a possible future refactor if a third caller appears; for v1.5 the one extra read keeps the function's contract narrow.

### 8.2 nthlayer-common

**`api_client.py` — `CoreAPIClient.apply_override`:**

```python
async def apply_override(
    self,
    verdict_id: str,
    payload: dict,
) -> APIResult:
    """Apply an operator override to a verdict.

    Calls POST /verdicts/{verdict_id}/override on the core API.

    Status code mapping (interpret via result.status_code, not result.ok):
        200 — applied (including idempotent re-apply)
        404 — verdict_not_found (no record or concurrent delete)
        409 — validation_error (conflict_with_existing OR CAS miss)
        422 — validation_error (terminal status block or schema failure)
        0   — connection failed (transport layer; result.error populated)

    Does not raise; check result.ok and result.status_code.
    """
    return await self._request("POST", f"/verdicts/{verdict_id}/override", json=payload)
```

Adds one new method alongside the existing `submit_verdict` / `resolve_outcome` / etc. surface. No new dependencies. Transport-layer retries / connection-error reset / 4xx-immediate-return semantics inherited from the base `_request` helper.

**`overrides/models.py` — `OverridePrivacyConfig.pre_redacted`:** per § 7.

**`overrides/ingestion.py`:** no functional change. The `_build_override` helper already reads `privacy.plaintext_reviewer`; adding `or privacy.pre_redacted` to that predicate is the entire change. One small test added (see § 9).

### 8.3 nthlayer-override-adapter

**Config (`override-adapter-config.yaml`):**

```yaml
core:
  url: http://core:8000   # required; no default
  timeout_seconds: 5.0    # default 5.0; sidecar enforces via asyncio.wait_for
```

`config.py` gains a `CoreConfig` dataclass and validates `core.url` as a required string (raises `ConfigError` on missing, matching the existing pattern). `timeout_seconds` defaults to 5.0 with the same int/float guard used for `batch.max_size`.

**`emission.py` (renamed concept; same file):** gains a `bind_to_core(event, decision_id) -> BindingResult` helper invoked after `emit_override`:

```python
async def bind_to_core(
    client: CoreAPIClient,
    event: OverrideEvent,
    timeout_seconds: float,
) -> BindingResult:
    payload = event.to_dict()   # new helper on OverrideEvent — see below
    try:
        result = await asyncio.wait_for(
            client.apply_override(event.decision_id, payload),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        BINDING_TOTAL.labels(result="failed", reason="core_timeout").inc()
        return BindingResult(core="failed", reason="core_timeout")

    # Map HTTP status to bounded reason set.
    reason = _MAP_STATUS_TO_REASON.get(result.status_code, "other")
    if result.ok:
        BINDING_TOTAL.labels(result="success", reason="ok").inc()
        return BindingResult(core="ok", reason="ok")
    BINDING_TOTAL.labels(result="failed", reason=reason).inc()
    return BindingResult(core="failed", reason=reason)


_MAP_STATUS_TO_REASON = {
    200: "ok",
    404: "verdict_not_found",
    409: "validation_error",
    422: "validation_error",
    0:   "core_unreachable",
}
```

Lookup dict over branching per the no-regex/no-conditional convention. Unknown status codes fall through to `"other"`.

**`OverrideEvent.to_dict()` helper:** add to `nthlayer-common/src/nthlayer_common/overrides/models.py`. Returns the canonical JSON-serializable dict (timestamp → ISO 8601 string with offset, None fields dropped). Sidecar uses it for the core POST body; existing `to_otel_attributes()` keeps the `gen_ai.override.*` prefix and stays distinct.

**`routes/canonical.py` and `routes/webhook.py`:** the existing emit-paths gain a call to `bind_to_core` per winner. The response builders (`accepted_single`, `build_batch_response`) accept a `bindings: dict[str, BindingResult]` and inject it into the response dict. `BatchResult.errors` (reserved per CLAUDE.md) remains unpopulated by this design; the per-id binding state lives in the new `bindings` field, not `errors`.

**`app.py`:** the app factory instantiates a single `CoreAPIClient(base_url=cfg.core.url)` at startup and shares it across requests (matches the existing single OTel-provider pattern). `atexit` hook closes the client alongside the existing OTel `force_flush + shutdown`.

**`metrics.py`:** new Counter `nthlayer_override_binding_total` with labels `result ∈ {success, failed, skipped}` and `reason ∈ {ok, core_unreachable, verdict_not_found, validation_error, core_timeout, other, no_client}`. 13-series max cardinality per process (12 from success/failed × reasons + 1 from `skipped/no_client`; the `skipped` path fires only when the absent-guard catches a missing `core_client` on `app.state` — diagnostic signal for misconfigured deployments).

---

## 9. Operator alert recipe

Document in the spec (and ideally as a starter alert rule in `nthlayer/demo/`):

```promql
# Alert: high override binding failure rate (broken down by reason)
sum(rate(nthlayer_override_binding_total{result="failed"}[5m])) by (reason)
/
sum(rate(nthlayer_override_binding_total[5m])) > 0.01
```

The `by (reason)` aggregation means the alert payload shows which failure mode is contributing most. Operators see "core_unreachable spike at 3am" rather than just "binding failures spiked at 3am." 1% over 5m is a reasonable starting threshold; operators tune per deployment.

---

## 10. Testing

### nthlayer-override-adapter (`tests/`)

- **Happy path single**: POST with mocked CoreAPIClient returning 200 → response has `bindings: {"d": {"otel": "ok", "core": "ok"}}`; counter incremented with `result=success, reason=ok`.
- **Happy path batch**: 3-entry batch (1 unique, 1 duplicate-of-first, 1 unique) → 2 accepted, 2 bindings; `bindings.keys() == set(accepted)` invariant holds.
- **Core unreachable**: mock CoreAPIClient returns `APIResult(ok=False, status_code=0, error="connection_failed")` → `core: "failed", reason: "core_unreachable"`; counter labelled accordingly.
- **Core 404**: mock returns 404 → `reason: "verdict_not_found"`.
- **Core 409**: mock returns 409 → `reason: "validation_error"`.
- **Core 422**: mock returns 422 → `reason: "validation_error"`.
- **Core timeout**: mock raises `asyncio.TimeoutError` on `wait_for` → `reason: "core_timeout"`.
- **OTel-fails-core-still-runs**: collector raises during emit; `override_collector_errors_total` is incremented (existing behaviour); core POST still attempted; response carries `{"otel": "failed", "core": "ok"}` with no `reason` field (per § 5.3, `reason` is core-specific and omitted when `core == "ok"`).
- **Config validation**: missing `core.url` raises `ConfigError`; non-string `core.url` raises `ConfigError`; `core.timeout_seconds` non-positive raises `ConfigError`.

### nthlayer-core (`tests/test_api_overrides.py` — new file)

- Happy path: POST with body matching a pre-seeded pending verdict → 200; verdict's `outcome.status == "overridden"` on subsequent GET.
- Idempotent re-apply: same body twice → both return 200; verdict state unchanged on second apply.
- `verdict_not_found`: POST against unknown id → 404.
- `override_conflicts_with_existing`: POST against an already-overridden verdict with a different reviewer → 409.
- `override_blocked_by_status`: POST against a verdict with `outcome.status="confirmed"` → 422.
- `decision_id_mismatch`: path id ≠ body decision_id → 400.
- Schema failure: body missing required `corrected_action` → 422.

### nthlayer-common (`tests/test_overrides.py`)

- `pre_redacted=True` produces an `Override` with the wire reviewer string unchanged (no `hash_reviewer` re-application).
- `plaintext_reviewer=True` (the deprecated alias) produces identical behaviour to `pre_redacted=True`.
- Setting both flags together produces identical behaviour to either alone (no surprising interaction).

### Integration smoke (`nthlayer/test/`)

- Real sidecar + real core via TestClient: POST sidecar `/api/v1/overrides` with a decision_id matching a pre-seeded verdict → assert (a) `nthlayer_override_binding_total{result=success}` incremented, (b) GET `/verdicts/{id}` on core shows `outcome.status="overridden"` with populated `outcome.override`, (c) sidecar response carries `bindings.{id}.core == "ok"`.

---

## 11. References

- Bead: `opensrm-jmy.18` (verdict-binding path for overrides: sidecar→core direct POST). Reframed 2026-05-19.
- Follow-up bead: `opensrm-jmy.19` (bench post_incident mutation-style attribution).
- Predecessor design: `nthlayer/docs/superpowers/specs/2026-05-15-jmy7-override-adapter-sidecar-design.md`.
- Spec source: `nthlayer/docs/roadmap/NTHLAYER_MISSING_CAPABILITIES_SPEC.md` § 4 steps 1-2.
- Foundation function: `nthlayer-common/src/nthlayer_common/overrides/ingestion.py::apply_override_to_verdict`.
- Existing client surface: `nthlayer-common/src/nthlayer_common/api_client.py::CoreAPIClient`.
- Existing endpoint sibling: `nthlayer-core/src/nthlayer_core/server.py::post_verdict_outcome` (lineage-style; unchanged by this design).
