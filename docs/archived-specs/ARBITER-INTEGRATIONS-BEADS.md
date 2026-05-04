# ARBITER-INTEGRATIONS-BEADS.md — Implementation Tasks

This document breaks the ARBITER-INTEGRATIONS.md spec into sequential implementation tasks. Each task is self-contained, testable, and builds on the previous one. Give this to Claude Code alongside ARBITER-INTEGRATIONS.md.

The Arbiter's evaluation pipeline already exists. These tasks add an HTTP API and MCP server on top of it.


## Prerequisites

- Arbiter repo with working PipelineRouter, ScoreStore, and verdict integration
- Python 3.11+, pytest, pytest-asyncio
- aiohttp or FastAPI for the HTTP server (recommend FastAPI for automatic OpenAPI docs)


## Task 1: Input Normalisation

**What:** Create the input normalisation layer that converts the simplified external format to the internal evaluation format.

**Files:**
- `arbiter/api/normalise.py`

**Interface:**

```python
@dataclass
class EvaluationRequest:
    agent_name: str
    task_id: str
    output: str
    context: str | None
    service: str | None
    environment: str
    callback_url: str | None
    metadata: dict

def normalise_input(body: dict) -> EvaluationRequest:
    """
    Required fields: agent, output
    Optional with defaults: task_id (uuid4), environment ("production"),
    context (None), service (None), callback_url (None), metadata ({})
    Raises ValueError if required fields missing.
    """
```

**Tests:**
- Valid input with all fields → returns EvaluationRequest with all fields populated
- Minimal input (agent + output only) → returns EvaluationRequest with defaults
- Missing "agent" → raises ValueError
- Missing "output" → raises ValueError
- Extra unknown fields → ignored (not rejected)


## Task 2: Response Builder

**What:** Create the response builder that converts internal verdicts to the simplified external response.

**Files:**
- `arbiter/api/response.py`

**Interface:**

```python
def build_response(verdict: Verdict, governance: GovernanceStatus | None = None) -> dict:
    """
    Returns simplified dict with: verdict_id, action, score, confidence,
    dimensions, reasoning, risk_tier, and optionally governance block.
    """

def build_error_response(status_code: int, message: str, details: dict | None = None) -> dict:
    """
    Standard error format: {"error": message, "status": status_code, "details": ...}
    """
```

**Tests:**
- Verdict with all fields → response has all expected keys
- Verdict without dimensions → response has empty dimensions dict
- Verdict with governance → response includes governance block
- Verdict without governance → response has no governance key


## Task 3: Evaluation Queue

**What:** Async evaluation queue for fire-and-forget requests.

**Files:**
- `arbiter/api/queue.py`

**Interface:**

```python
class EvaluationQueue:
    def __init__(self, router: PipelineRouter, max_workers: int = 5):
        ...

    async def start(self):
        """Start worker tasks."""

    async def stop(self):
        """Drain queue and stop workers."""

    async def submit(self, request: EvaluationRequest) -> str:
        """Submit for async evaluation. Returns eval_id."""

    async def get_result(self, eval_id: str) -> dict:
        """Get result by eval_id. Returns status: queued|evaluating|complete|error|not_found."""

    async def _send_callback(self, url: str, result: dict):
        """POST verdict to callback URL. Fire and forget with 3 retries."""
```

**Tests:**
- Submit request → returns eval_id, status is "queued"
- After processing → status is "complete", result has verdict
- Get non-existent eval_id → status is "not_found"
- Queue with mock router that raises → status is "error" with message
- Callback fires on completion (mock HTTP server)
- Queue respects max_workers (submit max_workers+1, verify only max_workers run concurrently)


## Task 4: Core HTTP Server

**What:** FastAPI application with the two core evaluation endpoints.

**Files:**
- `arbiter/api/server.py`
- `arbiter/api/__init__.py`

**Endpoints:**

```
POST /api/v1/evaluate          → 202 Accepted (async)
POST /api/v1/evaluate/sync     → 200 OK with verdict (sync)
GET  /api/v1/evaluations/{id}  → evaluation result (poll)
GET  /api/v1/health            → {"status": "ok"}
```

**Implementation notes:**
- `/evaluate` submits to the EvaluationQueue, returns eval_id + poll_url
- `/evaluate/sync` calls the PipelineRouter directly with asyncio.wait_for(timeout)
- `/evaluate/sync` returns 408 with poll_url on timeout
- `/evaluations/{id}` returns queue result
- Server reads config from ArbiterConfig (host, port, sync_timeout)
- CORS middleware with configurable origins

**Tests:**
- POST /evaluate with valid body → 202 with eval_id
- POST /evaluate with missing agent → 422
- POST /evaluate/sync with valid body → 200 with verdict (mock router)
- POST /evaluate/sync timeout → 408 with poll_url
- GET /evaluations/{id} after async complete → 200 with verdict
- GET /evaluations/nonexistent → 404
- GET /health → 200


## Task 5: Override and Confirm Endpoints

**What:** HTTP endpoints for the human feedback loop.

**Endpoints:**

```
POST /api/v1/override          → resolve verdict as overridden
POST /api/v1/confirm           → resolve verdict as confirmed
POST /api/v1/resolve/batch     → batch resolve
```

**Implementation notes:**
- Override calls `verdict_store.resolve(verdict_id, "overridden", override=...)`
- Confirm calls `verdict_store.resolve(verdict_id, "confirmed", ...)`
- Batch iterates and collects results, returns partial success if some fail
- All use asyncio.to_thread() for sync verdict store calls (existing pattern)

