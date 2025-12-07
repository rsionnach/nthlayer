# PagerDuty Integration

NthLayer can create and manage PagerDuty teams, services, and escalation policies.

## Configuration

### Via Setup Wizard

```bash
nthlayer setup
```

### Via Environment Variable

```bash
export PAGERDUTY_API_KEY=u+xxxxxxxxxxxxxxxxxx
```

### Via Config File

```yaml
# ~/.nthlayer/config.yaml
alerting:
  pagerduty:
    enabled: true
    api_key_secret: pagerduty/api_key
    default_escalation_policy: P123ABC
```

## Getting an API Key

1. Go to **Integrations > API Access Keys**
2. Create a new **REST API Key**
3. Select **Full Access** permissions
4. Copy the key (starts with `u+`)

## Service Spec Configuration

```yaml
name: payment-api
team: payments
tier: critical
type: api

resources:
  - kind: PagerDuty
    name: alerting
    spec:
      urgency: high           # high or low
      auto_create: true       # Create team/service automatically
      escalation_policy: P123ABC  # Optional: use existing policy
```

## What Gets Created

When `auto_create: true`:

### Team

```
Name: payments
Description: Auto-created by NthLayer
```

### Escalation Policy

```
Name: payments-escalation
Rules:
  - Escalate to team "payments" after 5 minutes (critical)
  - Escalate to team "payments" after 15 minutes (standard)
```

### Service

```
Name: payment-api
Description: payment-api reliability alerts
Escalation Policy: payments-escalation
Urgency: high
```

## Tier-Based Escalation

| Tier | Urgency | Escalation Time |
|------|---------|-----------------|
| **Critical (1)** | High | 5 minutes |
| **Standard (2)** | Low | 15 minutes |
| **Low (3)** | Low | 30 minutes |

## Manual Setup

To use existing PagerDuty resources:

```yaml
resources:
  - kind: PagerDuty
    name: alerting
    spec:
      auto_create: false
      service_id: PXXXXXX
      escalation_policy: PXXXXXX
```

## Alert Integration

Generated Prometheus alerts include PagerDuty annotations:

```yaml
- alert: PaymentApiHighErrorRate
  annotations:
    pagerduty_service: payment-api
    runbook_url: https://wiki.example.com/runbooks/payment-api
```

## Testing Connection

```bash
nthlayer setup --test
```

```
  PagerDuty
    [OK] Connected - 3 escalation policies
```

## Troubleshooting

### Invalid API Key

```
[FAIL] Invalid API key
```

- Verify key starts with `u+`
- Check key has Full Access
- Ensure key isn't revoked

### Team Already Exists

NthLayer checks for existing teams by name and reuses them.

### Permission Denied

Ensure API key has permissions to:

- Create/update teams
- Create/update services
- Create/update escalation policies
