# Deployment Gates

Deployment gates block or warn about deployments when error budget is exhausted. This is the core of NthLayer's **Shift Left** approach - catching reliability issues before they reach production.

## Why Deployment Gates?

Traditional monitoring tells you **after** a deployment causes problems. Deployment gates tell you **before** - enabling you to:

- **Prevent incidents** by blocking deploys when reliability is already degraded
- **Make informed decisions** with real-time error budget visibility
- **Enforce SLO discipline** across your organization

## How It Works

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   CI/CD     │────▶│  NthLayer   │────▶│ Prometheus  │
│  Pipeline   │     │ check-deploy │     │   Query     │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   Result    │
                    │ 0=Approved  │
                    │ 1=Warning   │
                    │ 2=Blocked   │
                    └─────────────┘
```

1. **Pipeline triggers**: Your CI/CD pipeline calls `nthlayer check-deploy`
2. **Query SLOs**: NthLayer queries Prometheus for current SLI values
3. **Calculate budget**: Error budget consumption is calculated
4. **Return decision**: Exit code determines if deploy proceeds

## Default Thresholds

Thresholds are based on service tier:

| Tier | Warning | Blocking |
|------|---------|----------|
| Critical | <20% remaining | <10% remaining |
| Standard | <20% remaining | None (advisory) |
| Low | <30% remaining | None (advisory) |

Critical services block deploys at 10% remaining budget. Standard and low tiers only warn.

## Custom Policies

Override defaults with a `DeploymentGate` resource in your `service.yaml`:

```yaml
resources:
  - kind: DeploymentGate
    name: custom-gate
    spec:
      thresholds:
        warning: 30
        blocking: 5
```

### Conditional Thresholds

Apply different thresholds based on conditions:

```yaml
resources:
  - kind: DeploymentGate
    name: smart-gate
    spec:
      thresholds:
        warning: 20
        blocking: 10

      conditions:
        # Stricter during business hours
        - name: business-hours
          when: "hour >= 9 AND hour <= 17 AND weekday"
          blocking: 15

        # Complete freeze during incidents
        - name: incident-freeze
          when: "budget_remaining < 5"
          blocking: 100
```

### Team Exceptions

Allow specific teams to bypass gates:

```yaml
spec:
  exceptions:
    - team: sre-oncall
      allow: always
```

## Integration Points

### CI/CD Pipelines

NthLayer integrates with:

- **GitHub Actions** - Reusable action
- **ArgoCD** - PreSync hook
- **GitLab CI** - Reusable template
- **Tekton** - Reusable task

See [examples/cicd/](https://github.com/nthlayer/nthlayer/tree/main/examples/cicd) for templates.

### Manual Check

Test locally before integrating:

```bash
nthlayer check-deploy services/api.yaml \
  --prometheus-url http://prometheus:9090

echo "Exit code: $?"
```

## Blast Radius Awareness

Gates consider downstream dependencies:

```yaml
resources:
  - kind: Dependencies
    name: downstream
    spec:
      services:
        - name: checkout-service
          criticality: high
        - name: analytics
          criticality: low
```

High-criticality downstream services increase the gate's caution level.

## Best Practices

### 1. Start with Advisory Mode

Begin with warnings only, then enable blocking:

```yaml
spec:
  thresholds:
    warning: 20
    blocking: null  # Advisory only
```

### 2. Use Environment-Specific Thresholds

Be lenient in dev, strict in prod:

```yaml
# dev environment
spec:
  thresholds:
    warning: 50
    blocking: null

# prod environment
spec:
  thresholds:
    warning: 20
    blocking: 10
```

### 3. Define SLO Queries

Gates need working SLO queries to calculate budget:

```yaml
- kind: SLO
  name: availability
  spec:
    objective: 99.95
    window: 30d
    indicator:
      query: |
        sum(rate(http_requests_total{status!~"5.."}[5m]))
        /
        sum(rate(http_requests_total[5m]))
```

### 4. Test Before Production

Use the demo mode to see gate behavior:

```bash
nthlayer check-deploy services/api.yaml --demo
```

## See Also

- [check-deploy Command](../commands/check-deploy.md)
- [SLO Concepts](./slos.md)
- [Shift Left Philosophy](./shift-left.md)
