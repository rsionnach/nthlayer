# opensrm-dpws Implementation Plan — Populate `trigger_service` on Retrospectives

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `trigger_service` (and the worker-path `declared_dependencies_by_service`) into both retrospective code paths so jmy.21's `add_dependency` recommendation type actually fires in production instead of emitting `log.debug` + `[]`.

**Architecture:** Two divergent retrospective paths (CLI verdict via `build_retrospective`, worker assessment via `LearnRetrospectiveModule`) each populate a new `trigger_service` key using a shared `_resolve_trigger_service` helper (correlation-first, subject-fallback precedence). The worker path additionally fetches manifests via `CoreAPIClient.get_manifests()` and populates `declared_dependencies_by_service` only when the trigger's own manifest is present in the result. A single new helper in `nthlayer_common.manifest` (`extract_declared_dependencies`) unifies the dict-of-list construction across both paths.

**Tech Stack:** Python 3.11+, async (`asyncio`), pytest + pytest-asyncio, structlog, dataclasses. Edits land in `nthlayer-common/` and `nthlayer-workers/`.

**Spec:** `nthlayer/docs/superpowers/specs/2026-05-29-dpws-trigger-service-design.md` (committed at `nthlayer@31c3b03`).

---

## File Structure

**New files:**
- `nthlayer-workers/src/nthlayer_workers/learn/_trigger.py` — module-level `resolve_trigger_service` helper (single source of truth for the precedence rule).
- `nthlayer-workers/tests/learn/test_retrospective_trigger.py` — CLI-path trigger_service tests.

**Modified files:**
- `nthlayer-common/src/nthlayer_common/manifest/parser/_shared.py` — add `extract_declared_dependencies` polymorphic helper.
- `nthlayer-common/src/nthlayer_common/manifest/__init__.py` — export `extract_declared_dependencies`.
- `nthlayer-common/tests/test_manifest_parser.py` — 4 new tests covering both branches of the helper.
- `nthlayer-workers/src/nthlayer_workers/learn/retrospective.py` — call shared helper; resolve + write `trigger_service`.
- `nthlayer-workers/src/nthlayer_workers/learn/worker.py` — fetch manifests; resolve trigger; populate both new keys per § 3.4 policy.
- `nthlayer-workers/tests/learn/test_learn_worker.py` — 5 new tests under `TestRetrospectiveCycle`.

**Task ordering rationale:** Land the `nthlayer-common` helper first (no dependents). Then the worker `_trigger.py` helper (consumed by both other modules). Then CLI-path wiring. Then worker-path wiring. This minimises rebases if any review pass surfaces issues — earlier tasks don't depend on later ones.

---

## Task 1: Shared `extract_declared_dependencies` helper in `nthlayer-common`

**Files:**
- Modify: `nthlayer-common/src/nthlayer_common/manifest/parser/_shared.py`
- Modify: `nthlayer-common/src/nthlayer_common/manifest/__init__.py`
- Test: `nthlayer-common/tests/test_manifest_parser.py`

- [ ] **Step 1.1: Write the failing tests**

Append the following test class to `nthlayer-common/tests/test_manifest_parser.py` (at end of file, after the existing classes):

```python
class TestExtractDeclaredDependencies:
    """opensrm-dpws: shared declared-dep extraction across CLI (Manifest
    dataclasses) and worker (raw HTTP dicts) retrospective paths."""

    def test_extract_declared_dependencies_from_manifests(self):
        """Manifest-dataclass input → {service: [dep_name, ...]}."""
        from nthlayer_common.manifest import (
            Dependency,
            ReliabilityManifest,
            extract_declared_dependencies,
        )

        m_a = ReliabilityManifest(
            name="svc-a", team="t", tier="standard", type="api",
            dependencies=[
                Dependency(name="svc-b", type="api"),
                Dependency(name="svc-c", type="api"),
            ],
        )
        m_b = ReliabilityManifest(
            name="svc-b", team="t", tier="standard", type="api",
            dependencies=None,
        )

        result = extract_declared_dependencies(
            from_manifests={"svc-a": m_a, "svc-b": m_b},
        )
        assert result == {"svc-a": ["svc-b", "svc-c"], "svc-b": []}

    def test_extract_declared_dependencies_from_dicts(self):
        """HTTP dict input (GET /manifests wire shape) → same output shape."""
        from nthlayer_common.manifest import extract_declared_dependencies

        manifest_dicts = [
            {"name": "svc-a", "dependencies": [
                {"name": "svc-b", "type": "api"},
                {"name": "svc-c", "type": "api"},
            ]},
            {"name": "svc-b", "dependencies": []},
            {"name": "svc-c"},  # missing dependencies key entirely
        ]
        result = extract_declared_dependencies(from_dicts=manifest_dicts)
        assert result == {
            "svc-a": ["svc-b", "svc-c"],
            "svc-b": [],
            "svc-c": [],
        }

    def test_extract_declared_dependencies_requires_exactly_one_input(self):
        """Neither / both supplied → ValueError."""
        import pytest
        from nthlayer_common.manifest import extract_declared_dependencies

        with pytest.raises(ValueError, match="exactly one"):
            extract_declared_dependencies()
        with pytest.raises(ValueError, match="exactly one"):
            extract_declared_dependencies(
                from_manifests={}, from_dicts=[],
            )

    def test_extract_declared_dependencies_skips_dict_with_no_name(self):
        """Dict entries without a name key are silently skipped (mirrors
        the _extract_service_slos precedent in observe/worker.py)."""
        from nthlayer_common.manifest import extract_declared_dependencies

        manifest_dicts = [
            {"name": "svc-a", "dependencies": [{"name": "svc-b"}]},
            {"dependencies": [{"name": "svc-x"}]},  # no name → skip
            {"name": "", "dependencies": []},  # empty-string name → skip
        ]
        result = extract_declared_dependencies(from_dicts=manifest_dicts)
        assert result == {"svc-a": ["svc-b"]}
```

