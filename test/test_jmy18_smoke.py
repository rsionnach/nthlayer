"""opensrm-jmy.18 cross-process smoke: real sidecar + real core via ASGI.

Both apps run in-process; the sidecar's CoreAPIClient is rewired to
hit the core app via an ASGI mock transport. Asserts the three end-
to-end claims from the design doc:
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

from nthlayer_common.api_client import CoreAPIClient
from nthlayer_common.overrides import OverridePrivacyConfig
from nthlayer_common.verdicts.models import (
    Judgment,
    Outcome,
    Producer,
    Subject,
    Verdict,
)
from nthlayer_core import server
from nthlayer_core.store import Store
from nthlayer_override_adapter.app import build_app
from nthlayer_override_adapter.config import AdapterConfig, CoreConfig
from nthlayer_override_adapter.metrics import binding_total


def _build_adapter_config() -> AdapterConfig:
    """Build a minimal AdapterConfig for in-process testing.

    No webhook adapters needed; the canonical routes are always registered.
    The URL is synthetic — actual transport is swapped to ASGI below.
    """
    return AdapterConfig(
        adapters=[],
        privacy=OverridePrivacyConfig(),
        core=CoreConfig(url="http://core-stub", timeout_seconds=5.0),
    )


def _make_verdict(vid: str, *, outcome_status: str = "pending") -> Verdict:
    """Canonical Verdict builder — mirrors nthlayer-core/tests/test_api_overrides.py."""
    return Verdict(
        id=vid,
        version=1,
        timestamp=datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc),
        producer=Producer(system="fraud-detect"),
        subject=Subject(
            type="agent_output",
            ref="fraud-detect",
            summary="smoke test verdict",
            service="fraud-detect",
        ),
        judgment=Judgment(action="approve", confidence=0.9),
        outcome=Outcome(status=outcome_status),
        service="fraud-detect",
        verdict_type="action_request",
    )


def _counter_value(counter, **labels) -> float:
    """Read a labelled counter's current value (works across prometheus_client versions)."""
    return counter.labels(**labels)._value.get()


def _wire_asgi_transport(sidecar_app, core_url: str) -> None:
    """Replace the sidecar's CoreAPIClient transport with an in-process ASGI link.

    Called after build_app so the CoreAPIClient instance already exists on
    app.state. We inject a pre-built httpx.AsyncClient with ASGITransport
    pointing at the core app. CoreAPIClient._get_client() re-uses _client
    when it is not None and not closed, so our injected client takes
    precedence over the auto-created one.
    """
    transport = ASGITransport(app=server.app)
    sidecar_app.state.core_client._client = httpx.AsyncClient(
        transport=transport,
        base_url=core_url,
    )


@pytest.mark.asyncio
async def test_sidecar_override_binds_to_core_verdict(tmp_path):
    """End-to-end: sidecar override → core POST → verdict mutated → counter incremented."""
    # 1. Real core with a pending verdict.
    store = Store(str(tmp_path / "core.db"))
    store.put(_make_verdict("dec-smoke-1"))
    server.set_store(store)

    # 2. Real sidecar app.
    cfg = _build_adapter_config()
    sidecar_app = build_app(cfg)

    # 3. Rewire sidecar's CoreAPIClient to talk to core ASGI in-process.
    _wire_asgi_transport(sidecar_app, cfg.core.url)

    # 4. Capture counter before.
    before = _counter_value(binding_total, result="success", reason="ok")

    # 5. Operator POSTs an override to the sidecar.
    with TestClient(sidecar_app, raise_server_exceptions=True) as client:
        resp = client.post(
            "/api/v1/overrides",
            json={
                "decision_id": "dec-smoke-1",
                "service": "fraud-detect",
                "corrected_action": "approve",
                "reviewer": "operator-hash",
                "timestamp": "2026-05-25T10:00:00+00:00",
            },
        )

    # (c) Sidecar response carries bindings with core="ok".
    assert resp.status_code == 201, f"expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["accepted"] == ["dec-smoke-1"]
    assert "bindings" in data, f"'bindings' key absent from response: {data}"
    assert data["bindings"]["dec-smoke-1"]["core"] == "ok", data["bindings"]
    assert data["bindings"]["dec-smoke-1"]["otel"] == "ok", data["bindings"]

    # (b) Core's verdict is mutated in real SQLite.
    # Spec § 7: sidecar applies privacy ONCE; core stores the hashed reviewer.
    # The default OverridePrivacyConfig hashes the reviewer before sending to core.
    from nthlayer_common.overrides import hash_reviewer
    v = store.get("dec-smoke-1")
    assert v is not None
    assert v.outcome.status == "overridden"
    assert v.outcome.override is not None
    assert v.outcome.override.by == hash_reviewer("operator-hash")

    # (a) Counter incremented by exactly 1.
    after = _counter_value(binding_total, result="success", reason="ok")
    assert after == before + 1.0

    # Cleanup global store reference.
    server.set_store(None)


