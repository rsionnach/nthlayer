# NthLayer Execution Bindings & Change Events Spec

## Overview

Two connected capabilities that close the remediation loop and enrich correlation:

**Execution Bindings** — when nthlayer-respond recommends a safe action (rollback, disable_feature_flag, reduce_autonomy), NthLayer can execute it by calling the operator's infrastructure via configured webhook bindings. NthLayer produces the judgment. The operator's tooling performs the execution. The binding is the bridge.

**Change Events** — when something changes in the system (deploy, config update, feature flag toggle, model version swap), NthLayer records it as a structured event that feeds into correlation. When correlate runs, it cross-references the breach timing against recent change events to identify causal relationships. This is the difference between "fraud-detect is degraded" and "fraud-detect is degraded, and model v2.3 was deployed 4 minutes ago."

The connection: every executed safe action IS a change event. When NthLayer triggers a rollback via GitHub Actions, that rollback is recorded as a change event. If the rollback causes a new problem, correlate will link the new breach to the rollback. The system is self-aware of its own actions.

---

# PART 1: EXECUTION BINDINGS

## Problem

nthlayer-respond's remediation agent recommends actions but cannot execute them. The incident state goes to `awaiting_approval` and a human must manually perform the action. For teams that want semi-autonomous or fully-autonomous remediation, NthLayer needs to trigger the action through the operator's existing infrastructure.

## Design Principle

**NthLayer is the judgment layer, not the execution layer.** It decides what should happen based on the OpenSRM spec, the correlation evidence, and the AI agent's reasoning. The operator's infrastructure decides how it happens. NthLayer makes an authenticated HTTP call to trigger a workflow, flip a flag, or invoke an API. It does not SSH into servers, modify Kubernetes resources directly, or run arbitrary scripts on production infrastructure.

The execution binding is a webhook template. Every tool in the market has a REST API. GitHub Actions, ArgoCD, LaunchDarkly, PagerDuty, Slack, Jira, Kubernetes API — all accessible via HTTP. The operator configures the URL, headers, and body template for each safe action. NthLayer renders the template with incident context and makes the call.

## Execution Binding Schema

Execution bindings live in the safe action registry (`specs/safe-actions.yaml`), extending each action with an `execution` block:

```yaml
# specs/safe-actions.yaml
apiVersion: opensrm/v1
kind: SafeActionRegistry
metadata:
  name: production
  environment: production

actions:
  rollback:
    description: "Revert service to previous known-good version"
    risk: low
    requires_approval: false
    applicable_to:
      service_types: [api, ai-gate]
      failure_modes: [deploy_regression, model_regression, config_change]
    blast_radius: "Target service only. Downstream services recover automatically."
    estimated_recovery: "2-5 minutes"

    execution:
      type: webhook
      url: "https://api.github.com/repos/{{ org }}/{{ service }}/actions/workflows/rollback.yml/dispatches"
      method: POST
      headers:
        Authorization: "Bearer {{ GITHUB_TOKEN }}"
        Accept: "application/vnd.github.v3+json"
        Content-Type: "application/json"
      body:
        ref: "main"
        inputs:
          service: "{{ service }}"
          target_version: "{{ previous_version }}"
          reason: "{{ incident_id }}: {{ reasoning }}"
          triggered_by: "nthlayer-respond"
      success_codes: [204]
      timeout: 30

  disable_feature_flag:
    description: "Disable a feature flag to remove recently enabled functionality"
    risk: low
    requires_approval: false
    applicable_to:
      service_types: [api, ai-gate]
      failure_modes: [config_change, feature_regression]

    execution:
      type: webhook
      url: "https://app.launchdarkly.com/api/v2/flags/{{ project }}/{{ flag_key }}"
      method: PATCH
      headers:
        Authorization: "{{ LAUNCHDARKLY_API_KEY }}"
        Content-Type: "application/json"
      body:
        patch:
          - op: "replace"
            path: "/environments/production/on"
            value: false
        comment: "{{ incident_id }}: Disabled by NthLayer respond"
      success_codes: [200]
      timeout: 15

  reduce_autonomy:
    description: "Reduce AI agent autonomy level one step"
    risk: low
    requires_approval: false
    applicable_to:
      service_types: [ai-gate]
      failure_modes: [model_regression, confidence_degradation]

    execution:
      # Internal execution — NthLayer's own governance, no external call
      type: internal
      action: "governance.reduce_autonomy"
      params:
        service: "{{ service }}"
        target_level: "{{ target_level }}"

  scale_up:
    description: "Increase replica count for the target service"
    risk: low
    requires_approval: false
    applicable_to:
      service_types: [api]
      failure_modes: [capacity, latency]
    not_applicable_to:
      failure_modes: [model_regression]
      reason: "Scaling does not address model quality issues"

    execution:
      type: webhook
      url: "{{ ARGOCD_URL }}/api/v1/applications/{{ service }}/resource-actions"
      method: POST
      headers:
        Authorization: "Bearer {{ ARGOCD_TOKEN }}"
        Content-Type: "application/json"
      body:
        action: "scale"
        params:
          replicas: "{{ current_replicas + 2 }}"
      success_codes: [200]
      timeout: 30

  pause_pipeline:
    description: "Pause a data or ML pipeline to stop processing"
    risk: medium
    requires_approval: true
    applicable_to:
      service_types: [ai-gate, pipeline]
      failure_modes: [data_quality, model_regression]

    execution:
      type: webhook
      url: "https://api.github.com/repos/{{ org }}/{{ service }}/actions/workflows/pause-pipeline.yml/dispatches"
      method: POST
      headers:
        Authorization: "Bearer {{ GITHUB_TOKEN }}"
        Content-Type: "application/json"
      body:
        ref: "main"
        inputs:
          pipeline: "{{ service }}"
          reason: "{{ incident_id }}: {{ reasoning }}"
      success_codes: [204]
      timeout: 30

  restart_service:
    description: "Rolling restart via Kubernetes (no downtime)"
    risk: medium
    requires_approval: true

    execution:
      type: webhook
      url: "{{ ARGOCD_URL }}/api/v1/applications/{{ service }}/actions/restart"
      method: POST
      headers:
        Authorization: "Bearer {{ ARGOCD_TOKEN }}"
      success_codes: [200]
      timeout: 60
```

