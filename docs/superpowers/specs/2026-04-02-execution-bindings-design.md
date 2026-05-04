# Execution Bindings Design — Safe Action Webhook Dispatch

**Date:** 2026-04-02
**Bead:** opensrm-9sv.3
**Status:** Design approved, ready for implementation plan

## Problem

nthlayer-respond's remediation agent can recommend safe actions (rollback, scale_up, etc.) but cannot execute them. The 5 handler stubs log intent and return `{"success": true}` without making any real changes. The gap: "recommend rollback" vs "actually execute rollback and verify the system improved."

## Design

### Binding in safe-actions.yaml

Each safe action gets a `binding` section that defines how to execute it. Policy and binding are a single unit — an action declared safe without a working binding is incomplete.

```yaml
actions:
  rollback:
    description: >
      Roll back a service to its previous stable deployment.
    risk: high
    requires_approval: true
    cooldown_seconds: 300
    target_type: service
    applicable_to:
      service_types: [api, worker, ai-gate]
      failure_modes: [deployment_regression, model_regression]
    binding:
      method: webhook
      url: "https://argocd.internal/api/v1/applications/{{service}}/rollback"
      headers:
        Authorization: "Bearer ${ARGOCD_TOKEN}"
        Content-Type: "application/json"
      body:
        revision: "{{previous_revision}}"
        prune: true
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

When no binding is configured, the stub handler fires (current behavior). For development/demo, actions can be explicitly marked `binding: stub`.

### Template Variables

Templates use `{{variable}}` syntax (same as prompt templates). Available variables:

| Variable | Source | Example |
|----------|--------|---------|
| `{{service}}` | `target` parameter from remediation result | `fraud-detect` |
| `{{target}}` | Same as service (alias) | `fraud-detect` |
| `{{incident_id}}` | `context.id` | `INC-FRAUD-20260402` |
| `{{severity}}` | `context.triage.severity` | `1` |
| `{{previous_revision}}` | From change event in correlation verdict | `v2.2` |

### Secret Resolution

`${ENV_VAR}` syntax resolves from `os.environ` at execution time. Secrets are never logged, stored in verdicts, or included in prompts. If an env var is missing, the binding fails with a clear error: `"Secret ${ARGOCD_TOKEN} not set"`.

### Verification (verify_after)

The most important part. After the webhook fires, the dispatcher waits `wait` seconds, then queries Prometheus with the `query` PromQL expression. The query must return a scalar boolean result (comparison operator).

```yaml
verify_after:
  wait: 60                    # seconds to wait before checking
  prometheus_url: "${PROMETHEUS_URL}"  # defaults to PROMETHEUS_URL env var
  query: >                   # PromQL with {{variable}} interpolation
    rate(http_server_request_duration_count{service="{{service}}", status=~"5.."}[2m])
    / rate(http_server_request_duration_count{service="{{service}}"}[2m])
    < 0.01
  description: "error rate below 1% within 60s of rollback"
```

**Verification result:**
- Query returns `1` (true): action verdict records `verified: true`. Incident can proceed to resolution.
- Query returns `0` (false) or fails: action verdict records `verified: false, verification_detail: "error rate 3.2%, expected < 1%"`. Respond escalates to human — the rollback didn't fix the problem.
- Query times out or Prometheus unreachable: `verified: null` (unknown). Logged as warning, not treated as failure.

The verification uses the same Prometheus instance that nthlayer-measure already talks to — no new infrastructure.

### Per-Action Binding Examples

```yaml
  scale_up:
    binding:
      method: webhook
      url: "https://k8s-api.internal/apis/apps/v1/namespaces/{{namespace}}/deployments/{{service}}/scale"
      headers:
        Authorization: "Bearer ${K8S_TOKEN}"
      body:
        spec:
          replicas: "{{current_replicas + 2}}"
      timeout: 15
      verify_after:
        wait: 30
        query: >
          avg_over_time(up{service="{{service}}"}[1m]) == 1
        description: "service healthy after scale-up"

  disable_feature_flag:
    binding:
      method: webhook
      url: "https://flagsmith.internal/api/v1/flags/{{target}}"
      headers:
        Authorization: "Bearer ${FLAGSMITH_TOKEN}"
      body:
        enabled: false
      timeout: 10
      # No verify_after — feature flag changes are instant

  reduce_autonomy:
    binding:
      method: webhook
      url: "${NTHLAYER_MEASURE_URL}/api/v1/governance/reduce"
      body:
        agent: "{{target}}"
        reason: "{{incident_id}}: model quality degradation detected"
      timeout: 10
      # No verify_after — autonomy reduction is instant and one-way

  pause_pipeline:
    binding:
      method: webhook
      url: "https://argocd.internal/api/v1/applications/{{service}}/sync"
      headers:
        Authorization: "Bearer ${ARGOCD_TOKEN}"
      body:
        prune: false
        dryRun: true
      timeout: 15
      verify_after:
        wait: 10
        query: >
          argocd_app_info{name="{{service}}", sync_status="Synced"} == 1
        description: "pipeline paused, no new syncs in progress"
