---
theme: the-unnamed
highlighter: shiki
title: NthLayer Technical Deep Dive
themeConfig:
  logoHeader: ''
  eventLogo: ''
  eventUrl: ''
  twitter: ''
  twitterUrl: ''
---

# NthLayer

## Technical Deep Dive

**Reliability Requirements as Code**

<div class="mt-4 text-sm">
For Platform Engineers & SREs
</div>

<div class="mt-4 text-blue-400">
Architecture • CLI • Enforcement • Integration
</div>

---
layout: default
---

# Agenda

<div class="grid grid-cols-2 gap-8 mt-8">

<div>

### Part 1: Core Concepts
- Reliability requirements as code
- The service.yaml contract
- Tier-based defaults

### Part 2: Enforcement Pipeline
- Generate → Lint → Verify → Gate
- Exit codes and CI/CD integration
- Error budget calculations

</div>

<div>

### Part 3: CLI Deep Dive
- All commands explained
- Real examples
- Best practices

### Part 4: Integration
- Prometheus, Grafana, PagerDuty
- GitOps workflow
- Extensibility

</div>

</div>

---
layout: section
---

# Part 1: Core Concepts

The Reliability Contract

---
layout: default
---

# What is "Reliability Requirements as Code"?

<div class="grid grid-cols-2 gap-8 mt-6">

<div>

### The Concept

Just like Infrastructure as Code (Terraform) defines **what infrastructure should exist**...

**Reliability as Code** defines **what reliability requirements a service must meet**.

```yaml
# Infrastructure as Code
resource "aws_instance" "web" {
  instance_type = "t3.micro"
  ami           = "ami-12345"
}

# Reliability Requirements as Code
name: payment-api
tier: critical
type: api
```

</div>

<div>

### The Contract

Your service.yaml is not configuration.<br/>
It is a **contract** that must be satisfied.

| Contract Element | Meaning |
|------------------|---------|
| `tier: critical` | 99.95% availability required |
| `type: api` | HTTP metrics must exist |
| `dependencies: [postgresql]` | DB metrics must exist |

**If the contract is not met, deployment is blocked.**

</div>

</div>

---
layout: default
---

# The Service Specification

```yaml
# services/payment-api.yaml
name: payment-api           # Service identifier
tier: critical              # Business criticality: critical | standard | low
type: api                   # Service type: api | worker | stream
team: payments              # Owning team

# SLO overrides (optional - tier provides defaults)
slos:
  availability: 99.99       # Override tier default
  latency_p99_ms: 150       # Override tier default

# Dependencies (for metric verification)
dependencies:
  - postgresql
  - redis

# Environment-specific config
environments:
  production:
    prometheus:
      url: https://prometheus.prod.example.com
```

---
layout: default
---

# Tier-Based Defaults

### Tier = Business Criticality

<div class="grid grid-cols-3 gap-4 mt-6">

<div class="p-4 border-2 border-red-500 rounded">

### Critical (Tier 1)

**Business Impact:** Revenue, safety, core flow

**Defaults:**
- Availability: 99.95%
- Latency P99: 200ms
- Error budget: 21.6 min/month
- Gate blocks at: <10% remaining
- PagerDuty: High urgency, 5min escalation

**Examples:** Checkout, Auth, Payments

</div>

<div class="p-4 border-2 border-yellow-500 rounded">

### Standard (Tier 2)

**Business Impact:** Degraded experience

**Defaults:**
- Availability: 99.5%
- Latency P99: 500ms
- Error budget: 3.6 hrs/month
- Gate blocks at: <5% remaining
- PagerDuty: Low urgency, 30min escalation

**Examples:** Search, Recommendations

</div>

<div class="p-4 border-2 border-green-500 rounded">

### Low (Tier 3)

**Business Impact:** Minimal

**Defaults:**
- Availability: 99.0%
- Latency P99: 2000ms
- Error budget: 7.2 hrs/month
- Gate: Advisory only
- PagerDuty: Low urgency, 60min escalation

**Examples:** Reports, Batch jobs

</div>

</div>

---
layout: section
---

# Part 2: Enforcement Pipeline

Generate → Lint → Verify → Gate

---
layout: default
---

# The Enforcement Pipeline

