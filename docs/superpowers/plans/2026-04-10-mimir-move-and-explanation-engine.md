# Mimir Client Move + Explanation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move MimirRulerProvider to clients/ with BaseHTTPClient resilience, and build an ExplanationEngine in nthlayer-observe with shared data model in nthlayer-common.

**Architecture:** Two independent beads. Bead 1 (nthlayer-2xe) refactors MimirRulerProvider in nthlayer-common. Bead 2 (nthlayer-hmj) adds explanation.py to nthlayer-common (data model + formatter), explanation.py to nthlayer-observe (engine + CLI), and removes the dead stub from nthlayer generate. Both share a dependency on nthlayer-common but can be implemented in parallel.

**Tech Stack:** Python, httpx, structlog, dataclasses, pytest, nthlayer-common BaseHTTPClient

**Spec:** `docs/superpowers/specs/2026-04-10-mimir-move-and-explanation-engine-design.md`

---

## BEAD nthlayer-2xe: Move MimirRulerProvider to clients/

### Task 1: Write failing tests for MimirRulerProvider as BaseHTTPClient

**Files:**
- Create: `nthlayer-common/tests/test_mimir_client.py`

- [ ] **Step 1: Write the failing tests**

```python
# nthlayer-common/tests/test_mimir_client.py
"""Tests for MimirRulerProvider as a BaseHTTPClient subclass."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from nthlayer_common.clients.mimir import (
    DEFAULT_USER_AGENT,
    MimirRulerError,
    MimirRulerProvider,
    RulerPushResult,
)
from nthlayer_common.clients.base import BaseHTTPClient


class TestMimirClientTaxonomy:
    def test_is_base_http_client(self) -> None:
        provider = MimirRulerProvider(ruler_url="http://mimir:8080")
        assert isinstance(provider, BaseHTTPClient)

    def test_default_user_agent(self) -> None:
        assert DEFAULT_USER_AGENT == "nthlayer-provider-mimir/0.1.0"


class TestMimirAuthHeaders:
    def test_tenant_id_header(self) -> None:
        provider = MimirRulerProvider(
            ruler_url="http://mimir:8080",
            tenant_id="my-tenant",
        )
        headers = provider._headers()
        assert headers["X-Scope-OrgID"] == "my-tenant"

    def test_api_key_header(self) -> None:
        provider = MimirRulerProvider(
            ruler_url="http://mimir:8080",
            api_key="secret-key",
        )
        headers = provider._headers()
        assert headers["Authorization"] == "Bearer secret-key"

    def test_basic_auth_not_in_headers(self) -> None:
        """Basic auth is handled by httpx auth param, not headers."""
        provider = MimirRulerProvider(
            ruler_url="http://mimir:8080",
            username="user",
            password="pass",
        )
        headers = provider._headers()
        assert "Authorization" not in headers

    def test_no_auth_headers(self) -> None:
        provider = MimirRulerProvider(ruler_url="http://mimir:8080")
        headers = provider._headers()
        assert "X-Scope-OrgID" not in headers
        assert "Authorization" not in headers
        assert headers["User-Agent"] == DEFAULT_USER_AGENT

    def test_combined_tenant_and_api_key(self) -> None:
        provider = MimirRulerProvider(
            ruler_url="http://mimir:8080",
            tenant_id="t1",
            api_key="k1",
        )
        headers = provider._headers()
        assert headers["X-Scope-OrgID"] == "t1"
        assert headers["Authorization"] == "Bearer k1"


class TestMimirPushRules:
    @pytest.mark.asyncio
    async def test_push_success(self) -> None:
        provider = MimirRulerProvider(ruler_url="http://mimir:8080")
        with patch.object(provider, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"status": "success"}
            result = await provider.push_rules("my-ns", "groups:\n- name: test\n")
            assert isinstance(result, RulerPushResult)
            assert result.success is True
            assert result.namespace == "my-ns"

    @pytest.mark.asyncio
    async def test_push_connection_error(self) -> None:
        import httpx
        provider = MimirRulerProvider(ruler_url="http://mimir:8080")
        with patch.object(provider, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = httpx.ConnectError("refused")
            with pytest.raises(MimirRulerError, match="connect"):
                await provider.push_rules("ns", "yaml")


class TestMimirDeleteRules:
    @pytest.mark.asyncio
    async def test_delete_success(self) -> None:
        provider = MimirRulerProvider(ruler_url="http://mimir:8080")
        with patch.object(provider, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            result = await provider.delete_rules("my-ns", "group1")
            assert result is True

    @pytest.mark.asyncio
    async def test_delete_all_in_namespace(self) -> None:
        provider = MimirRulerProvider(ruler_url="http://mimir:8080")
        with patch.object(provider, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            result = await provider.delete_rules("my-ns")
            assert result is True


class TestMimirListRules:
    @pytest.mark.asyncio
    async def test_list_rules(self) -> None:
        provider = MimirRulerProvider(ruler_url="http://mimir:8080")
        with patch.object(provider, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"my-ns": [{"name": "group1"}]}
            result = await provider.list_rules()
            assert "my-ns" in result


class TestMimirHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy(self) -> None:
        provider = MimirRulerProvider(ruler_url="http://mimir:8080")
        with patch.object(provider, "list_rules", new_callable=AsyncMock):
            assert await provider.health_check() is True

    @pytest.mark.asyncio
    async def test_unhealthy(self) -> None:
        provider = MimirRulerProvider(ruler_url="http://mimir:8080")
        with patch.object(
            provider, "list_rules", new_callable=AsyncMock,
            side_effect=MimirRulerError("down"),
        ):
            assert await provider.health_check() is False


class TestBackwardCompat:
    def test_import_from_providers(self) -> None:
        """Old import path still works via re-export shim."""
        from nthlayer_common.providers.mimir import MimirRulerProvider as P
        assert P is MimirRulerProvider

    def test_import_from_clients(self) -> None:
        from nthlayer_common.clients import MimirRulerProvider as P
        assert P is MimirRulerProvider
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-common && uv run pytest tests/test_mimir_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nthlayer_common.clients.mimir'`

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_mimir_client.py
git commit -m "test: add failing tests for MimirRulerProvider as BaseHTTPClient (nthlayer-2xe)"
```

### Task 2: Implement MimirRulerProvider as BaseHTTPClient

**Files:**
- Create: `nthlayer-common/src/nthlayer_common/clients/mimir.py`
- Modify: `nthlayer-common/src/nthlayer_common/clients/__init__.py`
- Modify: `nthlayer-common/src/nthlayer_common/providers/mimir.py` (becomes re-export shim)

- [ ] **Step 4: Create clients/mimir.py**

```python
# nthlayer-common/src/nthlayer_common/clients/mimir.py
"""Mimir Ruler API client — push alert/recording rules to Mimir/Cortex.

This is a BaseHTTPClient subclass (standalone HTTP client with retry +
circuit breaker), NOT a Provider protocol implementer. The Provider
protocol is for managed declarative resources (plan/apply/drift); this
client is for imperative rule operations (push/delete/list).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from nthlayer_common.clients.base import BaseHTTPClient
from nthlayer_common.errors import ProviderError

DEFAULT_USER_AGENT = "nthlayer-provider-mimir/0.1.0"


class MimirRulerError(ProviderError):
    """Error communicating with Mimir Ruler API."""


@dataclass
class RulerPushResult:
    """Result of pushing rules to Mimir."""

    success: bool
    namespace: str
    status_code: int = 0
    message: str = ""
    groups_pushed: int = 0


class MimirRulerProvider(BaseHTTPClient):
    """Push alert rules to Mimir/Cortex Ruler API.

    API endpoints:
        POST /api/v1/rules/{namespace} - Create/update rule groups
        DELETE /api/v1/rules/{namespace}/{groupName} - Delete rule group
        GET /api/v1/rules - List all rules
    """

    def __init__(
        self,
        ruler_url: str,
        *,
        tenant_id: str | None = None,
        api_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 30.0,
        user_agent: str = DEFAULT_USER_AGENT,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
    ) -> None:
        super().__init__(
            base_url=ruler_url,
            timeout=timeout,
            max_retries=max_retries,
            backoff_factor=backoff_factor,
        )
        self._tenant_id = tenant_id
        self._api_key = api_key
        self._user_agent = user_agent
        self._auth = (username, password) if username and password else None

    def _headers(self) -> dict[str, str]:
        """Build request headers with auth."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self._user_agent,
        }
        if self._tenant_id:
            headers["X-Scope-OrgID"] = self._tenant_id
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def push_rules(self, namespace: str, rules_yaml: str) -> RulerPushResult:
        """Push rule groups to a namespace.

        Raises:
            MimirRulerError: If the API request fails
        """
        try:
            resp = await self._request(
                "POST",
                f"/api/v1/rules/{namespace}",
                content=rules_yaml,
                headers={"Content-Type": "application/yaml"},
            )
            groups_count = rules_yaml.count("- name:")
            return RulerPushResult(
                success=True,
                namespace=namespace,
                status_code=200,
                message="Rules pushed successfully",
                groups_pushed=groups_count,
            )
        except httpx.ConnectError as e:
            raise MimirRulerError(
                f"Failed to connect to Mimir at {self._base_url}: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise MimirRulerError(
                f"Timeout connecting to Mimir at {self._base_url}: {e}"
            ) from e
        except httpx.HTTPError as e:
            raise MimirRulerError(f"HTTP error from Mimir: {e}") from e

    async def delete_rules(
        self, namespace: str, group_name: str | None = None
    ) -> bool:
        """Delete rules from a namespace.

        Raises:
            MimirRulerError: If the API request fails
        """
        path = f"/api/v1/rules/{namespace}"
        if group_name:
            path = f"{path}/{group_name}"
        try:
            await self._request("DELETE", path)
            return True
        except httpx.HTTPError as e:
            raise MimirRulerError(f"Failed to delete rules: {e}") from e

    async def list_rules(self) -> dict[str, Any]:
        """List all rules across all namespaces.

        Raises:
            MimirRulerError: If the API request fails
        """
        try:
            return await self._request("GET", "/api/v1/rules")
        except httpx.HTTPError as e:
            raise MimirRulerError(f"Failed to list rules: {e}") from e

    async def health_check(self) -> bool:
        """Check if Mimir Ruler is reachable."""
        try:
            await self.list_rules()
            return True
        except MimirRulerError:
            return False