@pytest.mark.asyncio
async def test_sidecar_override_handles_unknown_verdict(tmp_path):
    """Sidecar reports core failure when core has no matching verdict."""
    # Core has NO seeded verdict for "dec-missing".
    store = Store(str(tmp_path / "core.db"))
    server.set_store(store)

    cfg = _build_adapter_config()
    sidecar_app = build_app(cfg)
    _wire_asgi_transport(sidecar_app, cfg.core.url)

    before = _counter_value(binding_total, result="failed", reason="verdict_not_found")

    with TestClient(sidecar_app, raise_server_exceptions=True) as client:
        resp = client.post(
            "/api/v1/overrides",
            json={
                "decision_id": "dec-missing",
                "service": "fraud-detect",
                "corrected_action": "approve",
                "reviewer": "operator-hash",
                "timestamp": "2026-05-25T10:00:00+00:00",
            },
        )

    # Sidecar accepted the request; binding failure surfaces in body.
    assert resp.status_code == 201, f"expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["bindings"]["dec-missing"]["core"] == "failed", data["bindings"]
    assert data["bindings"]["dec-missing"]["reason"] == "verdict_not_found", data["bindings"]

    after = _counter_value(binding_total, result="failed", reason="verdict_not_found")
    assert after == before + 1.0

    server.set_store(None)


@pytest.mark.asyncio
async def test_plaintext_reviewer_is_hashed_at_sidecar_boundary(tmp_path):
    """opensrm-jmy.18: spec § 7 — sidecar applies privacy ONCE; core never holds plaintext.

    Regression test for the privacy leak fixed in the cross-cutting review.
    Posts a clearly-plaintext reviewer through the full sidecar → core path and
    asserts the stored override.by is hash_reviewer(plaintext), not the plaintext
    itself. This test FAILS on the pre-fix code (where bind_to_core received the
    un-masked original event) and PASSES after the fix.
    """
    from nthlayer_common.overrides import hash_reviewer

    # 1. Real core with a pending verdict.
    store = Store(str(tmp_path / "core.db"))
    store.put(_make_verdict("dec-privacy-1"))
    server.set_store(store)

    # 2. Real sidecar with default privacy (plaintext_reviewer=False, pre_redacted=False).
    #    Default config: sidecar MUST hash the reviewer before sending to core.
    cfg = _build_adapter_config()
    sidecar_app = build_app(cfg)
    _wire_asgi_transport(sidecar_app, cfg.core.url)

    # 3. POST with a clearly-plaintext reviewer.
    with TestClient(sidecar_app, raise_server_exceptions=True) as client:
        resp = client.post(
            "/api/v1/overrides",
            json={
                "decision_id": "dec-privacy-1",
                "service": "fraud-detect",
                "corrected_action": "approve",
                "reviewer": "alice@example.com",  # PLAINTEXT — sidecar must hash before sending
                "timestamp": "2026-05-25T10:00:00+00:00",
            },
        )

    assert resp.status_code == 201, f"expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["accepted"] == ["dec-privacy-1"]
    assert data["bindings"]["dec-privacy-1"]["core"] == "ok", data["bindings"]

    # 4. Core must have stored the SHA-256 hash, not the plaintext.
    v = store.get("dec-privacy-1")
    expected_hash = hash_reviewer("alice@example.com")
    assert v.outcome.override.by == expected_hash, (
        f"Privacy leak: core stored {v.outcome.override.by!r}, "
        f"expected hash {expected_hash!r}"
    )
    # Belt-and-suspenders: the plaintext string must not appear in stored data.
    assert "alice@example.com" not in v.outcome.override.by

    server.set_store(None)
