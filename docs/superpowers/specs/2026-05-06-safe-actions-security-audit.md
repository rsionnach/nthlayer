# Safe-actions and webhook execution audit (P4-SEC.2, opensrm-9uow.2)

**Date:** 2026-05-06
**Scope:** `nthlayer-workers/src/nthlayer_workers/respond/safe_actions/`
**Bead:** opensrm-9uow.2

## Findings

### 1. SSRF prevention — FIXED via host allowlist

**Pre-audit**: `WebhookDispatcher` accepted any URL specified in the
binding config and dispatched `httpx.AsyncClient.post()` with no
allowlist or scheme guard. An operator misconfiguration or a malicious
binding insertion could redirect calls to internal addresses (cloud
metadata endpoints `169.254.169.254`, internal admin services, etc.).

**Fix**: introduced a host-level allowlist:

- `WebhookDispatcher(allowlist=...)` accepts an explicit `set[str]` of
  `host` or `host:port` entries.
- Default reads from `NTHLAYER_WEBHOOK_ALLOWLIST` env var
  (comma-separated).
- Default-empty is **fail-closed** — no allowlist means no webhook
  succeeds. Operators must opt in to each host.
- Non-`http`/`https` schemes are rejected (`file://`, `gopher://`).
- Loopback (`127.0.0.1`, `localhost`) blocked unless explicitly
  allowlisted.
- Allowlist check runs **before** the network call; rejected URLs never
  produce a `httpx` request.

**Tests** (`TestAllowlist`, 5 tests):
default-empty fail-closed, env-var pickup, non-allowlisted host
rejected, loopback blocked, non-http scheme rejected.

### 2. Parameter / template injection — FIXED via secret-then-render order

**Pre-audit**: the binding config was rendered with incident variables
**before** secrets were resolved:

```python
rendered = render_binding_templates(binding, variables)  # variables → binding
rendered = resolve_secrets(rendered)                      # ${VAR} → env
```

A variable value of `${MY_SECRET}` (from an attacker-controlled service
name or kwarg) would substitute into the binding, then be re-resolved as
a secret reference, exfiltrating the env var into the URL or body.

**Fix**: reverse the order.

```python
resolved = resolve_secrets(binding)        # operator ${VAR} → env (trusted source)
rendered = render_binding_templates(resolved, variables)  # incident vars → resolved
```

Plus a defensive guard at the variables boundary: any variable value
containing `${...}` is rejected with `success=False` before substitution
occurs. Even if order is reversed in the future, the guard catches the
attempt.

**Tests** (`TestVariableInjection`, 2 tests): a variable containing
`${LEAKED}` produces failure with the secret value not appearing in
`detail`; clean variables pass.

### 3. Secrets in verdicts — FIXED via response body opacity

**Pre-audit**: on success the dispatcher returned `detail=resp.text[:500]`
and on HTTP error returned `detail=f"HTTP {status}: {text[:200]}"`. An
echo-server-style misconfigured webhook would reflect the request body
(including resolved `Authorization: Bearer ...` headers) into the
result detail. This `detail` flows into the safe-action result, then
into the remediation verdict's `metadata.custom`, then into bench briefs
and decision-record audit chains.

**Fix**: response bodies never enter `detail`. Success returns
`f"webhook returned {status_code}"`; HTTP errors return
`f"HTTP {status_code}"`; timeouts and exceptions return generic strings
(`"webhook call failed"`). The status code itself is preserved as a
typed field for operator-facing diagnostics.

**Tests** (`TestResponseBodyOpacity`, 2 tests): inject a webhook that
echoes a leaked secret in its response; assert the secret string does
not appear in the result `detail` for either success or error paths.

### 4. Cooldown bypass — SAFE

`SafeActionRegistry.execute()` is the only entry point that calls a
handler. It checks cooldown before dispatch, records execution after.
SQL is parameterised. No alternate path bypasses the check.

**Caveat (filed as future hardening)**: a window exists between
`check_cooldown()` and `_record_execution()` where two concurrent calls
could both pass. Single-instance v1.5 deployment makes this unreachable
in practice; multi-instance HA (v2 work) needs SQL-level conditional
INSERT or CAS to close the race.

### 5. Fail-closed on execution error — VERIFIED

- Unknown action name → `KeyError` from `registry.get()`.
- Cooldown violation → `RuntimeError`.
- Blast radius check failure → `RuntimeError`.
- Secret resolution failure → `ExecutionResult(success=False, detail=...)`.
- Non-allowlisted URL → `ExecutionResult(success=False, ...)`.
- Variable injection attempt → `ExecutionResult(success=False, ...)`.
- HTTP error after retries → `ExecutionResult(success=False, ...)`.
- Verification query failure → `verified=None` (best-effort, action
  already executed; documented intentional fail-open for verification
  only, not for execution).

All execution paths fail closed. The verification path is intentionally
fail-open because verification runs **after** the action has already
been dispatched; the absence of verification data does not change
whether the action ran.

## Acceptance criteria

| # | Criterion | State |
|---|---|---|
| 1 | Webhook URLs allowlisted | ✅ Default-deny allowlist; `NTHLAYER_WEBHOOK_ALLOWLIST` env var or constructor param |
| 2 | Secrets never in verdicts | ✅ Secret-then-render ordering + variable injection guard + response body opacity |
| 3 | Fail-closed on execution error | ✅ All execution paths return `success=False`; only verification is fail-open by design |
| 4 | Injection rejected | ✅ Variables containing `${...}` rejected at boundary |

## Known limitations (deliberately deferred)

- **Concurrent cooldown race.** `check_cooldown` → handler call →
  `_record_execution` is not atomic. v1.5 single-instance deployment
  makes this unreachable; v2 multi-instance work must close the race
  with SQL-level CAS.
- **Allowlist is host-only, not path.** A binding `url:
  https://api.internal/admin/delete-everything` is allowed if
  `api.internal` is allowlisted. Operators must trust the binding YAML
  authors; path-level review is out of scope for v1.5.
- **No request body redaction in server-side logging.** structlog logs
  do not include request bodies, but if operators add ad-hoc logging
  they need to be cautious. Documented for review.
- **No SHA-256-based binding integrity check.** A modified
  `safe-actions.yaml` would not be flagged. Tracked for v2.

## Cross-references

- Beads: `opensrm-9uow.2` (this audit), `opensrm-9uow.1` (Core API
  audit, separate scope), `opensrm-9uow.3` (dependency audit, P2).
- Code: `nthlayer-workers/src/nthlayer_workers/respond/safe_actions/webhook.py`,
  `registry.py`, `actions.py`.
- Tests: `nthlayer-workers/tests/respond/test_webhook.py` —
  `TestAllowlist`, `TestVariableInjection`, `TestResponseBodyOpacity`.
- Related decisions:
  `2026-05-06-core-api-security-audit.md` (Core API audit, parallel
  scope).