```

- [ ] **Step 5: Update clients/__init__.py**

Add to `nthlayer-common/src/nthlayer_common/clients/__init__.py`:

```python
from nthlayer_common.clients.mimir import (
    MimirRulerProvider,
    MimirRulerError,
    RulerPushResult,
    DEFAULT_USER_AGENT as MIMIR_DEFAULT_USER_AGENT,
)
```

Add to `__all__`: `"MimirRulerProvider"`, `"MimirRulerError"`, `"RulerPushResult"`

- [ ] **Step 6: Convert providers/mimir.py to re-export shim**

Replace the contents of `nthlayer-common/src/nthlayer_common/providers/mimir.py` with:

```python
"""Re-export shim — canonical source is nthlayer_common.clients.mimir.

This shim maintains backward compatibility for existing imports.
"""
from nthlayer_common.clients.mimir import (  # noqa: F401
    DEFAULT_USER_AGENT,
    MimirRulerError,
    MimirRulerProvider,
    RulerPushResult,
)

__all__ = [
    "DEFAULT_USER_AGENT",
    "MimirRulerError",
    "MimirRulerProvider",
    "RulerPushResult",
]
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-common && uv run pytest tests/test_mimir_client.py -v`
Expected: ALL PASS

- [ ] **Step 8: Run existing tests to verify no regressions**

Run: `uv run pytest tests/ -v --tb=short`
Expected: ALL PASS (including any old mimir tests if they exist)

Run: `uv run ruff check src/ tests/ --ignore E501`
Expected: All checks passed!

- [ ] **Step 9: Commit**

```bash
git add src/nthlayer_common/clients/mimir.py src/nthlayer_common/clients/__init__.py src/nthlayer_common/providers/mimir.py
git commit -m "refactor: move MimirRulerProvider to clients/, extend BaseHTTPClient (nthlayer-2xe)"
```

### Task 3: Verify nthlayer re-export shim still works

**Files:**
- Read: `nthlayer/src/nthlayer/providers/mimir.py` (should need no change)
- Read: `nthlayer/tests/test_mimir_provider.py`

- [ ] **Step 10: Verify nthlayer tests pass with new client**

Run: `cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer && uv run pytest tests/test_mimir_provider.py -v`
Expected: ALL 18 PASS (the shim chain: `nthlayer.providers.mimir` → `nthlayer_common.providers.mimir` → `nthlayer_common.clients.mimir`)

- [ ] **Step 11: Close bead**

```bash
bd close nthlayer-2xe --force --reason "MimirRulerProvider moved to clients/mimir.py, extends BaseHTTPClient. Auth wired through _headers(). providers/mimir.py is now a re-export shim. All tests pass."
```

---

## BEAD nthlayer-hmj: Restore alerts explain

### Task 4: Write BudgetExplanation model + formatter in nthlayer-common

**Files:**
- Create: `nthlayer-common/src/nthlayer_common/explanation.py`
- Create: `nthlayer-common/tests/test_explanation.py`

- [ ] **Step 12: Write failing tests for BudgetExplanation + format_explanation**

```python
# nthlayer-common/tests/test_explanation.py
"""Tests for BudgetExplanation data model and formatter."""
from __future__ import annotations

