# ARBITER-INTEGRATIONS.md — Universal Integration Specification

This document specifies how any agent orchestrator integrates with the Arbiter. The design principle: the minimum integration is one HTTP call. Everything beyond that is optional depth.

Read VERDICT.md for the verdict schema. Read the Arbiter README for the evaluation pipeline. This document covers the interface between the Arbiter and the outside world.


## Design Principle

**The adapter moves inside the Arbiter, not inside the orchestrator.**

Today: each orchestrator implements a custom adapter (Guardian plugin for GasTown, webhook adapter for generic systems). This means every new platform is custom code on their side.

After: the Arbiter exposes a universal HTTP API. Any system that can make an HTTP call can integrate. The Arbiter handles normalisation internally. The orchestrator sends agent output, receives a verdict.


## Three Integration Levels

| Level | Pattern | Coupling | Latency | Use Case |
|-------|---------|----------|---------|----------|
| 1 | Fire and forget | None | Async | Background quality tracking. Add one webhook and forget. |
| 2 | Synchronous gate | Low | In request path | Quality gate before merge/deploy/action. Arbiter approves or rejects. |
| 3 | Deep integration | Medium | Varies | Platform-level verdict production. Orchestrator is a first-class verdict citizen. |

Most teams start at Level 1, move to Level 2 when they want gating, and never need Level 3 unless they're building a platform.


## Level 1: Fire and Forget

### The Simplest Integration

The orchestrator sends agent output to the Arbiter via HTTP POST. The Arbiter evaluates asynchronously and stores the verdict. The orchestrator doesn't wait for the response.

**Request:**

```
POST /api/v1/evaluate
Content-Type: application/json

{
  "agent": "code-reviewer",
  "task_id": "PR-1234",
  "output": "Approved: the auth middleware correctly validates JWT tokens and rejects expired sessions.",
  "context": "Review PR #1234: Add JWT authentication to the API gateway."
}
```

**Response (immediate, before evaluation completes):**

```
202 Accepted
{
  "evaluation_id": "eval-2026-03-14-00421",
  "status": "queued",
  "poll_url": "/api/v1/evaluations/eval-2026-03-14-00421"
}
```

The 202 means "received, will evaluate." The orchestrator can poll the `poll_url` later to get the verdict, or ignore it entirely.

**That's it.** One POST. The orchestrator doesn't need to know about verdicts, dimensions, confidence scores, or any Arbiter internals. It sends output, the Arbiter handles the rest.

### Webhook Callback (Optional)

Instead of polling, the orchestrator can provide a callback URL:

```
POST /api/v1/evaluate
{
  "agent": "code-reviewer",
  "task_id": "PR-1234",
  "output": "...",
  "context": "...",
  "callback_url": "https://my-orchestrator.com/webhooks/arbiter"
}
```

When evaluation completes, the Arbiter POSTs the verdict to the callback:

```
POST https://my-orchestrator.com/webhooks/arbiter
{
  "evaluation_id": "eval-2026-03-14-00421",
  "verdict_id": "vrd-2026-03-14-00421",
  "action": "approve",
  "score": 0.84,
  "confidence": 0.78,
  "dimensions": {
    "correctness": 0.9,
    "completeness": 0.75,
    "safety": 0.88
  },
  "reasoning": "Auth check is sound. Missing rate limit on new endpoint."
}
```

### Minimum Orchestrator Code (Any Language)

```bash
# Bash (curl)
curl -X POST http://arbiter:8080/api/v1/evaluate \
  -H "Content-Type: application/json" \
  -d '{"agent":"code-reviewer","task_id":"PR-1234","output":"...","context":"..."}'
```

```python
# Python (requests)
requests.post("http://arbiter:8080/api/v1/evaluate", json={
    "agent": "code-reviewer",
    "task_id": "PR-1234",
    "output": agent_output,
    "context": task_description
})
```

```go
// Go
http.Post("http://arbiter:8080/api/v1/evaluate", "application/json",
    bytes.NewBuffer(payload))
```

```typescript
// TypeScript
fetch("http://arbiter:8080/api/v1/evaluate", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({agent, task_id, output, context})
});
```

No SDK. No library. No import. One HTTP call.


