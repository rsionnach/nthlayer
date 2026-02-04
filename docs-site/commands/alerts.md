# nthlayer alerts

Evaluate, simulate, and explain alert rules for a service.

## Synopsis

```bash
nthlayer alerts evaluate <service-file> [options]
nthlayer alerts show <service-file> [options]
nthlayer alerts explain <service-file> [options]
nthlayer alerts test <service-file> [options]
```

## Description

The `alerts` command family provides an intelligent alerts pipeline that combines explicit alert rules from your manifest with auto-generated rules based on service tier and SLOs. It supports live evaluation against Prometheus, burn simulation, and context-aware explanations.

### Subcommands

| Subcommand | Description |
|------------|-------------|
| `evaluate` | Full pipeline evaluation against live or simulated budget data |
| `show` | Display effective alert rules (explicit + auto-generated) |
| `explain` | Show context-aware budget explanations with investigation actions |
| `test` | Simulate budget burn and show what alerts would fire |

## Exit Codes

| Code | Severity | Meaning |
|------|----------|---------|
| 0 | Healthy | No alerts triggered |
| 1 | Warning | Warning-level alerts triggered |
| 2 | Critical | Critical alerts triggered |

## Subcommand Reference

### alerts evaluate

Run the full alert pipeline against a service or directory of manifests.

**Options:**

| Option | Description |
|--------|-------------|
| `--prometheus-url URL`, `-p URL` | Prometheus URL (or set `NTHLAYER_PROMETHEUS_URL`) |
| `--dry-run` | Evaluate without sending notifications |
| `--no-notify` | Suppress notification delivery |
| `--format FORMAT` | Output format: `table` (default), `json` |
| `--path DIR` | Evaluate all manifests in a directory |

**Example:**

```bash
nthlayer alerts evaluate services/payment-api.yaml \
  --prometheus-url http://prometheus:9090
```

Output:
```
Alert Evaluation Results

┏━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Service     ┃ SLOs ┃ Rules ┃ Alerts ┃ Notifications ┃ Status   ┃
┡━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ payment-api │    2 │     6 │      1 │             0 │ WARNING  │
└─────────────┴──────┴───────┴────────┴───────────────┴──────────┘
```

**Evaluate a directory:**

```bash
nthlayer alerts evaluate --path services/ \
  --prometheus-url http://prometheus:9090
```

### alerts show

Display the effective alert rules for a service — both explicitly defined rules and auto-generated rules based on service tier.

**Options:**

| Option | Description |
|--------|-------------|
| `--format FORMAT` | Output format: `table` (default), `json`, `yaml` |

**Example:**

```bash
nthlayer alerts show services/payment-api.yaml
```

Output:
```
Effective Alert Rules: payment-api
Tier: critical | Rules: 6

┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┓
┃ Name                    ┃ Type     ┃ SLO          ┃ Threshold ┃ Severity ┃ Enabled ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━┩
│ budget_burn_fast        │ burn     │ availability │      0.02 │ critical │ yes     │
│ budget_burn_slow        │ burn     │ availability │      0.05 │ warning  │ yes     │
│ budget_burn_fast        │ burn     │ latency      │      0.02 │ critical │ yes     │
│ budget_burn_slow        │ burn     │ latency      │      0.05 │ warning  │ yes     │
│ slo_target_miss         │ target   │ availability │      0.99 │ warning  │ yes     │
│ slo_target_miss         │ target   │ latency      │      0.99 │ warning  │ yes     │
└─────────────────────────┴──────────┴──────────────┴───────────┴──────────┴─────────┘
```

### alerts explain

Show context-aware budget explanations with technology-specific investigation actions.

**Options:**

| Option | Description |
|--------|-------------|
| `--prometheus-url URL`, `-p URL` | Prometheus URL (or set `NTHLAYER_PROMETHEUS_URL`) |
| `--format FORMAT` | Output format: `table` (default), `json`, `markdown` |
| `--slo NAME` | Filter explanations to a specific SLO |

**Example:**

```bash
nthlayer alerts explain services/payment-api.yaml \
  --prometheus-url http://prometheus:9090
```

The explanation engine provides:

- Budget status and burn rate analysis
- Technology-specific investigation steps (e.g., PostgreSQL slow query checks, Redis memory analysis)
- Recommended actions based on service type and tier
- Links to relevant runbooks and dashboards

### alerts test

Simulate budget burn at a specified level and show which alerts would fire.

**Options:**

| Option | Description |
|--------|-------------|
| `--prometheus-url URL`, `-p URL` | Prometheus URL (or set `NTHLAYER_PROMETHEUS_URL`) |
| `--simulate-burn PCT` | Percentage of budget consumed to simulate (default: 80) |
| `--no-notify` | Suppress sending notifications to configured channels |

**Example:**

```bash
nthlayer alerts test services/payment-api.yaml --simulate-burn 95
```

Output:
```
Alert Simulation: payment-api
Simulated burn: 95.0%

┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Rule             ┃ SLO          ┃ Severity ┃ Message                              ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ budget_burn_fast │ availability │ CRITICAL │ Budget burn rate exceeds threshold    │
│ budget_burn_slow │ availability │ WARNING  │ Slow budget erosion detected          │
└──────────────────┴──────────────┴──────────┴──────────────────────────────────────┘

Explanations:
  Budget is 95% consumed — immediate investigation required
```

## CI/CD Integration

### GitHub Actions

```yaml
jobs:
  alert-check:
    steps:
      - name: Evaluate Alerts
        run: |
          nthlayer alerts evaluate services/payment-api.yaml \
            --prometheus-url ${{ secrets.PROMETHEUS_URL }} \
            --dry-run \
            --format json > alerts.json

          # Fail on critical
          if [ $? -eq 2 ]; then
            echo "::error::Critical alerts detected"
            exit 1
          fi
```

### Directory-Wide Evaluation

```yaml
- name: Check All Services
  run: |
    nthlayer alerts evaluate \
      --path services/ \
      --prometheus-url ${{ secrets.PROMETHEUS_URL }} \
      --dry-run
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NTHLAYER_PROMETHEUS_URL` | Default Prometheus URL |

## See Also

- [Deployment Gates](check-deploy.md) — Error budget gates
- [Drift Detection](drift.md) — Trend analysis
- [Reliability Scorecard](scorecard.md) — Quantitative reliability scoring
- [Protection Overview](../protect/index.md) — Full protection stack