```
┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
│  Define   │ → │ Generate  │ → │   Lint    │ → │  Verify   │ → │   Gate    │
│           │    │           │    │           │    │           │    │           │
│ service   │    │ artifacts │    │ PromQL    │    │ metrics   │    │ budget    │
│ .yaml     │    │           │    │ valid?    │    │ exist?    │    │ ok?       │
└───────────┘    └───────────┘    └───────────┘    └───────────┘    └───────────┘
                      ↓                ↓                ↓                ↓
                 dashboard.json   exit 0/1        exit 0/1         exit 0/1/2
                 alerts.yaml
                 slos.yaml
```

<div class="grid grid-cols-4 gap-4 mt-6 text-sm">

<div>

**Generate**
`nthlayer apply`

Creates all artifacts from spec

</div>

<div>

**Lint**
`--lint` flag

Validates PromQL syntax with pint

</div>

<div>

**Verify**
`nthlayer verify`

Confirms metrics exist in Prometheus

</div>

<div>

**Gate**
`nthlayer check-deploy`

Checks error budget status

</div>

</div>

---
layout: default
---

# Exit Codes for CI/CD

### Machine-readable enforcement results

<div class="grid grid-cols-2 gap-8 mt-6">

<div>

### Exit Code Semantics

| Code | Meaning | Pipeline Action |
|------|---------|-----------------|
| `0` | Success | Continue |
| `1` | Warning / Failure | Fail (lint/verify) |
| `2` | Deploy Blocked | Hard stop (gate) |

### Why Three Codes?

```bash
nthlayer check-deploy service.yaml
EXIT=$?

if [ $EXIT -eq 2 ]; then
  echo "BLOCKED: Error budget exhausted"
  exit 1  # Fail pipeline
elif [ $EXIT -eq 1 ]; then
  echo "WARNING: Budget low"
  # Continue but alert
fi
```

</div>

<div>

### Pipeline Example

```yaml
# GitHub Actions
- name: Lint PromQL
  run: nthlayer apply service.yaml --lint
  # Fails on exit 1

- name: Verify Metrics
  run: nthlayer verify service.yaml
  # Fails on exit 1

- name: Check Gate
  run: |
    nthlayer check-deploy service.yaml
    if [ $? -eq 2 ]; then
      echo "::error::Deploy blocked"
      exit 1
    fi
```

</div>

</div>

---
layout: default
---

# Contract Verification: `nthlayer verify`

### "Do the metrics I declared actually exist?"

<div class="grid grid-cols-2 gap-8 mt-6">

<div>

### What It Checks

For each service type, verify required metrics exist:

**API Services:**
- `http_requests_total{service="X"}`
- `http_request_duration_seconds_bucket{service="X"}`

**Worker Services:**
- `job_processed_total{service="X"}`
- `job_duration_seconds_bucket{service="X"}`

**Dependencies:**
- PostgreSQL: `pg_stat_*` metrics
- Redis: `redis_*` metrics

</div>

<div>

### Verification Query

```python
def verify_metric(metric_name, service):
    query = f'count({metric_name}{{service="{service}"}}[5m]) > 0'
    result = prometheus.query(query)
    return result.value > 0
```

### Output

```
✓ http_requests_total: found
✓ http_request_duration_seconds_bucket: found
✗ redis_commands_total: NOT FOUND

Verification: FAILED (1 missing metric)
Exit code: 1
```

</div>

</div>

---
layout: default
---

# Deployment Gate: `nthlayer check-deploy`

### "Is it safe to deploy right now?"

<div class="grid grid-cols-2 gap-8 mt-6">

<div>

### Error Budget Calculation

```python
def calculate_error_budget(slo_target, window_days):
    # Total allowed downtime
    window_minutes = window_days * 24 * 60
    budget_minutes = (1 - slo_target) * window_minutes

    # Current consumption from Prometheus
    error_rate = query_current_error_rate()
    consumed = error_rate * window_minutes

    remaining_pct = (budget_minutes - consumed) / budget_minutes
    return remaining_pct

# Example: 99.95% SLO, 30-day window
# Budget: 21.6 minutes
# If consumed 19 min → 12% remaining
```

</div>

<div>

### Gate Logic

```python
def check_deploy(service, tier):
    remaining = calculate_error_budget(...)

    thresholds = {
        'critical': {'block': 0.10, 'warn': 0.20},
        'standard': {'block': 0.05, 'warn': 0.10},
        'low':      {'block': 0.00, 'warn': 0.20},
    }

    t = thresholds[tier]

    if remaining < t['block']:
        return EXIT_BLOCKED  # 2
    elif remaining < t['warn']:
        return EXIT_WARNING  # 1
    else:
        return EXIT_OK       # 0
```

</div>

</div>

---
layout: section
---