import json

from nthlayer_common.explanation import BudgetExplanation, format_explanation


class TestBudgetExplanation:
    def test_create(self) -> None:
        exp = BudgetExplanation(
            service="payment-api",
            slo_name="availability",
            headline="availability: 73% consumed (WARNING)",
            body="Budget: 1440 min total, 1051 min consumed, 389 min remaining.",
            causes=["Error rate gradually increasing over last 7 days"],
            recommended_actions=["Investigate before next deployment"],
            severity="warning",
        )
        assert exp.service == "payment-api"
        assert exp.severity == "warning"

    def test_to_dict(self) -> None:
        exp = BudgetExplanation(
            service="svc",
            slo_name="avail",
            headline="h",
            body="b",
            causes=["c1"],
            recommended_actions=["a1"],
            severity="info",
        )
        d = exp.to_dict()
        assert d["service"] == "svc"
        assert d["causes"] == ["c1"]
        assert isinstance(d, dict)


class TestFormatTable:
    def test_table_format(self) -> None:
        exp = BudgetExplanation(
            service="payment-api",
            slo_name="availability",
            headline="availability: 73% consumed (WARNING)",
            body="Budget details here.",
            causes=["Gradual error rate increase"],
            recommended_actions=["Investigate error rate"],
            severity="warning",
        )
        output = format_explanation(exp, fmt="table")
        assert "payment-api" in output
        assert "availability" in output
        assert "WARNING" in output.upper()


