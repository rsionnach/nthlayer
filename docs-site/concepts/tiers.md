# Service Tiers

Tiers are the foundation of NthLayer's reliability requirements. A service's tier determines its SLO targets, alerting thresholds, escalation urgency, and deployment gate strictness.

## What Tier Means

**Tier represents business criticality, not technical complexity.**

A simple CRUD API that processes payments is tier `critical`.
A sophisticated ML pipeline that generates recommendations is tier `standard`.

The question is: *What happens to the business if this service fails?*

| Tier | Business Impact | Examples |
|------|-----------------|----------|
| **critical** | Revenue loss, safety risk, core user flow blocked | Checkout, Authentication, Payments, Core API |
| **standard** | Degraded experience, workarounds exist | Search, Recommendations, Notifications |
| **low** | Minimal user impact, internal tooling | Reports, Batch jobs, Admin dashboards |

## What Tier Controls

### SLO Targets

| Metric | Critical | Standard | Low |
|--------|----------|----------|-----|
| Availability | 99.95% | 99.5% | 99.0% |
| Latency P99 | 200ms | 500ms | 2000ms |
| Error Rate | 0.05% | 0.5% | 1.0% |

### Error Budget & Gates

| Aspect | Critical | Standard | Low |
|--------|----------|----------|-----|
| Monthly error budget | 21.6 min | 3.6 hrs | 7.2 hrs |
| `check-deploy` blocks at | < 10% remaining | < 5% remaining | Advisory only |
| `check-deploy` warns at | < 20% remaining | < 10% remaining | < 20% remaining |

### Alerting Thresholds

| Alert Type | Critical | Standard | Low |
|------------|----------|----------|-----|
| Error rate threshold | > 1% | > 5% | > 10% |
| Latency P99 threshold | > 500ms | > 2s | > 5s |
| Availability threshold | < 99.9% | < 99% | < 95% |

### PagerDuty Escalation

| Aspect | Critical | Standard | Low |
|--------|----------|----------|-----|
| Initial urgency | High | Low | Low |
| Escalation delay | 5 minutes | 30 minutes | 60 minutes |
| Auto-resolve | No | After 30 min | After 60 min |

## Choosing a Tier

### Ask These Questions

1. **Revenue impact**: Does downtime directly cost money?
   - Yes → `critical`
   - Indirectly → `standard`
   - No → `low`

2. **User-facing**: Do end users see this service's output?
   - Core flow (checkout, login) → `critical`
   - Supporting flow (search, recommendations) → `standard`
   - Internal only → `low`

3. **Recovery time**: How quickly must this recover?
   - Minutes → `critical`
   - Hours → `standard`
   - Days acceptable → `low`

### Common Mistakes

❌ **Over-tiering**: Making everything `critical` dilutes urgency and causes alert fatigue.

❌ **Under-tiering**: A payment service marked `low` won't get appropriate alerting or gates.

❌ **Tiering by complexity**: A complex service isn't necessarily critical. A simple service can be.

## Specifying Tier

In your `service.yaml`:

```yaml
name: checkout-api
team: payments
tier: critical  # or: 1, "tier-1", "t1"
type: api
```

NthLayer accepts multiple formats:

| Input | Normalized To |
|-------|---------------|
| `critical`, `1`, `tier-1`, `t1` | `critical` |
| `standard`, `2`, `tier-2`, `t2` | `standard` |
| `low`, `3`, `tier-3`, `t3` | `low` |

## Overriding Tier Defaults

Tier sets defaults, but you can override any specific value:

```yaml
name: checkout-api
tier: critical

slos:
  - name: availability
    target: 99.99  # Override: stricter than critical default (99.95)

resources:
  - kind: PagerDuty
    spec:
      urgency: high
      escalation_delay: 3m  # Override: faster than critical default (5m)
```

## Tier Changes

Changing a service's tier should be deliberate:

**Promoting to higher tier** (e.g., `standard` → `critical`):
- Requires tighter SLOs
- Triggers more aggressive alerting
- Enables stricter deployment gates
- Consider: Is the service actually ready for this scrutiny?

**Demoting to lower tier** (e.g., `critical` → `standard`):
- Relaxes SLOs
- Reduces alert sensitivity
- Loosens deployment gates
- Consider: Is this reflecting reality or just avoiding alerts?

## Platform Team Guidance

For platform teams standardizing on NthLayer:

1. **Document your tier criteria** specific to your organization
2. **Require justification** for `critical` tier assignments
3. **Review tier assignments** quarterly
4. **Start services at `standard`** and promote based on evidence

The tier system only works if it reflects actual business reality.