- [ ] **Step 1.2: Run tests to verify they fail**

```
cd nthlayer-common && uv run pytest tests/test_manifest_parser.py::TestExtractDeclaredDependencies -v
```

Expected: 4 FAIL with `ImportError: cannot import name 'extract_declared_dependencies' from 'nthlayer_common.manifest'`.

- [ ] **Step 1.3: Add helper implementation to `_shared.py`**

Append to `nthlayer-common/src/nthlayer_common/manifest/parser/_shared.py`:

```python
def extract_declared_dependencies(
    *,
    from_manifests: dict[str, Any] | None = None,
    from_dicts: list[dict] | None = None,
) -> dict[str, list[str]]:
    """Build a {service_name: [dep_name, ...]} map from either Manifest
    dataclass instances (CLI/YAML path) or raw HTTP wire dicts (worker
    path). Exactly one of ``from_manifests`` / ``from_dicts`` must be
    supplied.

    Used by ``nthlayer-workers/learn`` retrospective generation
    (opensrm-jmy.21 / opensrm-dpws) to populate
    ``declared_dependencies_by_service`` on the retrospective payload.
    Downstream consumers (``_add_dependency_recommendations``) treat
    this map as the ground-truth view of operator-declared deps.

    A manifest with ``dependencies = None`` produces an empty list for
    that service; the absence of declared deps is itself information
    downstream consumers want to record. Dict entries without a
    non-empty ``name`` are silently skipped (mirrors the
    ``_extract_service_slos`` precedent in observe/worker.py).
    """
    if (from_manifests is None) == (from_dicts is None):
        raise ValueError(
            "extract_declared_dependencies: supply exactly one of "
            "from_manifests= or from_dicts="
        )

    if from_manifests is not None:
        return {
            service_name: [dep.name for dep in (manifest.dependencies or [])]
            for service_name, manifest in from_manifests.items()
        }

    out: dict[str, list[str]] = {}
    for m in from_dicts or []:
        name = m.get("name")
        if not name:
            continue
        out[name] = [
            d.get("name") for d in (m.get("dependencies") or [])
            if d.get("name")
        ]
    return out
```

- [ ] **Step 1.4: Export from `manifest/__init__.py`**

Add `extract_declared_dependencies` to the import block in `nthlayer-common/src/nthlayer_common/manifest/__init__.py`. Insert after the `LegacyFormatWarning` import block:

```python
from nthlayer_common.manifest.parser._shared import extract_declared_dependencies
```

Add `"extract_declared_dependencies"` to `__all__` (after `"is_manifest_file"`, in the Loader section).

- [ ] **Step 1.5: Run tests to verify they pass**

```
cd nthlayer-common && uv run pytest tests/test_manifest_parser.py::TestExtractDeclaredDependencies -v
```

Expected: 4 PASS.

- [ ] **Step 1.6: Run the full nthlayer-common test suite + lint**

```
cd nthlayer-common && uv run pytest -q && uv run ruff check src/ tests/
```

Expected: previous baseline (758+) tests + 4 new = pass. Lint clean.

- [ ] **Step 1.7: Commit**