## Level 2: Synchronous Gate

### Quality Gate in the Critical Path

The orchestrator sends agent output and waits for the verdict before proceeding. The response includes the verdict so the orchestrator can decide what to do.

**Request:**

```
POST /api/v1/evaluate/sync
Content-Type: application/json

{
  "agent": "code-reviewer",
  "task_id": "PR-1234",
  "output": "Approved: the auth middleware correctly validates JWT tokens.",
  "context": "Review PR #1234: Add JWT authentication.",
  "service": "webapp",
  "environment": "production"
}
```

**Response (after evaluation completes):**

```
200 OK
{
  "verdict_id": "vrd-2026-03-14-00421",
  "action": "approve",
  "score": 0.84,
  "confidence": 0.78,
  "dimensions": {
    "correctness": 0.9,
    "completeness": 0.75,
    "safety": 0.88
  },
  "reasoning": "Auth check is sound. Missing rate limit on new endpoint.",
  "risk_tier": "standard",
  "governance": {
    "agent_status": "autonomous",
    "review_threshold": 0.7,
    "error_budget_remaining": 0.82
  }
}
```

The `governance` block tells the orchestrator the agent's current autonomy status. If `agent_status` is `"advisory_only"`, the orchestrator knows this agent's output should be reviewed by a human regardless of the score.

### Orchestrator Decision Logic

```python
result = requests.post("http://arbiter:8080/api/v1/evaluate/sync", json=payload).json()

if result["action"] == "approve" and result["governance"]["agent_status"] == "autonomous":
    # Agent is trusted and output is good, proceed
    merge(pr)
elif result["action"] == "approve" and result["governance"]["agent_status"] == "advisory_only":
    # Agent is in reduced autonomy mode, needs human review even though score is good
    request_human_review(pr, reason="Agent in advisory-only mode")
elif result["action"] == "reject":
    # Output didn't meet quality threshold
    request_revision(pr, feedback=result["reasoning"])
```

### Timeout Handling

The synchronous endpoint has a configurable timeout (default 30 seconds). If the evaluation doesn't complete in time:

```
408 Request Timeout
{
  "evaluation_id": "eval-2026-03-14-00421",
  "status": "timeout",
  "message": "Evaluation did not complete within 30s. Poll for result.",
  "poll_url": "/api/v1/evaluations/eval-2026-03-14-00421"
}
```

The orchestrator can fall back to polling, or apply a default policy (e.g., require human review when the Arbiter is slow).

### Batch Evaluation