class TestFormatJSON:
    def test_json_format(self) -> None:
        exp = BudgetExplanation(
            service="svc",
            slo_name="avail",
            headline="h",
            body="b",
            causes=[],
            recommended_actions=[],
            severity="info",
        )
        output = format_explanation(exp, fmt="json")
        parsed = json.loads(output)
        assert parsed["service"] == "svc"

    def test_json_roundtrip(self) -> None:
        exp = BudgetExplanation(
            service="s",
            slo_name="n",
            headline="h",
            body="b",
            causes=["c"],
            recommended_actions=["a"],
            severity="critical",
        )
        parsed = json.loads(format_explanation(exp, fmt="json"))
        assert parsed["severity"] == "critical"
        assert parsed["causes"] == ["c"]


class TestFormatMarkdown:
    def test_markdown_format(self) -> None:
        exp = BudgetExplanation(
            service="payment-api",
            slo_name="availability",
            headline="availability: 73% consumed (WARNING)",
            body="Budget details.",
            causes=["Error rate increase"],
            recommended_actions=["Investigate"],
            severity="warning",
        )
        output = format_explanation(exp, fmt="markdown")
        assert "##" in output
        assert "payment-api" in output
```

- [ ] **Step 13: Run tests to verify they fail**

Run: `cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-common && uv run pytest tests/test_explanation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nthlayer_common.explanation'`