```
cd nthlayer-common && git add src/nthlayer_common/manifest/parser/_shared.py src/nthlayer_common/manifest/__init__.py tests/test_manifest_parser.py && git commit -m "feat(manifest): extract_declared_dependencies polymorphic helper

Single source of truth for {service: [dep, ...]} map construction
across CLI (Manifest dataclass) and worker (HTTP dict) paths.
Foundation for opensrm-dpws retrospective trigger_service wiring.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `resolve_trigger_service` helper in `nthlayer-workers/learn/_trigger.py`

**Files:**
- Create: `nthlayer-workers/src/nthlayer_workers/learn/_trigger.py`
- Test: covered indirectly via Task 3 / Task 4 tests; helper is tested at the call sites (no dedicated test file — the precedence rule is fully exercised via the CLI and worker test suites).

- [ ] **Step 2.1: Create the helper file**

Create `nthlayer-workers/src/nthlayer_workers/learn/_trigger.py`:

```python
"""Shared precedence rule for resolving the incident's trigger service.

opensrm-dpws: used by both retrospective code paths (CLI
``build_retrospective`` and worker ``LearnRetrospectiveModule``) so
the precedence rule has a single home — the correlator's grouping
is always preferred over the incident's primary-service field.
"""
from __future__ import annotations


def resolve_trigger_service(
    correlation_candidates: list[str | None],
    fallback: str | None,
) -> str | None:
    """Return the first non-empty string from ``correlation_candidates``,
    else ``fallback`` if non-empty, else ``None``.

    Correlation-first reflects the correlator's grouping IS the trigger
    context (its ``subject.service`` is literally "the service the
    correlator anchored a session window on"). The ``fallback`` is the
    incident verdict's ``subject.service`` (CLI) or the snapshot's
    top-level ``service`` field (worker) — both name the primary service
    of the incident when no correlation context exists.

    Returning ``None`` is the signal to OMIT the trigger_service key
    from the retrospective payload entirely (back-compat with jmy.21's
    ``log.debug + []`` no-rec path in ``_add_dependency_recommendations``).
    """
    for candidate in correlation_candidates:
        if candidate:
            return candidate
    return fallback or None
```

- [ ] **Step 2.2: Smoke-import check**

```
cd nthlayer-workers && uv run python -c "from nthlayer_workers.learn._trigger import resolve_trigger_service; print(resolve_trigger_service(['svc-a'], 'svc-b'))"
```

Expected: `svc-a`.

- [ ] **Step 2.3: Commit**

```
cd nthlayer-workers && git add src/nthlayer_workers/learn/_trigger.py && git commit -m "feat(learn): resolve_trigger_service precedence helper