## Execution Types

### `type: webhook` (primary, covers 90% of cases)

An authenticated HTTP call to an external API. NthLayer renders the URL, headers, and body templates with incident context, makes the call, and records the result.

Every tool with a REST API is supported without custom code: GitHub Actions (workflow dispatch), ArgoCD (application actions), LaunchDarkly (flag updates), PagerDuty (incident creation), Slack (message posting), Jira (issue creation), Kubernetes API (rolling restart, scale), and any custom webhook endpoint.

### `type: internal` (NthLayer's own governance actions)

Actions that NthLayer executes within its own ecosystem. No external HTTP call. Currently: `governance.reduce_autonomy` (reduce an AI agent's autonomy level via nthlayer-measure's governance engine). Future: `spec.update` (apply a spec recommendation from learn), `generate.reload` (re-generate monitoring after spec change).

### `type: manual` (future, v2)

Creates a task for a human in a ticketing system. The execution binding specifies a Jira/Linear/GitHub Issues template. NthLayer creates the ticket with the action details, evidence, reasoning, and verdict lineage. The human performs the action and closes the ticket. NthLayer tracks the ticket status.

### `type: script` (future, v3, requires careful security review)

Executes a local script or command on the NthLayer host. Example: `command: "./scripts/rollback.sh {{ service }} {{ previous_version }}"`. High risk — requires sandboxing, audit logging, and explicit operator opt-in. Should only be considered for air-gapped environments where webhook execution isn't possible.

## Template Variables

Templates use `{{ variable }}` syntax (Jinja2-compatible). Variables come from three sources:

**Incident context** (available for all actions):
- `{{ service }}` — the affected service name
- `{{ incident_id }}` — the incident identifier (e.g. INC-FRAUD-DETECT-20260331-160546)
- `{{ severity }}` — the triage severity (1-4)
- `{{ reasoning }}` — the remediation agent's rationale
- `{{ root_cause_type }}` — from correlation (model_regression, deploy_regression, etc.)
- `{{ blast_radius }}` — list of affected services
- `{{ confidence }}` — the remediation agent's confidence score
- `{{ timestamp }}` — current UTC timestamp

**Service context** (from the OpenSRM spec):
- `{{ service_type }}` — ai-gate, api, etc.
- `{{ tier }}` — critical, standard, etc.
- `{{ team }}` — owning team name
- `{{ org }}` — GitHub org (from spec metadata or config)
- `{{ previous_version }}` — last known-good version (from change events or spec)

**Environment variables** (secrets, resolved at render time):
- `{{ GITHUB_TOKEN }}` — resolved from `$GITHUB_TOKEN` env var
- `{{ LAUNCHDARKLY_API_KEY }}` — resolved from `$LAUNCHDARKLY_API_KEY` env var
- `{{ ARGOCD_TOKEN }}` — resolved from `$ARGOCD_TOKEN` env var
- `{{ ARGOCD_URL }}` — resolved from `$ARGOCD_URL` env var
- Any `{{ UPPER_CASE }}` variable is resolved from the environment

