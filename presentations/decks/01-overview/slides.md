---
theme: the-unnamed
highlighter: shiki
title: NthLayer - Reliability Requirements as Code
themeConfig:
  logoHeader: '/nthlayer_dark_logo.png'
  eventLogo: ''
  eventUrl: ''
  twitter: ''
  twitterUrl: ''
---

<div class="flex justify-center my-8">
  <img src="/nthlayer_dark_logo.png" class="h-56" />
</div>

<div class="text-center mt-8">

<div class="text-3xl font-bold mb-4">
The Missing Layer of Reliability
</div>

<div class="text-xl mb-4 text-blue-400">
Reliability Requirements as Code
</div>

<div class="text-base mb-6">
Define what "production-ready" means for a service.<br/>
Generate, validate, and enforce those requirements automatically.
</div>

<div class="text-lg font-bold">
Define once. Generate everything. Block bad deploys.
</div>

</div>

---
layout: default
---

# The Problem

### Reliability decisions happen at the wrong time

<div class="grid grid-cols-2 gap-8 mt-8">

<div>

### Today's Reality

- Alerts created **after** the first incident
- Dashboards built **after** users complain
- SLOs defined **after** budget is exhausted
- "Is this production-ready?" = **negotiated opinion**

</div>

<div>

### The Cost

- **Reactive reliability** - always responding, never preventing
- **Inconsistent standards** - each team invents their own
- **No gates** - risky deploys reach production
- **Repeated work** - same configs rebuilt per service

</div>

</div>

<div class="text-center mt-8 text-xl font-bold text-red-400">
Reliability is treated as an afterthought, not a requirement.
</div>

---
layout: default
---

# The Shift-Left Solution

### Move reliability decisions to build time

<div class="mt-6">

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ service.yaml → generate → lint → verify → check-deploy → deploy            │
│                   ↓         ↓       ↓           ↓                          │
│               artifacts   valid?  metrics?  budget ok?                     │
│                                                                            │
│ "Is this production-ready?" - answered BEFORE deployment                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

</div>

<div class="grid grid-cols-3 gap-6 mt-8">

<div class="text-center">

### Generate
`nthlayer apply`

Dashboards, alerts, SLOs<br/>from a single YAML spec

</div>

<div class="text-center">

### Validate
`nthlayer verify`

Confirm declared metrics<br/>exist in Prometheus

</div>

<div class="text-center">

### Protect
`nthlayer check-deploy`

Block deploys when<br/>error budget exhausted

</div>

</div>

---
layout: default
---

# What NthLayer Is

<div class="grid grid-cols-2 gap-8 mt-8">

<div>

### A Reliability Specification

- Define what "production-ready" means
- Tier-based defaults (critical, standard, low)
- SLO targets, alerting thresholds, escalation urgency

### A Compiler

- service.yaml → operational reality
- Dashboards, alerts, recording rules, PagerDuty configs
- Consistent output from simple input

### A CI/CD-Native Enforcement Layer

- Exit codes for pipeline integration
- `verify` fails if metrics don't exist
- `check-deploy` blocks if budget exhausted

</div>

<div>

### What NthLayer Is NOT

<div class="mt-4">

❌ **Not a service catalog**
<div class="text-sm text-gray-400 ml-6">Catalogs document; NthLayer enforces</div>

❌ **Not an observability platform**
<div class="text-sm text-gray-400 ml-6">Grafana/Datadog observe; NthLayer generates configs for them</div>

❌ **Not an incident management system**
<div class="text-sm text-gray-400 ml-6">PagerDuty responds; NthLayer prevents incidents</div>

❌ **Not a runtime control plane**
<div class="text-sm text-gray-400 ml-6">NthLayer operates at build time, not runtime</div>

</div>

<div class="mt-6 p-4 bg-blue-900/30 rounded">
NthLayer <strong>complements</strong> these systems by ensuring services meet reliability requirements <strong>before</strong> they are deployed.
</div>

