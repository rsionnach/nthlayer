# jmy.18 Override Verdict-Binding Path — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire a direct sidecar→core HTTP POST path so operator overrides emitted via `nthlayer-override-adapter` mutate the canonical verdict store, alongside the existing OTel observability emission.

**Architecture:** Three-repo change, sequenced bottom-up so each layer's dependencies are landed before the layer above. `nthlayer-common` gains a privacy-config flag, a wire helper on `OverrideEvent`, and a new `CoreAPIClient` method. `nthlayer-core` gains a new HTTP handler that calls the existing `apply_override_to_verdict` with `pre_redacted=True`. `nthlayer-override-adapter` gains a `CoreConfig` block, a `bind_to_core` helper invoked per accepted decision, a bounded Prometheus metric, and a per-decision `bindings` field in the response envelope. OTel emission and core POST run sequentially but independently per accepted decision; failures are reported in the response body without changing the HTTP status code.

**Tech Stack:** Python 3.11+ across all three repos. `uv` for env management. `pytest` + `pytest-asyncio` for tests. `httpx` (via `nthlayer-common.api_client.CoreAPIClient`) for the sidecar→core transport. `starlette` for `nthlayer-core` and the sidecar's HTTP surface. `prometheus-client` for the new counter.

**Spec:** `nthlayer/docs/superpowers/specs/2026-05-20-jmy18-override-verdict-binding-design.md` (committed `f2f3874`).

**Bead:** `opensrm-jmy.18`. Follow-up `opensrm-jmy.19` (bench post_incident mutation-style attribution) is **not** in this plan.

---

## File structure

### Files modified

| Repo | Path | Responsibility |
|---|---|---|
| nthlayer-common | `src/nthlayer_common/overrides/models.py` | `OverridePrivacyConfig.pre_redacted` flag; `OverrideEvent.to_dict()` helper |
| nthlayer-common | `src/nthlayer_common/overrides/ingestion.py` | `_build_override` predicate extended to `plaintext_reviewer or pre_redacted` |
| nthlayer-common | `src/nthlayer_common/api_client.py` | `CoreAPIClient.apply_override(verdict_id, payload) -> APIResult` |
| nthlayer-common | `tests/test_overrides.py` | New tests for `pre_redacted`, alias behaviour, `to_dict` |
| nthlayer-common | `tests/test_api_client.py` | New tests for `apply_override` happy path + status mapping |
| nthlayer-core | `src/nthlayer_core/server.py` | New `post_verdict_override` handler + route registration |
| nthlayer-core | `tests/test_api_overrides.py` (new file) | End-to-end handler tests covering all status codes |
| nthlayer-override-adapter | `src/nthlayer_override_adapter/config.py` | `CoreConfig` dataclass; `AdapterConfig.core` field; `load_config` parses `core:` YAML block |
| nthlayer-override-adapter | `src/nthlayer_override_adapter/metrics.py` | New `binding_total` Counter |
| nthlayer-override-adapter | `src/nthlayer_override_adapter/response.py` | `BindingResult` dataclass; `bindings` field on response helpers |
| nthlayer-override-adapter | `src/nthlayer_override_adapter/emission.py` | New `bind_to_core(client, event, timeout)` helper |
| nthlayer-override-adapter | `src/nthlayer_override_adapter/app.py` | Instantiate `CoreAPIClient` at startup; close via atexit |
| nthlayer-override-adapter | `src/nthlayer_override_adapter/routes/canonical.py` | Invoke `bind_to_core` per winner in single + batch |
| nthlayer-override-adapter | `src/nthlayer_override_adapter/routes/webhook.py` | Invoke `bind_to_core` per accepted decision |
| nthlayer-override-adapter | `tests/test_config.py` | New tests for `core` block parsing + validation |
| nthlayer-override-adapter | `tests/test_metrics.py` | Assert `binding_total` shape + labels |
| nthlayer-override-adapter | `tests/test_emission.py` | New tests for `bind_to_core` status mapping |
| nthlayer-override-adapter | `tests/test_routes_canonical.py` | Per-id `bindings` in single response |
| nthlayer-override-adapter | `tests/test_routes_canonical_batch.py` | Per-id `bindings` invariant in batch |
| nthlayer-override-adapter | `tests/test_routes_webhook.py` | Per-id `bindings` in webhook response |
| nthlayer | `test/test_jmy18_smoke.py` (new file) | Cross-process smoke: real sidecar + real core via TestClient |

### Files NOT modified

- `nthlayer-common/src/nthlayer_common/overrides/ingestion.py::apply_override_to_verdict` — function body is unchanged; only the predicate inside `_build_override` widens.
- `nthlayer-core/src/nthlayer_core/server.py::post_verdict_outcome` — the lineage-style handler stays exactly as-is.
- All `nthlayer-bench` and `nthlayer-workers` code — they read `outcome.override` already; jmy.18's writers light up the existing readers without code changes there. (jmy.19 is the separate follow-up for bench parity.)

---

## Phase A — nthlayer-common (foundation)

### Task A1: Add `pre_redacted` flag to `OverridePrivacyConfig`

**Files:**
- Modify: `nthlayer-common/src/nthlayer_common/overrides/models.py`
- Modify: `nthlayer-common/src/nthlayer_common/overrides/ingestion.py`
- Test: `nthlayer-common/tests/test_overrides.py`

- [ ] **Step 1: Write the failing test**

Add to `nthlayer-common/tests/test_overrides.py` at the bottom of `TestPrivacy` (or in a new class — the file already has `TestPrivacy`):

```python
class TestPreRedactedFlag:
    """opensrm-jmy.18: pre_redacted flag with plaintext_reviewer as deprecated alias."""

    def test_pre_redacted_true_skips_reviewer_hashing(self) -> None:
        event = OverrideEvent(
            decision_id="dec-1",
            service="fraud-detect",
            corrected_action="approve",
            reviewer="already-hashed-hex",
        )
        privacy = OverridePrivacyConfig(pre_redacted=True)
        store = MemoryStore()
        store.put(_make_pending_verdict("dec-1"))

        result = apply_override_to_verdict(store, event, privacy=privacy)

        assert result is not None
        assert result.outcome.override.by == "already-hashed-hex"

    def test_plaintext_reviewer_remains_an_alias(self) -> None:
        event = OverrideEvent(
            decision_id="dec-2",
            service="fraud-detect",
            corrected_action="approve",
            reviewer="already-hashed-hex",
        )
        store_a = MemoryStore()
        store_a.put(_make_pending_verdict("dec-2"))
        store_b = MemoryStore()
        store_b.put(_make_pending_verdict("dec-2"))

        r_pre = apply_override_to_verdict(
            store_a, event, privacy=OverridePrivacyConfig(pre_redacted=True),
        )
        r_plain = apply_override_to_verdict(
            store_b, event, privacy=OverridePrivacyConfig(plaintext_reviewer=True),
        )

        assert r_pre is not None and r_plain is not None
        assert r_pre.outcome.override.by == r_plain.outcome.override.by == "already-hashed-hex"

    def test_both_flags_set_together_behaves_identically(self) -> None:
        event = OverrideEvent(
            decision_id="dec-3",
            service="fraud-detect",
            corrected_action="approve",
            reviewer="already-hashed-hex",
        )
        store = MemoryStore()
        store.put(_make_pending_verdict("dec-3"))

        result = apply_override_to_verdict(
            store, event,
            privacy=OverridePrivacyConfig(pre_redacted=True, plaintext_reviewer=True),
        )

        assert result is not None
        assert result.outcome.override.by == "already-hashed-hex"
```

