# Execution Bindings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace safe action handler stubs with webhook-based execution that fires HTTP requests and verifies results via PromQL.

**Architecture:** A `WebhookDispatcher` reads binding config from `safe-actions.yaml`, renders `{{variable}}` templates, resolves `${ENV_VAR}` secrets, makes HTTP calls via httpx, and optionally verifies the result with a PromQL query against Prometheus. Existing registry, cooldown, blast radius, and approval logic unchanged.

**Tech Stack:** Python 3.11+, httpx, pytest, nthlayer-respond existing pipeline

**Spec:** `docs/superpowers/specs/2026-04-02-execution-bindings-design.md`

---

## File Structure

```
src/nthlayer_respond/
├── safe_actions/
│   ├── registry.py         # MODIFY — add binding field to SafeAction
│   ├── actions.py          # MODIFY — webhook handler factory
│   └── webhook.py          # NEW — WebhookDispatcher + ExecutionResult
registry/
└── safe-actions.yaml       # MODIFY — add binding sections

tests/
├── test_webhook.py         # NEW — dispatcher tests
└── test_safe_actions.py    # MODIFY — verify stub fallback still works
```

---

### Task 1: Create WebhookDispatcher with template rendering

**Files:**
- Create: `src/nthlayer_respond/safe_actions/webhook.py`
- Create: `tests/test_webhook.py`

- [ ] **Step 1: Write failing tests for template rendering and secret resolution**

Create `tests/test_webhook.py`:

```python
"""Tests for WebhookDispatcher — template rendering, secret resolution, execution."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from nthlayer_respond.safe_actions.webhook import (
    WebhookDispatcher,
    ExecutionResult,
    render_binding_templates,
    resolve_secrets,
)


class TestRenderTemplates:
    def test_renders_string_variables(self):
        result = render_binding_templates(
            "https://api.internal/{{service}}/rollback",
            {"service": "fraud-detect"},
        )
        assert result == "https://api.internal/fraud-detect/rollback"

    def test_renders_nested_dict(self):
        obj = {"url": "https://{{service}}", "body": {"target": "{{target}}"}}
        result = render_binding_templates(obj, {"service": "api", "target": "svc-1"})
        assert result == {"url": "https://api", "body": {"target": "svc-1"}}

    def test_missing_variable_left_as_is(self):
        result = render_binding_templates("{{missing}}", {})
        assert result == "{{missing}}"

    def test_renders_in_lists(self):
        result = render_binding_templates(["{{a}}", "{{b}}"], {"a": "1", "b": "2"})
        assert result == ["1", "2"]

    def test_non_string_passthrough(self):
        result = render_binding_templates(42, {})
        assert result == 42


class TestResolveSecrets:
    def test_resolves_env_var(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "secret123")
        result = resolve_secrets("Bearer ${MY_TOKEN}")
        assert result == "Bearer secret123"

    def test_missing_env_var_raises(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        with pytest.raises(ValueError, match="MISSING_VAR"):
            resolve_secrets("${MISSING_VAR}")

    def test_nested_dict_resolution(self, monkeypatch):
        monkeypatch.setenv("TOKEN", "abc")
        obj = {"headers": {"Authorization": "Bearer ${TOKEN}"}}
        result = resolve_secrets(obj)
        assert result == {"headers": {"Authorization": "Bearer abc"}}

    def test_no_secrets_passthrough(self):
        result = resolve_secrets("no secrets here")
        assert result == "no secrets here"


class TestWebhookDispatcherExecute:
    @pytest.mark.asyncio
    async def test_successful_webhook_call(self, monkeypatch):
        monkeypatch.setenv("TEST_TOKEN", "tok")
        binding = {
            "method": "webhook",
            "url": "https://api.internal/{{service}}/action",
            "headers": {"Authorization": "Bearer ${TEST_TOKEN}"},
            "body": {"target": "{{service}}"},
            "timeout": 10,
        }
        variables = {"service": "fraud-detect"}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK"
        mock_resp.raise_for_status = MagicMock()

        with patch("nthlayer_respond.safe_actions.webhook.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            dispatcher = WebhookDispatcher()
            result = await dispatcher.execute(binding, variables)

        assert result.success is True
        assert result.status_code == 200
        mock_client.post.assert_called_once()
        call_url = mock_client.post.call_args[0][0]
        assert "fraud-detect" in call_url

    @pytest.mark.asyncio
    async def test_http_error_returns_failure(self, monkeypatch):
        monkeypatch.delenv("TEST_TOKEN", raising=False)
        binding = {
            "method": "webhook",
            "url": "https://api.internal/action",
            "timeout": 5,
        }

        import httpx
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=mock_resp)
        )

        with patch("nthlayer_respond.safe_actions.webhook.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            dispatcher = WebhookDispatcher()
            result = await dispatcher.execute(binding, {})

        assert result.success is False
        assert result.status_code == 500

    @pytest.mark.asyncio
    async def test_stub_binding_returns_stub_result(self):
        dispatcher = WebhookDispatcher()
        result = await dispatcher.execute("stub", {"service": "test"})
        assert result.success is True
        assert "stub" in result.detail.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-respond && uv run --extra dev pytest tests/test_webhook.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement WebhookDispatcher**

Create `src/nthlayer_respond/safe_actions/webhook.py`:

```python
"""Webhook dispatcher for safe action execution bindings.

Renders {{variable}} templates, resolves ${ENV_VAR} secrets,
makes HTTP calls, and optionally verifies results via PromQL.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of a safe action execution."""

    success: bool
    status_code: int | None = None
    detail: str = ""
    verified: bool | None = None
    verification_detail: str | None = None