</div>

</div>

---
layout: default
---

# The Reliability Contract

### Define requirements once, enforce everywhere

<div class="grid grid-cols-2 gap-8 mt-6">

<div>

### Input: Service Spec

```yaml
name: payment-api
tier: critical
type: api
team: payments

dependencies:
  - postgresql
  - redis
```

<div class="text-sm text-gray-400 mt-2">
5 lines define the reliability contract
</div>

</div>

<div>

### What Tier Controls

| Aspect | Critical | Standard | Low |
|--------|----------|----------|-----|
| Availability SLO | 99.95% | 99.5% | 99.0% |
| Latency P99 | 200ms | 500ms | 2000ms |
| Gate blocks at | <10% budget | <5% budget | Advisory |
| PagerDuty urgency | High (5min) | Low (30min) | Low (60min) |

<div class="text-sm text-gray-400 mt-2">
Tier = business criticality, not technical complexity
</div>

</div>

</div>

---
layout: default
---

# The Three Enforcement Points

<div class="grid grid-cols-3 gap-6 mt-8">

<div class="p-4 border-2 border-yellow-500 rounded">

### 1. Lint
`nthlayer apply --lint`

**What:** Validates PromQL syntax

**When:** PR / CI

**Exit Code:**
- 0 = Valid
- 1 = Invalid queries

<div class="text-yellow-400 mt-4 font-bold">
Catch syntax errors before Prometheus rejects them
</div>

</div>

<div class="p-4 border-2 border-blue-500 rounded">

### 2. Verify
`nthlayer verify`

**What:** Confirms metrics exist

**When:** Pre-deploy

**Exit Code:**
- 0 = All metrics found
- 1 = Missing metrics

<div class="text-blue-400 mt-4 font-bold">
Contract verification: "Do the metrics I declared actually exist?"
</div>

</div>

<div class="p-4 border-2 border-red-500 rounded">

### 3. Gate
`nthlayer check-deploy`

**What:** Checks error budget

**When:** CD gate

**Exit Code:**
- 0 = Deploy allowed
- 1 = Warning
- 2 = Deploy blocked

<div class="text-red-400 mt-4 font-bold">
Prevent deploys that would violate SLOs
</div>

</div>

</div>

---
layout: default
---

# Pipeline Integration

### Reliability as a first-class CI/CD citizen

```yaml
# GitHub Actions / Tekton / GitLab CI
steps:
  - name: Generate reliability configs
    run: nthlayer apply services/*.yaml --lint
    # Exit 1 if PromQL invalid

  - name: Verify metrics exist
    run: nthlayer verify services/*.yaml
    # Exit 1 if declared metrics missing

  - name: Check deployment gate
    run: nthlayer check-deploy services/*.yaml
    # Exit 2 if error budget exhausted → block deploy

  - name: Deploy to production
    run: kubectl apply -f generated/
    # Only runs if all gates pass
```

<div class="text-center mt-6 text-lg">
Works with: <strong>GitHub Actions</strong> • <strong>Tekton</strong> • <strong>GitLab CI</strong> • <strong>ArgoCD</strong> • <strong>Jenkins</strong>
</div>

---
layout: default
---

# What Gets Generated

### From one YAML, NthLayer produces:

<div class="grid grid-cols-3 gap-4 mt-6">

<div class="p-4 border-2 border-green-500 rounded">

### 📊 Dashboards
Grafana JSON with:
- SLO panels
- Service health
- Dependency metrics

**12-28 panels per service**

</div>

<div class="p-4 border-2 border-orange-500 rounded">

### 🚨 Alerts
Prometheus rules with:
- Tier-based thresholds
- Burn rate alerts
- Dependency alerts

**Technology-specific rules**

</div>

<div class="p-4 border-2 border-purple-500 rounded">

### 🎯 SLOs
OpenSLO format with:
- Availability objectives
- Latency objectives
- Error budget calculation