Environment variables are never logged or written to verdicts. Template rendering replaces them at call time and discards them immediately.

## Execution Flow

```
Remediation agent recommends: "rollback on fraud-detect"
    │
    ▼
Parser validates:
    ✓ rollback is in registry
    ✓ applicable to ai-gate + model_regression
    ✗ if novel action → reject, force requires_approval=true
    │
    ▼
Approval check:
    if requires_approval == true:
        → verdict written: "awaiting_approval"
        → STOP (human approves via `nthlayer approve <verdict-id>`)
    if requires_approval == false:
        → proceed to execution
    │
    ▼
Execution binding loaded from safe-actions.yaml
    │
    ▼
Template rendered with incident context:
    url = "https://api.github.com/repos/acme/fraud-detect/actions/workflows/rollback.yml/dispatches"
    headers = { Authorization: "Bearer ghp_xxx...", ... }
    body = { ref: "main", inputs: { service: "fraud-detect", target_version: "v2.2", ... } }
    │
    ▼
HTTP call:
    POST url with headers and body
    │
    ├─ Success (status in success_codes):
    │   → execution_result = "success"
    │   → Record change event (Part 2 of this spec)
    │   → Update verdict: "executed", execution_result, response details
    │
    ├─ Failure (HTTP error, timeout):
    │   → execution_result = "failed: {error}"
    │   → Update verdict: "execution_failed", error details
    │   → Escalate: force requires_approval=true for retry
    │
    └─ No binding configured:
        → execution_result = "no_binding"
        → Verdict notes: "Action recommended but no execution binding configured"
        → Incident stays in awaiting_approval for manual execution
```

## Approval Workflow

### Auto-approved actions (requires_approval: false)

The remediation agent recommends an action. The parser validates it against the registry. If the registry says `requires_approval: false` and the action is applicable to this failure mode, NthLayer executes immediately. The verdict records the execution result.

### Actions requiring approval (requires_approval: true)

The remediation agent recommends an action. The verdict is written with state `awaiting_approval`. A human reviews and approves:

```bash
# List pending approvals
nthlayer approve list --verdict-store ./verdicts.db

# Approve and execute
nthlayer approve execute <verdict-id> --verdict-store ./verdicts.db --registry ./specs/safe-actions.yaml

# Approve but don't execute (human will perform manually)
nthlayer approve ack <verdict-id> --verdict-store ./verdicts.db

# Reject
nthlayer approve reject <verdict-id> --reason "Not appropriate for this situation"
```

`nthlayer approve execute` reads the verdict, loads the execution binding from the registry, renders the template, and makes the HTTP call. Same execution path as auto-approved, just gated by the human approval step.

### The Approval Ratchet

The registry's `requires_approval` is a floor, not a ceiling. The remediation agent can escalate to `requires_approval: true` even if the registry says false. The agent cannot downgrade to false if the registry says true. This is the one-way safety ratchet.

Additionally, if any execution attempt fails (HTTP error, timeout), the action is automatically escalated to `requires_approval: true` for any retry. Failed automation becomes manual until a human explicitly re-enables it.

## Implementation

### File: nthlayer-common/src/nthlayer_common/execution.py (NEW)

