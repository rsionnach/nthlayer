---
hide:
  - navigation
---

# Live Demo

<div class="hero-section" markdown>

## 20 Hours of SRE Work in 5 Minutes

Define your service once. NthLayer generates SLOs, alerts, dashboards, recording rules, and runbooks—with technology-specific best practices built in.

<div class="grid cards" markdown>

-   :material-lightning-bolt:{ .lg .middle } **99.6% Time Savings**

-   :material-brain:{ .lg .middle } **Tech-Aware (PostgreSQL, Redis, Kafka)**

-   :material-target:{ .lg .middle } **One Command for Everything**

-   :material-chart-line:{ .lg .middle } **Real-Time Error Budget Tracking**

</div>

</div>

---

## Live Grafana Dashboards

See auto-generated dashboards for 6 production services. Each dashboard includes SLO metrics, service health, and technology-specific panels.

<div class="grid cards" markdown>

-   :fontawesome-solid-credit-card:{ .lg .middle } **payment-api**

    ---

    PostgreSQL + Redis

    [:octicons-arrow-right-24: View Dashboard](https://nthlayer.grafana.net/dashboard/snapshot/GnDR7SU4YPkpMPFgFMUb94Z87NAI7USS){ target="_blank" }

-   :fontawesome-solid-cart-shopping:{ .lg .middle } **checkout-service**

    ---

    MySQL + Redis

    [:octicons-arrow-right-24: View Dashboard](https://nthlayer.grafana.net/dashboard/snapshot/TOnoDbGP8O3cJCGNI44IprF10oHr8uo8){ target="_blank" }

-   :fontawesome-solid-bell:{ .lg .middle } **notification-worker**

    ---

    Worker + Redis

    [:octicons-arrow-right-24: View Dashboard](https://nthlayer.grafana.net/dashboard/snapshot/tbDDNW5D3Yf4GkDVipSGWW3wBRKSwxJu){ target="_blank" }

-   :fontawesome-solid-chart-bar:{ .lg .middle } **analytics-stream**

    ---

    Stream + MongoDB

    [:octicons-arrow-right-24: View Dashboard](https://nthlayer.grafana.net/dashboard/snapshot/3TfGKKWaUlr4JiDTYcaopopnKUPcMuBP){ target="_blank" }

-   :fontawesome-solid-lock:{ .lg .middle } **identity-service**

    ---

    PostgreSQL + Redis

    [:octicons-arrow-right-24: View Dashboard](https://nthlayer.grafana.net/dashboard/snapshot/kzgo1UwIysfXVrSbj5hKKtP5i12saAgy){ target="_blank" }

-   :fontawesome-solid-magnifying-glass:{ .lg .middle } **search-api**

    ---

    Elasticsearch + Redis

    [:octicons-arrow-right-24: View Dashboard](https://nthlayer.grafana.net/dashboard/snapshot/5K9lhCTnAfNtXE3KhcNC4gt0J5ysj7Tj){ target="_blank" }

</div>

!!! info "Dashboard Structure"
    Each dashboard is organized into: **SLO Metrics** → **Service Health** → **Dependencies**

---

## Generated Alerts

**118 production-ready Prometheus alerts** across all services, sourced from [awesome-prometheus-alerts](https://github.com/samber/awesome-prometheus-alerts).

<div class="grid cards" markdown>

-   **payment-api** · 15 PostgreSQL alerts

    PostgresqlDown, PostgresqlRestarted, SlowQueries...

    [:octicons-arrow-right-24: View on GitHub](https://github.com/rsionnach/nthlayer/blob/develop/generated/payment-api/alerts.yaml){ target="_blank" }

-   **checkout-service** · 26 MySQL + Redis alerts

    MysqlDown, RedisMemoryHigh, ReplicationLag...

    [:octicons-arrow-right-24: View on GitHub](https://github.com/rsionnach/nthlayer/blob/develop/generated/checkout-service/alerts.yaml){ target="_blank" }

-   **notification-worker** · 12 Redis alerts

    RedisDown, RedisMemoryHigh, TooManyConnections...

    [:octicons-arrow-right-24: View on GitHub](https://github.com/rsionnach/nthlayer/blob/develop/generated/notification-worker/alerts.yaml){ target="_blank" }

-   **analytics-stream** · 19 MongoDB + Redis alerts

    MongodbDown, CursorsTimeouts, ReplicasetLag...

    [:octicons-arrow-right-24: View on GitHub](https://github.com/rsionnach/nthlayer/blob/develop/generated/analytics-stream/alerts.yaml){ target="_blank" }

-   **identity-service** · 27 PostgreSQL + Redis alerts

    PostgresqlDown, DeadLocks, RedisRejected...

    [:octicons-arrow-right-24: View on GitHub](https://github.com/rsionnach/nthlayer/blob/develop/generated/identity-service/alerts.yaml){ target="_blank" }

-   **search-api** · 19 Elasticsearch alerts

    ClusterRed, JvmHeapHigh, DiskSpaceLow...

    [:octicons-arrow-right-24: View on GitHub](https://github.com/rsionnach/nthlayer/blob/develop/generated/search-api/alerts.yaml){ target="_blank" }

</div>

---

## SLO Portfolio

Track org-wide reliability with tier-based health scoring:

```
================================================================================
  NthLayer SLO Portfolio
================================================================================

Organization Health: 78% (14/18 services meeting SLOs)

By Tier:
  Critical:  ████████░░  83% (5/6 services)
  Standard:  ███████░░░  75% (6/8 services)
  Low:       ███████░░░  75% (3/4 services)

--------------------------------------------------------------------------------
Services Needing Attention:
--------------------------------------------------------------------------------

  payment-api (Tier 1)
    availability: 156% budget burned - EXHAUSTED
    Remaining: -12.5 hours

  search-api (Tier 2)
    latency-p99: 95% budget burned - WARNING
    Remaining: 1.2 hours

--------------------------------------------------------------------------------
Total: 18 services, 16 with SLOs, 45 SLOs
```

!!! tip "Cross-Vendor Aggregation"
    **Why this matters:** PagerDuty can't give you this view—they want you locked into their ecosystem.
    NthLayer aggregates SLOs across any backend (Prometheus, Datadog, etc.) in a single, vendor-neutral portfolio.

---

## PagerDuty Integration

Complete incident response setup with tier-based escalation policies.

<div class="grid" markdown>

<div class="grid cards" markdown>

-   :fontawesome-solid-users:{ .lg .middle } **Team Management**

    ---

    Auto-creates teams with manager roles assigned to API key owner

-   :fontawesome-solid-calendar:{ .lg .middle } **On-Call Schedules**

    ---

    Primary, secondary, and manager schedules with weekly rotation

-   :fontawesome-solid-clock:{ .lg .middle } **Tier-Based Timing**

    ---

    Critical: 5→15→30min | High: 15→30→60min | Low: 60min only

-   :fontawesome-solid-link:{ .lg .middle } **Service Linking**

    ---

    Services linked to escalation policies with urgency settings

</div>

</div>

### Support Models

| Model | Description |
|-------|-------------|
| `self` | Team handles all alerts 24/7 |
| `shared` | Team (day) + SRE (off-hours) |
| `sre` | SRE handles all alerts |
| `business_hours` | Team (9-5) + low-priority queue |

---

## What Gets Generated

From a single `service.yaml`, NthLayer generates:

| Output | Description | Example |
|--------|-------------|---------|
| :material-view-dashboard: **Dashboard** | 22 panels: health, SLOs, latency, errors, dependencies | [View JSON](https://github.com/rsionnach/nthlayer/blob/develop/generated/payment-api/dashboard-sdk.json){ target="_blank" } |
| :material-target: **SLOs** | 3 SLOs with 30-day error budgets and burn rate calculations | [View YAML](https://github.com/rsionnach/nthlayer/blob/develop/generated/payment-api/slos.yaml){ target="_blank" } |
| :material-alert: **Alerts** | 15 PostgreSQL alerts with service labels and severity routing | [View YAML](https://github.com/rsionnach/nthlayer/blob/develop/generated/payment-api/alerts.yaml){ target="_blank" } |
| :material-lightning-bolt: **Recording Rules** | 21 pre-aggregated metrics for 10x faster dashboard queries | [View YAML](https://github.com/rsionnach/nthlayer/blob/develop/generated/payment-api/recording-rules.yaml){ target="_blank" } |

---

## Try It Yourself

```bash
# Install NthLayer
pipx install nthlayer

# Interactive setup (configures Prometheus, Grafana, PagerDuty)
nthlayer setup

# Generate configs for your service
nthlayer apply payment-api.yaml

# View org-wide SLO health
nthlayer portfolio
```

<div class="grid cards" markdown>

-   :material-download:{ .lg .middle } **Get Started**

    ---

    Install NthLayer and generate your first reliability stack

    [:octicons-arrow-right-24: Installation Guide](getting-started/installation.md)

-   :material-file-document:{ .lg .middle } **Full Documentation**

    ---

    Comprehensive guides for all features

    [:octicons-arrow-right-24: Documentation](index.md)

</div>

<style>
.hero-section {
    text-align: center;
    padding: 2rem 0;
    margin-bottom: 2rem;
}
.hero-section h2 {
    font-size: 2.5rem;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
</style>