- [ ] **Step 14: Implement BudgetExplanation + format_explanation**

```python
# nthlayer-common/src/nthlayer_common/explanation.py
"""Budget explanation data model and formatter.

Shared across the ecosystem: nthlayer-observe produces explanations,
nthlayer-respond can format them for incident communications.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict


@dataclass
class BudgetExplanation:
    """Human-readable explanation of error budget status."""

    service: str
    slo_name: str
    headline: str
    body: str
    causes: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    severity: str = "info"  # "info" | "warning" | "critical"

    def to_dict(self) -> dict:
        return asdict(self)


def format_explanation(explanation: BudgetExplanation, fmt: str = "table") -> str:
    """Format a BudgetExplanation for output.

    Args:
        explanation: The explanation to format
        fmt: Output format — "table", "json", or "markdown"
    """
    if fmt == "json":
        return json.dumps(explanation.to_dict(), indent=2)

    if fmt == "markdown":
        lines = [
            f"## {explanation.service} — {explanation.slo_name}",
            "",
            f"**{explanation.headline}**",
            "",
            explanation.body,
        ]
        if explanation.causes:
            lines.append("")
            lines.append("### Causes")
            for cause in explanation.causes:
                lines.append(f"- {cause}")
        if explanation.recommended_actions:
            lines.append("")
            lines.append("### Recommended Actions")
            for action in explanation.recommended_actions:
                lines.append(f"- {action}")
        return "\n".join(lines)

    # Default: table format
    severity_icon = {"info": "ℹ", "warning": "⚠", "critical": "✗"}.get(
        explanation.severity, "?"
    )
    lines = [
        f"{severity_icon} {explanation.service} / {explanation.slo_name}",
        f"  {explanation.headline}",
        f"  {explanation.body}",
    ]
    if explanation.causes:
        lines.append("  Causes:")
        for cause in explanation.causes:
            lines.append(f"    • {cause}")
    if explanation.recommended_actions:
        lines.append("  Actions:")
        for action in explanation.recommended_actions:
            lines.append(f"    → {action}")
    return "\n".join(lines)
```

- [ ] **Step 15: Run tests to verify they pass**

Run: `uv run pytest tests/test_explanation.py -v`
Expected: ALL PASS

- [ ] **Step 16: Commit**

```bash
git add src/nthlayer_common/explanation.py tests/test_explanation.py
git commit -m "feat: add BudgetExplanation data model and formatter (nthlayer-hmj)"
```

### Task 5: Build ExplanationEngine in nthlayer-observe

**Files:**
- Create: `nthlayer-observe/src/nthlayer_observe/explanation.py`
- Create: `nthlayer-observe/tests/test_explanation.py`

- [ ] **Step 17: Write failing tests for ExplanationEngine**

