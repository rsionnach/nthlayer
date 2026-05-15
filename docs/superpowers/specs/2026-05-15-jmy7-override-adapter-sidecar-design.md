# Override Adapter Sidecar Design (opensrm-jmy.7)

**Status:** Approved for implementation (Wave A only). Slack adapter and OTel consumer scoped to follow-ups (opensrm-jmy.17, opensrm-jmy.18).

**Spec source:** `nthlayer/docs/roadmap/NTHLAYER_MISSING_CAPABILITIES_SPEC.md` § 4.

**Foundation:** `nthlayer-common/src/nthlayer_common/overrides/` (jmy.4 + jmy.11) — `OverrideEvent`, `OverridePrivacyConfig`, `map_webhook_to_override`, `apply_override_to_verdict`, `hash_reviewer`.

---

## 1. Scope

### In scope (Wave A)

Spec § 4 test scenarios:

- **Scenario 2** — Override via adapter webhook: HTTP POST → OTel emission.
- **Scenario 3** — Batch import of 100 overrides processed in order.
- **Scenario 4** — Batch with duplicate `decision_id`: last-in-array wins, duplicates reported.

Plus the generic-webhook source adapter (configurable field-mapper, reuses `map_webhook_to_override` from nthlayer-common — already platform-generic, not Jira-specific).

### Out of scope (filed as follow-ups)

- **Slack adapter** — `opensrm-jmy.17` (signing-secret verification, event subscription model, slash-command handling).
- **OTel `gen_ai.override` consumer in nthlayer-workers/measure** — `opensrm-jmy.18` (verdict-binding side: call `apply_override_to_verdict` per event, per spec § 4 step 1-2).
- **Unmatched-override buffer** — belongs in the consumer (jmy.18), not the adapter. The adapter has no view of verdicts and always emits.
- **Auth / rate-limiting / body-size limits on the HTTP endpoints** — matches nthlayer-core posture in v1.5 (deferred to v2). File a follow-up if a deployment needs it sooner.

### Capability boundary (honest framing for external comms)

> In v1.5, override events propagate to **judgment SLO calibration metrics** via the reversal-rate path (sidecar → OTel collector → `gen_ai_overrides_total` → `nthlayer-workers/measure` PromQL). **Verdict-level binding** — knowing which specific verdicts were overridden — lands in jmy.18 and is required for retrospectives to claim "this was overridden by operator."

The v1.5 demo's reversal-rate narrative is fully delivered by Wave A; demo does not depend on jmy.18.

---

## 2. Architecture

### Home

New top-level sibling repo: `nthlayer-override-adapter/`.

- Own `pyproject.toml` + `uv.lock`
- Own release-please config (`release-please-config.json` + manifest), Conventional Commits taxonomy matching nthlayer-workers
- Own `Dockerfile` (python:3.11-slim base; mirrors core/workers/bench)
- Own `.github/workflows/test.yml` + `release.yml` (Docker smoke gate before PyPI publish)
- Console script: `nthlayer-override-adapter serve [--config <path>] [--host <h>] [--port <p>]`

Rationale: matches the existing per-tier shape (core/workers/bench/common are each their own repo, separately versioned and deployable). Sidecar is operationally distinct from `nthlayer-workers` (HTTP server, not a polling worker) and embedding it in workers would blur that boundary.

### Dependency posture

- `nthlayer-common>=...` (editable local path in dev, pinned in releases) — for `OverrideEvent`, `OverridePrivacyConfig`, `map_webhook_to_override`, `hash_reviewer`, `nthlayer_common.metrics`, `nthlayer_common.errors`.
- `starlette>=0.40`, `uvicorn>=0.30` — ASGI stack, matches `nthlayer-core/server.py` and `nthlayer-workers/respond/server.py`. Pure-async.
- `opentelemetry-api>=1.28`, `opentelemetry-sdk>=1.28`, `opentelemetry-exporter-otlp>=1.28` — OTel emission.
- `pyyaml>=6.0` — config loading.
- `structlog>=24.1.0` — logging.
- Dev: `pytest>=8.2`, `pytest-asyncio>=0.23`, `httpx>=0.27` (for Starlette `TestClient`), `opentelemetry-sdk[test]` for `InMemorySpanExporter`.