Correlation-first, subject-fallback rule shared by CLI build_retrospective
and worker LearnRetrospectiveModule (opensrm-dpws). Tested at call sites.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Wire CLI path — `build_retrospective` writes `metadata.custom["trigger_service"]`

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/retrospective.py`
- Create: `nthlayer-workers/tests/learn/test_retrospective_trigger.py`

- [ ] **Step 3.1: Write the failing tests**

Create `nthlayer-workers/tests/learn/test_retrospective_trigger.py`:

```python
"""CLI-path retrospective trigger_service wiring (opensrm-dpws)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from nthlayer_common.verdicts.core import create
from nthlayer_common.verdicts.store import MemoryStore
from nthlayer_workers.learn.retrospective import build_retrospective


def _make_incident(service: str | None) -> "Verdict":
    """Create an incident verdict with the given subject.service."""
    return create(
        subject={
            "type": "incident",
            "ref": "INC-1",
            "service": service,
            "summary": "test incident",
        },
        judgment={"action": "flag", "confidence": 0.9, "reasoning": "test"},
        producer={"system": "test"},
        metadata={"custom": {"incident_id": "INC-1"}},
    )


def _make_correlation(service: str | None) -> "Verdict":
    return create(
        subject={
            "type": "correlation",
            "ref": "csn-1",
            "service": service,
            "summary": "correlation snapshot",
        },
        judgment={"action": "flag", "confidence": 0.7, "reasoning": "test"},
        producer={"system": "nthlayer-correlate"},
        metadata={"custom": {"root_causes": []}},
    )


class TestTriggerServiceResolution:
    """opensrm-dpws: build_retrospective populates metadata.custom['trigger_service']."""

    def test_trigger_service_from_correlation_verdict(self):
        """Correlation verdict's subject.service wins over incident's."""
        store = MemoryStore()
        incident = _make_incident("fallback-service")
        correlation = _make_correlation("fraud-detect")
        store.put(incident)
        store.put(correlation)
        # Link correlation as ancestor of incident
        incident.lineage.context = [correlation.id]
        store.put(incident)

        retro = build_retrospective(incident.id, store)
        assert retro.metadata.custom["trigger_service"] == "fraud-detect"

    def test_trigger_service_fallback_to_incident_subject(self):
        """No correlation in lineage → falls back to incident.subject.service."""
        store = MemoryStore()
        incident = _make_incident("payments")
        store.put(incident)

        retro = build_retrospective(incident.id, store)
        assert retro.metadata.custom["trigger_service"] == "payments"

    def test_trigger_service_omitted_when_neither(self):
        """Both correlation absent and incident.subject.service empty → key absent."""
        store = MemoryStore()
        incident = _make_incident(None)
        store.put(incident)

        retro = build_retrospective(incident.id, store)
        assert "trigger_service" not in retro.metadata.custom

    def test_trigger_service_skips_empty_correlation_subject_to_fallback(self):
        """Correlation present but subject.service is empty → fallback wins."""
        store = MemoryStore()
        incident = _make_incident("payments")
        correlation = _make_correlation(None)
        store.put(incident)
        store.put(correlation)
        incident.lineage.context = [correlation.id]
        store.put(incident)

        retro = build_retrospective(incident.id, store)
        assert retro.metadata.custom["trigger_service"] == "payments"
```

- [ ] **Step 3.2: Run tests to verify they fail**

```
cd nthlayer-workers && uv run pytest tests/learn/test_retrospective_trigger.py -v
```

Expected: 4 FAIL with `KeyError: 'trigger_service'` (or "not in custom") — the key isn't written yet.

- [ ] **Step 3.3: Modify `retrospective.py` — import the helper**

In `nthlayer-workers/src/nthlayer_workers/learn/retrospective.py`, add to the imports block (alongside the existing `nthlayer_common` imports):

```python
from nthlayer_common.manifest import extract_declared_dependencies
from nthlayer_workers.learn._trigger import resolve_trigger_service
```

- [ ] **Step 3.4: Replace `_extract_declared_dependencies` with a wrapper**

In `retrospective.py`, replace the body of `_extract_declared_dependencies` (lines 249–265) with:

```python
def _extract_declared_dependencies(
    loaded_manifests: dict[str, Any],
) -> dict[str, list[str]]:
    """Wrapper around the shared helper (opensrm-dpws). The CLI path
    works with Manifest dataclass instances loaded via load_manifest().
    """
    return extract_declared_dependencies(from_manifests=loaded_manifests)
```

- [ ] **Step 3.5: Populate `trigger_service` in `build_retrospective`**

In `build_retrospective` (around line 100, after `correlation_verdicts` is populated and before the `metadata={"custom": ...}` dict is constructed), add:

```python
    # opensrm-dpws: resolve trigger_service via correlation-first /
    # subject-fallback precedence. None → key omitted (back-compat with
    # jmy.21's _add_dependency_recommendations no-rec path).
    trigger_service = resolve_trigger_service(
        [v.subject.service for v in correlation_verdicts],
        incident.subject.service,
    )
```

Then modify the `metadata={"custom": {...}}` block: add `trigger_service` conditionally. Replace the block (around lines 149–163) with:

```python
    custom: dict[str, Any] = {
        "incident_verdict_id": incident_verdict_id,
        "duration_minutes": round(duration_minutes, 1),
        "decisions_affected": decisions_affected,
        "root_cause": root_cause,
        "blast_radius": [
            s.get("service", s) if isinstance(s, dict) else s
            for s in blast_radius
        ],
        "verdict_count": len(all_verdicts),
        "timeline": timeline[:20],  # Cap at 20 entries
        "financial_impact": financial_impact,
        "recommendations": recommendations,
        "declared_dependencies_by_service": declared_dependencies_by_service,
    }
    if trigger_service is not None:
        custom["trigger_service"] = trigger_service

    retro = create(
        subject={...},  # unchanged
        judgment={...},  # unchanged
        producer={"system": "nthlayer-learn"},
        metadata={"custom": custom},
    )
```

(Preserve the existing `subject` / `judgment` blocks — only the `metadata` argument changes.)

- [ ] **Step 3.6: Run tests to verify they pass**

```
cd nthlayer-workers && uv run pytest tests/learn/test_retrospective_trigger.py -v
```

Expected: 4 PASS.

- [ ] **Step 3.7: Run financial-impact tests to verify the metadata reshape didn't regress**

```
cd nthlayer-workers && uv run pytest tests/learn/test_retrospective_financial.py -v
```

Expected: 10 PASS (the previous baseline). If any fail because they now see a `trigger_service` key in `metadata.custom` they weren't expecting, that's a test that asserts on full-dict equality — update it to either ignore the new key or include it.

- [ ] **Step 3.8: Run the full `nthlayer-workers` test suite + lint**

```
cd nthlayer-workers && uv run pytest -q && uv run ruff check src/ tests/
```

Expected: 1870 baseline + 4 new = 1874 pass. Lint clean.

- [ ] **Step 3.9: Commit**

```
cd nthlayer-workers && git add src/nthlayer_workers/learn/retrospective.py tests/learn/test_retrospective_trigger.py && git commit -m "feat(learn): populate trigger_service on retrospective verdicts

CLI-path build_retrospective writes metadata.custom['trigger_service']
using the correlation-first / subject-fallback precedence rule. Omits
the key entirely when neither source resolves (jmy.21 back-compat).
Also routes declared_dependencies extraction through the new shared
helper. opensrm-dpws.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Wire worker path — `LearnRetrospectiveModule` populates `trigger_service` + `declared_dependencies_by_service`

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/worker.py`
- Modify: `nthlayer-workers/tests/learn/test_learn_worker.py`

- [ ] **Step 4.1: Write the failing tests**

Append to the existing `TestRetrospectiveCycle` class in `nthlayer-workers/tests/learn/test_learn_worker.py` (or add a new sibling class `TestRetrospectiveTriggerService` if class size becomes unwieldy). All tests follow the existing pattern: `AsyncMock` `CoreAPIClient`, `process_cycle()`, then inspect `submit_assessment` call args.

```python
class TestRetrospectiveTriggerService:
    """opensrm-dpws: worker-path retrospective populates trigger_service
    and (when trigger's manifest is present) declared_dependencies_by_service."""

    async def test_retrospective_includes_trigger_service(self):
        """snapshot.data.domain.service → data['trigger_service']."""
        from unittest.mock import AsyncMock
        from nthlayer_workers.learn.worker import LearnRetrospectiveModule
        from nthlayer_common.api_client import APIResult

        client = AsyncMock()
        client.get_assessments.return_value = APIResult(
            ok=True, status_code=200,
            data=[{
                "id": "csn-1",
                "service": "fraud-detect",
                "created_at": "2026-05-29T00:00:00+00:00",
                "data": {
                    "domain": {"service": "fraud-detect", "environment": "prod"},
                    "window": {"opened_at": "2026-05-29T00:00:00+00:00",
                               "closed_at": "2026-05-29T00:05:00+00:00",
                               "duration_seconds": 300},
                    "affected_services": ["fraud-detect", "svc-x"],
                },
            }],
        )
        client.get_verdicts.return_value = APIResult(ok=True, status_code=200, data=[])
        client.get_manifests.return_value = APIResult(
            ok=True, status_code=200,
            data=[
                {"name": "fraud-detect", "dependencies": [
                    {"name": "svc-known", "type": "api"},
                ]},
            ],
        )
        client.submit_assessment.return_value = APIResult(ok=True, status_code=200, data={})

        module = LearnRetrospectiveModule(client=client)
        await module.process_cycle()

        # Inspect the submitted assessment
        submitted = client.submit_assessment.call_args.args[0]
        data = submitted["data"]["data"]
        assert data["trigger_service"] == "fraud-detect"

    async def test_retrospective_trigger_service_fallback_to_top_level_service(self):
        """data.domain.service absent → uses snapshot['service']."""
        from unittest.mock import AsyncMock
        from nthlayer_workers.learn.worker import LearnRetrospectiveModule
        from nthlayer_common.api_client import APIResult

        client = AsyncMock()
        client.get_assessments.return_value = APIResult(
            ok=True, status_code=200,
            data=[{
                "id": "csn-2",
                "service": "payments",
                "created_at": "2026-05-29T00:00:00+00:00",
                "data": {
                    "domain": {},
                    "window": {"opened_at": "2026-05-29T00:00:00+00:00",
                               "closed_at": "2026-05-29T00:05:00+00:00",
                               "duration_seconds": 300},
                    "affected_services": ["payments"],
                },
            }],
        )
        client.get_verdicts.return_value = APIResult(ok=True, status_code=200, data=[])
        client.get_manifests.return_value = APIResult(
            ok=True, status_code=200,
            data=[{"name": "payments", "dependencies": []}],
        )
        client.submit_assessment.return_value = APIResult(ok=True, status_code=200, data={})

        module = LearnRetrospectiveModule(client=client)
        await module.process_cycle()

        submitted = client.submit_assessment.call_args.args[0]
        data = submitted["data"]["data"]
        assert data["trigger_service"] == "payments"

    async def test_retrospective_includes_declared_dependencies(self):
        """get_manifests returns trigger's manifest → declared_deps populated."""
        from unittest.mock import AsyncMock
        from nthlayer_workers.learn.worker import LearnRetrospectiveModule
        from nthlayer_common.api_client import APIResult

        client = AsyncMock()
        client.get_assessments.return_value = APIResult(
            ok=True, status_code=200,
            data=[{
                "id": "csn-3", "service": "fraud-detect",
                "created_at": "2026-05-29T00:00:00+00:00",
                "data": {
                    "domain": {"service": "fraud-detect"},
                    "window": {"opened_at": "2026-05-29T00:00:00+00:00",
                               "closed_at": "2026-05-29T00:05:00+00:00",
                               "duration_seconds": 300},
                    "affected_services": ["fraud-detect"],
                },
            }],
        )
        client.get_verdicts.return_value = APIResult(ok=True, status_code=200, data=[])
        client.get_manifests.return_value = APIResult(
            ok=True, status_code=200,
            data=[
                {"name": "fraud-detect", "dependencies": [
                    {"name": "svc-known", "type": "api"},
                ]},
                {"name": "svc-known", "dependencies": []},
            ],
        )
        client.submit_assessment.return_value = APIResult(ok=True, status_code=200, data={})

        module = LearnRetrospectiveModule(client=client)
        await module.process_cycle()

        submitted = client.submit_assessment.call_args.args[0]
        data = submitted["data"]["data"]
        assert data["declared_dependencies_by_service"] == {
            "fraud-detect": ["svc-known"],
            "svc-known": [],
        }

    async def test_retrospective_omits_declared_deps_when_manifest_fetch_fails(self):
        """get_manifests returns ok=False → declared_deps key absent, no crash."""
        from unittest.mock import AsyncMock
        from nthlayer_workers.learn.worker import LearnRetrospectiveModule
        from nthlayer_common.api_client import APIResult

        client = AsyncMock()
        client.get_assessments.return_value = APIResult(
            ok=True, status_code=200,
            data=[{
                "id": "csn-4", "service": "fraud-detect",
                "created_at": "2026-05-29T00:00:00+00:00",
                "data": {
                    "domain": {"service": "fraud-detect"},
                    "window": {"opened_at": "2026-05-29T00:00:00+00:00",
                               "closed_at": "2026-05-29T00:05:00+00:00",
                               "duration_seconds": 300},
                    "affected_services": ["fraud-detect"],
                },
            }],
        )
        client.get_verdicts.return_value = APIResult(ok=True, status_code=200, data=[])
        client.get_manifests.return_value = APIResult(
            ok=False, status_code=503, data=None, error="connection_failed",
        )
        client.submit_assessment.return_value = APIResult(ok=True, status_code=200, data={})

        module = LearnRetrospectiveModule(client=client)
        await module.process_cycle()

        submitted = client.submit_assessment.call_args.args[0]
        data = submitted["data"]["data"]
        assert "declared_dependencies_by_service" not in data
        # trigger_service should still be set
        assert data["trigger_service"] == "fraud-detect"

    async def test_retrospective_omits_declared_deps_when_trigger_manifest_absent(self):
        """get_manifests succeeds but trigger's own manifest missing → declared_deps omitted."""
        from unittest.mock import AsyncMock
        from nthlayer_workers.learn.worker import LearnRetrospectiveModule
        from nthlayer_common.api_client import APIResult

        client = AsyncMock()
        client.get_assessments.return_value = APIResult(
            ok=True, status_code=200,
            data=[{
                "id": "csn-5", "service": "fraud-detect",
                "created_at": "2026-05-29T00:00:00+00:00",
                "data": {
                    "domain": {"service": "fraud-detect"},
                    "window": {"opened_at": "2026-05-29T00:00:00+00:00",
                               "closed_at": "2026-05-29T00:05:00+00:00",
                               "duration_seconds": 300},
                    "affected_services": ["fraud-detect", "svc-x"],
                },
            }],
        )
        client.get_verdicts.return_value = APIResult(ok=True, status_code=200, data=[])
        # Catalogue has svc-x but NOT fraud-detect (the trigger)
        client.get_manifests.return_value = APIResult(
            ok=True, status_code=200,
            data=[{"name": "svc-x", "dependencies": []}],
        )
        client.submit_assessment.return_value = APIResult(ok=True, status_code=200, data={})

        module = LearnRetrospectiveModule(client=client)
        await module.process_cycle()

        submitted = client.submit_assessment.call_args.args[0]
        data = submitted["data"]["data"]
        assert "declared_dependencies_by_service" not in data
        assert data["trigger_service"] == "fraud-detect"
```

- [ ] **Step 4.2: Run the new tests to verify they fail**

```
cd nthlayer-workers && uv run pytest tests/learn/test_learn_worker.py::TestRetrospectiveTriggerService -v
```

Expected: 5 FAIL — `data["trigger_service"]` missing / `KeyError`.

- [ ] **Step 4.3: Modify `worker.py` — imports**

In `nthlayer-workers/src/nthlayer_workers/learn/worker.py`, add to the imports block (after the existing `nthlayer_common` imports):

```python
from nthlayer_common.manifest import extract_declared_dependencies

from nthlayer_workers.learn._trigger import resolve_trigger_service
```

- [ ] **Step 4.4: Wire `_generate_retrospective`**

In `worker.py`, modify `LearnRetrospectiveModule._generate_retrospective` (lines 243–312). Replace the function body with:

```python
    async def _generate_retrospective(self, snapshot: dict) -> bool:
        """Generate and submit a retrospective assessment. Returns True on success."""
        snapshot_data = snapshot.get("data", {})
        domain = snapshot_data.get("domain", {})
        service = snapshot.get("service", domain.get("service", "unknown"))

        # opensrm-dpws: resolve trigger_service via correlation-first /
        # snapshot-service-fallback precedence. The snapshot's
        # data.domain.service IS the correlator's grouping anchor; the
        # top-level service field is the same value emitted at submit
        # time but kept independent for resilience.
        trigger_service = resolve_trigger_service(
            [domain.get("service")],
            snapshot.get("service"),
        )

        # Build verdict chain by querying verdicts for the affected service
        # during the snapshot window. Cannot use get_ancestors on an assessment
        # ID — that endpoint operates on verdict IDs only.
        chain = []
        window = snapshot_data.get("window", {})
        opened_at = window.get("opened_at")
        closed_at = window.get("closed_at")
        if opened_at and closed_at:
            chain_result = await self.client.get_verdicts(
                service=service,
                created_after=opened_at,
                created_before=closed_at,
                limit=100,
            )
            if chain_result.ok and chain_result.data:
                chain = chain_result.data

        # Build timeline
        timeline = _build_chain_timeline(chain)

        # Compute metrics
        resolved_count = sum(
            1 for v in chain
            if v.get("outcome", {}).get("status") not in (None, "pending")
        )
        pending_count = len(chain) - resolved_count

        # Extract root cause from correlation data
        root_cause = snapshot_data.get("correlation_groups", [{}])[0] if snapshot_data.get("correlation_groups") else None

        # opensrm-dpws: declared_dependencies_by_service — populate only
        # when the trigger's own manifest is in the API result.
        # _add_dependency_recommendations reads declared_map.get(trigger)
        # so non-trigger gaps are harmless; trigger gap → over-broad recs.
        declared_dependencies_by_service: dict[str, list[str]] | None = None
        if trigger_service:
            manifests_result = await self.client.get_manifests()
            if not manifests_result.ok:
                logger.warning(
                    "learn_manifest_fetch_failed",
                    error=manifests_result.error,
                )
            elif not manifests_result.data:
                logger.info("learn_manifest_catalogue_empty")
            else:
                manifest_names = {
                    m.get("name") for m in manifests_result.data if m.get("name")
                }
                if trigger_service not in manifest_names:
                    logger.warning(
                        "learn_trigger_manifest_absent",
                        service=trigger_service,
                    )
                else:
                    declared_dependencies_by_service = extract_declared_dependencies(
                        from_dicts=manifests_result.data,
                    )

        # Build recommendations
        recommendations = _generate_recommendations(chain, snapshot_data)

        now = datetime.now(timezone.utc)
        duration = snapshot_data.get("window", {}).get("duration_seconds", 0)

        data: dict[str, Any] = {
            "correlation_snapshot_id": snapshot.get("id"),
            "duration_minutes": duration / 60 if duration else 0,
            "decisions_affected": sum(1 for v in chain if v.get("type") == "quality_breach"),
            "verdict_count": len(chain),
            "root_cause": root_cause,
            "blast_radius": snapshot_data.get("affected_services", []),
            "timeline": timeline[:20],
            "recommendations": recommendations,
            "outcome_coverage": {
                "resolved": resolved_count,
                "pending": pending_count,
                "total": len(chain),
            },
        }
        if trigger_service is not None:
            data["trigger_service"] = trigger_service
        if declared_dependencies_by_service is not None:
            data["declared_dependencies_by_service"] = declared_dependencies_by_service

        assessment = {
            "id": f"retro-{service}-{uuid.uuid4().hex[:8]}",
            "created_at": now.isoformat(),
            "kind": "retrospective",
            "service": service,
            "data": data,
        }

        result = await self.client.submit_assessment(wrap_assessment(assessment, component="learn"))
        if not result.ok:
            logger.warning("retrospective_submit_failed", service=service, error=result.error)
            return False
        logger.info("retrospective_emitted", service=service, verdict_count=len(chain))
        return True
```

- [ ] **Step 4.5: Run the new tests to verify they pass**

```
cd nthlayer-workers && uv run pytest tests/learn/test_learn_worker.py::TestRetrospectiveTriggerService -v
```

Expected: 5 PASS.

- [ ] **Step 4.6: Run the full `TestRetrospectiveCycle` suite to check for regressions**

```
cd nthlayer-workers && uv run pytest tests/learn/test_learn_worker.py -v
```

Expected: prior `TestRetrospectiveCycle` tests still pass. If `test_snapshot_triggers_retrospective` or `test_outcome_coverage_reported` now fail because they assert on full `data` dict equality, update them to include the new `trigger_service` / `declared_dependencies_by_service` keys (or assert on individual keys instead).

- [ ] **Step 4.7: Run the full `nthlayer-workers` test suite + lint**

```
cd nthlayer-workers && uv run pytest -q && uv run ruff check src/ tests/
```

Expected: 1874 baseline (after Task 3) + 5 new = 1879 pass. Lint clean.

- [ ] **Step 4.8: Commit**

```
cd nthlayer-workers && git add src/nthlayer_workers/learn/worker.py tests/learn/test_learn_worker.py && git commit -m "feat(learn): populate trigger_service on worker-path retrospectives

LearnRetrospectiveModule resolves trigger_service via the same
correlation-first precedence as the CLI path, then fetches manifests
via client.get_manifests() to populate declared_dependencies_by_service
only when the trigger's own manifest is in the result (trigger-narrow
coverage policy per design § 3.4). Non-trigger gaps are harmless;
trigger gap → log warning + omit field. opensrm-dpws.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Ecosystem regression sweep + bead close