# Part 3: CLI Deep Dive

Commands & Usage

---
layout: default
---

# CLI Command Overview

<div class="grid grid-cols-2 gap-6 mt-6">

<div>

### Generate Commands

```bash
# Generate all artifacts
nthlayer apply services/*.yaml

# With PromQL linting
nthlayer apply services/*.yaml --lint

# Interactive service creation
nthlayer init
```

### Validate Commands

```bash
# Verify metrics exist
nthlayer verify services/*.yaml

# Validate spec syntax
nthlayer validate-spec services/*.yaml

# Validate metadata
nthlayer validate-metadata services/*.yaml
```

</div>

<div>

### Protect Commands

```bash
# Check deployment gate
nthlayer check-deploy services/*.yaml

# View SLO portfolio
nthlayer portfolio

# View single service SLO
nthlayer slo show services/payment.yaml

# Collect current metrics
nthlayer slo collect services/payment.yaml
```

### Integration Commands

```bash
# Setup PagerDuty resources
nthlayer setup-pagerduty services/*.yaml

# Interactive configuration
nthlayer setup
```

</div>

</div>

---
layout: default
---

# Command: `nthlayer apply`

### Generate artifacts from service specs

<div class="grid grid-cols-2 gap-6 mt-6">

<div>

### Usage

```bash
nthlayer apply services/payment-api.yaml \
  --output-dir generated/ \
  --lint \
  --verbose
```

### Options

| Flag | Description |
|------|-------------|
| `--output-dir` | Output directory |
| `--lint` | Validate PromQL with pint |
| `--push` | Push to Grafana (GitOps: avoid) |
| `--dry-run` | Preview only |
| `--verbose` | Detailed output |

</div>

<div>

### Output

```
Generating artifacts for payment-api...

✓ Dashboard: generated/payment-api/dashboard.json
  - 3 SLO panels
  - 3 Health panels
  - 8 Dependency panels (postgresql, redis)

✓ Alerts: generated/payment-api/alerts.yaml
  - 2 SLO burn rate alerts
  - 15 postgresql alerts
  - 12 redis alerts

✓ Recording Rules: generated/payment-api/recording-rules.yaml
  - 12 pre-computed metrics

✓ SLOs: generated/payment-api/slos.yaml
  - availability: 99.95%
  - latency_p99: 200ms

Linting with pint... ✓ All queries valid
```

</div>

</div>

---
layout: default
---

# Command: `nthlayer verify`

### Contract verification - confirm metrics exist

<div class="grid grid-cols-2 gap-6 mt-6">

<div>

### Usage

```bash
# Strict mode (fails on missing)
nthlayer verify services/payment-api.yaml

# Lenient mode (warnings only)
nthlayer verify services/payment-api.yaml --no-fail

# Specify Prometheus URL
nthlayer verify services/payment-api.yaml \
  --prometheus-url https://prometheus.example.com
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All metrics found |
| 1 | Required metrics missing |

</div>

<div>

### Output

```
Verifying metrics for payment-api...

Required metrics:
✓ http_requests_total{service="payment-api"}
✓ http_request_duration_seconds_bucket{service="payment-api"}

Dependency metrics (postgresql):
✓ pg_stat_activity_count
✓ pg_stat_database_tup_fetched
✓ pg_replication_lag_seconds

Dependency metrics (redis):
✓ redis_commands_total
✗ redis_memory_used_bytes  ← NOT FOUND

Verification: FAILED
1 required metric missing
Exit code: 1
```

</div>

</div>

---
layout: default
---

# Command: `nthlayer check-deploy`

### Deployment gate - check error budget

<div class="grid grid-cols-2 gap-6 mt-6">

<div>

### Usage

```bash
# Check if deploy is safe
nthlayer check-deploy services/payment-api.yaml

# Specify Prometheus URL
nthlayer check-deploy services/payment-api.yaml \
  --prometheus-url https://prometheus.example.com

# Specify time window
nthlayer check-deploy services/payment-api.yaml \
  --window 7d
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Deploy allowed |
| 1 | Warning (budget low) |
| 2 | Deploy BLOCKED |

</div>

<div>

### Output (Healthy)

```
Checking deployment gate for payment-api...

SLO: 99.95% availability (30-day window)

Error Budget Status:
  Total:     21.6 minutes
  Consumed:  8.2 minutes (38%)
  Remaining: 13.4 minutes (62%)

Status: ✅ HEALTHY
Tier: critical (blocks at <10%)

Exit code: 0
```

### Output (Blocked)