```

## Components

### WebhookDispatcher (`safe_actions/webhook.py`)

New file. Handles the entire execution lifecycle:

```python
class WebhookDispatcher:
    """Execute safe action bindings via HTTP webhooks."""

    async def execute(self, binding: dict, variables: dict) -> ExecutionResult:
        """Render templates, resolve secrets, make HTTP call, verify."""

    def _render_templates(self, obj: Any, variables: dict) -> Any:
        """Recursively render {{var}} in strings."""

    def _resolve_secrets(self, obj: Any) -> Any:
        """Recursively resolve ${ENV_VAR} in strings."""

    async def _verify(self, verify_config: dict, variables: dict) -> VerificationResult:
        """Wait, query Prometheus, return verified/not-verified/unknown."""
```

`ExecutionResult` dataclass:
```python
@dataclass
class ExecutionResult:
    success: bool
    status_code: int | None
    detail: str
    verified: bool | None  # True/False/None (unknown)
    verification_detail: str | None
```

### Modified: actions.py

`register_builtin_actions()` reads the `binding` section from each action's YAML spec. If `binding` is present and not `"stub"`, the handler wraps a `WebhookDispatcher.execute()` call. If `binding` is absent or `"stub"`, the existing stub handler is used.

```python
def _make_webhook_handler(binding_config: dict):
    """Create a handler that dispatches via webhook."""
    dispatcher = WebhookDispatcher()
    async def handler(target, context, **kwargs):
        variables = _build_variables(target, context, kwargs)
        return await dispatcher.execute(binding_config, variables)
    return handler
```

### Modified: registry.py

`SafeAction` gains an optional `binding` field. `execute()` is unchanged — it calls `action.handler()` regardless of whether it's a stub or webhook handler. The abstraction is at the handler level, not the registry level.

### Verdict enrichment

When a safe action executes via webhook, the verdict `metadata.custom` includes:
```json
{
  "execution": {
    "method": "webhook",
    "status_code": 200,
    "verified": true,
    "verification_detail": "error rate 0.3%, target < 1%",
    "timestamp": "2026-04-02T10:15:30Z"
  }
}
```

## What Doesn't Change

- Approval ratchet — model can escalate, never downgrade
- Cooldown tracking — SQLite-backed, checked before every execution
- Blast radius check — called before handler, blocks if check fails
- Coordinator approve/reject flow — unchanged
- Remediation agent _post_execute — calls `registry.execute()` as before
- Demo/development mode — actions without bindings use stubs

## Validation

`nthlayer validate` (or a startup check) should warn:
- Action declared but no binding and not marked `binding: stub`
- Binding references `${ENV_VAR}` that is not set
- `verify_after.query` contains `{{variables}}` not in the available variable list

## Verification

1. Stub mode: `binding: stub` or no binding → existing behavior (176 tests pass)
2. Webhook mode: mock httpx in tests, verify URL rendering, secret resolution, retry
3. Verification mode: mock Prometheus query response, verify `verified: true/false/null`
4. Demo scenario: configure rollback with Prometheus verify, run scenario, check verdict has `verified: true`