If the existing tests don't have a `_make_pending_verdict` helper, copy the verdict-construction pattern from the existing `TestApplyOverride` class (look at the first test in that class for the helper).

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-common
uv run pytest tests/test_overrides.py::TestPreRedactedFlag -v
```

Expected: 3 FAILED with `TypeError: __init__() got an unexpected keyword argument 'pre_redacted'`.

- [ ] **Step 3: Add the field + update `_build_override` predicate**

In `src/nthlayer_common/overrides/models.py`, find the existing `OverridePrivacyConfig` dataclass (the file already has `OverridePrivacyConfig(plaintext_reviewer=False, exclude_reason=False)` per the module docstring). Update its docstring and add the new field:

```python
@dataclass
class OverridePrivacyConfig:
    """Privacy policy for override processing.

    Attributes:
        pre_redacted: trust the wire; no further redaction. Set this when
            the caller (e.g. nthlayer-override-adapter) has already applied
            privacy policy at its boundary and the values arriving here are
            already in their final form. opensrm-jmy.18.
        plaintext_reviewer: alias for pre_redacted. DEPRECATED — use
            pre_redacted instead. Will be removed in v2. Both flags trigger
            the same code path in nthlayer_common.overrides.ingestion._build_override.
        exclude_reason: drop the reason field from the resulting Override.
            Independent of pre_redacted (a pre-redacted payload may still
            have a reason that the caller decided to keep).
    """
    pre_redacted: bool = False
    plaintext_reviewer: bool = False  # deprecated alias for pre_redacted
    exclude_reason: bool = False