```python
"""
Execution engine for safe action bindings.

Renders webhook templates with incident context and makes
authenticated HTTP calls to trigger actions in the operator's
infrastructure.
"""

import os
import re
import json
import httpx
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionResult:
    """Result of executing a safe action."""
    action: str                     # Action name (rollback, scale_up, etc.)
    service: str                    # Target service
    execution_type: str             # webhook, internal, manual, script
    success: bool                   # Whether execution succeeded
    status_code: int | None = None  # HTTP status code (webhook only)
    response_body: str = ""         # Response body (truncated)
    error: str = ""                 # Error message if failed
    duration_ms: int = 0            # Execution time
    change_event_id: str | None = None  # ID of the recorded change event


def render_template(template: Any, context: dict) -> Any:
    """
    Recursively render {{ variable }} placeholders in a template.
    
    - {{ UPPER_CASE }} variables are resolved from environment
    - {{ lower_case }} variables are resolved from context dict
    - Nested dicts and lists are rendered recursively
    """
    if isinstance(template, str):
        def replacer(match):
            var = match.group(1).strip()
            # Environment variable (UPPER_CASE)
            if var.isupper() or var.startswith("GITHUB_") or var.startswith("ARGOCD_") or var.startswith("LAUNCHDARKLY_"):
                value = os.environ.get(var, "")
                if not value:
                    raise ValueError(f"Environment variable {var} not set")
                return value
            # Context variable
            return str(context.get(var, f"{{{{ {var} }}}}"))
        return re.sub(r'\{\{\s*(.+?)\s*\}\}', replacer, template)
    elif isinstance(template, dict):
        return {k: render_template(v, context) for k, v in template.items()}
    elif isinstance(template, list):
        return [render_template(item, context) for item in template]
    return template


def execute_webhook(binding: dict, context: dict, timeout: int = 30) -> ExecutionResult:
    """
    Execute a webhook binding.
    
    Renders the URL, headers, and body templates with incident context,
    makes the HTTP call, and returns the result.
    """
    action = context.get("action", "unknown")
    service = context.get("service", "unknown")
    
    try:
        url = render_template(binding["url"], context)
        method = binding.get("method", "POST").upper()
        headers = render_template(binding.get("headers", {}), context)
        body = render_template(binding.get("body", {}), context)
        success_codes = binding.get("success_codes", [200, 201, 202, 204])
        req_timeout = binding.get("timeout", timeout)
        
        response = httpx.request(
            method=method,
            url=url,
            headers=headers,
            json=body if isinstance(body, dict) else None,
            content=body if isinstance(body, str) else None,
            timeout=req_timeout,
        )
        
        success = response.status_code in success_codes
        
        return ExecutionResult(
            action=action,
            service=service,
            execution_type="webhook",
            success=success,
            status_code=response.status_code,
            response_body=response.text[:500],
            error="" if success else f"HTTP {response.status_code}: {response.text[:200]}",
            duration_ms=int(response.elapsed.total_seconds() * 1000),
        )
        
    except httpx.TimeoutException as e:
        return ExecutionResult(
            action=action, service=service, execution_type="webhook",
            success=False, error=f"Timeout after {timeout}s: {e}",
        )
    except Exception as e:
        return ExecutionResult(
            action=action, service=service, execution_type="webhook",
            success=False, error=str(e),
        )


def execute_internal(binding: dict, context: dict) -> ExecutionResult:
    """Execute an internal NthLayer action."""
    action_path = binding.get("action", "")
    params = render_template(binding.get("params", {}), context)
    
    if action_path == "governance.reduce_autonomy":
        # Call nthlayer-measure's governance engine
        # Implementation: invoke measure CLI or call governance directly
        return ExecutionResult(
            action=context.get("action", "unknown"),
            service=context.get("service", "unknown"),
            execution_type="internal",
            success=True,  # Placeholder — wire to actual governance
            response_body=f"Autonomy reduced for {params.get('service')}",
        )
    
    return ExecutionResult(
        action=context.get("action", "unknown"),
        service=context.get("service", "unknown"),
        execution_type="internal",
        success=False,
        error=f"Unknown internal action: {action_path}",
    )


def execute_action(action_name: str, binding: dict, context: dict) -> ExecutionResult:
    """
    Execute a safe action using its binding configuration.
    
    Routes to the appropriate executor based on binding type.
    """
    exec_type = binding.get("type", "webhook")
    
    # Add action name to context
    context = {**context, "action": action_name}
    
    if exec_type == "webhook":
        return execute_webhook(binding, context)
    elif exec_type == "internal":
        return execute_internal(binding, context)
    elif exec_type == "manual":
        return ExecutionResult(
            action=action_name, service=context.get("service", "unknown"),
            execution_type="manual", success=True,
            response_body="Manual action created — awaiting human execution",
        )
    else:
        return ExecutionResult(
            action=action_name, service=context.get("service", "unknown"),
            execution_type=exec_type, success=False,
            error=f"Unknown execution type: {exec_type}",
        )
```

### Integration into nthlayer-respond

In the remediation agent's `_post_execute` method (or in the coordinator after remediation completes):

