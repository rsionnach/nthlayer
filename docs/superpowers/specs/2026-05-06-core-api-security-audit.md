# nthlayer-core security audit (P4-SEC.1, opensrm-9uow.1)

**Date:** 2026-05-06
**Scope:** `nthlayer-core/src/nthlayer_core/server.py` HTTP API + `store.py` SQLite layer
**Bead:** opensrm-9uow.1

## Findings

### 1. SQL injection — SAFE

Every `cursor.execute()` call in `store.py` uses parameterised queries (`?`
placeholders). Dynamic `WHERE` clauses are composed from a hardcoded
fragment list (`"service = ?"`, `"type = ?"`, etc.) joined with
`" AND "` and never include user-supplied identifiers. Audited paths:

- `query_verdicts` (store.py:245) — clauses are hardcoded; values
  parameterised.
- `query_assessments` (store.py:336) — same pattern.
- `query_cases` (store.py:436) — same pattern.
- `query_suppressions` (store.py:600) — same pattern.

The `f"SELECT ... WHERE {where} LIMIT ?"` template looks risky at first
glance, but `where` is built from a closed allowlist of column names; no
user input flows into the SQL string itself.

`_normalise_timestamp` uses `re.sub` to repair URL-decoded timezone
offsets before SQL parameter binding — operates on the parameter value,
not the SQL.

**No action required.**

### 2. Error leakage — FIXED

**Pre-audit**: five 500 handlers returned the raw exception string:

```python
return JSONResponse(
    {"error": "store_error", "detail": {"message": str(e)}},
    status_code=500,
)
```

This exposed SQLite error messages (constraint names, column types,
schema hints) to any caller that could POST. Sites:

- `post_verdict` (server.py:220-223)
- `post_verdict_outcome` (server.py:323-326)
- `post_assessment` (server.py:369-372)
- `post_case` (server.py:444-447)
- `post_change_freeze` (server.py:616-619)

**Fix**: introduced `_store_error_response(handler, exc, **context)`
helper. It emits a structlog `core_store_error` line server-side with
full exception type/string/context, and returns a generic 500 to the
client:

```json
{"error": "internal_error", "detail": {"message": "store operation failed"}}
```

**Tests**: `TestStoreErrorOpacity` (3 tests in
`nthlayer-core/tests/test_api.py`) inject store failures with leaky
messages (`UNDISCLOSED: PRAGMA table_info(...)`, `column 'kind'
constraint failed`, `foreign key fk_... violated`) and assert the
response body contains none of the original strings.

### 3. Input validation — ACCEPTABLE

Validated:

- Required fields enforced on POST endpoints (id/type/created_at on
  verdicts; id/service/kind/created_at on assessments;
  id/kind/created_at/underlying_verdict on cases; etc.).
- ISO timestamp parsing with try/except on lease and change_freeze.
- `_parse_int_param` validates non-negative integers on query params.
- CloudEvents envelope validation via `_unwrap_envelope` /
  `_validate_required` (see envelope-contract decision doc).

Gaps (known limitations, not fixed in v1.5):

- **No string length limits.** A 1GB verdict ID is technically
  acceptable; Starlette has no default body-size limit.
- **No deep type validation** — `body["id"]` could be a list/dict; SQLite
  will accept it serialised but downstream consumers may break.
- **No JSON depth limit** — pathological nested structures consume
  memory.

These are documented under "Known limitations" below; addressing them is
v2 hardening work.

### 4. Path / file injection — SAFE

The two file-system inputs (`NTHLAYER_STORE_PATH`, `NTHLAYER_MANIFESTS_DIR`)
come from server-side environment variables, not request data. Path
parameters from requests (`{verdict_id}`, `{service}`, `{component}`)
are used as SQL parameters or dict keys, never concatenated into
filesystem paths.

## Known limitations (deliberately deferred)

The following are out of scope for v1.5; they are documented as known
limitations rather than fixed:

- **No authentication / authorisation.** The server has no AuthN or
  AuthZ — anyone with network access can POST verdicts, lift change
  freezes, resolve cases. Phase 0 deferred auth to v2 (see
  `docs/superpowers/plans/2026-04-21-phase-0-decisions.md`). v1.5
  deployments must rely on network-level access control (private VPC,
  internal-only ingress, etc.).
- **No CORS / CSRF protection.** No middleware sets CORS headers; no
  CSRF token validation. Browser-based attacks are possible if the API
  is exposed to a domain visited by an authenticated browser.
  Mitigation: do not expose the API to public networks or domains
  reachable from operator browsers.
- **No rate limiting.** A single client can flood writes; no per-IP or
  per-component throttle. Mitigation: front the API with a load
  balancer that enforces rate limits, or rely on the v1.5 single-tenant
  deployment assumption.
- **No body size limit.** Starlette's default is unbounded; a malicious
  POST can consume memory. Mitigation: front the API with a reverse
  proxy that enforces `client_max_body_size`.
- **No request schema validation beyond required fields.** Unexpected
  fields are stored in the JSON content blob without warning.

These limitations are acceptable for v1.5's deployment shape (single
tenant, internal network, trusted callers). v2 hardening work is tracked
under the Phase 4-SEC epic.

## Acceptance criteria

| # | Criterion | State |
|---|---|---|
| 1 | All SQL parameterised | ✅ Audited; all `execute()` calls use `?` placeholders |
| 2 | No stack traces in responses | ✅ Fixed; `_store_error_response` returns generic message |
| 3 | Input validated | ✅ Required fields + types + timestamp + integer ranges; size/depth limits documented as known limitations |
| 4 | Known limitation documented | ✅ Auth, CORS, rate limiting, body size all called out |

## Cross-references

- Beads: `opensrm-9uow.1` (this audit), `opensrm-9uow.2` (safe-actions
  audit, separate scope), `opensrm-9uow.3` (dependency audit).
- Code: `nthlayer-core/src/nthlayer_core/server.py`,
  `nthlayer-core/src/nthlayer_core/store.py`.
- Tests: `nthlayer-core/tests/test_api.py::TestStoreErrorOpacity`.
- Decisions: `2026-04-21-phase-0-decisions.md` (auth deferred to v2),
  `envelope-contract-auto-detect-to-mandatory.md` (envelope error
  contract).