```
Error Budget Status:
  Remaining: 1.8 minutes (8%)

Status: 🛑 DEPLOY BLOCKED
Reason: Error budget below 10% threshold
Tier: critical

Exit code: 2
```

</div>

</div>

---
layout: default
---

# Command: `nthlayer portfolio`

### Org-wide SLO overview

<div class="grid grid-cols-2 gap-6 mt-6">

<div>

### Usage

```bash
# Table view (default)
nthlayer portfolio

# JSON for automation
nthlayer portfolio --format json

# Filter by tier
nthlayer portfolio --tier critical

# Filter by team
nthlayer portfolio --team payments
```

### Output Formats

| Format | Use Case |
|--------|----------|
| `table` | Terminal (default) |
| `json` | Automation, APIs |
| `csv` | Spreadsheets |
| `markdown` | PR comments, Slack |

</div>

<div>

### Output

```
┌─────────────────────────────────────────────────────┐
│                  SLO Portfolio                      │
├─────────────┬──────────┬─────────┬─────────┬───────┤
│ Service     │ Tier     │ SLO     │ Budget  │ Status│
├─────────────┼──────────┼─────────┼─────────┼───────┤
│ payment-api │ critical │ 99.95%  │ 62%     │ ✅    │
│ search-api  │ standard │ 99.5%   │ 45%     │ ✅    │
│ user-svc    │ critical │ 99.95%  │ 8%      │ 🛑    │
│ analytics   │ low      │ 99.0%   │ 78%     │ ✅    │
└─────────────┴──────────┴─────────┴─────────┴───────┘

Organization Health Score: 72/100

⚠️ 1 service below threshold (user-svc)
```

</div>

</div>

---
layout: section
---

# Part 4: Integration

Prometheus • Grafana • PagerDuty • GitOps

---
layout: default
---

# GitOps Workflow (Recommended)

### NthLayer generates, CD deploys

<div class="grid grid-cols-2 gap-8 mt-6">

<div>

### Why GitOps?

1. **Audit trail** - All changes PR-reviewed
2. **Rollback** - `git revert` undoes any change
3. **Separation** - NthLayer generates, ArgoCD deploys
4. **No credentials** - NthLayer doesn't need Grafana/Prometheus API keys

### Workflow

```
service.yaml → nthlayer apply → generated/
                                    ↓
                              git commit
                                    ↓
                               PR review
                                    ↓
                              merge to main
                                    ↓
                            ArgoCD/Flux sync
```

</div>

<div>

### Pipeline Example

```yaml
# CI: Generate and commit
- name: Generate configs
  run: nthlayer apply services/*.yaml --lint

- name: Commit if changed
  run: |
    git add generated/
    git diff --cached --quiet || \
      git commit -m "chore: regenerate configs"
    git push

# CD: ArgoCD syncs generated/ to cluster
```

### Directory Structure

```
repo/
├── services/           # Source of truth
│   └── payment-api.yaml
├── generated/          # NthLayer output
│   └── payment-api/
│       ├── dashboard.json
│       ├── alerts.yaml
│       └── slos.yaml
└── .github/workflows/
    └── nthlayer.yaml
```

</div>

</div>

---
layout: default
---

# Prometheus Integration

### Alert rules and recording rules

<div class="grid grid-cols-2 gap-6 mt-6">

<div>

### Generated Alerts

```yaml
# generated/payment-api/alerts.yaml
groups:
  - name: payment-api-slo
    rules:
      - alert: PaymentAPIHighErrorRate
        expr: |
          sum(rate(http_requests_total{
            service="payment-api",
            status=~"5.."
          }[5m]))
          /
          sum(rate(http_requests_total{
            service="payment-api"
          }[5m])) > 0.001
        for: 5m
        labels:
          severity: critical
          service: payment-api
          tier: critical
        annotations:
          summary: "High error rate on payment-api"
```

</div>

<div>

### Generated Recording Rules

```yaml
# generated/payment-api/recording-rules.yaml
groups:
  - name: payment-api-recording
    rules:
      # Pre-compute availability
      - record: service:availability:ratio5m
        expr: |
          sum(rate(http_requests_total{
            service="payment-api",
            status!~"5.."
          }[5m]))
          /
          sum(rate(http_requests_total{
            service="payment-api"
          }[5m]))
        labels:
          service: payment-api

      # Pre-compute p99 latency
      - record: service:latency:p99_5m
        expr: |
          histogram_quantile(0.99,
            sum by (le) (rate(
              http_request_duration_seconds_bucket{
                service="payment-api"
              }[5m])))
```

