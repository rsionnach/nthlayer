# Protect

**Block risky deploys before they cause incidents.**

NthLayer's protection layer enforces reliability policies in production. When error budget is exhausted, deployments are blocked - automatically.

## The Protection Stack

| Feature | Command | What It Does |
|---------|---------|--------------|
| **Deployment Gates** | `nthlayer check-deploy` | Block deploys when budget exhausted |
| **SLO Portfolio** | `nthlayer portfolio` | Org-wide reliability visibility |
| **Error Budgets** | `nthlayer slo collect` | Real-time budget consumption |

## Why Deployment Gates?

Traditional monitoring tells you **after** a deployment causes problems:

```
Deploy → Incident → Page → Investigate → Rollback → Postmortem
                      ↑
               "The deploy broke it"
```

Deployment gates tell you **before**:

```
Check Budget → Block/Allow → Deploy
      ↑
  "Budget exhausted - don't deploy"
```

## Quick Start

### 1. Check Before Deploy

```bash
nthlayer check-deploy services/payment-api.yaml \
  --prometheus-url http://prometheus:9090
```

Output:
```
╭──────────────────────────────────────────────────────────────╮
│  Deployment Gate: payment-api                                │
╰──────────────────────────────────────────────────────────────╯

  Tier:          critical
  Window:        30d

  SLO Status:
    availability   99.87%  (target: 99.95%)   42% remaining   ⚠ WARNING
    latency_p99    187ms   (target: 200ms)    78% remaining   ✓ OK

  Decision: ⚠ PROCEED WITH CAUTION
  Exit code: 1
```

### 2. View Portfolio Health

```bash
nthlayer portfolio --path services/
```

Output:
```
╭──────────────────────────────────────────────────────────────╮
│  NthLayer SLO Portfolio                                      │
╰──────────────────────────────────────────────────────────────╯

  Organization Health: 78% (14/18 services meeting SLOs)

  By Tier:
    Critical:  ████████░░  83% (5/6 services)
    Standard:  ███████░░░  75% (6/8 services)
    Low:       ███████░░░  75% (3/4 services)

  ⚠ Services Needing Attention:
    payment-api    availability  156% burned  EXHAUSTED
    search-api     latency       95% burned   WARNING
```

## Exit Codes

Deployment gates use exit codes for CI/CD integration:

| Code | Decision | Pipeline Action |
|------|----------|-----------------|
| `0` | Approved | Deploy proceeds |
| `1` | Warning | Deploy with caution |
| `2` | Blocked | Fail pipeline |

## Tier-Based Thresholds

Default thresholds vary by service tier:

| Tier | Warning | Blocking |
|------|---------|----------|
| Critical | <20% remaining | <10% remaining |
| Standard | <20% remaining | None (advisory) |
| Low | <30% remaining | None (advisory) |

Critical services block deploys at 10% remaining budget. Lower tiers only warn.

## Custom Policies

Override defaults with a `DeploymentGate` resource:

```yaml
resources:
  - kind: DeploymentGate
    name: strict-gate
    spec:
      thresholds:
        warning: 30
        blocking: 15

      conditions:
        # Stricter during business hours
        - name: business-hours
          when: "hour >= 9 AND hour <= 17 AND weekday"
          blocking: 20

        # Complete freeze during incidents
        - name: low-budget
          when: "budget_remaining < 5"
          blocking: 100
```

## CI/CD Integration

### GitHub Actions

```yaml
jobs:
  deploy:
    steps:
      - name: Check Deployment Gate
        run: |
          nthlayer check-deploy services/api.yaml \
            --prometheus-url ${{ secrets.PROMETHEUS_URL }}

      - name: Deploy
        if: success()  # Only if gate passed
        run: kubectl apply -f generated/
```

### ArgoCD PreSync Hook

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: deployment-gate
  annotations:
    argocd.argoproj.io/hook: PreSync
spec:
  template:
    spec:
      containers:
        - name: check
          image: ghcr.io/nthlayer/nthlayer:latest
          command:
            - nthlayer
            - check-deploy
            - /config/service.yaml
            - --prometheus-url
            - $(PROMETHEUS_URL)
```

## The Google SRE Connection

NthLayer automates the [Error Budget Policy](https://sre.google/sre-book/embracing-risk/) from the Google SRE Book:

> "If our SLO says we can have 0.1% downtime per month, and we've already used 0.08%, we should be very careful about deploying new features."

| SRE Concept | Manual Process | NthLayer Automation |
|-------------|----------------|---------------------|
| Error Budget Policy | Spreadsheet tracking | `nthlayer check-deploy` |
| Release Freeze | Calendar reminders | Automatic blocking |
| Budget Visibility | Monthly reports | `nthlayer portfolio` |

## Next Steps

- [Deployment Gates](../commands/check-deploy.md) - Full command reference
- [SLO Portfolio](../commands/portfolio.md) - Organization-wide view
- [Error Budgets](../concepts/slos.md) - Understanding SLOs
- [CI/CD Integration](../integrations/cicd.md) - Pipeline examples