```python
# After remediation agent produces a recommendation:
if not result.requires_human_approval and result.proposed_action:
    # Load execution binding from registry
    registry = load_safe_action_registry(specs_dir / "safe-actions.yaml")
    action_def = registry.get(result.proposed_action)
    
    if action_def and "execution" in action_def:
        # Build execution context from incident
        exec_context = {
            "service": context.service,
            "incident_id": context.incident_id,
            "severity": context.triage.severity if context.triage else "unknown",
            "reasoning": result.reasoning,
            "root_cause_type": context.metadata.get("root_causes", [{}])[0].get("type", "unknown"),
            "blast_radius": context.metadata.get("blast_radius", []),
            "confidence": result.confidence if hasattr(result, "confidence") else 0.5,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "team": context.metadata.get("service_context", {}).get("spec", {}).get("team", "unknown"),
            "org": os.environ.get("GITHUB_ORG", "unknown"),
            "previous_version": "v2.2",  # From change events or spec
        }
        
        exec_result = execute_action(result.proposed_action, action_def["execution"], exec_context)
        
        # Record result on the remediation verdict
        result.executed = exec_result.success
        result.execution_result = exec_result.response_body if exec_result.success else exec_result.error
        
        # Record as a change event (Part 2)
        if exec_result.success:
            record_change_event(
                service=context.service,
                change_type=f"nthlayer_{result.proposed_action}",
                detail=f"NthLayer executed {result.proposed_action}: {result.reasoning}",
                source="nthlayer-respond",
                incident_id=context.incident_id,
                verdict_id=current_verdict_id,
            )
    else:
        # No binding configured — action recommended but not executable
        result.executed = False
        result.execution_result = "No execution binding configured for this action"
```

### CLI: `nthlayer approve`

```bash
# List pending approvals
nthlayer approve list --verdict-store ./verdicts.db
# Output:
# PENDING APPROVALS
# vrd-2026-03-31-xxx  fraud-detect  rollback      SEV-1  conf 0.90  2m ago
# vrd-2026-03-31-yyy  payment-api   scale_up      SEV-2  conf 0.75  5m ago

# Approve and execute via binding
nthlayer approve execute vrd-2026-03-31-xxx \
  --verdict-store ./verdicts.db \
  --registry ./specs/safe-actions.yaml

# Approve but execute manually
nthlayer approve ack vrd-2026-03-31-xxx --verdict-store ./verdicts.db

# Reject with reason
nthlayer approve reject vrd-2026-03-31-xxx \
  --verdict-store ./verdicts.db \
  --reason "Root cause identified as data issue, not model issue. Rollback inappropriate."
```

Each approval action writes a verdict recording the human's decision. The approval verdict has `lineage.context` pointing to the remediation verdict. The audit trail is complete: evaluation → correlation → triage → investigation → remediation → approval → execution.

---

# PART 2: CHANGE EVENTS

## Problem

nthlayer-correlate has a `change_candidates` field on correlation groups and a `ChangeCandidate` type with `temporal_proximity_seconds` and `same_service` fields. The infrastructure is there. But no change events are being recorded, so the field is always empty. Without change events, the correlation says "fraud-detect is degraded, 1 services affected." With change events, it says "fraud-detect is degraded, and model v2.3 was deployed 4 minutes ago on the same service. Temporal proximity: 240s."

Change events are the single highest-value signal for turning correlation into causation.

## Design

Change events are recorded to a lightweight event store (SQLite, same as the verdict store) and queried by correlate during incident analysis. The event store is append-only and time-indexed. Change events expire after a configurable TTL (default 7 days — longer than alerts because change attribution often looks back further).

## Change Event Schema

```python
@dataclass
class ChangeEvent:
    id: str                         # Unique event ID (auto-generated)
    timestamp: str                  # ISO 8601
    service: str                    # Affected service name
    change_type: str                # deploy, config_change, feature_flag, model_version,
                                    # schema_migration, secret_rotation, nthlayer_rollback, etc.
    detail: str                     # Human-readable description
    source: str                     # Where this event came from (github, argocd, launchdarkly,
                                    # nthlayer-respond, manual, webhook)
    environment: str = "production" # Environment
    metadata: dict = field(default_factory=dict)
    # metadata examples:
    #   deploy: { from_version: "v2.2", to_version: "v2.3", commit: "abc123", author: "jdoe" }
    #   feature_flag: { flag: "new-fraud-model", from: false, to: true, project: "fraud" }
    #   model_version: { from: "v2.2", to: "v2.3", registry: "mlflow" }
    #   config_change: { key: "fraud.threshold", from: "0.7", to: "0.5" }
    #   nthlayer_rollback: { incident_id: "INC-xxx", verdict_id: "vrd-xxx" }
```

## Change Event Sources

### 1. CLI command (simplest, always available)

```bash
# Record a change event manually
nthlayer change record \
  --service fraud-detect \
  --type model_version \
  --detail "Model v2.3 deployed" \
  --source manual \
  --metadata '{"from": "v2.2", "to": "v2.3"}' \
  --store ./change-events.db

# List recent change events
nthlayer change list \
  --service fraud-detect \
  --since 1h \
  --store ./change-events.db

# Query change events for a time window (used by correlate)
nthlayer change query \
  --service fraud-detect \
  --from "2026-03-31T16:00:00Z" \
  --to "2026-03-31T17:00:00Z" \
  --format json \
  --store ./change-events.db
```

