# nthlayer-common — v1-draft

**Status:** Draft for implementation
**Date:** 2026-04-19
**Scope:** NthLayer reference implementation; not part of OpenSRM specification

---

## 1. Purpose

nthlayer-common is the shared library used by every other NthLayer component. It provides:

1. **LLM wrapper.** Model-agnostic interface over Anthropic, OpenAI, and other provider SDKs, with retry, timeout, cost accounting, and structured output via Instructor.
2. **Store access primitives.** SQLite connection management, WAL configuration, transactional helpers.
3. **Identity and principal resolution.** Consistent handling of human and agent principals across components.
4. **Provider SDK wrappers.** Prometheus, Grafana, PagerDuty, Mimir — the external observability systems components interact with.
5. **Telemetry emission.** OTel tracing, metrics, log emission with nthlayer-specific attribute conventions.
6. **Error handling patterns.** Structured errors, retry decorators, circuit breakers.
7. **Data models.** Pydantic models for verdicts, assessments, cases, and other shared types.

The library exists because every component needs these primitives and inlining them per-component produces drift. It deliberately does not include: component-specific business logic, anything that belongs in a single component's spec.

## 2. Design Principles

**Thin wrappers, not frameworks.** Each wrapper is an adapter over a native library. It does not hide the underlying library — it composes with it. Components needing native-library features can reach through.

**Zero Framework Cognition.** The library does not own reasoning. It provides transport — HTTP clients, structured parsers, connection pools. It never owns prompts, decision trees, or agent orchestration. Those live in components.

**No LiteLLM.** The LLM wrapper is httpx-based with per-provider adapters. LiteLLM is explicitly not a dependency, for two reasons: (1) its OpenAI-schema lowest-common-denominator loses Anthropic-native features like tool-use blocks, thinking, and prompt-caching semantics; (2) its 2026 supply-chain incident (versions 1.82.7 and 1.82.8 shipped with malicious `.pth` files) showed the dependency surface is a real risk. nthlayer-common depends directly on native SDKs.

**Python 3.11+.** All components target 3.11+. No backport layers, no compatibility shims. Async throughout.

## 3. LLM Wrapper

### 3.1 Interface

```python
class LLM:
    async def complete(
        self,
        prompt: str,
        *,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        response_model: Optional[type[BaseModel]] = None,
        tools: Optional[list[Tool]] = None,
        timeout: float = 60.0,
    ) -> LLMResponse:
        ...

    async def stream(self, ...) -> AsyncIterator[LLMChunk]:
        ...
```

When `response_model` is provided, the response is validated through Instructor and returned as an instance of the Pydantic model. The raw response is always available on the LLMResponse object for cases where both are needed.

### 3.2 Provider abstraction

Under the hood, each model string maps to a provider adapter:

```python
PROVIDER_MAP = {
    "claude-opus-4-7": AnthropicAdapter,
    "claude-sonnet-4-6": AnthropicAdapter,
    "claude-haiku-4-5": AnthropicAdapter,
    "gpt-4o": OpenAIAdapter,
    "gpt-4o-mini": OpenAIAdapter,
    # ...
}
```

Adapters are thin wrappers that:

- Translate the common interface to the provider's native API
- Handle provider-specific features when present (prompt caching, extended thinking, tool-use blocks for Anthropic)
- Return responses in a common shape

### 3.3 Instructor integration

Structured outputs use Instructor with the appropriate provider mode:

```python
import instructor
from anthropic import AsyncAnthropic

client = instructor.from_anthropic(AsyncAnthropic())

response = await client.messages.create(
    model="claude-opus-4-7",
    max_tokens=1024,
    messages=[{"role": "user", "content": prompt}],
    response_model=MyPydanticModel,
    max_retries=3,
)
```

Instructor handles JSON-mode validation, retry on schema violation, and partial streaming. This replaces hand-rolled "try to parse JSON, fall back, reask" patterns throughout the codebase.

### 3.4 Cost accounting

Every LLM call emits a `llm_call` OTel event with:

- `gen_ai.request.model`
- `gen_ai.usage.input_tokens`
- `gen_ai.usage.output_tokens`
- `gen_ai.usage.cached_tokens` (Anthropic)
- `gen_ai.usage.reasoning_tokens` (reasoning models)
- `nthlayer.llm.caller` (which component/agent made the call)
- `nthlayer.llm.caller_verdict_cid` (the verdict being produced, if applicable)