```python
# nthlayer-observe/tests/test_explanation.py
"""Tests for ExplanationEngine."""
from __future__ import annotations

from datetime import datetime, timezone

from nthlayer_common.explanation import BudgetExplanation
from nthlayer_observe.assessment import create as create_assessment
from nthlayer_observe.explanation import ExplanationEngine
from nthlayer_observe.store import MemoryAssessmentStore


def _make_slo_assessment(
    service: str,
    slo_name: str,
    percent_consumed: float,
    status: str,
    burned_minutes: float = 100.0,
    total_budget_minutes: float = 1440.0,
    current_sli: float = 0.998,
    objective: float = 0.999,
) -> None:
    return create_assessment(
        assessment_type="slo_state",
        service=service,
        data={
            "name": slo_name,
            "objective": objective,
            "window": "30d",
            "total_budget_minutes": total_budget_minutes,
            "current_sli": current_sli,
            "burned_minutes": burned_minutes,
            "percent_consumed": percent_consumed,
            "status": status,
        },
    )


class TestExplanationEngine:
    def test_healthy_slo(self) -> None:
        store = MemoryAssessmentStore()
        store.put(_make_slo_assessment("svc", "availability", 12.0, "HEALTHY"))
        engine = ExplanationEngine()
        results = engine.explain_service("svc", store)
        assert len(results) == 1
        assert results[0].severity == "info"
        assert "HEALTHY" in results[0].headline

    def test_warning_slo(self) -> None:
        store = MemoryAssessmentStore()
        store.put(_make_slo_assessment("svc", "availability", 73.0, "WARNING"))
        engine = ExplanationEngine()
        results = engine.explain_service("svc", store)
        assert len(results) == 1
        assert results[0].severity == "warning"

    def test_critical_slo(self) -> None:
        store = MemoryAssessmentStore()
        store.put(_make_slo_assessment("svc", "availability", 92.0, "CRITICAL"))
        engine = ExplanationEngine()
        results = engine.explain_service("svc", store)
        assert results[0].severity == "critical"

    def test_exhausted_slo(self) -> None:
        store = MemoryAssessmentStore()
        store.put(_make_slo_assessment("svc", "avail", 107.0, "EXHAUSTED",
                                        burned_minutes=1540, total_budget_minutes=1440))
        engine = ExplanationEngine()
        results = engine.explain_service("svc", store)
        assert results[0].severity == "critical"
        assert "exhausted" in results[0].headline.lower()

    def test_slo_filter(self) -> None:
        store = MemoryAssessmentStore()
        store.put(_make_slo_assessment("svc", "availability", 12.0, "HEALTHY"))
        store.put(_make_slo_assessment("svc", "latency", 55.0, "WARNING"))
        engine = ExplanationEngine()
        results = engine.explain_service("svc", store, slo_filter="latency")
        assert len(results) == 1
        assert results[0].slo_name == "latency"

    def test_no_assessments(self) -> None:
        store = MemoryAssessmentStore()
        engine = ExplanationEngine()
        results = engine.explain_service("svc", store)
        assert results == []

    def test_multiple_slos(self) -> None:
        store = MemoryAssessmentStore()
        store.put(_make_slo_assessment("svc", "availability", 12.0, "HEALTHY"))
        store.put(_make_slo_assessment("svc", "latency", 55.0, "WARNING"))
        engine = ExplanationEngine()
        results = engine.explain_service("svc", store)
        assert len(results) == 2

    def test_explanation_has_recommended_actions(self) -> None:
        store = MemoryAssessmentStore()
        store.put(_make_slo_assessment("svc", "avail", 92.0, "CRITICAL"))
        engine = ExplanationEngine()
        results = engine.explain_service("svc", store)
        assert len(results[0].recommended_actions) > 0

    def test_explanation_body_has_budget_math(self) -> None:
        store = MemoryAssessmentStore()
        store.put(_make_slo_assessment("svc", "avail", 50.0, "WARNING",
                                        burned_minutes=720, total_budget_minutes=1440))
        engine = ExplanationEngine()
        results = engine.explain_service("svc", store)
        assert "720" in results[0].body
        assert "1440" in results[0].body
```

- [ ] **Step 18: Run tests to verify they fail**

Run: `cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-observe && uv run pytest tests/test_explanation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nthlayer_observe.explanation'`

- [ ] **Step 19: Implement ExplanationEngine**