This is the v0 path. Any CI/CD pipeline can add `nthlayer change record` as a post-deploy step. No webhook infrastructure needed.

### 2. Webhook receiver (production path)

A lightweight HTTP server that receives webhook payloads from CI/CD tools and converts them to change events.

```bash
nthlayer change serve \
  --port 8090 \
  --store ./change-events.db
```

The webhook receiver accepts POST requests and normalises them to change events:

```
POST /webhook/github
POST /webhook/argocd
POST /webhook/launchdarkly
POST /webhook/generic
```

Each webhook path has a provider-specific parser that extracts service name, change type, and metadata from the payload.

#### GitHub webhook parser

GitHub sends webhook payloads for various events. The relevant ones:

- `deployment` event → change event with type `deploy`
- `push` to main/production branch → change event with type `deploy` (if no deployment events configured)
- `release` event → change event with type `release`

```python
def parse_github_webhook(payload: dict, headers: dict) -> ChangeEvent | None:
    event_type = headers.get("X-GitHub-Event", "")
    
    if event_type == "deployment":
        return ChangeEvent(
            service=payload["repository"]["name"],
            change_type="deploy",
            detail=f"Deployment {payload['deployment']['environment']}: {payload['deployment'].get('description', '')}",
            source="github",
            metadata={
                "sha": payload["deployment"]["sha"],
                "environment": payload["deployment"]["environment"],
                "creator": payload["deployment"]["creator"]["login"],
                "ref": payload["deployment"]["ref"],
            },
        )
    
    if event_type == "push" and payload.get("ref") in ("refs/heads/main", "refs/heads/production"):
        return ChangeEvent(
            service=payload["repository"]["name"],
            change_type="deploy",
            detail=f"Push to {payload['ref']}: {payload['head_commit']['message'][:100]}",
            source="github",
            metadata={
                "sha": payload["head_commit"]["id"],
                "author": payload["head_commit"]["author"]["name"],
                "commits": len(payload.get("commits", [])),
            },
        )
    
    return None
```

#### ArgoCD webhook parser

ArgoCD sends notifications on sync events:

```python
def parse_argocd_webhook(payload: dict) -> ChangeEvent | None:
    return ChangeEvent(
        service=payload.get("app", {}).get("metadata", {}).get("name", "unknown"),
        change_type="deploy",
        detail=f"ArgoCD sync: {payload.get('app', {}).get('status', {}).get('sync', {}).get('status', '')}",
        source="argocd",
        metadata={
            "revision": payload.get("app", {}).get("status", {}).get("sync", {}).get("revision", ""),
            "health": payload.get("app", {}).get("status", {}).get("health", {}).get("status", ""),
        },
    )
```

#### LaunchDarkly webhook parser

LaunchDarkly sends flag change events:

```python
def parse_launchdarkly_webhook(payload: dict) -> ChangeEvent | None:
    if payload.get("kind") != "flag":
        return None
    
    # Determine which service this flag belongs to
    # Convention: flag key starts with service name, or use tag metadata
    flag_key = payload.get("key", "")
    service = flag_key.split(".")[0] if "." in flag_key else flag_key.split("-")[0]
    
    return ChangeEvent(
        service=service,
        change_type="feature_flag",
        detail=f"Flag '{flag_key}' changed",
        source="launchdarkly",
        metadata={
            "flag_key": flag_key,
            "action": payload.get("accesses", [{}])[0].get("action", "unknown"),
            "member": payload.get("member", {}).get("email", "unknown"),
        },
    )
```

#### Generic webhook parser

For any tool that can send a JSON webhook:

```
POST /webhook/generic
Content-Type: application/json

{
  "service": "fraud-detect",
  "change_type": "config_change",
  "detail": "Updated fraud threshold from 0.7 to 0.5",
  "metadata": {
    "key": "fraud.threshold",
    "from": "0.7",
    "to": "0.5"
  }
}
```

The generic parser passes through the fields directly. Any tool that can POST JSON can record change events.

### 3. NthLayer's own actions (automatic)

Every executed safe action (Part 1) automatically records a change event. When NthLayer triggers a rollback via GitHub Actions, it records:

```python
ChangeEvent(
    service="fraud-detect",
    change_type="nthlayer_rollback",
    detail="NthLayer executed rollback: AI model quality degradation with 87% confidence",
    source="nthlayer-respond",
    metadata={
        "incident_id": "INC-FRAUD-DETECT-20260331-160546",
        "verdict_id": "vrd-2026-03-31-xxx",
        "action": "rollback",
        "target_version": "v2.2",
    },
)
```

This means if the rollback itself causes a new problem, correlate will link the new breach to the NthLayer-triggered rollback. The system is self-aware.