**Files:** None modified. Verifies all five Python repos are clean.

- [ ] **Step 5.1: Run nthlayer-common test suite**

```
cd nthlayer-common && uv run pytest -q
```

Expected: 762 pass (758 baseline + 4 new).

- [ ] **Step 5.2: Run nthlayer-workers test suite**

```
cd nthlayer-workers && uv run pytest -q
```

Expected: 1879 pass (1870 baseline + 4 CLI + 5 worker).

- [ ] **Step 5.3: Check git status across all repos**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem && for d in nthlayer-common nthlayer-workers nthlayer nthlayer-core nthlayer-bench opensrm; do echo "--- $d ---"; (cd $d && git status --short && git log --oneline -3); done
```

Expected: All repos clean. nthlayer-common HEAD = Task 1 commit. nthlayer-workers HEAD = Task 4 commit. `nthlayer` HEAD = spec commit (`31c3b03`).

- [ ] **Step 5.4: Invoke /r5-supervise dpws**

```
/r5-supervise dpws
```

Expected: 4 sequential R5 passes (Correctness / Clarity / Edge Cases / Excellence) each dispatching a reviewer subagent, applying fixes, committing with `r5(<pass>):` prefix, and re-dispatching until clean. When all four are clean the supervisor asks "all four clean — confirm bead close?"

- [ ] **Step 5.5: Close the bead**

After R5 sign-off, mark opensrm-dpws CLOSED:

```
cd opensrm && bd update dpws --state closed --note "Implemented in nthlayer-workers (Task 3 + Task 4) and nthlayer-common (Task 1) + R5 reviewed. trigger_service now populated on both retrospective code paths; declared_dependencies_by_service populated on worker path when trigger's manifest is present."
```

Verify with:

```
cd opensrm && bd show dpws | head -5
```

Expected: `[● P3 · CLOSED]`.

---

## Self-Review Notes

**Spec coverage map** (every § in the spec is implemented by a numbered step):
- § 3.1 (correlation-first / subject-fallback precedence) → Task 2 (helper), Task 3.5 (CLI call site), Task 4.4 (worker call site)
- § 3.2 (omit when None) → Task 3.5 conditional `if trigger_service is not None`, Task 4.4 same pattern
- § 3.3 (shared `extract_declared_dependencies`) → Task 1 (helper + 4 tests)
- § 3.4 (worker trigger-narrow coverage policy with 3 fail modes) → Task 4.4 (4-branch if/elif/elif/else with warn/info/warn/populate), Task 4.1 tests (`omits_when_manifest_fetch_fails`, `omits_when_trigger_manifest_absent`)
- § 3.5 (CLI coverage unchanged) → Task 3 deliberately does not touch the CLI coverage path
- § 3.6 (`trigger_service` and `declared_deps` decoupled) → Task 4.1 `omits_when_manifest_fetch_fails` test asserts `trigger_service` still set even when declared_deps omitted
- § 3.7 (integration test deferred to jmy.6) → no task; documented in plan header and spec § 3.7
- § 5 (test surface ~9 tests) → 4 in Task 1 + 4 in Task 3 + 5 in Task 4 = 13 tests (slightly more than the 9 baseline estimate because the worker-path coverage policy splits into 3 distinct failure-mode tests + 2 happy-path tests)

**Placeholder scan:** No "TBD" / "TODO" / "fill in" / "similar to" markers. Every code block contains complete, runnable code. Every step has an exact command and expected output.

**Type consistency:** Helper signature `resolve_trigger_service(correlation_candidates: list[str | None], fallback: str | None) -> str | None` consistent across Task 2 declaration, Task 3.5 call, Task 4.4 call. `extract_declared_dependencies(*, from_manifests=..., from_dicts=...) -> dict[str, list[str]]` consistent across Task 1, Task 3.4 wrapper, Task 4.4 call. `client.get_manifests()` returns `APIResult` with `data: list[dict]` — consistent in Task 4.1 mocks and Task 4.4 implementation.