```python
# nthlayer-observe/src/nthlayer_observe/explanation.py
"""ExplanationEngine — build human-readable budget explanations from assessments.

Deterministic. No LLM. Pure arithmetic on assessment data.
"""
from __future__ import annotations

from nthlayer_common.explanation import BudgetExplanation
from nthlayer_observe.store import AssessmentStore, AssessmentFilter


_STATUS_SEVERITY = {
    "EXHAUSTED": "critical",
    "CRITICAL": "critical",
    "WARNING": "warning",
    "ERROR": "warning",
    "HEALTHY": "info",
    "NO_DATA": "info",
    "UNKNOWN": "info",
}


class ExplanationEngine:
    """Build budget explanations from the assessment store."""

    def explain_service(
        self,
        service: str,
        store: AssessmentStore,
        slo_filter: str | None = None,
    ) -> list[BudgetExplanation]:
        """Build explanations for a service from latest slo_state assessments."""
        assessments = store.query(AssessmentFilter(
            service=service,
            assessment_type="slo_state",
            limit=0,
        ))

        # Deduplicate: keep latest per SLO name (query returns desc by timestamp)
        seen: set[str] = set()
        latest: list = []
        for a in assessments:
            slo_name = a.data.get("name", "unknown")
            if slo_name not in seen:
                seen.add(slo_name)
                latest.append(a)

        if slo_filter:
            latest = [a for a in latest if a.data.get("name") == slo_filter]

        return [self._explain_slo(service, a) for a in latest]

    def _explain_slo(self, service: str, assessment) -> BudgetExplanation:
        """Build a single BudgetExplanation from an slo_state assessment."""
        data = assessment.data
        slo_name = data.get("name", "unknown")
        status = data.get("status", "UNKNOWN")
        percent_consumed = data.get("percent_consumed", 0.0) or 0.0
        burned_minutes = data.get("burned_minutes", 0.0) or 0.0
        total_budget_minutes = data.get("total_budget_minutes", 0.0) or 0.0
        current_sli = data.get("current_sli", 0.0) or 0.0
        objective = data.get("objective", 0.0) or 0.0
        remaining_minutes = max(0, total_budget_minutes - burned_minutes)

        severity = _STATUS_SEVERITY.get(status, "info")

        # Headline
        if status == "EXHAUSTED":
            headline = (
                f"{slo_name}: {percent_consumed:.0f}% consumed "
                f"— budget exhausted (EXHAUSTED)"
            )
        elif status == "CRITICAL":
            headline = (
                f"{slo_name}: {percent_consumed:.0f}% consumed "
                f"— near exhaustion (CRITICAL)"
            )
        elif status == "WARNING":
            headline = (
                f"{slo_name}: {percent_consumed:.0f}% consumed "
                f"— approaching threshold (WARNING)"
            )
        else:
            headline = (
                f"{slo_name}: {percent_consumed:.0f}% consumed "
                f"— within budget ({status})"
            )

        # Body with budget math
        window = data.get("window", "30d")
        body = (
            f"Window: {window}. "
            f"Budget: {total_budget_minutes:.0f} min total, "
            f"{burned_minutes:.0f} min consumed, "
            f"{remaining_minutes:.0f} min remaining. "
            f"Current SLI: {current_sli:.4f} (target: {objective:.4f})."
        )

        # Causes (derived from data, not LLM)
        causes: list[str] = []
        if percent_consumed > 80:
            causes.append(
                "Budget consumption exceeds 80% — sustained error rate above target"
            )
        if current_sli < objective:
            gap = (objective - current_sli) * 100
            causes.append(
                f"Current SLI ({current_sli:.4f}) is {gap:.2f}pp below target ({objective:.4f})"
            )

        # Recommended actions (severity-aware)
        actions: list[str] = []
        if status == "EXHAUSTED":
            actions.append(
                "Deployment gate will block — resolve underlying issue before deploying"
            )
        if status in ("CRITICAL", "EXHAUSTED"):
            actions.append("Investigate root cause of elevated error rate")
            actions.append("Consider freezing deployments until budget recovers")
        elif status == "WARNING":
            actions.append("Monitor trend — investigate if consumption continues to rise")

        return BudgetExplanation(
            service=service,
            slo_name=slo_name,
            headline=headline,
            body=body,
            causes=causes,
            recommended_actions=actions,
            severity=severity,
        )
```

- [ ] **Step 20: Run tests to verify they pass**

Run: `uv run pytest tests/test_explanation.py -v`
Expected: ALL PASS

- [ ] **Step 21: Commit**

```bash
git add src/nthlayer_observe/explanation.py tests/test_explanation.py
git commit -m "feat: add ExplanationEngine — budget explanations from assessments (nthlayer-hmj)"
```

### Task 6: Add `explain` CLI subcommand to nthlayer-observe

**Files:**
- Modify: `nthlayer-observe/src/nthlayer_observe/cli.py`

- [ ] **Step 22: Add explain subcommand to CLI**

Add to the argument parser section of `cli.py` (after the `check-deploy` parser):