### 4. CI/CD pipeline integration (recommended production setup)

Add `nthlayer change record` as a step in your deployment pipeline:

```yaml
# GitHub Actions example
- name: Record deployment
  if: success()
  run: |
    nthlayer change record \
      --service ${{ github.event.repository.name }} \
      --type deploy \
      --detail "Deploy ${{ github.sha }}: ${{ github.event.head_commit.message }}" \
      --source github \
      --metadata '{"sha": "${{ github.sha }}", "author": "${{ github.actor }}", "ref": "${{ github.ref }}"}'
```

```yaml
# ArgoCD post-sync hook
apiVersion: batch/v1
kind: Job
metadata:
  name: nthlayer-change-record
  annotations:
    argocd.argoproj.io/hook: PostSync
spec:
  template:
    spec:
      containers:
        - name: record
          image: nthlayer/cli:latest
          command:
            - nthlayer
            - change
            - record
            - --service
            - "{{ .Values.service.name }}"
            - --type
            - deploy
            - --detail
            - "ArgoCD sync to {{ .Values.image.tag }}"
            - --source
            - argocd
```

## Change Event Store

### SQLite schema

```sql
CREATE TABLE change_events (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    service TEXT NOT NULL,
    change_type TEXT NOT NULL,
    detail TEXT NOT NULL,
    source TEXT NOT NULL,
    environment TEXT NOT NULL DEFAULT 'production',
    metadata TEXT NOT NULL DEFAULT '{}',  -- JSON
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    ttl INTEGER NOT NULL DEFAULT 604800   -- 7 days in seconds
);

CREATE INDEX idx_change_events_service_time ON change_events(service, timestamp DESC);
CREATE INDEX idx_change_events_time ON change_events(timestamp DESC);
CREATE INDEX idx_change_events_type ON change_events(change_type, timestamp DESC);
```

### Maintenance

A background cleanup runs periodically (or at the start of each `nthlayer change` command):

```sql
DELETE FROM change_events 
WHERE julianday('now') - julianday(created_at) > ttl / 86400.0;
```

## Integration with Correlate

This is the highest-value change. When correlate runs, it queries the change event store for recent changes affecting services in the blast radius.

### In correlate's event gathering phase

Currently, correlate gathers events from:
1. Prometheus alerts
2. Verdict store (recent evaluation verdicts)

Add a third source:

3. Change event store (recent changes for affected services)

```python
# In correlate's _gather_events (or equivalent):

async def _gather_change_events(
    self,
    affected_services: list[str],
    incident_time: str,
    window_minutes: int = 30,
    change_store_path: str = None,
) -> list[SitRepEvent]:
    """Query recent change events for affected services."""
    if not change_store_path:
        return []
    
    store = ChangeEventStore(change_store_path)
    events = []
    
    for service in affected_services:
        changes = store.query(
            service=service,
            since=incident_time - timedelta(minutes=window_minutes),
            until=incident_time + timedelta(minutes=5),  # Include changes just after breach
        )
        
        for change in changes:
            events.append(SitRepEvent(
                id=change.id,
                timestamp=change.timestamp,
                source=change.source,
                type=EventType.CHANGE,
                service=change.service,
                severity=0.5,  # Changes are neutral severity — the correlation determines impact
                payload={
                    "change_type": change.change_type,
                    "detail": change.detail,
                    **change.metadata,
                },
            ))
    
    return events
```

### In correlate's change indexing

The correlation engine already has change candidate logic. The `ChangeCandidate` type has:
- `temporal_proximity_seconds` — how close the change was to the breach
- `same_service` — whether the change was on the breaching service
- `dependency_related` — whether the change was on a dependency

The change events from the store feed directly into this existing logic. No changes to the correlation algorithm — just a new data source.

### In the reasoning layer prompt

Change events appear in the reasoning prompt as change candidates with temporal proximity:

```
Change candidates for this correlation group:
- fraud-detect: model_version change (v2.2 → v2.3) 4m before breach onset (same_service=true)
  Source: github, Author: jdoe, SHA: abc123
- payment-api: config_change (timeout threshold) 22m before breach onset (dependency_related=true)
  Source: argocd
```

The reasoning layer uses this to produce causal assessments: "Model v2.3 deployed to fraud-detect 4 minutes before reversal rate began climbing. Strong temporal proximity on the same service. Confidence: 0.90."

### New CLI flag for correlate

```bash
nthlayer-correlate correlate \
  --trigger-verdict <id> \
  --prometheus-url http://localhost:9090 \
  --specs-dir ./specs/ \
  --verdict-store ./verdicts.db \
  --change-store ./change-events.db    # NEW: path to change event store
```

