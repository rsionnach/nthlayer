# NthLayer Topology Discovery Spec

## The Core Insight

Every existing topology discovery tool — Datadog service map, Istio Kiali, Causely's auto-discovery — produces a visualisation. A picture for humans to look at. NthLayer's discovery tool produces a machine-readable contract. The output isn't a graph you stare at; it's a YAML file you commit to git and enforce.

The command is `nthlayer init`, not `nthlayer discover`. This is the canonical way you start using NthLayer. Your system already exists. NthLayer observes it, produces a contract, and from that point forward the contract governs.

```bash
# The on-ramp: point at your OTel Collector, get a spec
nthlayer init --otlp-endpoint localhost:4317 --window 24h --output ./specs/

# The ongoing validation: compare spec to reality
nthlayer drift --specs-dir ./specs/ --otlp-endpoint localhost:4317 --format diff
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     COLLECTION TIERS (by deployment friction)             │
├─────────────────────┬──────────────────────┬────────────────────────────┤
│   TIER 1            │   TIER 2             │   TIER 3                   │
│   Zero-install      │   Lightweight        │   Deep                     │
├─────────────────────┼──────────────────────┼────────────────────────────┤
│ • OTel Collector    │ • Kubernetes API     │ • eBPF                     │
│   (OTLP passthrough │   (Services, Deploys,│   (via Hubble, Pixie,      │
│   — read existing   │   Ingress, NetPol,   │   or Beyla — consumed,     │
│   traces + metrics) │   mesh CRDs)         │   not built)               │
│                     │                      │                            │
│ • Prometheus        │ • Consul / ZooKeeper │                            │
│   (metric labels)   │   (service catalog,  │                            │
│                     │   intentions)        │                            │
│                     │                      │                            │
│                     │ • Backstage catalog  │                            │
│                     │   (relations, owner) │                            │
│                     │                      │                            │
│                     │ • Terraform state    │                            │
│                     │   (resource refs)    │                            │
├─────────────────────┴──────────────────────┴────────────────────────────┤
│ Gets you ~70% of    │ Adds declared        │ Ground truth: catches      │
│ the topology.       │ topology + context   │ everything OTel misses.    │
│ Requires zero new   │ (ownership, tier).   │ Optional and additive.     │
│ deployment.         │ Cross-reference with │ Requires kernel access.    │
│                     │ Tier 1 to find       │                            │
│                     │ shadow dependencies. │                            │
└─────────────────────┴──────────────────────┴────────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │     STRUCTURAL INFERENCE      │
              │     ENGINE                    │
              │                              │
              │ • Dependency classification  │
              │ • Communication patterns     │
              │ • Criticality analysis       │
              │ • Topology pattern detection │
              │ • Anomaly identification     │
              │ • Confidence-weighted merge  │
              │ • Identity resolution        │
              └──────────────┬───────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │     SPEC GENERATOR            │
              │                              │
              │ • Draft OpenSRM manifests    │
              │ • Auto-generated SLOs        │
              │ • Confidence annotations     │
              │ • Source tags                │
              │ • Anomaly report            │
              └──────────────────────────────┘
                             │
                   ┌─────────┼──────────┐
                   ▼         ▼          ▼
            nthlayer init  nthlayer   nthlayer
            (bootstrap)    drift      deps
                          (validate)  (inspect)
```

## The Adoption Story

This architecture works at every maturity level. That's the key to adoption:

**Day 1 — "I have OTel tracing."** Point nthlayer-init at your OTel Collector. It reads 24 hours of trace data, builds the dependency graph from parent-child span relationships, classifies dependencies, generates draft specs with auto-SLOs. You review, annotate (add tiers, ownership, judgment SLOs for AI services), and commit. Time to value: 30 minutes.