**Tier-based defaults**

</div>

<div class="p-4 border-2 border-red-500 rounded">

### 📟 PagerDuty
Auto-creates:
- Teams
- Escalation policies
- Services

**Tier-based urgency**

</div>

<div class="p-4 border-2 border-cyan-500 rounded">

### ⚡ Recording Rules
Pre-computed metrics:
- SLO ratios
- Error rates
- Latency percentiles

**10x faster dashboards**

</div>

<div class="p-4 border-2 border-yellow-500 rounded">

### 🛡️ Deploy Gates
CI/CD integration:
- Error budget checks
- Exit codes
- Pipeline blocking

**Prevent risky deploys**

</div>

</div>

---
layout: default
---

# Why This Matters

<div class="grid grid-cols-2 gap-8 mt-8">

<div>

### With NthLayer

| Aspect | Result |
|--------|--------|
| Standards | Encoded once, inherited everywhere |
| Defaults | Teams get sane configs automatically |
| Production-ready | Deterministic check, not opinion |
| Reliability | Enforced by default |

</div>

<div>

### Without NthLayer

| Aspect | Result |
|--------|--------|
| Standards | Recreated per service |
| Defaults | Each team invents their own |
| Production-ready | Negotiated during incidents |
| Reliability | Reactive and inconsistent |

</div>

</div>

<div class="text-center mt-8">

<div class="text-2xl font-bold text-green-400">
Reliability stops being reactive.
</div>

<div class="text-xl mt-2">
It becomes defined, validated, and enforced by default.
</div>

</div>

---
layout: default
---

# Adoption Path

### Start small, expand with confidence

<div class="grid grid-cols-3 gap-6 mt-8">

<div class="p-4 border-2 border-green-500 rounded">

### Phase 1: Generate
**Week 1**

- Run `nthlayer apply` locally
- Review generated artifacts
- No CI/CD integration yet

<div class="text-green-400 mt-4">
✅ Zero risk
</div>

</div>

<div class="p-4 border-2 border-blue-500 rounded">

### Phase 2: Validate
**Week 2-3**

- Add to CI pipeline
- `--lint` on every PR
- `verify --no-fail` (warnings)

<div class="text-blue-400 mt-4">
📊 Build confidence
</div>

</div>

<div class="p-4 border-2 border-purple-500 rounded">

### Phase 3: Protect
**Week 4+**

- Enable `check-deploy` gate
- Start with non-critical services
- Graduate to blocking mode

<div class="text-purple-400 mt-4">
🛡️ Full enforcement
</div>

</div>

</div>

<div class="text-center mt-6 text-gray-400">
You don't need to adopt everything on day one.
</div>

---
layout: default
---

# Quick Start

```bash
# Install
pip install nthlayer

# Create a service spec
nthlayer init

# Generate all artifacts
nthlayer apply services/payment-api.yaml

# Verify metrics exist
nthlayer verify services/payment-api.yaml

# Check if deploy is safe
nthlayer check-deploy services/payment-api.yaml
```

<div class="grid grid-cols-2 gap-8 mt-6">

<div>

### Output Structure
```
generated/payment-api/
├── dashboard.json
├── alerts.yaml
├── recording-rules.yaml
└── slos.yaml
```

</div>

<div>

### Exit Codes
```
0 = Success / Deploy allowed
1 = Warning / Missing metrics
2 = Deploy blocked (budget exhausted)
```

</div>

</div>

---
layout: center
---

# Reliability Requirements as Code

<div class="text-center mt-8">

<div class="text-2xl mb-6">
Define what "production-ready" means.<br/>
Generate, validate, and enforce automatically.
</div>

<div class="text-xl font-bold text-blue-400 mb-8">
Define once. Generate everything. Block bad deploys.
</div>

**GitHub:** github.com/rsionnach/nthlayer

**Docs:** rsionnach.github.io/nthlayer

**PyPI:** `pip install nthlayer`

</div>