```

In `src/nthlayer_common/overrides/ingestion.py`, find `_build_override` (around line 32). Update the reviewer assignment:

```python
def _build_override(
    event: OverrideEvent, privacy: OverridePrivacyConfig,
) -> Override:
    trust_wire = privacy.plaintext_reviewer or privacy.pre_redacted
    reviewer = event.reviewer if trust_wire else hash_reviewer(event.reviewer)
    return Override(
        by=reviewer,
        at=event.timestamp,
        action=event.corrected_action,
        reasoning=None if privacy.exclude_reason else event.reason,
        original_action=event.original_action,
        confidence_at_decision=event.confidence_at_decision,
        source_system=event.source_system,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_overrides.py::TestPreRedactedFlag -v
```

Expected: 3 PASSED.

Also run the existing `TestPrivacy` class to confirm no regression on the alias:

```bash
uv run pytest tests/test_overrides.py::TestPrivacy -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_common/overrides/models.py src/nthlayer_common/overrides/ingestion.py tests/test_overrides.py
git commit -m "feat(overrides): add pre_redacted flag with plaintext_reviewer alias · opensrm-jmy.18

pre_redacted is the new primary flag with semantically accurate name
(\"trust the wire; no further redaction\"). plaintext_reviewer is kept
as a deprecated alias for backward compatibility and will be removed
in v2. Both flags trigger the same code path in _build_override."
```

---

### Task A2: Add `OverrideEvent.to_dict()` helper

**Files:**
- Modify: `nthlayer-common/src/nthlayer_common/overrides/models.py`
- Test: `nthlayer-common/tests/test_overrides.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_overrides.py` at the end of `TestOverrideEvent`:

```python
    def test_to_dict_canonical_wire_shape(self) -> None:
        """opensrm-jmy.18: to_dict produces a JSON-serializable canonical dict."""
        event = OverrideEvent(
            decision_id="dec-1",
            service="fraud-detect",
            corrected_action="approve",
            reviewer="reviewer-hash",
            original_action="reject",
            reason="false positive",
            confidence_at_decision=0.92,
            source_system="slack-adapter",
            timestamp=datetime(2026, 5, 20, 10, 33, 0, tzinfo=timezone.utc),
        )
        body = event.to_dict()
        assert body == {
            "decision_id": "dec-1",
            "service": "fraud-detect",
            "corrected_action": "approve",
            "reviewer": "reviewer-hash",
            "original_action": "reject",
            "reason": "false positive",
            "confidence_at_decision": 0.92,
            "source_system": "slack-adapter",
            "timestamp": "2026-05-20T10:33:00+00:00",
        }
        # The dict must round-trip through json.dumps.
        import json
        assert json.dumps(body)  # raises on non-serialisable

    def test_to_dict_drops_none_optional_fields(self) -> None:
        event = OverrideEvent(
            decision_id="dec-2",
            service="fraud-detect",
            corrected_action="approve",
            reviewer="reviewer-hash",
        )
        body = event.to_dict()
        assert "original_action" not in body
        assert "reason" not in body
        assert "confidence_at_decision" not in body
        assert "source_system" not in body
        assert "timestamp" in body  # timestamp is always present (default utcnow)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_overrides.py::TestOverrideEvent::test_to_dict_canonical_wire_shape tests/test_overrides.py::TestOverrideEvent::test_to_dict_drops_none_optional_fields -v
```

Expected: 2 FAILED with `AttributeError: 'OverrideEvent' object has no attribute 'to_dict'`.

- [ ] **Step 3: Implement `to_dict`**

In `src/nthlayer_common/overrides/models.py`, find the `OverrideEvent` class and add the method after `to_otel_attributes` (keep them adjacent — both are wire serializers):

```python
    def to_dict(self) -> dict:
        """Canonical JSON-serializable dict for the HTTP wire (opensrm-jmy.18).

        Distinct from to_otel_attributes (which prefixes keys with
        gen_ai.override.*). Used by nthlayer-override-adapter when
        POSTing to POST /verdicts/{id}/override.

        None-valued optional fields are dropped (the receiver's
        OverrideEvent dataclass defaults will fill them back in).
        timestamp is ISO 8601 with offset.
        """
        out: dict = {
            "decision_id": self.decision_id,
            "service": self.service,
            "corrected_action": self.corrected_action,
            "reviewer": self.reviewer,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.original_action is not None:
            out["original_action"] = self.original_action
        if self.reason is not None:
            out["reason"] = self.reason
        if self.confidence_at_decision is not None:
            out["confidence_at_decision"] = self.confidence_at_decision
        if self.source_system is not None:
            out["source_system"] = self.source_system
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_overrides.py::TestOverrideEvent -v
```

Expected: all PASS, including the two new tests.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_common/overrides/models.py tests/test_overrides.py
git commit -m "feat(overrides): add OverrideEvent.to_dict for HTTP wire · opensrm-jmy.18

Canonical JSON-serializable dict shape for POST /verdicts/{id}/override.
None-valued optional fields are dropped; timestamp is ISO 8601 with
offset. Distinct from to_otel_attributes which prefixes keys with
gen_ai.override.*."
```

---

### Task A3: Add `CoreAPIClient.apply_override` method

**Files:**
- Modify: `nthlayer-common/src/nthlayer_common/api_client.py`
- Test: `nthlayer-common/tests/test_api_client.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api_client.py` (the file already exists per `nthlayer-common/CLAUDE.md`). Look at how existing methods like `submit_verdict` or `resolve_outcome` are tested for the mock-transport pattern, then add:

```python
class TestApplyOverride:
    """opensrm-jmy.18: CoreAPIClient.apply_override happy path + status mapping."""

    @pytest.mark.asyncio
    async def test_apply_override_success(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path == "/verdicts/dec-1/override"
            assert json.loads(request.content) == {"reviewer": "h", "service": "s"}
            return httpx.Response(200, json={"id": "dec-1", "status": "overridden"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            api = CoreAPIClient(base_url="http://test")
            api._client = client  # inject mock transport
            result = await api.apply_override("dec-1", {"reviewer": "h", "service": "s"})

        assert result.ok is True
        assert result.status_code == 200
        assert result.data == {"id": "dec-1", "status": "overridden"}

    @pytest.mark.asyncio
    async def test_apply_override_404_returned_as_apiresult(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": "verdict_not_found"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            api = CoreAPIClient(base_url="http://test")
            api._client = client
            result = await api.apply_override("dec-missing", {"reviewer": "h"})

        assert result.ok is False
        assert result.status_code == 404
        assert result.error == "verdict_not_found"

    @pytest.mark.asyncio
    async def test_apply_override_connection_failed(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("simulated")

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            api = CoreAPIClient(base_url="http://test", max_retries=1)
            api._client = client
            result = await api.apply_override("dec-1", {"reviewer": "h"})

        assert result.ok is False
        assert result.status_code == 0
        assert "connection" in result.error.lower()
```

If `CoreAPIClient` uses a different injection pattern than `api._client = client` (e.g. constructor arg), look at how existing tests in `test_api_client.py` mock the transport and match that pattern instead.

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_api_client.py::TestApplyOverride -v
```

Expected: 3 FAILED with `AttributeError: 'CoreAPIClient' object has no attribute 'apply_override'`.

- [ ] **Step 3: Implement `apply_override`**

In `src/nthlayer_common/api_client.py`, find the existing `resolve_outcome` method (around line 201). Add `apply_override` immediately after it (keeps the verdict-mutation methods adjacent):

```python
    async def apply_override(
        self,
        verdict_id: str,
        payload: dict,
    ) -> APIResult:
        """Apply an operator override to a verdict (opensrm-jmy.18).

        Calls POST /verdicts/{verdict_id}/override on the core API.

        Status code mapping (interpret via result.status_code, not result.ok):
            200 - applied (including idempotent re-apply)
            404 - verdict_not_found (no record or concurrent delete)
            409 - conflict (existing override differs OR CAS miss)
            422 - validation_error (terminal status block or schema failure)
            0   - connection failed (transport layer; result.error populated)

        Does not raise; check result.ok and result.status_code.
        """
        return await self._request("POST", f"/verdicts/{verdict_id}/override", json=payload)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_api_client.py::TestApplyOverride -v
```

Expected: 3 PASSED.

Sanity check that no other CoreAPIClient test regressed:

```bash
uv run pytest tests/test_api_client.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_common/api_client.py tests/test_api_client.py
git commit -m "feat(api-client): add CoreAPIClient.apply_override · opensrm-jmy.18

POST /verdicts/{verdict_id}/override wrapper. Returns APIResult,
never raises; status_code distinguishes 200 (applied) / 404 (not
found) / 409 (conflict or CAS miss) / 422 (validation error) /
0 (connection failed). Used by nthlayer-override-adapter."
```

---

## Phase B — nthlayer-core

### Task B1: `POST /verdicts/{id}/override` handler

**Files:**
- Modify: `nthlayer-core/src/nthlayer_core/server.py`
- Create: `nthlayer-core/tests/test_api_overrides.py`

- [ ] **Step 1: Write the failing tests**

Create `nthlayer-core/tests/test_api_overrides.py`:

```python
"""opensrm-jmy.18: POST /verdicts/{id}/override handler tests."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import pytest
from httpx import ASGITransport

from nthlayer_common.verdicts.models import Outcome, Verdict
from nthlayer_common.verdicts.store import MemoryStore
from nthlayer_core import server


def _seed_pending(store: MemoryStore, vid: str) -> None:
    """Place a pending Verdict in the store keyed by vid (matches existing test helpers)."""
    # Mirror the verdict-construction pattern from tests/test_api.py::TestPostVerdict.
    # If that file uses a builder, import + reuse it here instead of duplicating.
    v = Verdict(
        id=vid,
        verdict_type="action_request",
        service="fraud-detect",
        outcome=Outcome(status="pending"),
        # Fill remaining required fields per Verdict dataclass — see existing helpers.
    )
    store.put(v)


def _body(decision_id: str = "dec-1", **overrides) -> dict:
    body = {
        "decision_id": decision_id,
        "service": "fraud-detect",
        "corrected_action": "approve",
        "reviewer": "reviewer-hash",
        "timestamp": "2026-05-20T10:33:00+00:00",
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_override_happy_path_returns_200_and_mutates_outcome():
    store = MemoryStore()
    _seed_pending(store, "dec-1")
    server.set_store(store)

    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/verdicts/dec-1/override", json=_body())

    assert resp.status_code == 200
    assert resp.json()["status"] == "overridden"
    # Verdict outcome mutated in place.
    v = store.get("dec-1")
    assert v.outcome.status == "overridden"
    assert v.outcome.override.by == "reviewer-hash"  # pre_redacted=True; no re-hash


@pytest.mark.asyncio
async def test_override_idempotent_reapply_returns_200():
    store = MemoryStore()
    _seed_pending(store, "dec-2")
    server.set_store(store)

    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post("/verdicts/dec-2/override", json=_body("dec-2"))
        r2 = await client.post("/verdicts/dec-2/override", json=_body("dec-2"))

    assert r1.status_code == 200
    assert r2.status_code == 200  # idempotent


@pytest.mark.asyncio
async def test_override_verdict_not_found_returns_404():
    store = MemoryStore()
    server.set_store(store)

    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/verdicts/dec-missing/override", json=_body("dec-missing"))

    assert resp.status_code == 404
    assert resp.json()["error"] == "verdict_not_found"


@pytest.mark.asyncio
async def test_override_decision_id_mismatch_returns_400():
    store = MemoryStore()
    _seed_pending(store, "dec-real")
    server.set_store(store)

    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/verdicts/dec-real/override", json=_body("dec-different"))

    assert resp.status_code == 400
    assert resp.json()["error"] == "decision_id_mismatch"


@pytest.mark.asyncio
async def test_override_schema_failure_returns_422():
    store = MemoryStore()
    _seed_pending(store, "dec-3")
    server.set_store(store)

    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Missing required field corrected_action.
        bad = {"decision_id": "dec-3", "service": "fraud-detect", "reviewer": "h",
               "timestamp": "2026-05-20T10:33:00+00:00"}
        resp = await client.post("/verdicts/dec-3/override", json=bad)

    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_error"


@pytest.mark.asyncio
async def test_override_conflict_with_existing_returns_409():
    store = MemoryStore()
    _seed_pending(store, "dec-4")
    server.set_store(store)

    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post("/verdicts/dec-4/override", json=_body("dec-4", reviewer="alice"))
        r2 = await client.post("/verdicts/dec-4/override", json=_body("dec-4", reviewer="bob"))

    assert r1.status_code == 200
    assert r2.status_code == 409
    assert r2.json()["error"] == "conflict"


@pytest.mark.asyncio
async def test_override_terminal_status_returns_422():
    """A confirmed verdict cannot be overridden."""
    store = MemoryStore()
    v = Verdict(
        id="dec-5",
        verdict_type="action_request",
        service="fraud-detect",
        outcome=Outcome(status="confirmed"),  # terminal
    )
    store.put(v)
    server.set_store(store)

    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/verdicts/dec-5/override", json=_body("dec-5"))

    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_error"
```

Look at `tests/test_api.py` to see exactly how the Verdict builder is set up; reuse that helper rather than duplicating field-fill code. If the existing file uses `_make_verdict(...)` or similar, import or copy it.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-core
uv run pytest tests/test_api_overrides.py -v
```

Expected: 7 FAILED with `404 Not Found` (no route registered yet) or similar.

- [ ] **Step 3: Implement handler + register route**

In `src/nthlayer_core/server.py`, add the imports (near the existing `from nthlayer_common...` imports):

```python
from nthlayer_common.overrides import (
    OverrideEvent,
    OverridePrivacyConfig,
    apply_override_to_verdict,
)
```

Add the handler immediately after `post_verdict_outcome` (around line 345):

```python
async def post_verdict_override(request: Request) -> JSONResponse:
    """Apply an operator override to a verdict (mutation-style, opensrm-jmy.18).

    Calls apply_override_to_verdict on the verdict store, mutating the
    original verdict's outcome in place. Distinct from POST /outcome
    which creates an outcome_resolution child verdict (lineage-style).
    """
    verdict_id = request.path_params["verdict_id"]
    body, err = await _parse_json_body(request)
    if err:
        return err

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
        return JSONResponse(
            {"id": verdict_id, "status": "overridden"},
            status_code=200,
        )

    # None-path: read the verdict back to map cause → HTTP status. The
    # function logged a structured warning identifying the underlying
    # cause; this handler only needs the bounded operator-facing mapping.
    verdict = store.get(verdict_id)
    if verdict is None:
        return JSONResponse({"error": "verdict_not_found"}, status_code=404)

    current = (getattr(verdict.outcome, "status", None) or "").lower()
    if current == "overridden":
        # Either conflict_with_existing or CAS race won by another writer.
        return JSONResponse({"error": "conflict"}, status_code=409)
    # Terminal non-pending status.
    return JSONResponse({"error": "validation_error"}, status_code=422)
```

Register the route in the existing `Mount`/`Route` list (around line 825). Add immediately after the `/outcome` route:

```python
    Route("/verdicts/{verdict_id}/override", post_verdict_override, methods=["POST"]),
```

If the store accessor pattern in the existing handlers uses `store.get_verdict(...)` returning a dict (not a `Verdict` dataclass), adapt the None-path branch accordingly — the existing `get_verdict` handler at line 297 is the right reference for what the store actually returns.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_api_overrides.py -v
```

Expected: 7 PASSED.

Run the full test_api.py too to confirm no regression on the lineage-style `/outcome` handler:

```bash
uv run pytest tests/test_api.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_core/server.py tests/test_api_overrides.py
git commit -m "feat(api): add POST /verdicts/{id}/override handler · opensrm-jmy.18

Mutation-style override binding. Calls apply_override_to_verdict
from nthlayer-common with pre_redacted=True; status-code mapping
per the design doc (200/404/409/422/400). Distinct from POST
/outcome which is the lineage-style child-verdict creator and
remains unchanged."
```

---

## Phase C — nthlayer-override-adapter

### Task C1: `CoreConfig` block

**Files:**
- Modify: `nthlayer-override-adapter/src/nthlayer_override_adapter/config.py`
- Test: `nthlayer-override-adapter/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
class TestCoreConfig:
    """opensrm-jmy.18: core: block in adapter config."""

    def test_core_block_parsed(self, tmp_path):
        cfg_path = tmp_path / "cfg.yaml"
        cfg_path.write_text(
            "core:\n"
            "  url: http://core:8000\n"
            "  timeout_seconds: 7.5\n"
        )
        cfg = load_config(str(cfg_path))
        assert cfg.core.url == "http://core:8000"
        assert cfg.core.timeout_seconds == 7.5

    def test_core_url_required(self, tmp_path):
        cfg_path = tmp_path / "cfg.yaml"
        cfg_path.write_text("core:\n  timeout_seconds: 5.0\n")
        with pytest.raises(ConfigError, match="core.url"):
            load_config(str(cfg_path))

    def test_core_timeout_defaults_to_5(self, tmp_path):
        cfg_path = tmp_path / "cfg.yaml"
        cfg_path.write_text("core:\n  url: http://core:8000\n")
        cfg = load_config(str(cfg_path))
        assert cfg.core.timeout_seconds == 5.0

    def test_core_timeout_must_be_positive(self, tmp_path):
        cfg_path = tmp_path / "cfg.yaml"
        cfg_path.write_text(
            "core:\n  url: http://core:8000\n  timeout_seconds: 0\n"
        )
        with pytest.raises(ConfigError, match="timeout_seconds"):
            load_config(str(cfg_path))

    def test_core_block_required(self, tmp_path):
        cfg_path = tmp_path / "cfg.yaml"
        cfg_path.write_text("# empty config\n")
        with pytest.raises(ConfigError, match="core"):
            load_config(str(cfg_path))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-override-adapter
uv run pytest tests/test_config.py::TestCoreConfig -v
```

Expected: 5 FAILED.

- [ ] **Step 3: Add `CoreConfig` + parser branch**

In `src/nthlayer_override_adapter/config.py`, add the dataclass next to `AdapterConfig`:

```python
@dataclass(frozen=True)
class CoreConfig:
    """Core API connection settings (opensrm-jmy.18)."""
    url: str
    timeout_seconds: float = 5.0
```

Add `core: CoreConfig` as a required field on `AdapterConfig` (no default — the parser fills it).

In the `load_config` function, find where the YAML root dict is split into sections (`privacy`, `otel`, `field_mapping`, `defaults`, `adapters`, `batch`) and add a `core` section parser. Use the same dict/None coercion pattern existing sections use:

```python
    core_raw = data.get("core")
    if core_raw is None:
        raise ConfigError("core: block is required")
    if not isinstance(core_raw, dict):
        raise ConfigError("core: must be a mapping")
    core_url = core_raw.get("url")
    if not isinstance(core_url, str) or not core_url:
        raise ConfigError("core.url is required and must be a non-empty string")
    core_timeout_raw = core_raw.get("timeout_seconds", 5.0)
    if not isinstance(core_timeout_raw, (int, float)) or core_timeout_raw <= 0:
        raise ConfigError("core.timeout_seconds must be a positive number")
    core_cfg = CoreConfig(url=core_url, timeout_seconds=float(core_timeout_raw))
```

Pass `core=core_cfg` to the `AdapterConfig(...)` constructor at the end of the function.

Update the `override-adapter-config.yaml.example` at the repo root to include a `core:` block:

```yaml
core:
  url: http://core:8000
  timeout_seconds: 5.0
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: all PASS, including the 5 new tests.

The existing config tests may break because they construct sample YAML configs without a `core:` block. Fix those test fixtures by adding the `core:` block (matches the new required-field reality). The example config file (`override-adapter-config.yaml.example`) gives the canonical shape.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_override_adapter/config.py tests/test_config.py override-adapter-config.yaml.example
git commit -m "feat(config): add required core block (url + timeout_seconds) · opensrm-jmy.18

CoreConfig dataclass with url (required string) and timeout_seconds
(positive float, default 5.0). Sidecar fails to start without a
core: block. Example config updated."
```

---

### Task C2: `nthlayer_override_binding_total` Counter

**Files:**
- Modify: `nthlayer-override-adapter/src/nthlayer_override_adapter/metrics.py`
- Test: `nthlayer-override-adapter/tests/test_metrics.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_metrics.py`:

```python
def test_binding_total_counter_exists_with_bounded_labels():
    """opensrm-jmy.18: nthlayer_override_binding_total{result, reason}."""
    from nthlayer_override_adapter.metrics import binding_total

    # Bound the cardinality by exhausting expected label combinations.
    binding_total.labels(result="success", reason="ok").inc()
    for reason in ("core_unreachable", "verdict_not_found",
                   "validation_error", "core_timeout", "other"):
        binding_total.labels(result="failed", reason=reason).inc()

    # Counter is the expected type; metric name is exactly as specified.
    samples = list(binding_total.collect())
    names = {s.name for s in samples}
    assert "nthlayer_override_binding" in names or \
           any("nthlayer_override_binding_total" in n for n in names)
```

If the test file already imports + asserts on other counters, mirror that pattern.

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_metrics.py::test_binding_total_counter_exists_with_bounded_labels -v
```

Expected: FAIL with `ImportError: cannot import name 'binding_total'`.

- [ ] **Step 3: Add the counter**

In `src/nthlayer_override_adapter/metrics.py`, add alongside the existing counters:

```python
binding_total = Counter(
    "nthlayer_override_binding",
    "Override binding attempts to nthlayer-core, by result and reason (opensrm-jmy.18).",
    labelnames=("result", "reason"),
)
```

`prometheus_client.Counter` automatically appends `_total` to the exposed metric name; declaring it as `nthlayer_override_binding` produces `nthlayer_override_binding_total` on the wire. Verify by inspecting an existing counter in the same file (`requests_total` etc.) — match whichever pattern is in use.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_metrics.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_override_adapter/metrics.py tests/test_metrics.py
git commit -m "feat(metrics): add nthlayer_override_binding_total · opensrm-jmy.18

Counter with bounded labels: result ∈ {success, failed} ×
reason ∈ {ok, core_unreachable, verdict_not_found,
validation_error, core_timeout, other}. Max 12 series per process."
```

---

### Task C3: `BindingResult` dataclass + `bind_to_core` helper

**Files:**
- Modify: `nthlayer-override-adapter/src/nthlayer_override_adapter/response.py`
- Modify: `nthlayer-override-adapter/src/nthlayer_override_adapter/emission.py`
- Test: `nthlayer-override-adapter/tests/test_emission.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_emission.py`:

```python
class TestBindToCore:
    """opensrm-jmy.18: bind_to_core maps APIResult → BindingResult."""

    @pytest.mark.asyncio
    async def test_bind_to_core_success_returns_ok(self):
        from nthlayer_override_adapter.emission import bind_to_core
        from nthlayer_common.api_client import APIResult

        class _FakeClient:
            async def apply_override(self, vid, payload):
                return APIResult(ok=True, status_code=200, data={"id": vid}, error=None, detail=None)

        event = OverrideEvent(
            decision_id="dec-1", service="s", corrected_action="approve",
            reviewer="h",
        )
        result = await bind_to_core(_FakeClient(), event, timeout_seconds=5.0)
        assert result.core == "ok"
        assert result.reason == "ok"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status,expected_reason", [
        (404, "verdict_not_found"),
        (409, "validation_error"),
        (422, "validation_error"),
        (500, "other"),
    ])
    async def test_bind_to_core_status_mapping(self, status, expected_reason):
        from nthlayer_override_adapter.emission import bind_to_core
        from nthlayer_common.api_client import APIResult

        class _FakeClient:
            async def apply_override(self, vid, payload):
                return APIResult(ok=False, status_code=status, data=None,
                                 error="err", detail=None)

        event = OverrideEvent(decision_id="d", service="s",
                              corrected_action="approve", reviewer="h")
        result = await bind_to_core(_FakeClient(), event, timeout_seconds=5.0)
        assert result.core == "failed"
        assert result.reason == expected_reason

    @pytest.mark.asyncio
    async def test_bind_to_core_connection_failed_returns_core_unreachable(self):
        from nthlayer_override_adapter.emission import bind_to_core
        from nthlayer_common.api_client import APIResult

        class _FakeClient:
            async def apply_override(self, vid, payload):
                return APIResult(ok=False, status_code=0, data=None,
                                 error="connection_failed", detail=None)

        event = OverrideEvent(decision_id="d", service="s",
                              corrected_action="approve", reviewer="h")
        result = await bind_to_core(_FakeClient(), event, timeout_seconds=5.0)
        assert result.core == "failed"
        assert result.reason == "core_unreachable"

    @pytest.mark.asyncio
    async def test_bind_to_core_timeout_returns_core_timeout(self):
        from nthlayer_override_adapter.emission import bind_to_core
        import asyncio

        class _SlowClient:
            async def apply_override(self, vid, payload):
                await asyncio.sleep(10)  # exceeds the 0.05s timeout below

        event = OverrideEvent(decision_id="d", service="s",
                              corrected_action="approve", reviewer="h")
        result = await bind_to_core(_SlowClient(), event, timeout_seconds=0.05)
        assert result.core == "failed"
        assert result.reason == "core_timeout"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_emission.py::TestBindToCore -v
```

Expected: FAILED with `ImportError: cannot import name 'bind_to_core'`.

- [ ] **Step 3: Add `BindingResult` + `bind_to_core`**

In `src/nthlayer_override_adapter/response.py`, add the dataclass near the existing `BatchResult`:

```python
@dataclass(frozen=True)
class BindingResult:
    """Per-decision binding outcome (opensrm-jmy.18).

    otel and core each ∈ {"ok", "failed"}.
    reason is core-specific: present iff core == "failed",
    None when core == "ok". Values match the bounded set in the
    spec: ok | core_unreachable | verdict_not_found |
    validation_error | core_timeout | other.
    """
    otel: str = "ok"
    core: str = "ok"
    reason: str | None = None

    def to_dict(self) -> dict:
        out: dict = {"otel": self.otel, "core": self.core}
        if self.reason is not None and self.core == "failed":
            out["reason"] = self.reason
        return out
```

In `src/nthlayer_override_adapter/emission.py`, add the helper alongside the existing `emit_override`:

```python
import asyncio
from typing import Any

from nthlayer_common.overrides import OverrideEvent

from nthlayer_override_adapter.metrics import binding_total
from nthlayer_override_adapter.response import BindingResult


_STATUS_TO_REASON: dict[int, str] = {
    200: "ok",
    404: "verdict_not_found",
    409: "validation_error",
    422: "validation_error",
    0:   "core_unreachable",
}


async def bind_to_core(
    client: Any,  # nthlayer_common.api_client.CoreAPIClient
    event: OverrideEvent,
    timeout_seconds: float,
) -> BindingResult:
    """Apply the override to core via HTTP POST; map result → BindingResult.

    Wraps the CoreAPIClient call in asyncio.wait_for so the sidecar enforces
    its own timeout regardless of CoreAPIClient's internal retry semantics.
    Always increments nthlayer_override_binding_total.
    """
    payload = event.to_dict()
    try:
        api_result = await asyncio.wait_for(
            client.apply_override(event.decision_id, payload),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        binding_total.labels(result="failed", reason="core_timeout").inc()
        return BindingResult(core="failed", reason="core_timeout")

    if api_result.ok:
        binding_total.labels(result="success", reason="ok").inc()
        return BindingResult(core="ok", reason=None)

    reason = _STATUS_TO_REASON.get(api_result.status_code, "other")
    binding_total.labels(result="failed", reason=reason).inc()
    return BindingResult(core="failed", reason=reason)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_emission.py::TestBindToCore -v
```

Expected: 7 PASSED (1 success + 4 parametrized + 1 connection + 1 timeout).

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_override_adapter/response.py src/nthlayer_override_adapter/emission.py tests/test_emission.py
git commit -m "feat(emission): add bind_to_core helper · opensrm-jmy.18

Wraps CoreAPIClient.apply_override with sidecar-enforced asyncio
timeout. Maps APIResult.status_code to bounded reason set via
lookup dict (200→ok, 404→verdict_not_found, 409/422→
validation_error, 0→core_unreachable, else other). asyncio
TimeoutError → core_timeout. Always increments
nthlayer_override_binding_total."
```

---

### Task C4: Wire `bind_to_core` into canonical single route

**Files:**
- Modify: `nthlayer-override-adapter/src/nthlayer_override_adapter/response.py`
- Modify: `nthlayer-override-adapter/src/nthlayer_override_adapter/routes/canonical.py`
- Test: `nthlayer-override-adapter/tests/test_routes_canonical.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_routes_canonical.py`:

```python
class TestCanonicalSingleBindings:
    """opensrm-jmy.18: single-override response carries bindings field."""

    def test_single_success_response_includes_bindings(self, app_with_fake_core):
        """app_with_fake_core fixture wires a fake CoreAPIClient that returns 200."""
        client = TestClient(app_with_fake_core(fake_status=200))
        body = {
            "decision_id": "dec-1",
            "service": "fraud-detect",
            "corrected_action": "approve",
            "reviewer": "reviewer-hash",
        }
        resp = client.post("/api/v1/overrides", json=body)
        assert resp.status_code == 201
        data = resp.json()
        assert data["accepted"] == ["dec-1"]
        assert data["bindings"]["dec-1"]["otel"] == "ok"
        assert data["bindings"]["dec-1"]["core"] == "ok"
        assert "reason" not in data["bindings"]["dec-1"]

    def test_single_core_failure_surfaces_in_response(self, app_with_fake_core):
        client = TestClient(app_with_fake_core(fake_status=404))
        body = {
            "decision_id": "dec-missing",
            "service": "fraud-detect",
            "corrected_action": "approve",
            "reviewer": "reviewer-hash",
        }
        resp = client.post("/api/v1/overrides", json=body)
        assert resp.status_code == 201  # unchanged HTTP status
        data = resp.json()
        assert data["accepted"] == ["dec-missing"]
        assert data["bindings"]["dec-missing"]["core"] == "failed"
        assert data["bindings"]["dec-missing"]["reason"] == "verdict_not_found"
```

Add an `app_with_fake_core` fixture in `tests/conftest.py` (or extend the existing fixture if one exists):

```python
@pytest.fixture
def app_with_fake_core():
    """Returns a factory that builds the adapter app with a stubbed CoreAPIClient.

    Usage: client = TestClient(app_with_fake_core(fake_status=200))
    """
    from unittest.mock import MagicMock
    from nthlayer_common.api_client import APIResult
    from nthlayer_override_adapter.app import build_app
    from nthlayer_override_adapter.config import (
        AdapterConfig, CoreConfig, OverridePrivacyConfig,  # imports match config.py
    )

    def _factory(fake_status: int = 200):
        cfg = AdapterConfig(  # fill remaining required fields from existing tests
            core=CoreConfig(url="http://test", timeout_seconds=5.0),
            # ... other required fields per AdapterConfig
        )
        app = build_app(cfg)

        fake_client = MagicMock()
        async def _fake_apply(vid, payload):
            return APIResult(
                ok=fake_status == 200, status_code=fake_status,
                data={"id": vid} if fake_status == 200 else None,
                error=None if fake_status == 200 else "err",
                detail=None,
            )
        fake_client.apply_override = _fake_apply
        app.state.core_client = fake_client
        return app

    return _factory
```

The fixture's `AdapterConfig` constructor needs the other required fields — look at any existing fixture in `tests/conftest.py` that already builds an `AdapterConfig` and copy its field-fill, then add `core=...`.

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_routes_canonical.py::TestCanonicalSingleBindings -v
```

Expected: 2 FAILED (no `bindings` key in response).

- [ ] **Step 3: Wire `bind_to_core` into the single-route handler**

In `src/nthlayer_override_adapter/response.py`, find `accepted_single` and add a `bindings` parameter:

```python
def accepted_single(decision_id: str, bindings: BindingResult | None = None) -> dict:
    out = {
        "accepted": [decision_id],
        "rejected": [],
        "duplicates": [],
        "errors": [],
    }
    if bindings is not None:
        out["bindings"] = {decision_id: bindings.to_dict()}
    return out
```

In `src/nthlayer_override_adapter/routes/canonical.py`, find the single-override handler. After the existing `emit_override(...)` call, add:

```python
    binding = await bind_to_core(
        request.app.state.core_client,
        event,
        timeout_seconds=request.app.state.adapter_config.core.timeout_seconds,
    )
    response_body = accepted_single(event.decision_id, bindings=binding)
    return JSONResponse(response_body, status_code=201)
```

The exact attribute paths (`request.app.state.core_client`, `request.app.state.adapter_config`) must match how `build_app` stores these — verify in `app.py` and adjust if the existing convention differs (e.g. some adapters use `request.app.config`).

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_routes_canonical.py -v
```

Expected: all PASS, including the 2 new tests. Existing single-route tests should still pass — the `bindings` field is additive.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_override_adapter/response.py src/nthlayer_override_adapter/routes/canonical.py tests/test_routes_canonical.py tests/conftest.py
git commit -m "feat(routes): wire bind_to_core into canonical single · opensrm-jmy.18

POST /api/v1/overrides now runs OTel emission then bind_to_core
per accepted decision and returns the binding state in the
response body's bindings field. HTTP status is unchanged."
```

---

### Task C5: Wire `bind_to_core` into canonical batch route

**Files:**
- Modify: `nthlayer-override-adapter/src/nthlayer_override_adapter/response.py`
- Modify: `nthlayer-override-adapter/src/nthlayer_override_adapter/routes/canonical.py`
- Test: `nthlayer-override-adapter/tests/test_routes_canonical_batch.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_routes_canonical_batch.py` (the file already exists per the jmy.7 CLAUDE.md mention):

```python
class TestBatchBindings:
    """opensrm-jmy.18: per-id bindings in batch response."""

    def test_batch_response_includes_bindings_per_accepted_id(self, app_with_fake_core):
        client = TestClient(app_with_fake_core(fake_status=200))
        body = {
            "overrides": [
                {"decision_id": "dec-1", "service": "s", "corrected_action": "approve", "reviewer": "h"},
                {"decision_id": "dec-2", "service": "s", "corrected_action": "approve", "reviewer": "h"},
            ]
        }
        resp = client.post("/api/v1/overrides/batch", json=body)
        assert resp.status_code == 201
        data = resp.json()
        assert set(data["accepted"]) == {"dec-1", "dec-2"}
        # Cardinality invariant: bindings.keys() == set(accepted).
        assert set(data["bindings"].keys()) == set(data["accepted"])
        for entry in data["bindings"].values():
            assert entry["core"] == "ok"

    def test_batch_duplicates_do_not_appear_in_bindings(self, app_with_fake_core):
        client = TestClient(app_with_fake_core(fake_status=200))
        body = {
            "overrides": [
                {"decision_id": "dec-1", "service": "s", "corrected_action": "reject", "reviewer": "h"},
                {"decision_id": "dec-1", "service": "s", "corrected_action": "approve", "reviewer": "h"},  # winner
                {"decision_id": "dec-2", "service": "s", "corrected_action": "approve", "reviewer": "h"},
            ]
        }
        resp = client.post("/api/v1/overrides/batch", json=body)
        data = resp.json()
        assert set(data["accepted"]) == {"dec-1", "dec-2"}
        assert set(data["bindings"].keys()) == {"dec-1", "dec-2"}
        assert "dec-1" in data["duplicates"] or len(data["duplicates"]) >= 1
        # The duplicate-loser's decision_id should NOT have its own bindings entry
        # (the cardinality invariant is by unique decision_id, not by occurrence).
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_routes_canonical_batch.py::TestBatchBindings -v
```

Expected: 2 FAILED.

- [ ] **Step 3: Wire `bind_to_core` into batch emit-pass**

In `src/nthlayer_override_adapter/response.py`, extend `build_batch_response`:

```python
def build_batch_response(
    accepted: list[str],
    rejected: list[dict],
    duplicates: list[dict],
    bindings: dict[str, BindingResult] | None = None,
) -> dict:
    out = {
        "accepted": accepted,
        "rejected": rejected,
        "duplicates": duplicates,
        "errors": [],
    }
    if bindings is not None:
        out["bindings"] = {k: v.to_dict() for k, v in bindings.items()}
    return out
```

In `src/nthlayer_override_adapter/routes/canonical.py`, find the batch handler (look for `_process_batch` per jmy.7 CLAUDE.md). After the existing per-winner OTel emission, add a per-winner core POST and collect into a `bindings` dict:

```python
    bindings: dict[str, BindingResult] = {}
    for winner_id, winner in winners.items():
        emit_override(winner.event, privacy)
        bindings[winner_id] = await bind_to_core(
            request.app.state.core_client,
            winner.event,
            timeout_seconds=request.app.state.adapter_config.core.timeout_seconds,
        )

    response_body = build_batch_response(
        accepted=list(winners.keys()),
        rejected=rejected,
        duplicates=duplicates,
        bindings=bindings,
    )
    return JSONResponse(response_body, status_code=201)
```

The exact variable names (`winners`, `rejected`, `duplicates`) must match the existing handler — read it first and adapt.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_routes_canonical_batch.py -v
```

Expected: all PASS, including new tests. The existing cardinality-invariant test (`TestCardinalityInvariant` per jmy.7 CLAUDE.md) should still pass and now extends naturally to `bindings.keys() == set(accepted)`.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_override_adapter/response.py src/nthlayer_override_adapter/routes/canonical.py tests/test_routes_canonical_batch.py
git commit -m "feat(routes): wire bind_to_core into canonical batch · opensrm-jmy.18

Per-winner OTel emission then bind_to_core in the existing
two-pass batch handler. Response gains bindings field keyed by
decision_id; cardinality invariant bindings.keys() == set(accepted)
preserved."
```

---

### Task C6: Wire `bind_to_core` into webhook route

**Files:**
- Modify: `nthlayer-override-adapter/src/nthlayer_override_adapter/routes/webhook.py`
- Test: `nthlayer-override-adapter/tests/test_routes_webhook.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_routes_webhook.py`:

```python
class TestWebhookBindings:
    """opensrm-jmy.18: webhook response carries bindings."""

    def test_webhook_success_response_includes_bindings(self, app_with_fake_core):
        # Use whatever webhook adapter the existing tests use as a minimal
        # config. The point is the response shape, not the adapter logic.
        client = TestClient(app_with_fake_core(fake_status=200))
        # Pick the route path from an existing webhook test; payload must be
        # mappable by the configured webhook field_mapping.
        resp = client.post("/webhook/jira", json={
            # ... shape that maps to decision_id="dec-1" via existing tests' fixtures
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "bindings" in data
        # The webhook route handles one decision per request.
        assert len(data["bindings"]) == 1
```

If the existing webhook tests use a particular payload shape, copy it and assert the new `bindings` field.

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_routes_webhook.py::TestWebhookBindings -v
```

Expected: FAILED (no `bindings` key).

- [ ] **Step 3: Wire `bind_to_core` into the webhook handler**

In `src/nthlayer_override_adapter/routes/webhook.py`, find the per-adapter handler (per jmy.7 CLAUDE.md, dynamic POST routes call `map_webhook_to_override` then `emit_override`). After `emit_override`, add:

```python
    binding = await bind_to_core(
        request.app.state.core_client,
        event,
        timeout_seconds=request.app.state.adapter_config.core.timeout_seconds,
    )
    response_body = accepted_single(event.decision_id, bindings=binding)
    return JSONResponse(response_body, status_code=201)
```

The webhook route handles a single decision per request, so reusing `accepted_single` is correct.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_routes_webhook.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_override_adapter/routes/webhook.py tests/test_routes_webhook.py
git commit -m "feat(routes): wire bind_to_core into webhook · opensrm-jmy.18

Dynamic per-adapter webhook handlers now emit OTel then bind to
core per accepted decision, returning the binding state via the
shared accepted_single response helper."
```

---

### Task C7: CoreAPIClient lifecycle in `app.py`

**Files:**
- Modify: `nthlayer-override-adapter/src/nthlayer_override_adapter/app.py`
- Modify: `nthlayer-override-adapter/src/nthlayer_override_adapter/cli.py` (if atexit hook lives there per jmy.7 layout)
- Test: covered by existing test_app + test_routes_* tests through fixtures

- [ ] **Step 1: Write the failing test**

Add to `tests/test_app.py` (or wherever `build_app` tests live):

```python
def test_build_app_attaches_core_client_to_state(monkeypatch):
    """opensrm-jmy.18: build_app instantiates CoreAPIClient on state."""
    cfg = AdapterConfig(  # match Task C4 fixture pattern
        core=CoreConfig(url="http://core:8000", timeout_seconds=5.0),
        # ... other required fields
    )
    app = build_app(cfg)
    assert app.state.core_client is not None
    # The client's base_url should reflect the config.
    assert app.state.core_client._client.base_url == "http://core:8000"
```

If `CoreAPIClient` doesn't expose `_client` publicly, assert on whatever observable attribute it does have (look at `nthlayer-common/src/nthlayer_common/api_client.py`).

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_app.py::test_build_app_attaches_core_client_to_state -v
```

Expected: FAIL.

- [ ] **Step 3: Wire `CoreAPIClient` lifecycle**

In `src/nthlayer_override_adapter/app.py`, find `build_app(config)` and add:

```python
from nthlayer_common.api_client import CoreAPIClient

def build_app(config: AdapterConfig) -> Starlette:
    app = Starlette(routes=[...])  # existing route list
    app.state.adapter_config = config
    app.state.core_client = CoreAPIClient(base_url=config.core.url)
    return app
```

In `src/nthlayer_override_adapter/cli.py`, find the existing `atexit.register(...)` block that handles OTel `force_flush + shutdown`. Add a parallel teardown for the core client:

```python
    @atexit.register
    def _shutdown_core_client() -> None:
        try:
            asyncio.run(app.state.core_client.close())
        except Exception:  # noqa: BLE001 — fail-soft shutdown
            logger.warning("core_client_shutdown_error")
```

Match the existing OTel shutdown hook's exact shape (the jmy.7 CLAUDE.md describes `provider.force_flush(timeout_millis=5000)` then `provider.shutdown()` — pattern-match on that style).

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_app.py -v
uv run pytest -q  # full suite sanity
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_override_adapter/app.py src/nthlayer_override_adapter/cli.py tests/test_app.py
git commit -m "feat(app): CoreAPIClient lifecycle in build_app + atexit · opensrm-jmy.18

Single client instance on app.state.core_client, instantiated at
build_app time from config.core.url. atexit hook closes the client
alongside the existing OTel force_flush + shutdown."
```

---

## Phase D — Integration smoke

### Task D1: Cross-process smoke in `nthlayer/test/`

**Files:**
- Create: `nthlayer/test/test_jmy18_smoke.py`

- [ ] **Step 1: Write the smoke test**

Create `nthlayer/test/test_jmy18_smoke.py`:

```python
"""opensrm-jmy.18 cross-process smoke: real sidecar + real core via TestClient.

Verifies the three end-to-end claims from the design doc § 9:
(a) nthlayer_override_binding_total{result=success} increments,
(b) GET /verdicts/{id} on core shows outcome.status=overridden,
(c) sidecar response carries bindings.{id}.core == "ok".
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from httpx import ASGITransport
from starlette.testclient import TestClient

from nthlayer_common.verdicts.models import Outcome, Verdict
from nthlayer_common.verdicts.store import MemoryStore
from nthlayer_common.api_client import CoreAPIClient
from nthlayer_core import server
from nthlayer_override_adapter.app import build_app
from nthlayer_override_adapter.config import AdapterConfig, CoreConfig
from nthlayer_override_adapter.metrics import binding_total


@pytest.mark.asyncio
async def test_sidecar_override_binds_to_core_verdict():
    # Set up real core with a pending verdict.
    store = MemoryStore()
    pending = Verdict(
        id="dec-smoke-1",
        verdict_type="action_request",
        service="fraud-detect",
        outcome=Outcome(status="pending"),
    )
    store.put(pending)
    server.set_store(store)

    # Build the sidecar app pointed at the in-process core (ASGI transport).
    cfg = AdapterConfig(
        core=CoreConfig(url="http://core-stub", timeout_seconds=5.0),
        # ... other required fields per AdapterConfig
    )
    sidecar_app = build_app(cfg)
    # Swap the sidecar's CoreAPIClient for one that talks to core's ASGI app.
    core_transport = ASGITransport(app=server.app)
    real_client = CoreAPIClient(base_url="http://core-stub")
    real_client._client = httpx.AsyncClient(transport=core_transport, base_url="http://core-stub")
    sidecar_app.state.core_client = real_client

    # Capture the counter value before.
    before = _counter_value(binding_total, result="success", reason="ok")

    # Operator POSTs an override to the sidecar.
    with TestClient(sidecar_app) as client:
        resp = client.post("/api/v1/overrides", json={
            "decision_id": "dec-smoke-1",
            "service": "fraud-detect",
            "corrected_action": "approve",
            "reviewer": "reviewer-hash",
            "timestamp": "2026-05-20T10:33:00+00:00",
        })

    # (c) Sidecar response carries bindings.
    assert resp.status_code == 201
    data = resp.json()
    assert data["bindings"]["dec-smoke-1"]["core"] == "ok"

    # (b) Core's verdict is mutated.
    v = store.get("dec-smoke-1")
    assert v.outcome.status == "overridden"
    assert v.outcome.override.by == "reviewer-hash"

    # (a) Counter incremented.
    after = _counter_value(binding_total, result="success", reason="ok")
    assert after == before + 1


def _counter_value(counter, **labels) -> float:
    """Read a labelled counter's current value."""
    return counter.labels(**labels)._value.get()
```

The exact `AdapterConfig` field-fill must match Tasks C1/C4 — use the same fixture pattern. The test is in `nthlayer/test/`, which is the ecosystem hub's integration-test directory per `CLAUDE.md` (`An ecosystem-wide test harness change → nthlayer/test/`).

- [ ] **Step 2: Run the smoke test**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer
uv run pytest test/test_jmy18_smoke.py -v
```

Expected: PASSED.

- [ ] **Step 3: Commit**

```bash
git add test/test_jmy18_smoke.py
git commit -m "test(smoke): jmy.18 cross-process verdict-binding smoke · opensrm-jmy.18

Real sidecar (nthlayer-override-adapter) + real core (nthlayer-core)
via in-process ASGI transports. Asserts (a) counter increments,
(b) verdict outcome mutated, (c) sidecar response bindings field
populated. Lives in nthlayer/test/ per the ecosystem hub's
integration-test convention."
```

---

## Self-review

### Spec coverage

Walked each spec section; mapping to tasks:

| Spec section | Task(s) |
|---|---|
| § 2 outcome representation patterns (docs only) | covered in spec — no code change needed |
| § 3 scope: new POST /verdicts/{id}/override endpoint | B1 |
| § 3 scope: CoreAPIClient.apply_override | A3 |
| § 3 scope: pre_redacted flag | A1 |
| § 3 scope: sidecar core-binding path | C1–C7 |
| § 3 out-of-scope: jmy.19 bench parity | explicitly NOT in plan ✓ |
| § 4 architecture diagram | covered across C4/C5/C6 wiring + B1 handler |
| § 5.1 request body shape | A2 (`OverrideEvent.to_dict`) |
| § 5.2 status-code mapping | B1 (handler) + C3 (sidecar mapping dict) |
| § 5.3 response envelope with bindings | C3 (`BindingResult`) + C4/C5/C6 (response helpers) |
| § 6 data flow (sequential OTel-then-core, independent) | C4/C5/C6 — bind_to_core called unconditionally after emit_override |
| § 7 privacy locus + pre_redacted | A1 + B1 (handler passes pre_redacted=True) |
| § 8.1 core handler | B1 |
| § 8.2 nthlayer-common changes | A1 + A2 + A3 |
| § 8.3 sidecar changes (CoreConfig, bind_to_core, metric, response, lifecycle) | C1 + C2 + C3 + C4–C7 |
| § 9 operator alert recipe (PromQL) | covered in spec — no code change |
| § 10 testing | each task's Step 1 implements the test cases from § 10; D1 covers the integration smoke |

No gaps.

### Placeholder scan

- No "TBD", "TODO", or "fill in details" lines in any task body.
- The two "match existing fixture pattern" notes in C4 and C7 are not placeholders — they're concrete instructions to read a specific file and reuse a documented pattern. The task body shows the exact code the engineer needs to write; the fixture-fill is the only adaptive piece, and it's bounded ("the same `AdapterConfig(...)` call that existing tests make").
- The webhook test in C6 says "shape that maps to decision_id='dec-1' via existing tests' fixtures" — this is necessary because webhook adapter config is per-deployment; the engineer reads existing webhook tests for the canonical fixture. Not a placeholder, but worth flagging.

### Type / signature consistency

- `BindingResult` defined in C3, consumed in C4 (`accepted_single(decision_id, bindings=binding)`), C5 (`build_batch_response(..., bindings=bindings)`), C6 (`accepted_single(...)`). Names and shapes consistent.
- `bind_to_core(client, event, timeout_seconds)` defined in C3, called identically in C4/C5/C6. ✓
- `CoreAPIClient.apply_override(verdict_id, payload)` defined in A3, called in C3 (`client.apply_override(event.decision_id, payload)`). ✓
- `OverrideEvent.to_dict()` defined in A2, called in C3 (`payload = event.to_dict()`). ✓
- `OverridePrivacyConfig(pre_redacted=True)` defined in A1, passed in B1 (`OverridePrivacyConfig(pre_redacted=True, exclude_reason=False)`). ✓
- `CoreConfig(url, timeout_seconds)` defined in C1, consumed in C4 (`request.app.state.adapter_config.core.timeout_seconds`) and C7 (`config.core.url`). ✓

No mismatches.

---

## Done criteria

- [ ] All 12 tasks marked complete in this plan.
- [ ] `uv run pytest -q` passes cleanly in each of: nthlayer-common, nthlayer-core, nthlayer-override-adapter, nthlayer.
- [ ] No regressions in the four pre-existing test suites.
- [ ] `nthlayer_override_binding_total` appears in the sidecar's `/metrics` output.
- [ ] Bead `opensrm-jmy.18` ready for R5 supervision (`/r5-supervise opensrm-jmy.18`).