**Week 2 — "I want richer context."** Enable the Kubernetes provider. nthlayer-init now cross-references observed traffic against declared Kubernetes Services, Ingress rules, and NetworkPolicies. The delta between observed and declared surfaces shadow dependencies (i.e. services calling things they shouldn't be). Enable the Backstage provider. Now the draft specs include ownership and lifecycle metadata.

**Month 2 — "I want ground truth."** Enable the Hubble provider. nthlayer-init now includes eBPF-observed connections that OTel missed: uninstrumented services, sidecar communications, connections to external APIs. The drift report shows dependencies that exist in the kernel but not in the spec.

At each level, the user gets more value without rearchitecting. Each tier is additive. No tier is required.

---

## Collection Layer

### Tier 1: OTel Collector Passthrough (Zero-Install)

The primary data source. Requires zero new deployment from the user — most teams already have an OTel Collector running.

**How it works:** Connect to an existing OTel Collector's OTLP export endpoint (or a copy of the export stream) and passively read traces and metrics for a configurable observation window (default 24 hours, ideally spanning a business cycle).

**What it sees:**
- Parent-child span relationships → direct dependency edges
- Span attributes: `service.name`, `peer.service`, `db.system`, `messaging.system`, `http.url`, `rpc.service`
- Span kind (CLIENT, SERVER, PRODUCER, CONSUMER) → communication directionality
- Span timing → latency baselines (p50, p95, p99)
- Span status → error rates
- Metric labels referencing other services

**What it misses:**
- Uninstrumented services (no OTel SDK = invisible)
- Infrastructure-level connections (database connections not wrapped in spans)
- Sidecar and service mesh control plane traffic
- External API calls without instrumented HTTP clients

**Configuration:**

```yaml
# nthlayer-init config
collection:
  otlp:
    enabled: true
    endpoint: "localhost:4317"      # OTel Collector OTLP gRPC
    # OR
    endpoint: "http://localhost:4318/v1/traces"  # OTLP HTTP
    window: "24h"                   # Observation window
    tls:
      enabled: false
      cert_file: ""
      key_file: ""

  prometheus:
    enabled: true
    url: "http://localhost:9090"
    queries:                        # Additional metric-based discovery
      - name: "istio"
        query: 'sum by (source_workload, destination_workload) (rate(istio_requests_total[1h]) > 0)'
        source_label: "source_workload"
        target_label: "destination_workload"
      - name: "otel_service_graph"
        query: 'sum by (client, server) (rate(traces_service_graph_request_total[1h]) > 0)'
        source_label: "client"
        target_label: "server"
```

**CLI:**

```bash
# Minimal: just OTel
nthlayer init --otlp-endpoint localhost:4317 --output ./specs/

# With Prometheus for additional metric-based discovery
nthlayer init --otlp-endpoint localhost:4317 --prometheus-url http://localhost:9090 --output ./specs/

# Custom observation window
nthlayer init --otlp-endpoint localhost:4317 --window 48h --output ./specs/
```

### Tier 2: Kubernetes + Service Registry (Lightweight)

Adds declared topology and rich context. Cross-referencing with Tier 1 is where the real value emerges.

**Kubernetes API watcher:**
- Services and Endpoints → service names, namespaces, ports
- Deployments/StatefulSets → replica count, resource limits, labels
- Ingress / Gateway API → external-facing services
- NetworkPolicy → declared allowed/denied traffic (high confidence for what's permitted)
- Istio VirtualService / DestinationRule → mesh routing rules
- Linkerd ServiceProfile → retry budgets, timeouts

**Service registries:**
- Consul → service catalog, Connect intentions (allow/deny policy), health checks
- ZooKeeper → broker topology, consumer groups (Kafka dependency mapping)
- etcd / Eureka → service registration

**Platform catalogs:**
- Backstage → explicitly declared `dependsOn` and `consumesAPI` relations, ownership, lifecycle, tier
- Terraform state → infrastructure resource references (RDS instances, ElastiCache clusters, SQS queues)

**What Tier 2 adds that Tier 1 cannot:**
- Ownership and team assignment (from Backstage or Kubernetes labels)
- Tier/criticality classification (from Backstage lifecycle or custom labels)
- Declared policy intent (from NetworkPolicy and Consul intentions)
- Infrastructure dependencies (from Terraform state — "this service uses RDS instance X")
- The delta between declared and observed: services in Kubernetes that weren't seen in traces (possible dead services) and services in traces that aren't in Kubernetes (possible external dependencies)

**Configuration:**

```yaml
collection:
  kubernetes:
    enabled: true
    context: "production"           # kubectl context
    namespaces: ["production", "staging"]  # Or empty for all
    mesh: "istio"                   # "istio" | "linkerd" | "none"

  consul:
    enabled: true
    url: "http://consul.service.consul:8500"
    token_env: "CONSUL_TOKEN"
    datacenter: "dc1"

  backstage:
    enabled: false
    url: "http://backstage.internal:7007"

  terraform:
    enabled: false
    state_path: "./terraform.tfstate"  # Or remote backend config
```

### Tier 3: eBPF (Deep, Optional)

Ground truth. Catches everything Tier 1 and Tier 2 miss.

**NthLayer does NOT implement eBPF directly.** It consumes the output of existing eBPF tools via their APIs:

| Tool | API | What it sees | Best for |
|------|-----|-------------|----------|
| Cilium Hubble | gRPC Relay API | L3/L4 flows (IP, port, bytes) | K8s with Cilium CNI |
| Pixie (New Relic) | PxL query API | L7 protocol-aware flows (HTTP, gRPC, MySQL, Kafka) | Protocol-aware discovery |
| Grafana Beyla | Prometheus metrics | HTTP/gRPC traces + network flows | Grafana stack environments |

**Why not build eBPF directly:**
- Requires CAP_BPF / CAP_SYS_ADMIN (kernel privileges)
- Linux only, kernel version dependent
- Significant maintenance burden across kernel versions
- Hubble, Pixie, and Beyla already solve this well
- NthLayer's value is governance, not data collection

**What Tier 3 adds that Tier 1 and 2 cannot:**
- Uninstrumented services (no OTel SDK, no Kubernetes registration)
- Sidecar-to-sidecar communication
- Direct database connections that bypass service mesh
- Connections to external APIs without instrumented HTTP clients
- DNS resolution patterns (who is resolving what?)

**Noise filtering is critical.** Raw eBPF flow data includes enormous noise. The Hubble/Pixie consumer must filter:
- Exclude kube-system, kube-dns, monitoring namespace traffic
- Exclude traffic below a byte threshold (health checks, probes)
- Exclude well-known infrastructure ports (9090 Prometheus, 4317 OTel Collector, 10250 kubelet)
- Aggregate by service identity (Kubernetes labels), not ephemeral pod IPs
- Configurable exclusion list for known infrastructure services

**Configuration:**

```yaml
collection:
  ebpf:
    enabled: false                  # Opt-in only
    backend: "hubble"               # "hubble" | "pixie" | "beyla"
    hubble:
      address: "localhost:4245"     # Hubble Relay gRPC
      namespace_filter: "production"
    noise_filter:
      exclude_namespaces: ["kube-system", "monitoring", "istio-system"]
      exclude_ports: [9090, 4317, 4318, 10250, 10255]
      min_bytes: 1024               # Ignore flows below this
```

---

## Structural Inference Engine

This is where the intelligence lives. Not ML inference — structural pattern recognition on the dependency graph. Deliberately deterministic and explainable.

### Dependency Classification

For each observed connection between services, classify along several dimensions:

**Communication pattern:**
- Synchronous request-response (span kind CLIENT→SERVER, short duration, 1:1 fanout)
- Asynchronous messaging (span kind PRODUCER→CONSUMER, broker intermediary, variable delay)
- Event streaming (continuous CONSUMER spans, Kafka/Kinesis attributes)
- Periodic batch (connections that only appear at regular intervals, not continuous)
- Inferred from: span kind, timing patterns, presence of messaging semantic conventions (`messaging.system`, `messaging.destination`)

**Criticality:**
- Hard dependency: service A calls B on every request (fanout ratio ≈ 1.0)
- Soft dependency: service A calls B on some requests (fanout ratio < 1.0)
- Optional dependency: service A calls B rarely or only for non-critical paths
- Inferred from: call frequency relative to inbound request rate, error handling patterns (does A fail when B is unavailable or degrade gracefully?)

**Directionality:**
- Client → Server (span kind indicates who initiates)
- Bidirectional (both services initiate connections)
- Inferred from: span kind (CLIENT/SERVER), connection initiation in eBPF flows

**Data tier detection:**
- Database: `db.system` attribute, known ports (3306, 5432, 6379, 27017), connection pooling patterns
- Cache: `db.system` = "redis" or "memcached", short TTL patterns, high frequency reads
- Message broker: `messaging.system` attribute, known ports (9092 Kafka, 5672 RabbitMQ)
- External API: connections to non-cluster IPs, TLS on non-standard ports, known SaaS domains
- Inferred from: OTel semantic conventions, port patterns, connection behaviour

### Topology Pattern Detection

Beyond individual edges, the engine analyses the graph structure:

**Single points of failure:** Services that are on the critical path for a disproportionate number of upstream services. If auth-service is called by 18 of 21 services and has no redundancy, that's a finding.

**Circuit breaker behaviour:** Retry bursts followed by backoff in span timing. Indicates the calling service has resilience patterns but also that the dependency is known to be flaky.

**Load balancer fanout:** One service calling N instances of another with round-robin or weighted distribution. Inferred from trace data showing the same source calling multiple distinct target IPs for the same service.

**Saga / choreography patterns:** Multi-service workflows with correlated trace IDs but no single orchestrator. Multiple services producing and consuming events in sequence.

**Missing abstraction layers:** A database accessed directly by > N services (configurable, default 5). Suggests a missing data access service that would provide a single reliability boundary.

**Orphaned services:** Services registered in Kubernetes or Consul but not observed in any traces or connections. Possibly dead services consuming resources.

### Confidence-Weighted Merge

When multiple collection tiers report the same dependency (A → B), confidence increases:

```
merged_confidence = 1 - ∏(1 - confidence_i) for each source i
```

Base confidence per source type:

| Source | Base Confidence |
|--------|----------------|
| eBPF (kernel-level connection) | 0.95 |
| OTel trace (parent-child span) | 0.90 |
| Service mesh (Istio/Linkerd) | 0.85 |
| Consul Connect intention | 0.85 |
| Kubernetes NetworkPolicy | 0.80 |
| Prometheus metric labels | 0.75 |
| Distributed traces (explicit) | 0.75 |
| ZooKeeper topology | 0.70 |
| Backstage catalog relation | 0.70 |
| Terraform state reference | 0.65 |

Example: OTel traces (0.90) and Consul intentions (0.85) both report A → B. Merged confidence = `1 - (0.10 × 0.15) = 0.985`. Two independent sources agreeing is near-certain.

Context is merged additively: OTel provides latency baselines, Consul provides intention policy, Backstage provides ownership. The merged dependency carries all context from all sources.

### Identity Resolution

Different sources use different names for the same service:
- OTel traces: `fraud-detection-service`
- Kubernetes: `fraud-detect` (in namespace `production`)
- Consul: `fraud-detect`
- Hubble: `10.0.3.47:8080` (pod IP)
- Backstage: `fraud-detection`

The identity resolver normalises these to a canonical name:

1. Kubernetes pod IP → Kubernetes Service name (via Endpoints API)
2. Kubernetes Service name → normalised name (strip namespace, apply naming convention)
3. Cross-reference: find the name that appears in the most sources
4. If ambiguous, flag for human review with all observed aliases

```yaml
# Example identity resolution output
identity:
  canonical: fraud-detect
  aliases:
    - name: "fraud-detection-service"
      source: "otlp"
    - name: "fraud-detection"
      source: "backstage"
    - name: "10.0.3.47:8080"
      source: "hubble"
      resolved_via: "kubernetes_endpoints"
```

Configurable identity mappings for edge cases:

```yaml
# nthlayer-init config
identity:
  mappings:
    "api-gateway@consul": "gateway-api"
    "payment-svc@kubernetes": "payment-api"
  normalize:
    strip_suffixes: ["-service", "-svc", "-api"]  # Applied during matching, not to canonical name
```

### Confidence Thresholds

```yaml
inference:
  confidence:
    include_threshold: 0.50      # Below: ignored
    review_threshold: 0.70       # Below: flagged for human review in draft spec
    auto_declare_threshold: 0.90 # Above: included in draft spec without review flag
  criticality:
    hard_dep_fanout: 0.8         # Fanout ratio above this = hard dependency
    soft_dep_fanout: 0.3         # Between soft and hard = soft dependency
  anomaly:
    max_direct_db_consumers: 5   # Flag databases with more direct consumers than this
    orphan_threshold: "7d"       # Service not observed in this window = possibly dead
```

---

## Spec Generator

The output of `nthlayer init` is a set of draft OpenSRM manifests, one per discovered service, ready to commit to git.

### Draft Spec Format

```yaml
# specs/fraud-detect.yaml
# Generated by nthlayer init on 2026-03-26T14:00:00Z
# Observation window: 24h (2026-03-25T14:00:00Z to 2026-03-26T14:00:00Z)
# Sources: otlp, kubernetes, consul
# Overall confidence: 0.94

apiVersion: opensrm/v1
kind: ServiceReliabilityManifest
metadata:
  name: fraud-detect
  labels:
    tier: critical                        # REVIEW: inferred from call frequency (called by 8 services)
    team: payments-ml                     # From: backstage
    domain: ml
  annotations:
    nthlayer.io/discovered-at: "2026-03-26T14:00:00Z"
    nthlayer.io/observation-window: "24h"
    nthlayer.io/confidence: "0.94"
    nthlayer.io/sources: "otlp,kubernetes,consul"

spec:
  type: ai-gate                           # REVIEW: inferred from gen_ai.* span attributes

  dependencies:
    - service: payment-api
      type: downstream                    # fraud-detect is called BY payment-api
      pattern: synchronous                # Inferred: CLIENT→SERVER spans, p99 < 200ms
      criticality: hard                   # Inferred: fanout ratio 0.97 (called on nearly every payment request)
      confidence: 0.98                    # Sources: otlp (0.90) + consul (0.85) = merged 0.985
      # Sources: otlp (parent-child spans), consul (connect intention)

    - service: feature-store
      type: upstream                      # fraud-detect CALLS feature-store
      pattern: synchronous
      criticality: hard                   # Inferred: fanout ratio 0.92
      confidence: 0.90
      # Sources: otlp (parent-child spans)

    - service: model-registry
      type: upstream
      pattern: periodic                   # Inferred: connections every ~60s, not per-request
      criticality: soft                   # Inferred: fanout ratio 0.02
      confidence: 0.75
      # Sources: otlp

    - service: analytics-api
      type: upstream
      pattern: asynchronous               # Inferred: PRODUCER spans, Kafka messaging.system
      criticality: soft
      confidence: 0.70
      # REVIEW: low confidence, only observed in otlp traces intermittently

  slos:
    availability:
      target: 0.999                       # Auto-generated: observed 99.97% over 24h, conservative target
      # auto-generated from 24h observation window — review and adjust

    latency:
      p99_target: 180ms                   # Auto-generated: observed p99 148ms + 20% buffer
      # auto-generated from 24h observation window — review and adjust

    # judgment:                           # NOT auto-generated — requires human declaration
    #   reversal_rate:
    #     target: 0.015
    #     window: 7d
    #     observation_period: 24h
    #   NOTE: This service has gen_ai.* span attributes indicating it's an AI decision
    #   service. Consider adding judgment SLOs. See: https://nthlayer.io/docs/judgment-slos

  baselines:
    # Observed metrics during the discovery window (informational, not enforced)
    latency:
      p50: 42ms
      p95: 98ms
      p99: 148ms
    throughput: 42.8 req/s
    error_rate: 0.002

_discovery_metadata:
  generated_at: "2026-03-26T14:00:00Z"
  window_start: "2026-03-25T14:00:00Z"
  window_end: "2026-03-26T14:00:00Z"
  sources_used:
    otlp: { spans_analysed: 847293, services_found: 21 }
    kubernetes: { services: 24, network_policies: 8 }
    consul: { services: 19, intentions: 34 }
  anomalies:
    - type: "undocumented_dependency"
      description: "fraud-detect calls analytics-api but analytics-api has no inbound trace data for this connection. Possible missing instrumentation on analytics-api."
      severity: "info"
    - type: "possible_ai_service"
      description: "Service has gen_ai.client.operation.duration spans and gen_ai.decision events. Consider declaring as type: ai-gate with judgment SLOs."
      severity: "recommendation"
```

### What the Generator Does NOT Auto-Generate

Some things require human judgment and are deliberately left as comments or placeholders:

- **Judgment SLOs:** The generator can detect that a service emits `gen_ai.*` span attributes and flag it as a probable AI decision service. But the reversal rate target, observation period, and confidence thresholds require domain knowledge. The generator leaves a commented-out judgment SLO block with a prompt to configure it.
- **Tier classification:** The generator infers criticality from call frequency (a service called by many others is probably critical). But the definitive tier assignment is a business decision. The generator sets the inferred value with a `# REVIEW:` comment.
- **Ownership:** If Backstage or Kubernetes labels provide team information, it's included. Otherwise, left empty for human assignment.
- **Business outcomes:** The `outcomes` block (financial impact of decisions) cannot be discovered. It's inherently a human declaration.

### Draft Review Annotations

Every auto-generated value that requires human review is annotated:

```yaml
tier: critical    # REVIEW: inferred from call frequency (called by 8 services)
target: 0.999     # auto-generated from 24h observation window — review and adjust
confidence: 0.70  # REVIEW: low confidence, only observed in otlp traces intermittently
```

The intent: a human can grep for `REVIEW:` and `auto-generated` to find every value that needs attention. Everything else can be committed as-is.

---

## CLI Commands

### `nthlayer init`

The on-ramp. Run once to bootstrap your spec portfolio.

```bash
# Minimal: OTel only
nthlayer init \
  --otlp-endpoint localhost:4317 \
  --output ./specs/

# With Prometheus and Kubernetes
nthlayer init \
  --otlp-endpoint localhost:4317 \
  --prometheus-url http://localhost:9090 \
  --kubernetes-context production \
  --output ./specs/

# Full stack
nthlayer init \
  --config ./nthlayer-discovery.yaml \
  --output ./specs/

# Dry run: show what would be generated without writing files
nthlayer init \
  --otlp-endpoint localhost:4317 \
  --dry-run
```

Output: one `.yaml` file per discovered service in the output directory, plus a `_discovery_report.yaml` with the full anomaly report and summary statistics.

### `nthlayer drift`

Ongoing validation. Run on a schedule or as a CI step.

```bash
# Compare committed specs to current runtime
nthlayer drift \
  --specs-dir ./specs/ \
  --otlp-endpoint localhost:4317 \
  --format diff

# Output as a PR-ready spec update
nthlayer drift \
  --specs-dir ./specs/ \
  --otlp-endpoint localhost:4317 \
  --output ./specs-updated/ \
  --format patch
```

Drift report categories:

```
NEW DEPENDENCIES (observed but not in spec):
  + fraud-detect → cache-service (confidence: 0.82, sources: otlp, hubble)
    Action: Add to spec or add to exclusion list

STALE DEPENDENCIES (in spec but not observed for > 7d):
  ~ fraud-detect → legacy-scoring-api (last seen: 2026-03-12)
    Action: Remove from spec or investigate

BASELINE DRIFT (observed metrics shifted beyond SLO):
  ! payment-api latency p99: 148ms → 312ms (target: 200ms)
    Action: Investigate or adjust SLO target

NEW SERVICES (observed but no spec exists):
  ? cache-service (observed in otlp traces, no spec)
    Action: Run nthlayer init for this service

TOPOLOGY CHANGES (structural shifts):
  ⚠ fraud-detect now calls 3 services that were not in the dependency graph
    after deploy at 2026-03-25T16:30:00Z
```

### `nthlayer deps`

Inspect the discovered dependency graph interactively.

```bash
# Show dependencies for a specific service
nthlayer deps fraud-detect \
  --otlp-endpoint localhost:4317

# Show full graph
nthlayer deps --all \
  --otlp-endpoint localhost:4317

# Compare discovered to declared
nthlayer deps fraud-detect \
  --otlp-endpoint localhost:4317 \
  --specs-dir ./specs/ \
  --show-diff
```

Output:

```
Dependencies for fraud-detect (confidence threshold: 0.50)

Upstream (fraud-detect calls):
┌──────────────────┬────────────┬──────────┬──────────────┬─────────────────────┐
│ Service          │ Pattern    │ Critical │ Confidence   │ Sources             │
├──────────────────┼────────────┼──────────┼──────────────┼─────────────────────┤
│ feature-store    │ sync       │ hard     │ ████████░░   │ otlp, kubernetes    │
│ model-registry   │ periodic   │ soft     │ ██████░░░░   │ otlp                │
│ analytics-api    │ async      │ soft     │ █████░░░░░   │ otlp (low)          │
└──────────────────┴────────────┴──────────┴──────────────┴─────────────────────┘

Downstream (services calling fraud-detect):
┌──────────────────┬────────────┬──────────┬──────────────┬─────────────────────┐
│ Service          │ Pattern    │ Critical │ Confidence   │ Sources             │
├──────────────────┼────────────┼──────────┼──────────────┼─────────────────────┤
│ payment-api      │ sync       │ hard     │ ██████████   │ otlp, consul, k8s   │
│ checkout-svc     │ sync       │ hard     │ █████████░   │ otlp, consul        │
│ admin-api        │ sync       │ soft     │ ██████░░░░   │ otlp                │
└──────────────────┴────────────┴──────────┴──────────────┴─────────────────────┘

Anomalies:
  ⚠ analytics-api: no inbound traces for connection from fraud-detect (missing instrumentation?)
  ℹ Detected as AI decision service (gen_ai.* spans). Consider adding judgment SLOs.
```

---

## Implementation

### Provider Base

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator

@dataclass
class DiscoveredDependency:
    """A single discovered dependency edge."""
    source_service: str          # Raw name from provider
    target_service: str          # Raw name from provider
    dep_type: str                # "service" | "datastore" | "queue" | "external" | "unknown"
    confidence: float            # Provider's base confidence for this edge
    provider: str                # Provider name
    metadata: dict = field(default_factory=dict)
    # metadata examples:
    #   otlp: { latency_p99: 148, error_rate: 0.002, span_count: 4523 }
    #   consul: { action: "allow", precedence: 9 }
    #   hubble: { bytes_total: 14523000, protocol: "TCP" }

@dataclass
class DiscoveredService:
    """A discovered service with attributes for identity resolution."""
    name: str                    # Raw name from provider
    provider: str
    attributes: dict = field(default_factory=dict)
    # attributes examples:
    #   kubernetes: { namespace: "production", labels: {...}, replicas: 3 }
    #   backstage: { owner: "payments-ml", lifecycle: "production", tier: "critical" }
    #   otlp: { span_count: 84723, has_genai_spans: true }

class BaseDepProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def discover(self, service: str) -> list[DiscoveredDependency]: ...

    @abstractmethod
    async def list_services(self) -> list[DiscoveredService]: ...

    @abstractmethod
    async def health_check(self) -> bool: ...

    async def discover_all(self) -> AsyncIterator[DiscoveredDependency]:
        """Default: iterate all services. Override for bulk APIs."""
        services = await self.list_services()
        for svc in services:
            deps = await self.discover(svc.name)
            for dep in deps:
                yield dep
```

### Build Priority

**v0 (build first — the on-ramp):**
1. OTel Collector provider (Tier 1) — reads OTLP trace data, builds dependency graph from parent-child spans
2. Structural inference engine — dependency classification (sync/async, hard/soft), baseline extraction, AI service detection
3. Spec generator — draft OpenSRM manifests with auto-SLOs, confidence annotations, anomaly report
4. Identity resolver — basic normalisation (strip suffixes, lowercase, cross-reference service names across sources)
5. `nthlayer init` CLI command
6. Prometheus provider (Tier 1) — metric label-based discovery as a complement to OTel traces

**v1 (adds declared topology):**
7. Kubernetes provider (Tier 2) — Services, Deployments, NetworkPolicy, mesh CRDs
8. Consul provider (Tier 2) — service catalog, Connect intentions
9. Confidence-weighted merge across all enabled providers
10. `nthlayer drift` CLI command
11. `nthlayer deps` CLI command

**v2 (adds ground truth):**
12. Hubble consumer (Tier 3) — eBPF flow data via Hubble Relay gRPC API
13. Pixie consumer (Tier 3) — alternative eBPF backend
14. Enhanced noise filtering for eBPF data
15. Topology pattern detection (single points of failure, missing abstraction layers, circuit breaker patterns)

**v3 (adds platform context):**
16. Backstage provider — ownership, lifecycle, tier from software catalog
17. Terraform provider — infrastructure dependencies from state
18. ZooKeeper provider — Kafka/messaging topology

---

## Drift Detection Design

`nthlayer drift` is not continuous monitoring. It's a point-in-time comparison: run discovery with the same providers, compare the result to the committed specs, produce a structured diff.

**When to run:**
- On a schedule (daily or weekly cron)
- As a CI step triggered by deployments
- Manually when investigating an incident or planning a change
- Before and after infrastructure migrations

**Output formats:**
- `--format diff` — human-readable summary of changes (for terminal or Slack)
- `--format patch` — updated spec files that can be committed (for PR automation)
- `--format json` — machine-readable for integration with other tools

**What drift compares:**
- Dependencies: new edges, removed edges, changed patterns or criticality
- Baselines: latency, error rate, throughput shifts beyond thresholds
- Services: new services without specs, specs without observed services
- Topology: structural changes (new single points of failure, changed fanout patterns)

**What drift does NOT do:**
- It does not auto-update specs. The output is a proposal. A human reviews and commits.
- It does not alert. It produces a report. If you want alerts on drift, pipe the JSON output to your existing alerting system.
- It does not run continuously. It runs on invocation. NthLayer's continuous monitoring is measure's job, not drift's.

---

## Audit First (for Claude Code)

Before implementing any provider or the inference engine:

1. **Read the existing OpenSRM schema.** What fields exist for dependencies? What does the `dependencies` block look like in current specs? Does it support the `pattern`, `criticality`, `confidence` fields proposed here, or do these need to be added to the schema?

2. **Read the existing nthlayer-generate code.** How does generate currently read dependencies from specs? The discovery output must produce specs that generate can consume without changes.

3. **Read the existing nthlayer-correlate code.** How does correlate walk the dependency graph? It needs to work identically whether the spec was hand-written or generated by init.

4. **Check for existing discovery-related code.** The January discussion produced provider base classes and Consul/Kubernetes provider sketches. Check if any of this was implemented.

5. **Check OTel Collector client libraries available in Python.** The OTLP receiver will need to read trace data. Options: `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, or raw gRPC/HTTP against the OTLP protocol.

6. **Document findings before implementing.**

---

## Notes for Claude Code

- **Start with v0.** OTel provider + inference engine + spec generator + `nthlayer init`. Everything else is additive.
- **The spec generator output must be valid OpenSRM.** Run `nthlayer generate` against every draft spec to verify it produces valid Prometheus rules. If generate fails on a draft spec, the spec is wrong.
- **Identity resolution is hard.** Start simple (lowercase, strip common suffixes, match across sources by string similarity). Don't build an ML-based entity resolver. Provide manual mappings for edge cases.
- **The `_discovery_metadata` block is not part of the OpenSRM schema.** It's an annotation block that nthlayer init writes and nthlayer drift reads. It should be ignored by generate and other components. Use a convention that makes this clear (leading underscore, or a separate metadata file alongside the spec).
- **Auto-generated SLOs should be conservative.** p99 + 20% buffer is a starting point. The human will tighten. It's better to generate an SLO that's too loose than one that fires false alerts on day one.
- **The anomaly report is a first-class output.** Don't bury it in log messages. Write it to a structured file that the user reads alongside the draft specs. The anomalies are where the discovery tool earns its keep: "14 services access this database directly" is a reliability insight that falls out of the topology for free.
- **Test with real OTel trace data.** The Jaeger project has sample trace datasets. Use them for integration tests rather than mocking the OTel protocol from scratch.