### Module layout (proposed)

```
nthlayer-override-adapter/
  pyproject.toml
  uv.lock
  release-please-config.json
  .release-please-manifest.json
  Dockerfile
  README.md
  CLAUDE.md
  .github/
    workflows/{test.yml, release.yml, dependabot-automerge.yml}
    dependabot.yml
  src/nthlayer_override_adapter/
    __init__.py
    cli.py              # `serve` entrypoint; reads config, builds app, runs uvicorn
    config.py           # AdapterConfig dataclass + load_config()
    app.py              # build_app(config) -> Starlette — registers routes per config
    routes/
      canonical.py      # POST /api/v1/overrides, POST /api/v1/overrides/batch
      webhook.py        # POST /webhook/{source} — dynamically registered per YAML adapter
    emission.py         # emit_override(event) — unparented gen_ai.override span
    response.py         # AcceptResponse, BatchResponse helpers (decision_id-shaped lists)
    metrics.py          # adapter-specific Prometheus counters (override_requests_total, ...)
  tests/
    test_routes_canonical.py
    test_routes_batch.py
    test_routes_webhook.py
    test_emission.py
    test_config.py
    test_cli.py
    smoke/
      __init__.py
      test_imports.py
      test_cli.py
```

---

## 3. HTTP API

Starlette routes; canonical endpoints exactly per spec § 4.

### 3.1 `POST /api/v1/overrides`

Body: canonical `OverrideEvent` JSON (decision_id, service, corrected_action, reviewer required; original_action, reason, confidence_at_decision, source_system, timestamp optional). `__post_init__` validation in `OverrideEvent` runs at construction — invalid input → `400` with `{detail: <message>}`.

Success: `201 Created`, body `{"decision_id": "<id>", "emitted_to_otel": true}`.

### 3.2 `POST /api/v1/overrides/batch`

Body: `{"overrides": [<OverrideEvent JSON>, ...]}`.

Processing: iterate in array order. For each entry:
- If JSON shape invalid → record in `rejected` with index + reason; continue.
- If `decision_id` already seen in this batch at an earlier index → record the earlier index in `duplicates[].discarded_indices`; the current entry overwrites the prior (last-in-array-wins per spec).
- Otherwise → emit OTel span; record `decision_id` in `accepted`.

Response (success — always `200 OK`, even with partial failures, since this is a bulk operation):

```json
{
  "accepted": ["dec_001", "dec_004", "dec_007"],
  "rejected": [{"index": 3, "reason": "missing field 'severity'"}],
  "duplicates": [
    {"decision_id": "dec_002", "applied_at_index": 5, "discarded_indices": [1, 3]}
  ],
  "errors": []
}
```

`errors` is reserved for non-input failures (e.g., OTel emission failed for a specific span); empty in the happy path.

Operators see exactly which decision_ids were collapsed and at which indices, so submission can be reconciled against emitted state.

### 3.3 `POST /webhook/{source}`

Dynamically registered per YAML adapter entry (see § 5). Body shape is whatever the source system sends (e.g., a Jira webhook payload). Sidecar runs `map_webhook_to_override(payload, adapter.field_mapping, defaults=adapter.defaults)` then emits OTel.

Success: `201 Created`, body `{"decision_id": "<id>", "emitted_to_otel": true}`. Mapper raising `ValueError` (missing required path / unparseable confidence / naive timestamp) → `400` with the error message.

### 3.4 `GET /healthz` and `GET /metrics`

Standard liveness + Prometheus metrics endpoints, matching nthlayer-core conventions.

---

## 4. OTel emission

Each accepted override emits **one unparented span** named `gen_ai.override`. Attributes from `OverrideEvent.to_otel_attributes()` — the spec § 4 canonical `gen_ai.override.*` shape, None-valued fields dropped.

### Rationale for unparented spans

