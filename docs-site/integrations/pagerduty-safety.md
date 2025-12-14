# PagerDuty Safety & Idempotency

NthLayer can create and manage PagerDuty resources (teams, services, escalation policies). This page documents exactly what NthLayer does, what permissions it needs, and how to use it safely.

## Safety Principles

1. **NthLayer never deletes** - Only creates and updates, never removes
2. **Idempotent by design** - Running twice produces the same result
3. **Dry-run first** - Always preview changes before applying
4. **Minimal permissions** - Only request what's needed

---

## What NthLayer Creates

### When `auto_create: true`

| Resource | Created If | Named As |
|----------|------------|----------|
| Team | Team doesn't exist | `{team}` from service.yaml |
| Escalation Policy | Policy doesn't exist | `{team}-escalation` |
| Service | Service doesn't exist | `{service-name}` |

### Example

```yaml
# service.yaml
name: checkout-api
team: payments
tier: critical

resources:
  - kind: PagerDuty
    spec:
      auto_create: true
```

Creates:
- Team: `payments`
- Escalation Policy: `payments-escalation`
- Service: `checkout-api`

---

## What NthLayer Does NOT Do

### Never Deletes

- ❌ Never deletes teams
- ❌ Never deletes escalation policies
- ❌ Never deletes services
- ❌ Never removes team members
- ❌ Never removes schedules

### Never Modifies Without Consent

- ❌ Never changes existing escalation policy rules (unless explicitly configured)
- ❌ Never reassigns services to different teams
- ❌ Never changes service urgency settings on existing services

---

## Idempotency Model

NthLayer uses **upsert by name** semantics:

### First Run (Resource Doesn't Exist)

```
Team "payments" → CREATE
Escalation Policy "payments-escalation" → CREATE
Service "checkout-api" → CREATE
```

### Second Run (Resources Exist)

```
Team "payments" → EXISTS, skip
Escalation Policy "payments-escalation" → EXISTS, skip
Service "checkout-api" → EXISTS, skip
```

### Name Collision Handling

If a resource exists with the same name but different configuration:

| Scenario | NthLayer Behavior |
|----------|-------------------|
| Team exists with same name | Reuses existing team |
| Service exists with same name | Reuses existing service |
| Escalation policy exists | Reuses existing policy |

NthLayer **does not** overwrite existing configurations.

---

## Required Permissions

### Minimum API Key Scope

```
Teams: Read/Write
Services: Read/Write
Escalation Policies: Read/Write
Users: Read (for team membership)
```

### Creating an API Key

1. Go to **Integrations → API Access Keys**
2. Click **Create New API Key**
3. Select **Full Access** (or configure specific scopes)
4. Copy the key (starts with `u+`)

### Recommended: Scoped Token

For production use, create a scoped token with only:
- `teams:write`
- `services:write`
- `escalation_policies:write`
- `users:read`

---

## Dry Run Mode

**Always run with `--dry-run` first**:

```bash
nthlayer setup-pagerduty services/checkout-api.yaml --dry-run
```

Output shows what would be created:

```
PagerDuty Dry Run
─────────────────

Would create:
  ✓ Team: payments
  ✓ Escalation Policy: payments-escalation
  ✓ Service: checkout-api

No changes made (dry run mode)
```

---

## Using Existing Resources

### Use Existing Team

```yaml
resources:
  - kind: PagerDuty
    spec:
      auto_create: false
      team_id: PXXXXXX  # Existing team ID
```

### Use Existing Escalation Policy

```yaml
resources:
  - kind: PagerDuty
    spec:
      auto_create: false
      escalation_policy: PXXXXXX  # Existing policy ID
```

### Use Existing Service

```yaml
resources:
  - kind: PagerDuty
    spec:
      auto_create: false
      service_id: PXXXXXX  # Existing service ID
```

---

## Rollback & Recovery

### If Something Goes Wrong

1. **NthLayer doesn't delete**, so existing resources are safe
2. Created resources can be manually deleted in PagerDuty UI
3. No cascading changes to worry about

### Manual Cleanup

If you need to remove NthLayer-created resources:

1. Go to PagerDuty → Configuration → Services
2. Delete the service (this doesn't delete the team)
3. Go to Escalation Policies, delete if unused
4. Go to Teams, delete if unused

### Identifying NthLayer-Created Resources

NthLayer adds metadata to created resources:

- Service description includes: `Created by NthLayer`
- Team description includes: `Auto-created by NthLayer`

---

## Best Practices

### 1. Start with Existing Resources

For your first services, use existing PagerDuty resources:

```yaml
resources:
  - kind: PagerDuty
    spec:
      auto_create: false
      team_id: PXXXXXX
      escalation_policy: PXXXXXX
```

### 2. Use Dry Run in CI

```yaml
# CI pipeline
- name: Validate PagerDuty config
  run: |
    nthlayer setup-pagerduty services/${{ matrix.service }}.yaml --dry-run
```

### 3. Separate Staging from Production

```yaml
environments:
  staging:
    pagerduty:
      auto_create: true
      urgency: low
  production:
    pagerduty:
      auto_create: false
      service_id: PXXXXXX  # Use existing prod service
```

### 4. Audit Regularly

Review NthLayer-created resources quarterly:
- Are escalation policies still appropriate?
- Are team memberships current?
- Are services still active?

---

## Troubleshooting

### "Permission Denied" Error

```
Error: Unable to create team - permission denied
```

**Fix**: Ensure API key has `teams:write` permission

### "Team Already Exists" (No Error)

This is expected behavior. NthLayer reuses existing teams.

### "Service Already Exists" with Different Team

```
Warning: Service 'checkout-api' exists but belongs to team 'old-team'
```

NthLayer will **not** reassign the service. Either:
- Manually move the service in PagerDuty UI
- Or use `service_id` to explicitly reference it

### Rate Limiting

PagerDuty has API rate limits. If you hit them:
- NthLayer automatically retries with backoff
- For bulk operations, run services sequentially

---

## Enterprise Considerations

### Change Management

For organizations with change management processes:

1. Run `--dry-run` and capture output
2. Submit output for change approval
3. After approval, run without `--dry-run`

### Audit Trail

NthLayer operations are logged. Enable verbose logging:

```bash
nthlayer setup-pagerduty services/checkout-api.yaml --verbose
```

### Multi-Account PagerDuty

If you have multiple PagerDuty accounts:

```yaml
environments:
  us-east:
    pagerduty:
      api_key_secret: pagerduty/us-east/api_key
  eu-west:
    pagerduty:
      api_key_secret: pagerduty/eu-west/api_key
```