```python
    explain_parser = subparsers.add_parser(
        "explain", help="Show human-readable budget explanations"
    )
    explain_parser.add_argument("--store", default="assessments.db", help="Assessment store path")
    explain_parser.add_argument("--service", help="Filter by service name")
    explain_parser.add_argument("--slo", help="Filter by SLO name")
    explain_parser.add_argument(
        "--format", dest="output_format", default="table",
        choices=["table", "json", "markdown"],
        help="Output format (default: table)",
    )
```

Add the command handler:

```python
def _cmd_explain(args: argparse.Namespace) -> int:
    """Show human-readable budget explanations from assessment store."""
    from nthlayer_common.explanation import format_explanation
    from nthlayer_observe.explanation import ExplanationEngine
    from nthlayer_observe.sqlite_store import SQLiteAssessmentStore

    store = SQLiteAssessmentStore(args.store)
    engine = ExplanationEngine()

    if args.service:
        services = [args.service]
    else:
        # Get all services from store
        all_assessments = store.query(AssessmentFilter(
            assessment_type="slo_state", limit=0
        ))
        services = sorted({a.service for a in all_assessments})

    if not services:
        print("No SLO assessments found in store.", file=sys.stderr)
        return 0

    fmt = args.output_format
    all_explanations = []

    for service in services:
        explanations = engine.explain_service(service, store, slo_filter=args.slo)
        all_explanations.extend(explanations)

    if not all_explanations:
        print("No matching SLO assessments found.", file=sys.stderr)
        return 0

    if fmt == "json":
        import json
        print(json.dumps([e.to_dict() for e in all_explanations], indent=2))
    else:
        for exp in all_explanations:
            print(format_explanation(exp, fmt=fmt))
            print()

    return 0
```

Add dispatch in the main `if/elif` chain:

```python
    elif args.command == "explain":
        return _cmd_explain(args)
```

- [ ] **Step 23: Test CLI manually**

Run: `uv run nthlayer-observe explain --help`
Expected: Shows help with --store, --service, --slo, --format options

- [ ] **Step 24: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: ALL PASS

Run: `uv run ruff check src/ tests/ --ignore E501`
Expected: All checks passed!

- [ ] **Step 25: Commit**

```bash
git add src/nthlayer_observe/cli.py
git commit -m "feat: add explain CLI subcommand (nthlayer-hmj)"
```

### Task 7: Remove dead explain stub from nthlayer generate

**Files:**
- Modify: `nthlayer/src/nthlayer/cli/alerts.py`
- Modify: `nthlayer/tests/test_cli_alerts.py`

- [ ] **Step 26: Remove explain from alerts.py**

In `nthlayer/src/nthlayer/cli/alerts.py`:

1. Delete the `alerts_explain_command` function (lines 104-117)
2. Delete the `explain` subparser registration (lines 341-355)
3. Delete the `explain` dispatch branch in `handle_alerts_command` (lines 398-404)
4. Update the usage string to remove `explain` (line 414): `"Usage: nthlayer alerts {evaluate|show|test}"`
5. Remove `explain` from the module docstring (line 7)

- [ ] **Step 27: Remove explain tests from test_cli_alerts.py**

Delete the `TestAlertsExplain` class (3 tests) and remove `alerts_explain_command` from the import on line 14.

- [ ] **Step 28: Run tests**

Run: `cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer && uv run pytest tests/test_cli_alerts.py -v`
Expected: ALL PASS (explain tests gone, other tests still pass)

Run: `uv run ruff check src/ tests/`
Expected: All checks passed!

- [ ] **Step 29: Commit**

```bash
git add src/nthlayer/cli/alerts.py tests/test_cli_alerts.py
git commit -m "refactor: remove dead alerts explain stub — now in nthlayer-observe (nthlayer-hmj)"
```

- [ ] **Step 30: Close bead**

```bash
bd close nthlayer-hmj --force --reason "ExplanationEngine built in nthlayer-observe with shared BudgetExplanation model in nthlayer-common. nthlayer-observe explain CLI produces table/json/markdown output from assessment store. Dead stub removed from nthlayer generate. All tests pass across all 3 repos."
```