For orchestrators that produce multiple agent outputs in a batch (e.g., GasTown's merge pipeline with multiple workers):

```
POST /api/v1/evaluate/batch
{
  "evaluations": [
    {"agent": "worker-1", "task_id": "task-001", "output": "...", "context": "..."},
    {"agent": "worker-2", "task_id": "task-002", "output": "...", "context": "..."},
    {"agent": "worker-3", "task_id": "task-003", "output": "...", "context": "..."}
  ]
}
```

Response:

```
200 OK
{
  "results": [
    {"agent": "worker-1", "task_id": "task-001", "verdict_id": "vrd-...", "action": "approve", "score": 0.87, ...},
    {"agent": "worker-2", "task_id": "task-002", "verdict_id": "vrd-...", "action": "approve", "score": 0.91, ...},
    {"agent": "worker-3", "task_id": "task-003", "verdict_id": "vrd-...", "action": "reject", "score": 0.42, ...}
  ]
}
```

Evaluations within a batch run in parallel. The response returns when all evaluations complete (or timeout).


## Level 3: Deep Integration

### For Platform Builders

Orchestrators that want to be first-class verdict producers import the verdict library directly and produce their own verdicts alongside (or instead of) calling the Arbiter's API.

**Use cases:**
- GasTown producing beads-linked verdicts (bead completion triggers verdict creation)
- A custom orchestrator that wants to emit verdicts for non-quality judgments (triage, routing, scheduling decisions)
- Platforms that want full control over verdict metadata and lineage

**Python SDK:**

```python
from verdicts import create, Producer, Subject, Judgment
from verdicts.stores.sqlite import SQLiteVerdictStore

store = SQLiteVerdictStore("verdicts.db")

# The orchestrator produces its own verdict
v = create(
    subject=Subject(
        type="agent_output",
        agent="worker-3",
        service="webapp",
        ref="task-003",
        summary="Code review of auth middleware changes"
    ),
    judgment=Judgment(
        action="approve",
        score=0.87,
        confidence=0.82,
        dimensions={"correctness": 0.9, "completeness": 0.8, "safety": 0.9},
        reasoning="Clean implementation with good test coverage"
    ),
    producer=Producer(
        system="gastown",
        instance="rig-webapp",
        model="claude-sonnet-4-20250514"
    )
)
store.put(v)

# Later, the Arbiter can evaluate the same output independently
# and produce its own verdict, creating a second opinion with lineage
```

**MCP Integration:**

For orchestrators that support MCP (Model Context Protocol), the Arbiter can expose its evaluation pipeline as MCP tools:

```json
{
  "mcpServers": {
    "arbiter": {
      "command": "arbiter",
      "args": ["mcp-server"],
      "tools": [
        "arbiter_evaluate",
        "arbiter_query_verdicts",
        "arbiter_agent_accuracy",
        "arbiter_governance_status"
      ]
    }
  }
}
```

MCP tools exposed:

| Tool | What It Does | Level Equivalent |
|------|-------------|-----------------|
| `arbiter_evaluate` | Send agent output for evaluation, receive verdict | Level 2 (sync) |
| `arbiter_query_verdicts` | Query verdicts by agent, service, time range | Verdict store query |
| `arbiter_agent_accuracy` | Get accuracy metrics for an agent | Dashboard data |
| `arbiter_governance_status` | Get current autonomy status for an agent | Governance check |

This is useful for AI agents that want to check their own quality or the quality of other agents as part of their reasoning. An investigation agent in Mayday could call `arbiter_agent_accuracy` to assess how reliable a code-reviewer agent has been before trusting its output.


## Human Override API

Overrides close the verdict feedback loop. Any integration level can submit overrides.

```
POST /api/v1/override
{
  "verdict_id": "vrd-2026-03-14-00421",
  "status": "overridden",
  "actor": "human:rob",
  "action": "reject",
  "reasoning": "Missed rate limiting on the new endpoint. Should have been flagged."
}
```

Response:

```
200 OK
{
  "verdict_id": "vrd-2026-03-14-00421",
  "outcome": {
    "status": "overridden",
    "override": {
      "by": "human:rob",
      "action": "reject",
      "reasoning": "Missed rate limiting on the new endpoint."
    }
  }
}
```

For orchestrators with their own review UI, the override API lets human decisions flow back into the Arbiter's calibration loop without the human needing to interact with the Arbiter directly.

**Confirm endpoint (for confirming correct verdicts):**

```
POST /api/v1/confirm
{
  "verdict_id": "vrd-2026-03-14-00421",
  "actor": "human:rob",
  "reasoning": "Reviewed the evaluation, judgment was correct."
}
```

**Bulk resolve (for batch post-review):**

```
POST /api/v1/resolve/batch
{
  "resolutions": [
    {"verdict_id": "vrd-001", "status": "confirmed", "actor": "human:rob"},
    {"verdict_id": "vrd-002", "status": "overridden", "actor": "human:rob", "action": "reject", "reasoning": "..."},
    {"verdict_id": "vrd-003", "status": "confirmed", "actor": "human:rob"}
  ]
}
```


## Query API

Orchestrators can query the Arbiter for agent quality data.

### Agent Accuracy

```
GET /api/v1/agents/{agent_name}/accuracy?window=30d
```

```
{
  "agent": "code-reviewer",
  "window": "30d",
  "total_verdicts": 247,
  "confirmed": 231,
  "overridden": 12,
  "pending": 4,
  "confirmation_rate": 0.95,
  "override_rate": 0.05,
  "mean_score": 0.84,
  "mean_confidence": 0.79,
  "calibration_gap": 0.05,
  "governance": {
    "status": "autonomous",
    "error_budget_remaining": 0.82,
    "review_threshold": 0.7
  }
}
```

### Agent Verdicts

```
GET /api/v1/agents/{agent_name}/verdicts?limit=20&status=overridden
```

Returns recent verdicts for the agent, filterable by status. Useful for review UIs.

### Governance Status

```
GET /api/v1/governance/{agent_name}
```

```
{
  "agent": "code-reviewer",
  "status": "autonomous",
  "review_threshold": 0.7,
  "error_budget_remaining": 0.82,
  "last_governance_action": null,
  "reversal_rate": 0.05,
  "reversal_rate_target": 0.05,
  "window": "30d"
}
```

Orchestrators can check governance status before submitting work to an agent. If an agent is in `advisory_only` mode, the orchestrator can route work to a different agent or require human review upfront.


## Platform-Specific Integration Guides

### GasTown

GasTown already has the Guardian (PR #2263) as a Deacon plugin. The migration path to the Arbiter API:

**Current (Guardian):** Tightly coupled Deacon plugin that scores per-worker output in the merge pipeline. Quality scores stored in wisps. Trend tracking via 6-hour cycles.

**Migrated (Arbiter API):** The Deacon plugin becomes a thin HTTP client. When a worker's output reaches the merge pipeline, the Deacon calls the Arbiter's Level 2 (synchronous) endpoint. The verdict response determines whether the output merges. All quality scoring, trend tracking, and governance moves to the Arbiter. The Guardian plugin shrinks from evaluation logic to a single HTTP call.

```go
// Guardian Deacon plugin after migration
func (g *Guardian) ReviewOutput(worker string, output string, taskID string) (bool, error) {
    resp, err := http.Post(arbiterURL+"/api/v1/evaluate/sync", "application/json",
        toJSON(map[string]string{
            "agent":   worker,
            "task_id": taskID,
            "output":  output,
            "context": g.getTaskContext(taskID),
        }))
    if err != nil {
        // Arbiter unavailable, fail open (merge without score)
        return true, nil
    }

    var result EvalResult
    json.NewDecoder(resp.Body).Decode(&result)

    // Merge if approved and agent is autonomous
    return result.Action == "approve" && result.Governance.AgentStatus == "autonomous", nil
}
```

The beads connection: when a bead completes, GasTown can fire an evaluation to the Arbiter with the bead ID as the `task_id`. The verdict links to the bead via `subject.ref`. This creates a natural bridge: beads track work, verdicts track judgment quality, linked by task ID.

### Devin

Devin produces task outputs (code changes, plans, debugging sessions). Integration:

```python
# After Devin completes a task
requests.post("http://arbiter:8080/api/v1/evaluate", json={
    "agent": "devin",
    "task_id": devin_session_id,
    "output": devin_task_output,
    "context": devin_task_description,
    "service": project_name,
    "callback_url": "https://devin-instance.com/webhooks/quality"
})
```

Level 1 (fire and forget) is sufficient. Devin gets quality tracking without modifying its execution pipeline.

### LangChain / LangGraph

For teams building custom agent pipelines with LangChain:

```python
from langchain.callbacks import BaseCallbackHandler

class ArbiterCallback(BaseCallbackHandler):
    def __init__(self, arbiter_url: str, agent_name: str):
        self.arbiter_url = arbiter_url
        self.agent_name = agent_name

    def on_chain_end(self, outputs, **kwargs):
        requests.post(f"{self.arbiter_url}/api/v1/evaluate", json={
            "agent": self.agent_name,
            "task_id": kwargs.get("run_id", str(uuid4())),
            "output": str(outputs),
            "context": str(kwargs.get("inputs", ""))
        })

# Usage
chain = my_chain.with_config(callbacks=[ArbiterCallback("http://arbiter:8080", "my-agent")])
```

A callback handler that fires evaluations on every chain completion. One class, no SDK dependency beyond requests.

### CrewAI

```python
from crewai import Agent, Task, Crew

class ArbiterMonitoredCrew(Crew):
    def __init__(self, *args, arbiter_url="http://arbiter:8080", **kwargs):
        super().__init__(*args, **kwargs)
        self.arbiter_url = arbiter_url

    def kickoff(self):
        result = super().kickoff()
        # Evaluate each agent's output
        for task in self.tasks:
            requests.post(f"{self.arbiter_url}/api/v1/evaluate", json={
                "agent": task.agent.role,
                "task_id": str(task.id),
                "output": task.output.raw if task.output else "",
                "context": task.description
            })
        return result
```

### Generic Webhook (Any System)

Any system that can make an HTTP POST can integrate:

```bash
# In your CI/CD pipeline, after an AI agent produces output
curl -s -X POST http://arbiter:8080/api/v1/evaluate \
  -H "Content-Type: application/json" \
  -d "{
    \"agent\": \"${AGENT_NAME}\",
    \"task_id\": \"${BUILD_ID}\",
    \"output\": $(cat agent_output.txt | jq -Rs .),
    \"context\": \"${TASK_DESCRIPTION}\"
  }"
```

One curl in your pipeline script. That's the minimum viable integration.


## API Server Implementation

### Server Architecture

The API server is a lightweight HTTP service that wraps the existing Arbiter evaluation pipeline. It doesn't replace the pipeline. It exposes it.

```
HTTP Request → API Server → Input Normalisation → PipelineRouter → Verdict Store
                                                        │
                                                        ▼
                                                   Model Evaluator
                                                        │
                                                        ▼
HTTP Response ← Response Builder ← Verdict ← Score Store + Verdict Store
```

### Server Configuration

```yaml
# In arbiter.yaml
server:
  enabled: true
  host: "0.0.0.0"
  port: 8080
  sync_timeout: 30            # seconds, for /evaluate/sync
  batch_max: 20               # max evaluations per batch request
  cors_origins: ["*"]         # or specific origins for production
  auth:
    enabled: false            # Tier 1: no auth
    # Tier 2+: API key or JWT
    # api_keys: ["key1", "key2"]
```

### Endpoints Summary

| Method | Path | Level | Description |
|--------|------|-------|-------------|
| POST | `/api/v1/evaluate` | 1 | Async evaluation, returns immediately |
| POST | `/api/v1/evaluate/sync` | 2 | Sync evaluation, waits for verdict |
| POST | `/api/v1/evaluate/batch` | 2 | Batch sync evaluation |
| GET | `/api/v1/evaluations/{id}` | 1 | Poll for evaluation result |
| POST | `/api/v1/override` | All | Submit human override |
| POST | `/api/v1/confirm` | All | Confirm a verdict |
| POST | `/api/v1/resolve/batch` | All | Batch resolve verdicts |
| GET | `/api/v1/agents/{name}/accuracy` | All | Agent accuracy metrics |
| GET | `/api/v1/agents/{name}/verdicts` | All | Agent verdict history |
| GET | `/api/v1/governance/{name}` | All | Agent governance status |
| GET | `/api/v1/health` | All | Health check |

### Input Normalisation

The API accepts a simplified input format and normalises it to the internal evaluation structure. This is where the "adapter moves inside the Arbiter" principle lives.

```python
def normalise_input(request_body: dict) -> EvaluationRequest:
    """
    Accepts the simplified external format and produces the internal format.
    This is the only place where external format meets internal format.
    """
    return EvaluationRequest(
        agent_name=request_body["agent"],
        task_id=request_body.get("task_id", str(uuid4())),
        output=request_body["output"],
        context=request_body.get("context"),
        service=request_body.get("service"),
        environment=request_body.get("environment", "production"),
        callback_url=request_body.get("callback_url"),
        metadata=request_body.get("metadata", {})
    )
```

Fields not provided get sensible defaults. `task_id` auto-generates if not provided. `environment` defaults to production. The external format is intentionally minimal, the internal format is richer.

### Async Evaluation Queue

For Level 1 (fire and forget) and for managing concurrent evaluations:

```python
class EvaluationQueue:
    """
    In-memory queue for async evaluations.
    Not a message broker. Just an asyncio queue within the server process.
    """
    def __init__(self, router: PipelineRouter, max_workers: int = 5):
        self.router = router
        self.queue = asyncio.Queue()
        self.results = {}  # eval_id -> result (for polling)
        self.workers = max_workers

    async def submit(self, request: EvaluationRequest) -> str:
        eval_id = generate_eval_id()
        self.results[eval_id] = {"status": "queued"}
        await self.queue.put((eval_id, request))
        return eval_id

    async def worker(self):
        while True:
            eval_id, request = await self.queue.get()
            try:
                self.results[eval_id] = {"status": "evaluating"}
                result = await self.router.evaluate(request)
                self.results[eval_id] = {
                    "status": "complete",
                    "verdict": result
                }
                # Fire callback if provided
                if request.callback_url:
                    await self._send_callback(request.callback_url, result)
            except Exception as e:
                self.results[eval_id] = {
                    "status": "error",
                    "error": str(e)
                }
            finally:
                self.queue.task_done()

    async def get_result(self, eval_id: str) -> dict:
        return self.results.get(eval_id, {"status": "not_found"})
```

### Response Builder

Transforms internal verdicts to the simplified external response format:

```python
def build_response(verdict: Verdict, governance: GovernanceStatus | None = None) -> dict:
    """
    Simplified external format. Orchestrators don't need to understand
    the full verdict schema. They need: action, score, confidence, reasoning.
    """
    response = {
        "verdict_id": verdict.id,
        "action": verdict.judgment.action,
        "score": verdict.judgment.score,
        "confidence": verdict.judgment.confidence,
        "dimensions": verdict.judgment.dimensions or {},
        "reasoning": verdict.judgment.reasoning,
        "risk_tier": verdict.metadata.get("risk_tier", "standard"),
    }
    if governance:
        response["governance"] = {
            "agent_status": governance.status,
            "review_threshold": governance.review_threshold,
            "error_budget_remaining": governance.error_budget_remaining,
        }
    return response
```


## MCP Server Implementation

The Arbiter can also run as an MCP server, exposing its functionality as tools that AI agents can call directly.

### MCP Server Configuration

```yaml
# In arbiter.yaml
mcp:
  enabled: true
  transport: stdio              # or sse for remote
```

### MCP Tools

```python
# Tool definitions for the MCP server

tools = [
    {
        "name": "arbiter_evaluate",
        "description": "Evaluate agent output quality. Returns a verdict with action, score, confidence, dimensions, and reasoning.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "Name of the agent being evaluated"},
                "task_id": {"type": "string", "description": "Identifier for the task"},
                "output": {"type": "string", "description": "The agent's output to evaluate"},
                "context": {"type": "string", "description": "What the agent was asked to do"}
            },
            "required": ["agent", "output"]
        }
    },
    {
        "name": "arbiter_agent_accuracy",
        "description": "Get accuracy metrics for an agent over a time window.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "Agent name"},
                "window": {"type": "string", "description": "Time window (e.g. 30d, 7d)", "default": "30d"}
            },
            "required": ["agent"]
        }
    },
    {
        "name": "arbiter_governance_status",
        "description": "Get current governance status for an agent (autonomy level, error budget, review threshold).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "Agent name"}
            },
            "required": ["agent"]
        }
    },
    {
        "name": "arbiter_query_verdicts",
        "description": "Query recent verdicts for an agent, optionally filtered by status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "Agent name"},
                "status": {"type": "string", "enum": ["pending", "confirmed", "overridden", "all"], "default": "all"},
                "limit": {"type": "integer", "default": 10}
            },
            "required": ["agent"]
        }
    }
]
```

### MCP Tool Handlers

```python
async def handle_tool_call(name: str, arguments: dict) -> str:
    if name == "arbiter_evaluate":
        request = normalise_input(arguments)
        result = await router.evaluate(request)
        return json.dumps(build_response(result))

    elif name == "arbiter_agent_accuracy":
        accuracy = verdict_store.accuracy(
            producer_system="arbiter",
            agent=arguments["agent"],
            time_range=parse_window(arguments.get("window", "30d"))
        )
        return json.dumps(accuracy)

    elif name == "arbiter_governance_status":
        status = governance.get_status(arguments["agent"])
        return json.dumps(status)

    elif name == "arbiter_query_verdicts":
        verdicts = verdict_store.query(
            producer_system="arbiter",
            agent=arguments["agent"],
            status=arguments.get("status"),
            limit=arguments.get("limit", 10)
        )
        return json.dumps([build_response(v) for v in verdicts])
```


## Authentication (Tier 2+)

For production deployments, the API should be authenticated. Tier 1 (single team, internal network) can run without auth. Tier 2+ should use API keys or JWT.

### API Key Authentication

```yaml
server:
  auth:
    enabled: true
    type: api_key
    keys:
      - name: "gastown-integration"
        key: "arb_live_..."
        permissions: ["evaluate", "query"]
      - name: "human-reviewer"
        key: "arb_live_..."
        permissions: ["evaluate", "query", "override", "confirm"]
      - name: "readonly-dashboard"
        key: "arb_live_..."
        permissions: ["query"]
```

Request:

```
POST /api/v1/evaluate
Authorization: Bearer arb_live_...
```

### Permission Model

| Permission | What It Allows |
|-----------|---------------|
| `evaluate` | Submit evaluations (POST /evaluate, /evaluate/sync, /evaluate/batch) |
| `query` | Read verdicts, accuracy, governance status (all GET endpoints) |
| `override` | Submit overrides and confirmations (POST /override, /confirm, /resolve/batch) |
| `admin` | All permissions + server configuration |


## Degradation Behaviour

| Failure | API Behaviour |
|---------|--------------|
| Model API unavailable | `/evaluate`: returns 202, queues for later. `/evaluate/sync`: returns 503 with retry-after header. Orchestrator falls back to default policy. |
| Verdict store unavailable | Evaluations proceed, verdicts buffered in memory. 503 on query endpoints. |
| Queue full | Returns 429 Too Many Requests with retry-after. |
| Evaluation timeout (sync) | Returns 408 with poll URL for async retrieval. |
| Arbiter server down | Orchestrator gets connection refused. Should have fallback: fail open (merge without score) or fail closed (require human review). This is the orchestrator's decision, not the Arbiter's. |

The most important design decision: **the Arbiter should never block an orchestrator's pipeline permanently.** If the Arbiter is down, the orchestrator proceeds with its default policy. Quality measurement is valuable but not worth stopping work entirely. This is consistent with the ecosystem's degradation philosophy: fail safe, fail with explicit warnings, never fail silently.


## Implementation Priority

1. **HTTP server with `/evaluate` and `/evaluate/sync`** — the two endpoints that cover Level 1 and Level 2. Use the existing PipelineRouter. Add input normalisation and response builder. This is the minimum that makes the Arbiter universally integrable.

2. **Evaluation queue** — async processing for Level 1. In-memory asyncio queue, configurable worker count. Poll endpoint for checking results.

3. **Override and confirm endpoints** — closes the feedback loop via HTTP. Maps directly to `verdict.resolve()`.

4. **Query endpoints** — agent accuracy, verdict history, governance status. Wraps existing verdict store queries.

5. **Callback webhooks** — fire verdict to orchestrator's callback URL after async evaluation.

6. **Batch endpoint** — parallel evaluation for multi-agent orchestrators.

7. **MCP server** — expose evaluation and query as MCP tools. Useful for AI agents that want to self-assess or assess other agents.

8. **Authentication** — API keys with permission model. Tier 2+ requirement.

9. **Platform-specific examples** — working integration code for GasTown, LangChain, CrewAI, Devin. These go in an `examples/` directory in the Arbiter repo.

Items 1-4 give you a universally integrable Arbiter. Items 5-6 improve the integration ergonomics. Items 7-9 extend to specialised use cases.


## Relationship to Other Specs

| Spec | Relationship |
|------|-------------|
| **VERDICT.md** | The API produces and resolves verdicts. The response format is a simplified view of the verdict schema. |
| **VERDICT-INTEGRATION.md** | The API is the mechanism through which external systems produce verdicts via the Arbiter. |
| **MAYDAY.md** | Mayday's agents could use the MCP tools to check agent accuracy during investigation. |
| **ECOSYSTEM-GAPS.md** | The API's degradation behaviour follows the staleness policy. Authentication follows the security model. |
| **SRE-EXPERIENCE.md** | The override/confirm endpoints are how the human feedback loop connects through orchestrator UIs. |
| **COSTOPTIMISATION.md** | The risk tier in the response tells orchestrators how the evaluation was classified (minimal/standard/deep/critical), which relates to evaluation cost. |