This makes cost attribution tractable: which components and agents use how much of what model. Not cheap to ignore.

### 3.5 Circuit breakers and rate limits

Per-provider circuit breakers prevent runaway retries when a provider is degraded. Per-component rate limits prevent one component from starving others. Both configurable at deployment time.

## 4. Store Access

### 4.1 Connection management

A singleton connection pool per component, configured with the serve-mode WAL pragmas:

```python
class StorePool:
    def __init__(self, path: str):
        self.path = path
        self.pool = [self._new_conn() for _ in range(10)]

    def _new_conn(self):
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn
```

### 4.2 Transactional helpers

```python
@contextmanager
def write_transaction(store):
    conn = store.acquire()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        store.release(conn)
```

Writes use `BEGIN IMMEDIATE` to acquire the write lock atomically, preventing the "multiple writers thinking they won the lock" race.

### 4.3 Verdict operations

```python
class VerdictStore:
    async def write_verdict(self, verdict: Verdict) -> CID:
        """Compute CID, write verdict, update lineage index."""

    async def get_verdict(self, cid: CID) -> Verdict:
        ...

    async def query_verdicts(
        self,
        *,
        service: Optional[str] = None,
        types: Optional[list[VerdictType]] = None,
        created_between: Optional[tuple[datetime, datetime]] = None,
        limit: int = 100,
    ) -> list[Verdict]:
        ...

    async def query_descendants(self, cid: CID, max_hops: int = None) -> list[Verdict]:
        ...

    async def query_ancestors(self, cid: CID, max_hops: int = None) -> list[Verdict]:
        ...
```

The lineage queries use the pre-computed lineage table (see nthlayer-learn §5.2).

### 4.4 CID computation

Delegated to libipld (MarshalX/python-libipld). See nthlayer-learn §4.2 for the canonical encoding details.

## 5. Provider Integrations

### 5.1 Prometheus

```python
from nthlayer_common.providers.prometheus import PrometheusClient

client = PrometheusClient(url="http://prometheus:9090")

result = await client.query("rate(http_requests_total[5m])", time=datetime.now())
```

Uses `prometheus-api-client` underneath with async wrapping.

### 5.2 Grafana

```python
from nthlayer_common.providers.grafana import GrafanaClient

client = GrafanaClient(url="http://grafana:3000", api_key=...)

dashboard = await client.get_dashboard(uid="payments-overview")
await client.create_alert_rule(rule_def)
```

### 5.3 PagerDuty

```python
from nthlayer_common.providers.pagerduty import PagerDutyClient

client = PagerDutyClient(api_key=...)

await client.trigger_incident(
    service_id="P123",
    summary="Payment service error budget exhausted",
    severity="critical",
)
```

### 5.4 Mimir / Thanos

Same interface as Prometheus, different underlying endpoint. The LLM wrapper pattern applies — a thin adapter over the provider's native API.

### 5.5 Provider extension

Organisations with additional observability providers (Datadog, New Relic, etc.) implement adapters conforming to the same interface pattern. nthlayer-common ships the common ones; bespoke providers are the deployer's concern.

## 6. Identity and Principal

### 6.1 Principal model

```python
@dataclass
class Principal:
    kind: Literal["human", "agent", "system"]
    id: str
    attributes: dict[str, Any]

    @classmethod
    def from_context(cls, ctx: AuthContext) -> "Principal":
        """Construct a principal from the component's auth context."""
```

### 6.2 Identity sources

- **Human principals from OIDC/SAML.** nthlayer-common consumes the platform's ID token and maps claims to the principal model.
- **Agent principals from SPIFFE.** Where py-spiffe is configured, SVIDs are validated and principal attributes populated from the SVID's SAN.
- **Agent principals from static certs.** Fallback for deployments without SPIRE. Certificates are provisioned at deployment time.

### 6.3 Attribute resolution

Principal attributes may come from multiple sources (identity provider, team roster, on-call schedule, autonomy state). nthlayer-common provides a layered resolver that composes attributes from all configured sources with documented precedence.

## 7. Telemetry Emission

### 7.1 OTel integration

nthlayer-common initialises the OTel SDK with the deployment's configured exporter (OTLP by default). Components import the configured tracer and meter:

```python
from nthlayer_common.telemetry import get_tracer, get_meter

tracer = get_tracer(__name__)
meter = get_meter(__name__)

with tracer.start_as_current_span("process_verdict"):
    # ...
```

### 7.2 Nthlayer-specific attributes

Common attributes set on traces and emitted with events:

- `nthlayer.component` — which component (observe, measure, etc.)
- `nthlayer.instance_id` — deployment-unique instance identifier
- `nthlayer.deployment_id` — deployment-unique deployment identifier
- `nthlayer.verdict.cid` — when processing a specific verdict
- `nthlayer.service` — when operating on a specific service

### 7.3 Self-metrics

Components emit Prometheus-compatible self-metrics via `prometheus-client`:

- `nthlayer_cycle_duration_seconds{component}`
- `nthlayer_verdicts_written_total{component,type}`
- `nthlayer_heartbeats_emitted_total{component}`
- `nthlayer_llm_calls_total{component,model,outcome}`
- `nthlayer_errors_total{component,error_type}`

These scrape from a `/metrics` endpoint each component exposes.

## 8. Data Models

Pydantic models for the common types:

```python
class Verdict(BaseModel):
    cid: str
    type: VerdictType
    created_at: datetime
    created_by: PrincipalRef
    judgment: Judgment
    outcome: Optional[Outcome] = None
    parent_cids: list[str] = Field(default_factory=list)
    lineage_reasoning: Optional[str] = None
    pipeline_latency_ms: int
    chain_depth: int

class Assessment(BaseModel):
    cid: str
    kind: AssessmentKind
    service: Optional[str]
    created_at: datetime
    content: dict

class Case(BaseModel):
    cid: str
    kind: CaseKind
    priority: Priority
    state: CaseState
    # ...
```

Components import from `nthlayer_common.models`. Any extension to these models happens through pydantic's subclassing — components may use extended models internally, but round-trip through the store uses the common form.

## 9. Error Handling

### 9.1 Structured errors

```python
class NthlayerError(Exception):
    """Base class for NthLayer-specific errors."""

class TransientError(NthlayerError):
    """Error that may succeed on retry."""

class PermanentError(NthlayerError):
    """Error that will not succeed on retry."""

class PolicyError(PermanentError):
    """Policy evaluation produced a deny."""

class DegradedError(TransientError):
    """A dependency is degraded but not unavailable."""
```

### 9.2 Retry decorators

```python
from nthlayer_common.errors import retry

@retry(
    exceptions=TransientError,
    max_attempts=3,
    backoff=ExponentialBackoff(initial=1.0, factor=2.0, max=30.0),
)
async def call_llm(...):
    ...
```

Retries emit telemetry on each attempt; the retry count is visible in traces.

### 9.3 Circuit breakers

Per-dependency circuit breakers prevent cascading failures. When a dependency is in "open" state, calls fail fast with `DegradedError` rather than timing out repeatedly.

## 10. Configuration

### 10.1 Shape

A single `nthlayer.yaml` file per deployment with component-specific subsections:

```yaml
deployment:
  id: "production-eu"
  signing_key_id: "ed25519-2026q2"

store:
  path: "/var/lib/nthlayer/store.db"
  connection_pool_size: 10

llm:
  providers:
    anthropic:
      api_key_env: ANTHROPIC_API_KEY
    openai:
      api_key_env: OPENAI_API_KEY
  default_model: "claude-opus-4-7"
  summary_model: "claude-haiku-4-5"

prometheus:
  url: "http://prometheus:9090"

components:
  observe:
    cycle_interval_seconds: 60
  measure:
    cycle_interval_seconds: 60
    self_calibration_interval: "24h"
  # ...
```

### 10.2 Loading

```python
from nthlayer_common.config import Config

config = Config.load()  # default path, or env-var-specified
```

Components read their own section; shared config is available globally.

## 11. Testing Primitives

nthlayer-common ships testing helpers:

- `pytest` fixtures for a temporary in-memory store
- Mock LLM provider that returns pre-programmed responses
- Fake Prometheus endpoint for integration tests
- Verdict builders for test data

Each component's test suite uses these. Real-dependency integration tests (against actual Prometheus, actual LLMs) use environment-gated pytest marks.

## 12. Dependencies

Declared in `pyproject.toml`:

```toml
[project]
dependencies = [
    "httpx>=0.27",
    "anthropic>=0.40",
    "openai>=1.50",
    "instructor>=1.5",
    "pydantic>=2.9",
    "prometheus-client>=0.21",
    "prometheus-api-client>=0.5",
    "sqlite-utils>=3.38",
    "libipld>=3.3",
    "sigstore>=3.6",
    "pynacl>=1.5",
    "networkx>=3.4",
    "scipy>=1.14",
    "numpy>=2.0",
    "opentelemetry-api>=1.28",
    "opentelemetry-sdk>=1.28",
    "opentelemetry-exporter-otlp>=1.28",
]

[project.optional-dependencies]
spiffe = ["spiffe>=0.2.3", "spiffe-tls>=0.3.1"]
vault = ["hvac>=2.0"]
kubernetes = ["kubernetes>=31.0"]
biscuit = ["biscuit-python>=0.4"]
regorus = ["regorus"]  # pinned via git or local wheel path until PyPI distribution
```

Versions pinned to minor where the upstream is stable; pinned to exact where supply-chain risk warrants (see §2 on LiteLLM).

## 13. Non-Dependencies

Explicitly not in the dependency tree:

- **LiteLLM.** See §2. Provider adapters are direct.
- **LangChain.** Owns reasoning; incompatible with Zero Framework Cognition.
- **LangGraph.** Transport-only story is defensible, but for nthlayer's use case asyncio plus state machines cover it. Reconsider if durable multi-day agent sessions become a requirement.
- **CrewAI.** Owns agent roles and delegation.
- **AutoGen.** In maintenance mode per Microsoft's redirect to Agent Framework.
- **smolagents.** Agent generates code as the reasoning loop.
- **DSPy.** Reserved for if/when prompt optimisation becomes a product feature.

## 14. Versioning

Semantic versioning. Breaking changes in the common library propagate to all components. Because all components in a deployment typically share a version, breakage is detectable at deploy time.

Major version bumps in `nthlayer-common` are breaking; component pins are expected to be tight.

## 15. Failure Modes

**LLM provider outage.** Circuit breaker opens; `DegradedError` returned. Callers decide whether to fail fast or degrade.

**Store unavailable.** Components can't read or write. Degraded state is emitted; heartbeat fails. Operators see the outage.

**OTel exporter unavailable.** Telemetry is buffered per the SDK's configured behaviour. If buffers fill, telemetry is dropped (not critical-path).

**Configuration malformed.** Components fail to start. Startup errors are clear about what's wrong.

## 16. Implementation Notes

### 16.1 Build and distribution

The library is distributed via PyPI as `nthlayer-common`. Components depend on it as a versioned package.

### 16.2 Compatibility with native SDKs

The library wraps native SDKs but does not prevent reaching through. Components needing features the wrapper doesn't expose can access the underlying client:

```python
llm = LLM()
anthropic_client = llm.providers["anthropic"].native_client
# use Anthropic SDK directly
```

### 16.3 Async throughout

All I/O is async. Components using sync code (rarely) use `asyncio.to_thread()` or a thread pool explicitly.

## 17. Future Work

**Connector to Backstage.** A client for Backstage's API to fetch entity metadata. Would simplify Principal attribute resolution and OpenSRM manifest loading.

**Distributed trace propagation.** Ensure traceparent flows through verdict chains so the full authorisation flow can be reconstructed end-to-end from telemetry.

**Schema validation for verdicts.** JSON Schema validation at the store boundary would catch malformed verdicts before they pollute the lineage graph. Currently done at the Pydantic-model level; stronger validation would be nice.

## 18. References

- httpx: https://www.python-httpx.org/
- Instructor: https://github.com/567-labs/instructor
- Anthropic SDK: https://github.com/anthropics/anthropic-sdk-python
- OpenAI SDK: https://github.com/openai/openai-python
- libipld: https://github.com/MarshalX/python-libipld
- sigstore-python: https://github.com/sigstore/sigstore-python
- py-spiffe: https://github.com/HewlettPackard/py-spiffe
- biscuit-python: https://github.com/eclipse-biscuit/biscuit-python
- OpenTelemetry Python: https://github.com/open-telemetry/opentelemetry-python

## 19. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1-draft | 2026-04-19 | Initial spec |