If `--change-store` is not provided, correlate runs without change events (current behaviour). The change event integration is additive.

## Demo Integration

### Scenario runner records change events

Before degrading fraud-detect, the scenario runner records a change event:

```python
# In demo.sh scenario, before degrading the service:
nthlayer change record \
  --service fraud-detect \
  --type model_version \
  --detail "Model v2.3 deployed (canary → production)" \
  --source github \
  --metadata '{"from": "v2.2", "to": "v2.3", "author": "ml-pipeline", "commit": "abc123"}' \
  --store ./demo-output/change-events.db
```

Then when correlate runs, it finds this change event 4 minutes before the breach and includes it as a change candidate. The correlation verdict now says "model v2.3 deploy correlated with reversal rate breach" instead of just "fraud-detect incident."

### Demo verdict stream shows the change correlation

The correlation verdict card in the browser panel changes from:

```
CORRELATION
fraud-detect incident — 2 services affected
▸ nthlayer-correlate · conf 0.85
```

To:

```
CORRELATION
fraud-detect model v2.3 deploy → reversal rate breach.
4m temporal proximity, same service.
▸ nthlayer-correlate · conf 0.92
```

The confidence increases because the change event provides causal evidence that wasn't available before.

---

## Implementation Order

| Step | Feature | Effort | Priority |
|------|---------|--------|----------|
| 1 | Change event schema + SQLite store | 1 day | Highest — foundation for everything |
| 2 | `nthlayer change record` CLI command | 1 day | Highest — immediate demo value |
| 3 | Correlate: query change events during event gathering | 1-2 days | Highest — the payoff |
| 4 | Demo: scenario runner records change event before degradation | 0.5 days | High — demo improvement |
| 5 | Execution engine (webhook executor + template renderer) | 2 days | High — enables auto-remediation |
| 6 | `nthlayer approve` CLI command | 1 day | High — approval workflow |
| 7 | Integration: respond → execution engine → change event recording | 1-2 days | High — closes the loop |
| 8 | Generic webhook receiver (`nthlayer change serve`) | 2 days | Medium — production path |
| 9 | GitHub webhook parser | 1 day | Medium — most common CI/CD |
| 10 | ArgoCD webhook parser | 1 day | Medium — K8s deployments |
| 11 | LaunchDarkly webhook parser | 1 day | Medium — feature flag provider |
| 12 | CI/CD pipeline examples (GitHub Actions, ArgoCD hooks) | 0.5 days | Low — documentation |

**Steps 1-4 should be done first.** They have the highest impact on the demo and on correlation quality. The execution bindings (steps 5-7) are the next milestone. The webhook parsers (steps 8-11) are production features that can wait.

---

## Audit First (for Claude Code)

Before implementing:

1. **Read correlate's existing change candidate handling.** Where does it look for change candidates? What type is `ChangeCandidate`? How are candidates added to correlation groups? The change event store is a new data source for existing logic.

2. **Read correlate's event gathering code.** Where are alerts and verdict events gathered? The change event query plugs in alongside them as a third source.

3. **Read respond's `_post_execute` method.** Where does the execution result get recorded? The execution binding call happens here.

4. **Read the existing safe action registry loading.** Where is the registry currently loaded in respond? The execution binding is an extension of the existing registry, not a new system.

5. **Check whether a change event store already exists.** The pre-correlation spec described an event store. Check if any of that was implemented.

6. **Document findings before implementing.**

---

## Notes for Claude Code

- **The change event store is separate from the verdict store.** They're both SQLite but different databases with different schemas. Change events have their own TTL and lifecycle. Don't merge them into the verdict store.

- **The webhook receiver is NOT required for v0.** The CLI command (`nthlayer change record`) is sufficient. The demo scenario runner calls it directly. The webhook receiver is for production environments where CI/CD tools push events via HTTP.

- **Environment variables in execution templates must never be logged.** The render function resolves them at call time. The rendered URL, headers, and body (with secrets) are used for the HTTP call and then discarded. The verdict records the execution result (success/failure, status code, response body) but NOT the rendered template with secrets.

- **Every executed action is a change event.** This is automatic, not optional. If NthLayer triggers a rollback, it records a change event. If that rollback causes a problem, correlate will find it. The system must be self-aware of its own actions.

- **The approval workflow is append-only.** Approvals and rejections are verdicts in the verdict store with lineage pointing to the remediation verdict. The audit trail is: evaluation → correlation → triage → investigation → remediation → approval → execution → change event → (if the action causes a new problem) → new evaluation → new correlation referencing the change event.
