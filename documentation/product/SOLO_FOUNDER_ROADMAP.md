# NthLayer Technical Roadmap

**Date:** January 2025
**Status:** Active Development
**Current Position:** Phase 1 - Drift Detection

---

## Mission

**Reliability at build time, not incident time.**

NthLayer validates production readiness in CI/CD through the Generate → Validate → Gate workflow. This roadmap outlines the technical implementation path from core differentiation features through enterprise integrations.

---

## Roadmap Overview

```
Phase 1: Core Differentiation                           [5-7 days]
─────────────────────────────────────────────────────────────────
1. Drift detection                              ← YOU ARE HERE
   SPEC: DRIFT_DETECTION_SPEC.md ✓

Phase 2: Dependency Intelligence                        [8-10 days]
─────────────────────────────────────────────────────────────────
2. Identity resolution layer                    [2 days]
3. Dependency graph + Prometheus provider       [3 days]
4. validate-slo command                         [1 day]
5. Backstage provider                           [1 day]
6. blast-radius command                         [1 day]
7. Ownership resolution (PagerDuty, GitHub)     [2-3 days]
   SPEC: DEPENDENCY_DISCOVERY_SPEC.md ✓

Phase 3: Interface Layers                               [5-8 days]
─────────────────────────────────────────────────────────────────
8. MCP server                                   [2-3 days]
   SPEC: MCP_SERVER_SPEC.md ✓

9. Backstage plugin                             [3-5 days]
   SPEC: BACKSTAGE_PLUGIN_SPEC.md ✓

Phase 4: Expansion                                      [ongoing]
─────────────────────────────────────────────────────────────────
10. Additional providers (Consul, ZooKeeper, etc.)
11. Portfolio enhancements
12. Reliability contracts (future spec needed)
```

---

## Phase 1: Core Differentiation

**Timeline:** 5-7 days
**Goal:** Detect configuration drift between service.yaml and live infrastructure

### 1. Drift Detection ← CURRENT

**Specification:** [DRIFT_DETECTION_SPEC.md](../../DRIFT_DETECTION_SPEC.md)

Detect mismatches between declared service.yaml configuration and actual production state:

- **Alert rules drift**: Compare generated vs deployed Prometheus/Mimir rules
- **Dashboard drift**: Compare generated vs deployed Grafana dashboards
- **PagerDuty drift**: Compare declared vs actual service/escalation policy config
- **SLO drift**: Compare declared objectives vs configured alert thresholds

**Key Deliverables:**
- `nthlayer drift` CLI command
- Prometheus/Mimir rule comparison
- Grafana dashboard comparison
- PagerDuty configuration comparison
- CI/CD integration patterns

---

## Phase 2: Dependency Intelligence

**Timeline:** 8-10 days
**Goal:** Build a dependency graph for blast radius analysis and ownership resolution

**Specification:** [DEPENDENCY_DISCOVERY_SPEC.md](../../DEPENDENCY_DISCOVERY_SPEC.md)

### 2. Identity Resolution Layer [2 days]

Normalize service identities across different systems:
- Kubernetes labels → service name
- Prometheus job labels → service name
- PagerDuty service IDs → service name
- Backstage entity refs → service name

### 3. Dependency Graph + Prometheus Provider [3 days]

Discover runtime dependencies from Prometheus metrics:
- HTTP client/server relationships
- Database connections
- Message queue producers/consumers
- gRPC service mesh relationships

### 4. validate-slo Command [1 day]

Validate that declared SLOs have corresponding metrics available:
- Check metric existence in Prometheus
- Validate label cardinality
- Suggest missing exporters

### 5. Backstage Provider [1 day]

Import service catalog and ownership from Backstage:
- Fetch entities from Backstage API
- Map to NthLayer service model
- Sync team ownership

### 6. blast-radius Command [1 day]

Calculate deployment risk based on dependency graph:
- Identify downstream services
- Calculate criticality scores
- Generate risk assessment

### 7. Ownership Resolution [2-3 days]

Resolve service ownership from multiple sources:
- PagerDuty escalation policies
- GitHub CODEOWNERS
- Backstage ownership
- Kubernetes annotations

---

## Phase 3: Interface Layers

**Timeline:** 5-8 days
**Goal:** Expose NthLayer functionality through MCP and Backstage integrations

### 8. MCP Server [2-3 days]

**Specification:** [MCP_SERVER_SPEC.md](../../MCP_SERVER_SPEC.md)

Model Context Protocol server for AI assistant integration:
- Service catalog queries
- SLO status and error budgets
- Dependency graph traversal
- Drift detection results
- Alert and incident context

### 9. Backstage Plugin [3-5 days]

**Specification:** [BACKSTAGE_PLUGIN_SPEC.md](../../BACKSTAGE_PLUGIN_SPEC.md)

Backstage frontend plugin for service reliability:
- SLO dashboard widget
- Error budget visualization
- Drift detection status
- Dependency graph visualization
- Deployment gate status

---

## Phase 4: Expansion

**Timeline:** Ongoing
**Goal:** Extend provider coverage and enhance portfolio features

### 10. Additional Providers

- Consul service mesh discovery
- ZooKeeper configuration detection
- etcd configuration detection
- AWS service discovery
- GCP service discovery

### 11. Portfolio Enhancements

- Cross-service reliability scoring
- Team-level aggregations
- Executive dashboards
- Trend analysis and forecasting

### 12. Reliability Contracts

- Service-level agreements (SLAs)
- Contract validation
- Penalty calculations
- Future specification needed

---

## Completed Phases

### Phase 3.5: Technology Templates ✅

**Status:** Complete

Intent-based dashboard templates for common technologies:
- PostgreSQL, MySQL, Redis, MongoDB, Elasticsearch
- Kafka, RabbitMQ, NATS, Pulsar
- HTTP, gRPC, Worker patterns
- Nginx, HAProxy, Traefik
- Consul, etcd

### Previous Phases ✅

- OpenSLO parser and validation
- Prometheus/Mimir integration
- Error budget calculation
- PagerDuty integration (services, escalation policies, event orchestration)
- Grafana dashboard generation
- Alert rule generation
- Deployment gates
- CLI framework (91% test coverage)

---

## Specification Files

| Spec | Phase | Status |
|------|-------|--------|
| [DRIFT_DETECTION_SPEC.md](../../DRIFT_DETECTION_SPEC.md) | Phase 1 | Ready |
| [DEPENDENCY_DISCOVERY_SPEC.md](../../DEPENDENCY_DISCOVERY_SPEC.md) | Phase 2 | Ready |
| [MCP_SERVER_SPEC.md](../../MCP_SERVER_SPEC.md) | Phase 3 | Ready |
| [BACKSTAGE_PLUGIN_SPEC.md](../../BACKSTAGE_PLUGIN_SPEC.md) | Phase 3 | Ready |

---

**Document Version:** 2.0
**Last Updated:** January 2025
**Status:** Active - Phase 1 in progress