`gen_ai.override` events are emitted as unparented spans (no trace_id continuity). This is deliberate: overrides represent operator decisions that aren't bound to any specific service trace. Treating them as standalone spans rather than children of an arbitrary trace preserves the semantic that "an override is its own thing." Downstream collectors route span → metric via the `spanmetricsconnector` following standard OTel patterns.

Pin this in the doc to prevent future contributors from "fixing" the unparented span thinking it's a bug.

### Emission failure handling

OTel exporter failures are logged via `structlog` and counted in `override_collector_errors_total`. The HTTP request still returns `201` (the override is "accepted" by the adapter even if export is degraded) — exporter retry/buffering is OTel SDK's job, not the adapter's. This matches the fail-open posture established for `GovernanceBridgeEmitter`.

Alternative considered: return `503` on emission failure. Rejected: forces the client to retry on transient collector unreachability, multiplying the duplicate-decision_id case unnecessarily. Fail-open is consistent with how the rest of the ecosystem handles downstream-collector outages.

---

## 5. Configuration

`override-adapter-config.yaml` (path passed via `--config` or `NTHLAYER_OVERRIDE_ADAPTER_CONFIG`):

```yaml
adapters:
  - source: jira
    webhook_path: /webhook/jira
    field_mapping:
      decision_id: "issue.customfield_10042"
      corrected_action: "issue.resolution.name"
      reviewer: "issue.assignee.emailAddress"
      timestamp: "issue.updated"
      reason: "issue.resolution.description"
    defaults:
      source_system: jira

privacy:
  plaintext_reviewer: false   # Default: false (hashed)
  exclude_reason: false        # Default: false (stored)

otel:
  exporter: otlp
  endpoint: "http://localhost:4317"   # OTel collector OTLP gRPC endpoint
  # Standard OTEL_* env vars also honoured per OTel SDK conventions
```

`AdapterConfig` dataclass:

```python
@dataclass
class WebhookAdapter:
    source: str
    webhook_path: str
    field_mapping: dict[str, str]
    defaults: dict[str, Any] = field(default_factory=dict)

@dataclass
class AdapterConfig:
    adapters: list[WebhookAdapter]
    privacy: OverridePrivacyConfig
    otel_endpoint: str | None = None
```

Empty `adapters:` list is legal (canonical `/api/v1/overrides` endpoints still register).

---

## 6. Privacy

Privacy is applied at the **sidecar emission boundary**, not the consumer side.

Rationale: once the event hits the OTel collector / exporter pipeline, the payload is observable by anything downstream. Hashing at the consumer (jmy.18) is too late — the plaintext reviewer would already be in the OTel backend. The sidecar is the right place to apply the spec § 4 privacy posture, consistent with "the adapter's job is translation" (translation includes privacy translation).

Concretely, before calling `to_otel_attributes()`:

- If `privacy.plaintext_reviewer == False` (default): replace `event.reviewer` with `hash_reviewer(event.reviewer)`.
- If `privacy.exclude_reason == True`: set `event.reason = None` (drops from OTel attributes via the existing None-drop in `to_otel_attributes`).

The sidecar does not mutate the inbound JSON or response body — only the OTel-emitted form. The response can echo the original `decision_id` since that's identifier, not PII.

---

## 7. Test strategy

### Unit tests (in-process, Starlette `TestClient`)

For each spec § 4 scenario in scope (2, 3, 4), assert on:

1. **Response JSON shape and content** — `accepted` / `rejected` / `duplicates` lists with the right decision_ids and indices.
2. **OTel emission via `InMemorySpanExporter`** — captured spans have the canonical `gen_ai.override.*` attributes, with privacy correctly applied (hashed reviewer by default).
3. **Cardinality-match invariant** — explicit assertion that "what the response claims" matches "what OTel shows":
   - If response says 3 accepted, there are 3 spans.
   - If 2 inputs duplicate each other (same decision_id), only 1 span emitted for that decision_id (last-in-array's attributes).
   - Total spans == count of unique accepted decision_ids.

The cardinality assertion catches the silent-divergence regression class where per-scenario tests pass but response counts and emission cardinality drift.

### Integration test

Defer to `nthlayer/test/`: spin up the sidecar process, send real HTTP, verify OTel events reach a test collector (a real `otel/opentelemetry-collector` container with a file exporter, asserted from disk). Not in MVP scope for jmy.7; file as a small follow-up if useful.

### Test pattern note (for future testing.md addition)

The pattern established here — real Starlette + `InMemorySpanExporter` + behavioural assertions on captured artefacts — is the right OTel testing default. Add to `nthlayer/docs/testing.md` backlog (after v1.5 ships) so the pattern is codified for future OTel-emitting code. Not in jmy.7 scope to keep this bead tight.

---

## 8. Self-observability

Prometheus metrics, following `nthlayer_common.metrics` conventions:

- `override_requests_total{endpoint, status}` — Counter; endpoint in {`canonical`, `batch`, `webhook`}, status in {`accepted`, `rejected`, `duplicate`}.
- `override_emission_total{result}` — Counter; result in {`emitted`, `failed`}.
- `override_validation_errors_total{reason}` — Counter; reason from `OverrideEvent.__post_init__` / `map_webhook_to_override` error messages, normalised to a small label set (avoid high-cardinality reviewer strings in labels).
- `override_emit_duration_seconds` — Histogram; emission latency (HTTP receipt → span emitted).
- `override_collector_errors_total` — Counter; OTel exporter failures.

`/metrics` exposes via `render_metrics()` / `metrics_content_type()` from `nthlayer_common.metrics`.

---

## 9. Acceptance criteria

1. **Repo bootstrapped** — `nthlayer-override-adapter/` exists with pyproject.toml, uv.lock, Dockerfile, release-please config, CI workflows mirroring nthlayer-workers' shape.
2. **Endpoints work end-to-end** — `POST /api/v1/overrides`, `POST /api/v1/overrides/batch`, `POST /webhook/<source>` all emit `gen_ai.override` OTel spans with the canonical attribute set; privacy hashing applied by default.
3. **Spec § 4 scenarios 2, 3, 4 pass** — unit tests assert response shape, span attributes, and cardinality-match invariant.
4. **R5 review clean** — Correctness / Clarity / Edge Cases / Excellence passes via `/r5-supervise opensrm-jmy.7`.
5. **Live verification** — after R5, run the sidecar locally with a real OTel collector, post a canonical override, confirm the span lands. Standing rule from 2026-05-15 handoff: data-flow / pagination / sentinel changes get a live-stack check before claiming convergence.
6. **CLAUDE.md updated** — `nthlayer-override-adapter/CLAUDE.md` documents module layout, dependencies, conventions. Cross-link from `nthlayer-ecosystem/CLAUDE.md` member table + `nthlayer/CLAUDE.md` ecosystem hub.

---

## 10. Open questions / decisions deferred

- **Auth on HTTP endpoints** — none in v1.5, matching core. File a follow-up bead if needed for a real deployment.
- **`override-adapter-config.yaml` reload** — static at startup in MVP. Live reload (SIGHUP / config watcher) deferred.
- **Multi-instance HA** — single-instance contract in v1.5, matches `RespondModule`. Sidecar is stateless except for the OTel SDK's in-memory export buffer; running multiple replicas behind a load balancer is operationally safe but not part of MVP acceptance.
- **OTel events API vs spans** — chose spans (named `gen_ai.override`) over the OTel Events API. Spans are universally supported by exporters today; the Events API is still stabilising. Revisit at v2.

---

## 11. References

- Spec § 4 — `nthlayer/docs/roadmap/NTHLAYER_MISSING_CAPABILITIES_SPEC.md`
- Foundation library — `nthlayer-common/src/nthlayer_common/overrides/{models.py, ingestion.py}`
- Parent bead — `opensrm-jmy.7`
- Follow-ups — `opensrm-jmy.17` (Slack), `opensrm-jmy.18` (OTel consumer in measure)
- Discipline note — `MEMORY.md` entry on live-verify after data-flow / sentinel / pagination R5 fixes (2026-05-15)