</div>

</div>

---
layout: default
---

# Grafana Integration

### Dashboard generation

<div class="grid grid-cols-2 gap-6 mt-6">

<div>

### Dashboard Structure

```
Dashboard: payment-api
├── Row: SLO Metrics
│   ├── Availability (gauge)
│   ├── Error Budget (gauge)
│   └── Burn Rate (timeseries)
├── Row: Service Health
│   ├── Request Rate
│   ├── Error Rate
│   └── Latency P99
└── Row: Dependencies
    ├── PostgreSQL
    │   ├── Connections
    │   ├── Query Rate
    │   └── Replication Lag
    └── Redis
        ├── Memory Usage
        ├── Hit Rate
        └── Commands/sec
```

</div>

<div>

### Panel Types

| Intent | Panel Type |
|--------|------------|
| Availability | Gauge with thresholds |
| Error Budget | Gauge (remaining %) |
| Request Rate | Time series |
| Latency | Time series (heatmap) |
| Error Rate | Time series |

### Metric Resolution

NthLayer uses **intent-based templates**:

1. Define what you **want** to show
2. Discover what metrics **exist**
3. Resolve intent → actual metric

```python
# Intent: http_latency_p99
# Candidates: [
#   http_request_duration_seconds_bucket,
#   http_request_latency_seconds_bucket,
#   request_duration_seconds_bucket
# ]
# Resolved: http_request_duration_seconds_bucket
```

</div>

</div>

---
layout: default
---

# PagerDuty Integration

### Auto-create teams, services, escalations

<div class="grid grid-cols-2 gap-6 mt-6">

<div>

### What Gets Created

```yaml
# When auto_create: true
Team: payments
Escalation Policy: payments-escalation
Service: payment-api
```

### Idempotency

- Uses **upsert by name**
- Safe to run multiple times
- Never deletes existing resources
- Never modifies existing configs

### Dry Run

```bash
# Preview what would be created
nthlayer setup-pagerduty service.yaml --dry-run

Would create:
  ✓ Team: payments
  ✓ Escalation Policy: payments-escalation
  ✓ Service: payment-api

No changes made (dry run mode)
```

</div>

<div>

### Tier-Based Escalation

| Tier | Urgency | Escalation |
|------|---------|------------|
| critical | High | 5 min → 15 min → 30 min |
| standard | Low | 30 min → 60 min |
| low | Low | 60 min |

### Using Existing Resources

```yaml
# service.yaml
resources:
  - kind: PagerDuty
    spec:
      auto_create: false
      team_id: PXXXXXX       # Existing team
      service_id: PXXXXXX    # Existing service
```

### Required Permissions

```
teams:write
services:write
escalation_policies:write
users:read
```

</div>

</div>

---
layout: default
---

# Best Practices

<div class="grid grid-cols-2 gap-8 mt-6">

<div>

### Directory Organization

```
services/
├── tier-1/
│   ├── payment-api.yaml
│   └── auth-service.yaml
├── tier-2/
│   ├── search-api.yaml
│   └── recommendation-svc.yaml
└── tier-3/
    ├── analytics.yaml
    └── reports.yaml
```

### Naming Conventions

```yaml
# Good
name: payment-api
team: payments

# Bad
name: PaymentAPI_v2_PROD
team: Team_Payments_123
```

</div>

<div>

### Workflow

1. **Validate locally** before commit
   ```bash
   nthlayer validate-spec services/*.yaml
   nthlayer apply services/*.yaml --lint --dry-run
   ```

2. **Use `--no-fail` initially** for verify
   ```bash
   nthlayer verify services/*.yaml --no-fail
   ```

3. **Graduate to blocking** after burn-in
   ```bash
   nthlayer check-deploy services/*.yaml
   ```

### Version Control

- ✅ Commit service.yaml specs to Git
- ✅ Commit generated/ artifacts to Git
- ✅ PR reviews for all changes
- ❌ Never commit API keys

</div>

</div>

---
layout: center
---

# Questions?

<div class="text-center mt-8">

**Resources:**

- 📚 **Docs:** rsionnach.github.io/nthlayer
- 💻 **GitHub:** github.com/rsionnach/nthlayer
- 📦 **PyPI:** `pip install nthlayer`

<div class="mt-8 text-xl font-bold text-blue-400">
Reliability Requirements as Code
</div>

<div class="mt-2">
Define once. Generate everything. Block bad deploys.
</div>

</div>