**Tests:**
- Override existing pending verdict → 200, verdict resolved
- Override non-existent verdict → 404
- Override already-resolved verdict → 409 Conflict
- Confirm pending verdict → 200
- Batch with mix of valid and invalid → 200 with per-item status


## Task 6: Query Endpoints

**What:** Read-only endpoints for agent accuracy, verdict history, and governance status.

**Endpoints:**

```
GET /api/v1/agents/{name}/accuracy?window=30d
GET /api/v1/agents/{name}/verdicts?limit=20&status=overridden
GET /api/v1/governance/{name}
```

**Implementation notes:**
- Accuracy wraps `verdict_store.accuracy()`
- Verdicts wraps `verdict_store.query()`
- Governance wraps the existing governance module
- Window parameter parsed: "30d", "7d", "24h"

**Tests:**
- Accuracy with verdicts in store → returns metrics
- Accuracy with no verdicts → returns zeroes
- Verdicts with status filter → returns only matching
- Governance for known agent → returns status
- Governance for unknown agent → returns defaults


## Task 7: Batch Evaluation Endpoint

**What:** Evaluate multiple agent outputs in one request.

**Endpoint:**

```
POST /api/v1/evaluate/batch    → array of verdicts
```

**Implementation notes:**
- Accepts `{"evaluations": [...]}` with max `batch_max` items (config, default 20)
- Runs evaluations in parallel using asyncio.gather()
- Returns when all complete (or timeout)
- Each evaluation is independent (one failure doesn't fail the batch)

**Tests:**
- Batch of 3 valid evaluations → 200 with 3 results
- Batch exceeding batch_max → 422 with error
- Batch with 1 invalid item → 200 with 2 successes and 1 error
- Empty batch → 422


## Task 8: Server Configuration and CLI

**What:** Add server configuration to arbiter.yaml and a CLI command to start the server.

**Files:**
- Update `arbiter/config.py` with ServerConfig
- `arbiter/cli.py` or update existing CLI with `serve` command

**Configuration:**

```yaml
server:
  enabled: true
  host: "0.0.0.0"
  port: 8080
  sync_timeout: 30
  batch_max: 20
  cors_origins: ["*"]
```

**CLI:**

```bash
arbiter serve                    # start API server
arbiter serve --port 9090        # override port
arbiter serve --workers 10       # override queue workers
```

**Tests:**
- Config parses server section
- Config defaults when server section absent
- Server starts and responds to /health


## Task 9: MCP Server

**What:** Expose Arbiter evaluation and query as MCP tools.

**Files:**
- `arbiter/mcp/server.py`
- `arbiter/mcp/__init__.py`

**Tools:**
- `arbiter_evaluate` → calls PipelineRouter, returns verdict
- `arbiter_agent_accuracy` → wraps verdict_store.accuracy()
- `arbiter_governance_status` → wraps governance module
- `arbiter_query_verdicts` → wraps verdict_store.query()

**Implementation notes:**
- Use the MCP Python SDK (or implement stdio transport directly)
- Tool handlers reuse normalise_input() and build_response() from the HTTP API
- MCP server started via `nthlayer-measure mcp-server` CLI command

**Configuration:**

```yaml
mcp:
  enabled: true
  transport: stdio
```

**Tests:**
- Each tool returns valid JSON
- arbiter_evaluate with minimal input → verdict response
- arbiter_agent_accuracy for known agent → accuracy metrics
- arbiter_governance_status → governance response


## Task 10: Authentication

**What:** API key authentication for Tier 2+ deployments.

**Files:**
- `arbiter/api/auth.py`

**Implementation notes:**
- FastAPI dependency that checks Authorization header
- API keys stored in config with name, key, permissions
- Middleware checks permissions per endpoint
- When auth.enabled is false, all requests pass (Tier 1 default)

**Configuration:**

```yaml
server:
  auth:
    enabled: true
    type: api_key
    keys:
      - name: "integration"
        key: "arb_live_..."
        permissions: ["evaluate", "query"]
```

**Tests:**
- Auth disabled → all requests pass
- Valid key with correct permission → 200
- Valid key with wrong permission → 403
- Invalid key → 401
- Missing Authorization header → 401


## Task 11: Platform Integration Examples

**What:** Working example code for popular orchestrators.

**Files:**
- `examples/gastown/guardian_adapter.go`
- `examples/langchain/callback.py`
- `examples/crewai/monitored_crew.py`
- `examples/bash/evaluate.sh`
- `examples/README.md`

Each example should be self-contained, runnable, and documented. The README explains which example to use for which platform.

**Not code-tested in CI** (they depend on external systems), but should be syntactically valid and manually verified.


## Task 12: OpenAPI Documentation

**What:** FastAPI auto-generates OpenAPI docs. Verify they're complete and accurate.

**Files:**
- Verify `/docs` (Swagger UI) and `/openapi.json` endpoints work
- Add description strings to all endpoints
- Add example request/response bodies

**Tests:**
- GET /docs returns HTML
- GET /openapi.json returns valid OpenAPI 3.0 spec
- All endpoints appear in the spec with descriptions


## Completion Checklist

- [ ] All 12 tasks implemented and tested
- [ ] `nthlayer-measure serve` starts the API server
- [ ] `nthlayer-measure mcp-server` starts the MCP server
- [ ] POST /api/v1/evaluate works (fire and forget)
- [ ] POST /api/v1/evaluate/sync works (synchronous gate)
- [ ] POST /api/v1/override works (human feedback)
- [ ] GET /api/v1/agents/{name}/accuracy works (quality metrics)
- [ ] OpenAPI docs accessible at /docs
- [ ] All platform examples in examples/ directory
- [ ] README updated with API documentation and integration guide
- [ ] Existing tests still pass (no regressions)