def render_binding_templates(obj: Any, variables: dict[str, str]) -> Any:
    """Recursively render {{variable}} placeholders in strings."""
    if isinstance(obj, str):
        for key, value in variables.items():
            obj = obj.replace("{{" + key + "}}", str(value))
            obj = obj.replace("{{ " + key + " }}", str(value))
        return obj
    if isinstance(obj, dict):
        return {k: render_binding_templates(v, variables) for k, v in obj.items()}
    if isinstance(obj, list):
        return [render_binding_templates(item, variables) for item in obj]
    return obj


def resolve_secrets(obj: Any) -> Any:
    """Recursively resolve ${ENV_VAR} placeholders from os.environ.

    Raises ValueError if a referenced env var is not set.
    """
    if isinstance(obj, str):
        def _replace(match):
            var_name = match.group(1)
            value = os.environ.get(var_name)
            if value is None:
                raise ValueError(
                    f"Secret ${{{var_name}}} not set. "
                    f"Set the {var_name} environment variable."
                )
            return value
        return re.sub(r'\$\{(\w+)\}', _replace, obj)
    if isinstance(obj, dict):
        return {k: resolve_secrets(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_secrets(item) for item in obj]
    return obj


class WebhookDispatcher:
    """Execute safe action bindings via HTTP webhooks."""

    async def execute(
        self, binding: dict | str, variables: dict[str, str]
    ) -> ExecutionResult:
        """Render templates, resolve secrets, make HTTP call, verify."""
        # Stub binding — no real execution
        if binding == "stub" or not binding:
            target = variables.get("service", variables.get("target", "unknown"))
            return ExecutionResult(
                success=True,
                detail=f"Stub execution for {target} (no binding configured).",
            )

        # Render templates in the binding config
        rendered = render_binding_templates(binding, variables)

        # Resolve secrets
        try:
            rendered = resolve_secrets(rendered)
        except ValueError as exc:
            return ExecutionResult(success=False, detail=str(exc))

        url = rendered.get("url", "")
        headers = rendered.get("headers", {})
        body = rendered.get("body")
        timeout = int(rendered.get("timeout", 30))
        retry_config = rendered.get("retry", {})
        verify_config = rendered.get("verify_after")

        # Execute HTTP call with retries
        result = await self._call_webhook(url, headers, body, timeout, retry_config)

        # Post-execution verification
        if verify_config and result.success:
            verification = await self._verify(verify_config, variables)
            result.verified = verification.verified
            result.verification_detail = verification.detail

        return result

    async def _call_webhook(
        self,
        url: str,
        headers: dict,
        body: dict | None,
        timeout: int,
        retry_config: dict,
    ) -> ExecutionResult:
        """Make HTTP POST with retry logic."""
        attempts = retry_config.get("attempts", 1)
        backoff = retry_config.get("backoff", [1])

        last_error = ""
        last_status = None

        async with httpx.AsyncClient() as client:
            for attempt in range(attempts):
                try:
                    resp = await client.post(
                        url,
                        headers=headers,
                        json=body,
                        timeout=timeout,
                    )
                    last_status = resp.status_code

                    if resp.is_success:
                        return ExecutionResult(
                            success=True,
                            status_code=resp.status_code,
                            detail=resp.text[:500],
                        )

                    resp.raise_for_status()

                except httpx.HTTPStatusError as exc:
                    last_error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
                    last_status = exc.response.status_code
                except httpx.TimeoutException:
                    last_error = f"Timeout after {timeout}s"
                except Exception as exc:
                    last_error = str(exc)

                # Backoff before retry
                if attempt < attempts - 1:
                    delay = backoff[min(attempt, len(backoff) - 1)]
                    await asyncio.sleep(delay)

        return ExecutionResult(
            success=False,
            status_code=last_status,
            detail=last_error,
        )

    async def _verify(
        self, verify_config: dict, variables: dict
    ) -> ExecutionResult:
        """Wait, query Prometheus, return verification result."""
        wait = int(verify_config.get("wait", 30))
        query = verify_config.get("query", "")
        description = verify_config.get("description", "")
        prometheus_url = verify_config.get("prometheus_url") or os.environ.get(
            "PROMETHEUS_URL", "http://localhost:9090"
        )

        # Render any remaining template variables in the query
        query = render_binding_templates(query, variables)

        logger.info("Waiting %ds before verification: %s", wait, description)
        await asyncio.sleep(wait)

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{prometheus_url}/api/v1/query",
                    params={"query": query},
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("data", {}).get("result", [])

                if not results:
                    return ExecutionResult(
                        success=True,
                        verified=None,
                        verification_detail=f"No data for query: {description}",
                    )

                value = float(results[0].get("value", [None, "0"])[1])
                # PromQL comparison returns 1 for true, 0 for false
                verified = value == 1.0

                return ExecutionResult(
                    success=True,
                    verified=verified,
                    verification_detail=(
                        f"Verified: {description}"
                        if verified
                        else f"Verification failed: {description} (value={value})"
                    ),
                )

        except Exception as exc:
            logger.warning("Verification query failed: %s", exc)
            return ExecutionResult(
                success=True,
                verified=None,
                verification_detail=f"Verification unavailable: {exc}",
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_webhook.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_respond/safe_actions/webhook.py tests/test_webhook.py
git commit -m "feat: WebhookDispatcher with template rendering, secret resolution, PromQL verification"
```

---

### Task 2: Wire webhook handlers into actions.py

**Files:**
- Modify: `src/nthlayer_respond/safe_actions/actions.py`
- Test: `tests/test_safe_actions.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_safe_actions.py`:

```python
def test_webhook_binding_creates_handler(tmp_path):
    """Actions with webhook bindings get webhook handlers, not stubs."""
    from nthlayer_respond.safe_actions.actions import _make_webhook_handler

    binding = {
        "method": "webhook",
        "url": "https://api.internal/{{service}}/rollback",
        "timeout": 10,
    }
    handler = _make_webhook_handler(binding)
    assert callable(handler)
    assert asyncio.iscoroutinefunction(handler)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_safe_actions.py::test_webhook_binding_creates_handler -v`
Expected: FAIL — `ImportError: cannot import name '_make_webhook_handler'`

- [ ] **Step 3: Add webhook handler factory to actions.py**

Modify `src/nthlayer_respond/safe_actions/actions.py`. Add after the `_HANDLERS` dict:

```python
from nthlayer_respond.safe_actions.webhook import WebhookDispatcher, render_binding_templates


def _make_webhook_handler(binding_config: dict):
    """Create an async handler that dispatches via webhook."""
    dispatcher = WebhookDispatcher()

    async def handler(target: str, context, **kwargs) -> dict:
        variables = _build_variables(target, context, kwargs)
        result = await dispatcher.execute(binding_config, variables)
        return {
            "success": result.success,
            "detail": result.detail,
            "status_code": result.status_code,
            "verified": result.verified,
            "verification_detail": result.verification_detail,
        }

    return handler


def _build_variables(target: str, context, kwargs: dict) -> dict[str, str]:
    """Build template variable dict from execution context."""
    variables = {
        "service": target,
        "target": target,
        "incident_id": getattr(context, "id", "unknown"),
    }
    if hasattr(context, "triage") and context.triage:
        variables["severity"] = str(context.triage.severity)
    # Pass through any extra kwargs as variables
    for k, v in kwargs.items():
        if isinstance(v, str):
            variables[k] = v
    return variables
```

Modify `register_builtin_actions()` to use webhook handlers when bindings are configured:

```python
def register_builtin_actions(registry: SafeActionRegistry) -> None:
    """Load safe action policy from YAML and register with handlers."""
    policy = load_safe_action_policy()

    for name, spec in policy.items():
        binding = spec.get("binding")

        # Determine handler: webhook binding > stub handler > skip
        if binding and binding != "stub":
            handler = _make_webhook_handler(binding)
        elif name in _HANDLERS:
            handler = _HANDLERS[name]
        else:
            logger.warning("Safe action %r has no binding or stub handler — skipping", name)
            continue

        registry.register(SafeAction(
            name=name,
            description=spec.get("description", "").strip(),
            target_type=spec.get("target_type", "service"),
            requires_approval=spec.get("requires_approval", True),
            cooldown_seconds=spec.get("cooldown_seconds", 300),
            handler=handler,
        ))
```

- [ ] **Step 4: Run full test suite**

Run: `uv run --extra dev pytest tests/ -v --tb=short`
Expected: ALL PASS (existing tests use the stub path since safe-actions.yaml has no binding sections yet)

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_respond/safe_actions/actions.py tests/test_safe_actions.py
git commit -m "feat: webhook handler factory — actions with bindings dispatch via WebhookDispatcher"
```

---

### Task 3: Add binding sections to safe-actions.yaml

**Files:**
- Modify: `registry/safe-actions.yaml`

- [ ] **Step 1: Add binding to each action**

Add a `binding: stub` to each action in `registry/safe-actions.yaml`. This explicitly marks them as stubs for now. Production deployments will replace `stub` with real webhook configs.

For rollback, add the full binding example from the spec:

```yaml
  rollback:
    # ... existing fields ...
    binding:
      method: webhook
      url: "https://argocd.internal/api/v1/applications/{{service}}/rollback"
      headers:
        Authorization: "Bearer ${ARGOCD_TOKEN}"
      body:
        revision: "{{previous_revision}}"
      timeout: 30
      retry:
        attempts: 3
        backoff: [1, 2, 4]
      verify_after:
        wait: 60
        prometheus_url: "${PROMETHEUS_URL}"
        query: >
          rate(http_server_request_duration_count{service="{{service}}", status=~"5.."}[2m])
          / rate(http_server_request_duration_count{service="{{service}}"}[2m])
          < 0.01
        description: "error rate below 1% within 60s of rollback"
```

For other actions, add `binding: stub` (demo mode — no real execution):

```yaml
  scale_up:
    # ... existing fields ...
    binding: stub

  disable_feature_flag:
    # ... existing fields ...
    binding: stub

  reduce_autonomy:
    # ... existing fields ...
    binding: stub

  pause_pipeline:
    # ... existing fields ...
    binding: stub
```

- [ ] **Step 2: Run full test suite**

Run: `uv run --extra dev pytest tests/ -v --tb=short`
Expected: ALL PASS (rollback binding references env vars that aren't set, but the demo path uses `--no-model` which patches `_call_model` so the handler is never actually invoked during tests)

- [ ] **Step 3: Commit**

```bash
git add registry/safe-actions.yaml
git commit -m "feat: add binding sections to safe-actions.yaml (rollback has full webhook config, others stub)"
```

---

### Task 4: Add PromQL verification tests

**Files:**
- Modify: `tests/test_webhook.py`

- [ ] **Step 1: Add verification tests**

Add to `tests/test_webhook.py`:

```python
class TestVerification:
    @pytest.mark.asyncio
    async def test_verification_success(self):
        dispatcher = WebhookDispatcher()
        verify_config = {
            "wait": 0,  # no wait in tests
            "prometheus_url": "http://mock:9090",
            "query": 'up{service="test"} == 1',
            "description": "service is up",
        }

        # Mock successful Prometheus query returning 1 (true)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": {"result": [{"value": [1234, "1"]}]}
        }

        with patch("nthlayer_respond.safe_actions.webhook.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await dispatcher._verify(verify_config, {"service": "test"})

        assert result.verified is True
        assert "Verified" in result.verification_detail

    @pytest.mark.asyncio
    async def test_verification_failure(self):
        dispatcher = WebhookDispatcher()
        verify_config = {
            "wait": 0,
            "prometheus_url": "http://mock:9090",
            "query": 'error_rate < 0.01',
            "description": "error rate below 1%",
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": {"result": [{"value": [1234, "0"]}]}
        }

        with patch("nthlayer_respond.safe_actions.webhook.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await dispatcher._verify(verify_config, {})

        assert result.verified is False

    @pytest.mark.asyncio
    async def test_verification_prometheus_unreachable(self):
        dispatcher = WebhookDispatcher()
        verify_config = {
            "wait": 0,
            "prometheus_url": "http://unreachable:9090",
            "query": 'up == 1',
            "description": "check",
        }

        with patch("nthlayer_respond.safe_actions.webhook.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await dispatcher._verify(verify_config, {})

        assert result.verified is None  # unknown, not failure
```

- [ ] **Step 2: Run tests**

Run: `uv run --extra dev pytest tests/test_webhook.py -v`
Expected: ALL PASS

- [ ] **Step 3: Run full suite**

Run: `uv run --extra dev pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 4: Commit and push**

```bash
git add tests/test_webhook.py
git commit -m "test: PromQL verification tests for WebhookDispatcher"
git push origin main
```

---

## Verification Checklist

1. `binding: stub` or no binding → existing stub behavior (176 existing tests pass)
2. Webhook binding → httpx POST with rendered URL, resolved secrets, retried on failure
3. `verify_after` → waits, queries Prometheus, returns `verified: true/false/null`
4. Missing `${ENV_VAR}` → clear error, execution fails gracefully
5. Template rendering → `{{service}}` replaced in URL, headers, body, query
